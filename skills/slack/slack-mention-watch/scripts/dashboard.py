#!/usr/bin/env python3
"""Local dashboard for slack-mention-watch: mentions, bot replies, run activity, review sessions,
and pause / resume of the cron job. Python stdlib only, bound to 127.0.0.1.

Never calls Slack itself. Writes are limited to `hermes cron pause|resume|create|remove` and one
helper script under $HERMES_HOME/scripts/ ("Pause until"). Every SQLite open is read-only.

Run:  python3 dashboard.py [--port 8090] [--job ID ...] [--open]      (--check: inspect and exit)
"""

import argparse
import contextlib
import json
import math
import os
import re
import secrets
import shlex
import shutil
import sqlite3
import subprocess
import sys
import time
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlsplit

HERE = Path(__file__).resolve().parent
WATCH_SCRIPTS = {"slack_mention_digest_cron.py", "slack_mention_watch_cron.py"}
ACTIONS = ("pause", "resume", "pause_until", "cancel_resume")
HOSTS = ("127.0.0.1", "localhost")
SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")  # ids end up in a file name and a bash script
HEAD = re.compile(r"### Mention \d+ -- (.*) -- from (.*) at (\w{3} \d{4}-\d\d-\d\d \d\d:\d\d)$")
MAX_HOURS = 24 * 90


class BadRequest(ValueError):
    """Invalid caller input: HTTP 400."""


# --- paths -------------------------------------------------------------------------------------

def home():
    return Path(os.path.expanduser(os.environ.get("HERMES_HOME") or "~/.hermes"))


def hermes_bin():
    return os.path.abspath(os.path.expanduser(
        os.environ.get("HERMES_BIN") or shutil.which("hermes") or "~/.local/bin/hermes"))


def sources():
    h = home()
    return {"jobs.json": h / "cron" / "jobs.json", "executions.db": h / "cron" / "executions.db",
            "state.db": h / "state.db", "scripts dir": h / "scripts"}


def ro(path):
    """The only SQLite open in this file: read-only, so it can never create or change a DB.

    A WAL database whose -wal/-shm sidecars are absent (gateway idle) cannot be opened mode=ro by
    some SQLite builds ("unable to open database file"): read-only cannot create the -shm. Then we
    retry once with immutable=1, which skips locking and the WAL. Safe here: the sidecars are only
    absent when no writer has the DB open, so there is nothing in flight to miss."""
    uri = f"file:{quote(str(path))}?mode=ro"
    try:
        c = sqlite3.connect(uri, uri=True, timeout=5)
        try:
            c.execute("PRAGMA schema_version")  # the open is lazy; force it so failure lands here
        except sqlite3.OperationalError:
            c.close()
            raise
        return c
    except sqlite3.OperationalError:
        return sqlite3.connect(uri + "&immutable=1", uri=True, timeout=5)


@contextlib.contextmanager
def _db(name):
    """Read-only connection to a data source, or None when the file does not exist."""
    path = sources()[name]
    if not path.exists():
        yield None
        return
    with contextlib.closing(ro(path)) as c:
        yield c


# --- jobs --------------------------------------------------------------------------------------

def load_jobs():
    try:
        data = json.loads(sources()["jobs.json"].read_text())
    except (OSError, ValueError):
        return []
    jobs = data.get("jobs") if isinstance(data, dict) else data
    return [j for j in jobs if isinstance(j, dict) and j.get("id")] if isinstance(jobs, list) else []


def watched_jobs(jobs, ids=None):
    if ids:
        return [j for j in jobs if j["id"] in ids]
    return [j for j in jobs
            if os.path.basename(str(j.get("script") or "")) in WATCH_SCRIPTS
            or str(j.get("name") or "").startswith("slack-mention")]


def find_helper(jobs, job_id):
    """The enabled no-agent job whose script names `job_id` as a whole token, i.e. a scheduled
    resume (made here or by hand)."""
    token = re.compile(rf"(?<![\w-]){re.escape(str(job_id))}(?![\w-])")
    for j in jobs:
        if j["id"] == job_id or not (j.get("no_agent") and j.get("enabled") and j.get("script")):
            continue
        try:  # basename only: never read outside the scripts dir
            body = (sources()["scripts dir"] / os.path.basename(str(j["script"]))).read_text(
                errors="replace")
        except OSError:
            continue
        if token.search(body):
            return j
    return None


def job_status(job, jobs):
    schedule = job.get("schedule")
    helper = find_helper(jobs, job["id"])
    return {
        "id": job["id"], "name": str(job.get("name") or job["id"]),
        "enabled": bool(job.get("enabled")), "state": job.get("state"),
        "schedule": job.get("schedule_display")
        or (schedule.get("display") if isinstance(schedule, dict) else None),
        "next_run_at": job.get("next_run_at"), "last_run_at": job.get("last_run_at"),
        "last_status": job.get("last_status"), "last_error": job.get("last_error"),
        "paused_at": job.get("paused_at"),
        "scheduled_resume": {"job_id": helper["id"], "run_at": helper.get("next_run_at")}
        if helper else None,
    }


def status(ids=None):
    jobs = load_jobs()
    return {"jobs": [job_status(j, jobs) for j in watched_jobs(jobs, ids)],
            "now": datetime.now().astimezone().isoformat(timespec="seconds")}


def _pick(job_id, ids):
    """Watched jobs, or just `job_id`; anything outside the watched set is a 400."""
    jobs = watched_jobs(load_jobs(), ids)
    if job_id is None:
        return jobs
    jobs = [j for j in jobs if j["id"] == job_id]
    if not jobs:
        raise BadRequest("unknown job")
    return jobs


# --- bot replies and the mentions they were given ---------------------------------------------

def parse_mentions(text):
    """Mention blocks of a `watch_mentions.py --digest` output embedded in a cron prompt. Hermes
    fences the script output, so parsing runs from the `NEW MENTIONS:` header to the closing
    fence and never reads the prompt after it."""
    out, cur, in_text, started = [], None, False, False
    for line in str(text or "").splitlines():
        if not started:
            started = line.startswith("NEW MENTIONS:")
            continue
        if line.strip() == "```":
            break
        m = HEAD.match(line)
        if m:
            cur = {"channel": m[1], "sender": m[2], "at": m[3], "permalink": "", "text": "",
                   "reacted": "", "review": ""}
            out.append(cur)
            in_text = False
        elif cur is None:
            continue
        elif line.startswith("Mention: "):
            cur["text"], in_text = line[9:], True
        elif in_text and line.startswith("    "):
            cur["text"] += "\n" + line[4:]
        else:
            in_text = False
            if line.startswith("Permalink: "):
                cur["permalink"] = line[11:].strip()
            elif line.startswith("Reacted: "):
                cur["reacted"] = line[9:]
            elif line.startswith("review: "):
                cur["review"] = (cur["review"] + "\n" + line[8:]).strip()
    return out


def _runs(job_id, ids, since=0):
    """Cron sessions that woke the LLM for the picked job(s), newest first."""
    prefixes = tuple(f"{j['name']} \u00b7 " for j in _pick(job_id, ids) if j.get("name"))
    out = []
    with _db("state.db") as c:
        if c is None or not prefixes:
            return out
        # ponytail: every call re-reads and re-parses the matching sessions (a few hundred rows);
        # cache by max(started_at) if the page ever feels slow.
        for sid, title, model, started in c.execute(
                "SELECT id, title, model, started_at FROM sessions WHERE source = 'cron'"
                " AND message_count > 0 AND started_at >= ? ORDER BY started_at DESC", (since,)):
            if not str(title or "").startswith(prefixes):
                continue
            user, reply = None, ""
            for role, content in c.execute(
                    "SELECT role, content FROM messages WHERE session_id = ?"
                    " AND role IN ('user', 'assistant') ORDER BY timestamp, id", (sid,)):
                content = content if isinstance(content, str) else ""
                if role == "user":
                    user = content if user is None else user
                elif content.strip():
                    reply = content.strip()
            out.append({"session_id": sid, "model": model,
                        "started_at": datetime.fromtimestamp(float(started or 0)).astimezone()
                        .isoformat(),
                        "silent": reply == "[SILENT]", "reply": reply,
                        "mentions": parse_mentions(user)})
    return out


def replies(job_id=None, q="", limit=50, offset=0, ids=None):
    runs = _runs(job_id, ids)
    q = (q or "").strip().lower()
    if q:
        runs = [r for r in runs
                if q in "\n".join([r["reply"], *(m["text"] for m in r["mentions"])]).lower()]
    return {"items": runs[offset:offset + limit], "total": len(runs)}


def _when(at):
    try:
        return datetime.strptime(at[4:], "%Y-%m-%d %H:%M")
    except ValueError:
        return datetime.min


def mentions(job_id=None, hours=24, ids=None, now=None):
    since = (time.time() if now is None else now) - float(hours) * 3600
    seen, items = set(), []
    for run in _runs(job_id, ids, since):
        for m in run["mentions"]:
            key = m["permalink"] or (m["channel"], m["sender"], m["at"], m["text"])
            if key not in seen:  # newest run wins: it carries the latest Reacted/review lines
                seen.add(key)
                items.append({**m, "session_id": run["session_id"]})
    items.sort(key=lambda m: _when(m["at"]), reverse=True)
    return {"items": items}


# --- run activity ------------------------------------------------------------------------------

def classify(status_, outcome):
    if status_ in ("failed", "unknown"):
        return "error"
    if status_ == "missed":
        return "missed"
    if status_ == "completed" and outcome in ("delivered", "suppressed"):
        return "sent" if outcome == "delivered" else "nothing_new"
    return status_


def activity(job_id=None, limit=200, ids=None):
    job_ids = [j["id"] for j in _pick(job_id, ids)]
    where = f"job_id IN ({','.join('?' * len(job_ids))})"
    counts = {"nothing_new": 0, "sent": 0, "error": 0, "missed": 0}
    items = []
    with _db("executions.db") as c:
        if c is not None and job_ids:
            for st, outcome, n in c.execute(
                    f"SELECT status, delivery_outcome, COUNT(*) FROM executions WHERE {where}"
                    " GROUP BY status, delivery_outcome", job_ids):
                kind = classify(st, outcome)
                if kind in counts:
                    counts[kind] += n
            items = [{"id": i, "status": st, "claimed_at": claimed, "finished_at": finished,
                      "outcome": classify(st, outcome), "error": error}
                     for i, st, claimed, finished, error, outcome in c.execute(
                         "SELECT id, status, claimed_at, finished_at, error, delivery_outcome"
                         f" FROM executions WHERE {where} ORDER BY claimed_at DESC LIMIT ?",
                         [*job_ids, limit])]
    return {"items": items, "counts": counts}


# --- review sessions and live fetch (sibling scripts, as subprocesses) -------------------------

def reviews():
    try:
        r = subprocess.run([sys.executable, str(HERE / "review_spawn.py"), "--sessions"],
                           capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as e:
        return {"rows": [], "note": f"Could not read the review session table: {e}"}
    lines = r.stdout.splitlines()
    if r.returncode != 0 or not lines:
        return {"rows": [], "note": "Could not read the review session table: "
                + ((r.stderr or "").strip() or f"exit {r.returncode}")}
    cols = re.split(r" {2,}", lines[0].strip())
    rows = [dict(zip(cols, re.split(r" {2,}", l.strip(), maxsplit=len(cols) - 1)))
            for l in lines[1:] if l.strip()]
    if not rows:
        return {"rows": [], "note": "No review sessions recorded. The background review agent is"
                                    " opt-in (SLACK_REVIEW_AGENT)."}
    return {"rows": rows}


def _hours(value, default=None):
    try:
        h = float(default if value is None else value)
    except (TypeError, ValueError):
        raise BadRequest("hours must be a number") from None
    if not (math.isfinite(h) and 0 < h <= MAX_HOURS):
        raise BadRequest(f"hours must be above 0 and at most {MAX_HOURS}")
    return h


def live(hours):
    """Ask Slack directly: `watch_mentions.py --recent N` (read only, no watcher state)."""
    argv = [sys.executable, str(HERE / "watch_mentions.py"), "--recent", f"{_hours(hours):g}"]
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        return {"output": "Timed out after 120 s.", "exit": -1}
    return {"output": r.stdout or r.stderr, "exit": r.returncode}


# --- controls ----------------------------------------------------------------------------------

def _hermes(*args):
    try:
        r = subprocess.run([hermes_bin(), *args], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, f"hermes {' '.join(args[:2])}: {e}"
    return r.returncode == 0, (r.stderr or r.stdout).strip() or f"exit {r.returncode}"


def _until(value):
    if not isinstance(value, str) or not value.strip():
        raise BadRequest("until must be an ISO-8601 date and time")
    try:
        dt = datetime.fromisoformat(value.strip())
    except ValueError:
        raise BadRequest("until must be an ISO-8601 date and time") from None
    if dt.tzinfo is None:
        dt = dt.astimezone()  # naive = local time
    if dt.timestamp() <= time.time():
        raise BadRequest("until must be in the future")
    return dt.replace(microsecond=0).isoformat()


def helper_script(job_id, name):
    """Bash for the one-shot resume job. `hermes cron resume <id> --at` rejects recurring jobs
    (re-arm is one-shot-only), so a helper job is the only way to resume on a date."""
    q = shlex.quote
    return "\n".join([
        "#!/bin/bash",
        '# Written by the slack-mention-watch dashboard ("Pause until"): resumes one cron job.',
        f"if {q(hermes_bin())} cron resume {q(job_id)} >/dev/null 2>&1; then",
        f"  echo {q('resumed ' + name)}",
        "else",
        f"  echo {q(f'FAILED to resume {name}. Run: hermes cron resume {job_id}')}",
        "  exit 1",
        "fi", ""])


def _write_helper(job_id, name):
    path = sources()["scripts dir"] / f"slack_dashboard_resume_{job_id}.sh"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o700)
        with os.fdopen(fd, "w") as f:
            f.write(helper_script(job_id, name))
        os.chmod(path, 0o700)
    except OSError as e:
        return False, f"cannot write {path.name}: {e}"
    return True, ""


def control(job_id, action, until=None, ids=None):
    jobs = load_jobs()
    job = next((j for j in watched_jobs(jobs, ids) if j["id"] == job_id), None)
    if job is None or not SAFE_ID.fullmatch(str(job_id)):
        raise BadRequest("unknown job")
    if action not in ACTIONS:
        raise BadRequest("unknown action")
    name = str(job.get("name") or job_id)
    helper = find_helper(jobs, job_id)
    drop = [("cron", "remove", helper["id"])] if helper else []
    if action == "pause":
        steps, done = [("cron", "pause", job_id)], "Paused."
    elif action == "resume":
        steps, done = [*drop, ("cron", "resume", job_id)], "Resumed."
    elif action == "cancel_resume":
        if not helper:
            raise BadRequest("no scheduled resume for this job")
        steps, done = drop, "Scheduled resume cancelled. The job stays paused."
    else:
        when = _until(until)
        script = f"slack_dashboard_resume_{job_id}.sh"
        steps = [("cron", "pause", job_id), *drop, lambda: _write_helper(job_id, name),
                 ("cron", "create", when, "--name", f"resume-{name}", "--script", script,
                  "--no-agent", "--deliver", "local", "--catch-up", "on")]
        done = f"Paused until {when}."
    ok, message = True, done
    for step in steps:  # stop at the first failure and report it
        ok, err = step() if callable(step) else _hermes(*step)
        if not ok:
            message = err
            break
    fresh = next((j for j in status(ids)["jobs"] if j["id"] == job_id), None)
    return {"ok": ok, "message": message, "status": fresh}


# --- HTTP --------------------------------------------------------------------------------------

def _int(q, name, default, lo, hi):
    try:
        n = int(q.get(name, [default])[0])
    except ValueError:
        raise BadRequest(f"{name} must be an integer") from None
    if not lo <= n <= hi:
        raise BadRequest(f"{name} must be between {lo} and {hi}")
    return n


class Handler(BaseHTTPRequestHandler):
    server_version = "slack-mention-dashboard"

    def log_message(self, *args):  # quiet: request lines would bury the start-up URL
        pass

    def _send(self, code, body, ctype="application/json", extra=()):
        data = body.encode() if isinstance(body, str) else json.dumps(body).encode()
        self.send_response(code)
        for k, v in (("Content-Type", ctype), ("Content-Length", str(len(data))),
                     ("Cache-Control", "no-store"), ("X-Content-Type-Options", "nosniff"), *extra):
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def _allowed(self, post):
        """DNS-rebinding guard on every request; CSRF token + same-origin on every POST."""
        port = self.server.server_address[1]
        if self.headers.get("Host") not in {f"{h}:{port}" for h in HOSTS}:
            return False
        if not post:
            return True
        origin = self.headers.get("Origin")
        return (secrets.compare_digest(self.headers.get("X-CSRF-Token") or "", self.server.token)
                and (origin is None or origin in {f"http://{h}:{port}" for h in HOSTS}))

    def _handle(self, post):
        if not self._allowed(post):
            return self._send(403, {"error": "forbidden"})
        url = urlsplit(self.path)
        q = parse_qs(url.query)
        ids = self.server.job_ids
        job = q.get("job", [None])[0]
        try:
            if post:
                return self._post(url.path, q, ids)
            if url.path == "/":
                csp = ("default-src 'none'; style-src 'unsafe-inline'; connect-src 'self'; "
                       f"script-src 'nonce-{self.server.nonce}'; base-uri 'none'; "
                       "form-action 'none'; frame-ancestors 'none'")
                page = PAGE.replace("__CSRF__", self.server.token).replace(
                    "__NONCE__", self.server.nonce)
                return self._send(200, page, "text/html; charset=utf-8",
                                  (("Content-Security-Policy", csp),
                                   ("Referrer-Policy", "no-referrer")))
            if url.path == "/api/status":
                return self._send(200, status(ids))
            if url.path == "/api/replies":
                return self._send(200, replies(job, q.get("q", [""])[0],
                                               _int(q, "limit", 50, 1, 500),
                                               _int(q, "offset", 0, 0, 10 ** 9), ids))
            if url.path == "/api/mentions":
                return self._send(200, mentions(job, _hours(q.get("hours", [None])[0], 24), ids))
            if url.path == "/api/activity":
                return self._send(200, activity(job, _int(q, "limit", 200, 1, 2000), ids))
            if url.path == "/api/reviews":
                return self._send(200, reviews())
            return self._send(404, {"error": "not found"})
        except BadRequest as e:
            return self._send(400, {"error": str(e)})
        except Exception as e:  # shown by the page as an explicit error state
            return self._send(500, {"error": f"{type(e).__name__}: {e}"})

    def _post(self, path, q, ids):
        if path == "/api/live":
            return self._send(200, live(q.get("hours", [None])[0]))
        if path != "/api/control":
            return self._send(404, {"error": "not found"})
        try:
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n)) if 0 < n <= 65536 else None
        except ValueError:
            body = None
        if not isinstance(body, dict):
            raise BadRequest("body must be a JSON object")
        return self._send(200, control(body.get("job"), body.get("action"), body.get("until"), ids))

    def do_GET(self):
        self._handle(False)

    def do_POST(self):
        self._handle(True)


def make_server(port=8090, job_ids=None):
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)  # loopback only, by design
    srv.daemon_threads = True
    srv.token = secrets.token_urlsafe(32)  # per process; never logged
    srv.nonce = secrets.token_urlsafe(16)
    srv.job_ids = list(job_ids) if job_ids else None
    return srv


# --- CLI ---------------------------------------------------------------------------------------

def _tilde(path):
    s, h = str(path), os.path.expanduser("~")
    return "~" + s[len(h):] if s == h or s.startswith(h + os.sep) else s


def check(ids=None):
    lines = [f"hermes home:    {_tilde(home())}"]
    for name, path in sources().items():
        lines.append(f"{name + ':':15} {_tilde(path)} ({'found' if path.exists() else 'MISSING'})")
    hb = hermes_bin()
    lines.append(f"hermes bin:     {_tilde(hb)} ({'found' if os.path.exists(hb) else 'MISSING'})")
    jobs = status(ids)["jobs"]
    lines.append(f"watched jobs:   {len(jobs)}")
    for j in jobs:
        paused = not j["enabled"] or j["state"] == "paused"
        resume = j["scheduled_resume"]
        lines.append(f"  {j['id']}  {j['name']}  {'paused' if paused else 'running'}"
                     f"  {j['schedule'] or '-'}"
                     + (f"  (resume scheduled: {resume['run_at']} by job {resume['job_id']})"
                        if resume else ""))
    return "\n".join(lines) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description="Local dashboard for slack-mention-watch.")
    ap.add_argument("--port", type=int, default=8090)
    ap.add_argument("--host", default="127.0.0.1", help="loopback only (127.0.0.1 or localhost)")
    ap.add_argument("--job", action="append", metavar="ID",
                    help="watch this cron job id instead of auto-detecting (repeatable)")
    ap.add_argument("--open", action="store_true", help="open the page in the browser")
    ap.add_argument("--check", action="store_true",
                    help="print detected jobs and data sources, then exit")
    args = ap.parse_args(argv)
    if args.host not in HOSTS:
        ap.error("--host must be 127.0.0.1 or localhost: the dashboard is loopback only")
    if args.check:
        sys.stdout.write(check(args.job))
        return 0
    srv = make_server(args.port, args.job)
    url = f"http://{args.host}:{srv.server_address[1]}"
    print(f"slack-mention dashboard: {url}", flush=True)
    if args.open:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
    return 0


PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="csrf" content="__CSRF__">
<meta name="color-scheme" content="light dark">
<title>Slack mention watch</title>
<style>
/* Matte e-ink page. Every text/fill pair below is WCAG AA (>= 4.5:1) on paper, band and wash;
   --edge (control outlines) and --track (pause rule) are >= 3:1 on the band. --fill is the one
   filled control: dark fill 4.95:1 with its ink (hover 4.59:1), deliberately deep so the button is
   not the brightest area of the dark page. Re-check the ratios when changing a value. */
:root {
  color-scheme: light dark;
  --paper: #e9e6df; --band: #e1ddd4; --wash: #dcd7cc; --rule: #cdc8bd; --edge: #7d786d;
  --ink: #2e2c29; --ink-2: #5b574f; --accent: #3d5a80; --accent-hi: #334c6d; --on-accent: #f3f1ec;
  --fill: var(--accent); --fill-hi: var(--accent-hi); --on-fill: var(--on-accent); --track: #817b6f;
  --hold: #6f510f; --ok: #3f6247; --err: #8c3b2f;
  --pad: 48px;
  --ui: -apple-system, BlinkMacSystemFont, "Helvetica Neue", sans-serif;
  --read: Charter, "Iowan Old Style", Georgia, serif;
  --mono: ui-monospace, Menlo, Consolas, monospace;
}
@media (prefers-color-scheme: dark) {
  :root {
    --paper: #2b2a27; --band: #33322e; --wash: #3a3833; --rule: #47453f; --edge: #8a8579;
    --ink: #d9d4c9; --ink-2: #ada79b; --accent: #8fa9c9; --accent-hi: #a3b9d4; --on-accent: #23221f;
    --fill: #3e5878; --fill-hi: #425d7e; --on-fill: var(--ink); --track: #807c72;
    --hold: #d0a85a; --ok: #8db592; --err: #dc9585;
  }
}
@media (width <= 640px) { :root { --pad: 16px; } }
* { box-sizing: border-box; }
html { scrollbar-color: var(--edge) var(--paper); }
body { margin: 0; padding: 0 0 96px; background: var(--paper); color: var(--ink);
       font: 0.9375rem/1.55 var(--ui); caret-color: var(--accent); accent-color: var(--accent); }
::selection { background: var(--accent); color: var(--on-accent); }
:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
[role=tabpanel]:focus-visible, [role=tab]:focus-visible { outline-offset: -2px; }
h1, h2, h3, p { margin: 0; }
.vh { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%);
      white-space: nowrap; }
.num, time { font-variant-numeric: tabular-nums; }
.quiet { color: var(--ink-2); }
.small { font-size: 0.8125rem; }
.mono { font-family: var(--mono); font-size: 0.8125rem; }
.caps, th { font-size: 0.75rem; font-weight: 600; letter-spacing: 0.04em; text-transform: uppercase; }
.hold { color: var(--hold); } .ok { color: var(--ok); } .err { color: var(--err); }
a { color: var(--accent); text-decoration: none; text-underline-offset: 3px; }
a:hover, a:focus-visible { text-decoration: underline; }

button, input, select { font: inherit; color: var(--ink); }
button, select, input[type=datetime-local], input[type=search] {
  min-height: 36px; padding: 6px 14px; background: var(--paper); border: 1px solid var(--edge);
  border-radius: 6px; transition: background-color 150ms ease-out, border-color 150ms ease-out; }
button { cursor: pointer; }
button:hover:not(:disabled), select:hover, input:hover { background: var(--wash); }
button:active:not(:disabled) { background: var(--rule); }
button:disabled { opacity: 0.55; cursor: progress; }
button.primary { background: var(--fill); border-color: var(--fill); color: var(--on-fill);
                 font-weight: 600; }
button.primary:hover:not(:disabled), button.primary:active:not(:disabled) {
  background: var(--fill-hi); border-color: var(--fill-hi); }
input::placeholder { color: var(--ink-2); opacity: 1; }
input[type=checkbox] { width: 16px; height: 16px; margin: 0; }
label { display: inline-flex; align-items: center; gap: 8px; }
@media (width <= 640px) {
  button, select, input[type=datetime-local], input[type=search] { min-height: 44px; }
}

/* header band: one block per watched job */
header { background: var(--band); border-bottom: 1px solid var(--rule); }
.job { padding: 22px var(--pad) 0; }
.job.plain { padding-bottom: 22px; }
.job + .job { border-top: 1px solid var(--rule); }
.head { display: grid; grid-template-columns: minmax(0, 1fr) auto; align-items: start; gap: 16px 24px; }
h2 { font-size: 0.9375rem; font-weight: 600; overflow-wrap: anywhere; }
h2 span { font-weight: 400; color: var(--ink-2); }
.sentence { margin-top: 8px; font-size: 1.375rem; line-height: 1.3; font-weight: 600; }
.meta { margin-top: 4px; color: var(--ink-2); overflow-wrap: anywhere; }
.actions { display: flex; flex-wrap: wrap; justify-content: flex-end; align-items: center; gap: 10px; }
/* the track is its own tone (>= 3:1 on the band); a 2x9px tick marks "now", so 0% and 100% read */
.progress { height: 3px; margin: 22px calc(-1 * var(--pad)) 0; background: var(--track); }
.progress i { position: relative; display: block; height: 100%; min-width: 2px; background: var(--hold);
              transition: width 200ms ease-out; }
.progress i::after { content: ""; position: absolute; right: 0; top: -3px; width: 2px; height: 9px;
                     background: var(--hold); }
.progress-l { display: grid; grid-template-columns: 1fr auto 1fr; gap: 0 16px; padding: 6px 0 12px;
              color: var(--ink-2); font-size: 0.8125rem; }
.progress-l span:last-child { text-align: right; }
@media (width <= 900px) {
  .head { grid-template-columns: minmax(0, 1fr); }
  .actions { justify-content: flex-start; }
}
@media (width <= 640px) {
  .progress-l { grid-template-columns: auto auto; justify-content: space-between; }
  .progress-l span:nth-child(2) { grid-row: 2; grid-column: 1 / -1; }
}
#flash { padding: 0 var(--pad); font-weight: 600; }
#flash:not(:empty) { padding-block: 12px; border-bottom: 1px solid var(--rule); }

.tabs { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between;
        gap: 0 24px; padding: 0 var(--pad); border-bottom: 1px solid var(--rule); }
[role=tablist] { display: flex; flex-wrap: wrap; gap: 0 28px; }
@media (width <= 640px) {  /* four tabs with counts do not fit 390px: the strip scrolls sideways */
  [role=tablist] { flex-wrap: nowrap; gap: 0; min-width: 0; padding: 2px; overflow-x: auto;
                   scrollbar-width: thin; }
  .tabs [role=tab] { flex: none; padding-inline: 10px; }  /* room for the inset focus ring */
}
[role=tab] { min-height: 44px; padding: 10px 0; background: none; border: 0; border-radius: 0;
             color: var(--ink-2); transition: color 150ms ease-out, box-shadow 150ms ease-out; }
[role=tab]:hover:not(:disabled), [role=tab]:active:not(:disabled) { background: none; color: var(--ink); }
[role=tab][aria-selected=true] { color: var(--ink); font-weight: 600;
                                 box-shadow: inset 0 -2px 0 var(--ink); }
.count { font-weight: 400; color: var(--ink-2); }

.tools { display: flex; flex-wrap: wrap; align-items: center; gap: 10px 16px; padding: 16px var(--pad); }
.tools input[type=search] { flex: 1 1 320px; }
.note { padding: 20px var(--pad); color: var(--ink-2); }
.note.err { color: var(--err); font-weight: 600; }

/* notifications: fixed columns, one size, hairline between rows */
.row { display: grid; grid-template-columns: 160px 240px minmax(0, 1fr) 140px; gap: 4px 24px;
       padding: 14px var(--pad); border-bottom: 1px solid var(--rule);
       transition: background-color 150ms ease-out; }
.row:hover, .row:focus-within { background: var(--wash); }
.group { display: flex; align-items: baseline; gap: 8px; padding: 26px var(--pad) 10px;
         border-bottom: 1px solid var(--rule); font-size: 0.9375rem; font-weight: 600; }
.fold { margin: 0; border-bottom: 1px solid var(--rule); }
.fold > summary { padding: 12px var(--pad); color: var(--ink-2); }
.fold[open] > summary { border-bottom: 1px solid var(--rule); }
.fold .row:last-child { border-bottom: 0; }
.who { font-weight: 600; overflow-wrap: anywhere; }
.src { color: var(--ink-2); overflow-wrap: anywhere; }
.txt, .reply { font-family: var(--read); font-size: 1rem; line-height: 1.5; white-space: pre-wrap;
               overflow-wrap: anywhere; }
.ask { margin-right: 8px; font-family: var(--ui); color: var(--accent); }
.extra { margin-top: 4px; color: var(--ink-2); font-size: 0.8125rem; overflow-wrap: anywhere; }
.at { text-align: right; color: var(--ink-2); }
.at a { display: block; }
@media (width <= 1000px) { .row { grid-template-columns: 120px 160px minmax(0, 1fr) 130px; } }
@media (width <= 640px) {
  .row { grid-template-columns: minmax(0, 1fr) auto; }
  .row .src, .row .body { grid-column: 1 / -1; }
  .row .at { grid-row: 1; grid-column: 2; }
  .at a { display: inline; margin-left: 10px; }
}

/* bot replies: pages, not cards */
.run { padding: 18px var(--pad); border-bottom: 1px solid var(--rule); }
.run-head { display: flex; flex-wrap: wrap; align-items: baseline; gap: 2px 14px; }
.reply { margin: 8px 0 0; }
.reply > * { margin: 0; }
.reply > * + * { margin-top: 0.75em; }
.reply ul, .reply ol { padding-left: 1.4em; white-space: normal; }
.reply code { padding: 0 3px; border-radius: 3px; background: var(--band); font: 0.9375rem var(--mono); }
details { margin-top: 8px; }
summary { display: inline-block; padding: 6px 0; color: var(--accent); cursor: pointer;
          list-style-position: inside; }
summary:hover { text-decoration: underline; text-underline-offset: 3px; }
.run details .row { padding-inline: 0; border-bottom: 0; border-top: 1px solid var(--rule); }
.run details .row:hover, .run details .row:focus-within { background: none; }
pre { margin: 0 var(--pad) 8px; padding: 14px 16px; background: var(--band); border-radius: 6px;
      font: 0.8125rem/1.55 var(--mono); white-space: pre-wrap; overflow-wrap: anywhere; }

/* activity: figures as text, table with hairline rows */
.counts { display: flex; flex-wrap: wrap; gap: 4px 32px; margin: 0; padding: 18px var(--pad) 0; }
.counts div { display: flex; align-items: baseline; gap: 6px; }
.counts dt { order: 2; color: var(--ink-2); }
.counts dd { margin: 0; font-weight: 600; }
.scroll { padding: 0 var(--pad); overflow-x: auto; }
table { width: 100%; border-collapse: collapse; }
th, td { padding: 9px 20px 9px 0; text-align: left; vertical-align: top;
         border-bottom: 1px solid var(--rule); }
th { color: var(--ink-2); white-space: nowrap; border-bottom-color: var(--edge); }
td:not(:last-child) { white-space: nowrap; }
th:last-child, td:last-child { width: 100%; overflow-wrap: anywhere; }
tbody tr { transition: background-color 150ms ease-out; }
tbody tr:hover { background: var(--wash); }

/* loading: skeleton lines in place of the content they stand for */
.skel { padding: 20px var(--pad); }
.skel i { display: block; height: 12px; margin: 0 0 14px; border-radius: 2px; background: var(--rule);
          animation: wait 1.4s ease-in-out infinite alternate; }
.skel i:nth-of-type(1) { width: 38%; } .skel i:nth-of-type(2) { width: 72%; }
.skel i:nth-of-type(3) { width: 55%; margin-bottom: 0; }
@keyframes wait { from { opacity: 1; } to { opacity: 0.45; } }
@media (prefers-reduced-motion: reduce) {
  *, .progress i { transition: none !important; }
  .skel i { animation: none; }
}
[hidden] { display: none !important; }
</style>
</head>
<body>
<h1 class="vh">Slack mention watch</h1>
<header id="jobs" aria-label="Bot status">
  <div class="skel" role="status"><span class="vh">Loading bot status…</span><i></i><i></i><i></i></div>
</header>
<p id="flash" role="status" aria-live="polite"></p>

<div class="tabs">
  <div role="tablist" aria-label="Views">
    <button role="tab" id="tab-notifications" aria-controls="panel-notifications">Notifications <span class="count num" id="count-notifications"></span></button>
    <button role="tab" id="tab-replies" aria-controls="panel-replies">Bot replies <span class="count num" id="count-replies"></span></button>
    <button role="tab" id="tab-activity" aria-controls="panel-activity">Activity <span class="count num" id="count-activity"></span></button>
    <button role="tab" id="tab-reviews" aria-controls="panel-reviews">Reviews <span class="count num" id="count-reviews"></span></button>
  </div>
  <span class="quiet small num" id="updated" aria-live="off">loading…</span>
</div>

<section role="tabpanel" id="panel-notifications" aria-labelledby="tab-notifications" tabindex="0">
  <div class="tools">
    <label>Window
      <select id="win">
        <option value="1">Last hour</option><option value="24">Last 24 hours</option>
        <option value="168" selected>Last 7 days</option><option value="720">Last 30 days</option>
      </select>
    </label>
    <button type="button" id="live">Fetch live from Slack</button>
    <span class="quiet">Mentions the bot was given. A live fetch asks Slack directly.</span>
  </div>
  <pre id="live-out" hidden></pre>
  <div id="mentions"><div class="skel" role="status"><span class="vh">Loading mentions…</span><i></i><i></i><i></i></div></div>
</section>

<section role="tabpanel" id="panel-replies" aria-labelledby="tab-replies" tabindex="0" hidden>
  <div class="tools">
    <input type="search" id="q" placeholder="Search replies and mentions" aria-label="Search replies and mentions">
    <label><input type="checkbox" id="silent"> Show silent runs</label>
  </div>
  <div id="replies"><div class="skel" role="status"><span class="vh">Loading replies…</span><i></i><i></i><i></i></div></div>
</section>

<section role="tabpanel" id="panel-activity" aria-labelledby="tab-activity" tabindex="0" hidden>
  <dl class="counts num" id="counts"></dl>
  <div class="tools"><label><input type="checkbox" id="erronly"> Errors only</label></div>
  <div id="activity"><div class="skel" role="status"><span class="vh">Loading activity…</span><i></i><i></i><i></i></div></div>
</section>

<section role="tabpanel" id="panel-reviews" aria-labelledby="tab-reviews" tabindex="0" hidden>
  <div id="reviews"><div class="skel" role="status"><span class="vh">Loading review sessions…</span><i></i><i></i><i></i></div></div>
</section>

<script nonce="__NONCE__">
'use strict';
// All data reaches the DOM through textContent / text nodes, never as markup.
const $ = id => document.getElementById(id);
const csrf = document.querySelector('meta[name=csrf]').content;
const TABS = ['notifications', 'replies', 'activity', 'reviews'];
const OUTCOME = {nothing_new: 'Nothing new', sent: 'Sent', error: 'Error', missed: 'Missed'};
const TONE = {sent: 'ok', error: 'err', missed: 'hold', nothing_new: 'quiet'};
const DAY = new Intl.DateTimeFormat('en-GB', {weekday: 'short', day: 'numeric', month: 'short'});
const HM = new Intl.DateTimeFormat('en-GB', {hour: '2-digit', minute: '2-digit', hourCycle: 'h23'});
const openRuns = new Set();
const shown = {};
let tab = 'notifications', replyLimit = 50;

function el(tag, attrs, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (k === 'class') e.className = v; else e.setAttribute(k, v);
  }
  e.append(...kids.filter(k => k !== null && k !== undefined && k !== ''));
  return e;
}
// "Wed 25 Nov, 08:00" (the year only when it is not this year)
function when(v, timeOnlyToday) {
  if (!v) return '-';
  const d = v instanceof Date ? v : new Date(v), now = new Date();
  if (isNaN(d)) return String(v);
  if (timeOnlyToday && d.toDateString() === now.toDateString()) return HM.format(d);
  return DAY.format(d).replace(',', '') + (d.getFullYear() === now.getFullYear() ? '' : ' ' + d.getFullYear())
    + ', ' + HM.format(d);
}
async function api(path, opts) {
  const r = await fetch(path, opts);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || (r.status + ' ' + r.statusText));
  return data;
}
const post = (path, body) => api(path, {method: 'POST', body: JSON.stringify(body || {}),
  headers: {'X-CSRF-Token': csrf, 'Content-Type': 'application/json'}});
function flash(msg, bad) {
  $('flash').textContent = msg || '';
  $('flash').className = bad ? 'err' : '';
}
// Re-render a region only when its data changed, so a refresh never collapses or scrolls it.
function paint(id, key, build) {
  if (shown[id] === key) return;
  shown[id] = key;
  $(id).replaceChildren(...[].concat(build()));
}
function fail(id, what, e) {
  shown[id] = null;
  $(id).replaceChildren(el('p', {class: 'note err', role: 'alert'},
    'Could not load ' + what + ': ' + e.message));
}
const empty = text => el('p', {class: 'note'}, text);
const count = (name, n) => { $('count-' + name).textContent = Number(n || 0).toLocaleString(); };

// --- header band: state sentence, controls, pause-progress rule
function left(ms) {
  const m = Math.floor(ms / 60000), d = Math.floor(m / 1440), h = Math.floor(m % 1440 / 60);
  if (m <= 0) return 'Resume is due';
  return (d ? d + (d === 1 ? ' day ' : ' days ') + h + ' h' : h ? h + ' h ' + m % 60 + ' min' : m + ' min')
    + ' left';
}
function tick() {  // elapsed share between paused-at and the scheduled resume
  for (const p of document.querySelectorAll('.progress')) {
    const from = +p.dataset.from, to = +p.dataset.to, now = Date.now();
    const pct = Math.max(0, Math.min(100, (now - from) / (to - from) * 100));
    p.firstChild.style.width = pct.toFixed(2) + '%';
    p.setAttribute('aria-valuenow', Math.round(pct));
    p.setAttribute('aria-valuetext', left(to - now));
    p.nextSibling.children[1].textContent = left(to - now);
  }
}
function jobRow(j) {
  const paused = !j.enabled || j.state === 'paused';
  const resume = j.scheduled_resume;
  const sentence = paused
    ? el('p', {class: 'sentence'}, el('span', {class: 'hold'}, 'Paused'),
        resume ? ' until ' + when(resume.run_at) : null)
    : el('p', {class: 'sentence'}, el('span', {class: 'ok'}, 'Running'),
        j.next_run_at ? ' \u00b7 next check ' + when(j.next_run_at, true) : null);  // never while paused
  const from = Date.parse(j.paused_at), to = resume ? Date.parse(resume.run_at) : NaN;
  const bar = paused && to > from;
  const meta = el('p', {class: 'meta num'},
    (paused && !bar && j.paused_at ? 'Paused since ' + when(j.paused_at) + ' \u00b7 ' : '')
    + (j.last_run_at ? 'Last check ' + when(j.last_run_at) + (j.last_status ? ' \u00b7 ' + j.last_status : '')
      : 'No check yet'));
  const btn = (label, action, getUntil, cls) => {
    const b = el('button', {type: 'button', class: cls || ''}, label);
    b.addEventListener('click', () => control(j, action, getUntil && getUntil(), b));
    return b;
  };
  const until = el('input', {type: 'datetime-local', 'aria-label': 'Pause ' + j.name + ' until'});
  const actions = el('div', {class: 'actions'},
    paused ? btn('Resume now', 'resume', null, 'primary') : btn('Pause', 'pause', null, 'primary'),
    until, btn('Pause until', 'pause_until', () => until.value),
    resume ? btn('Cancel scheduled resume', 'cancel_resume') : null);
  const head = el('div', {class: 'head'},
    el('div', null,
      el('h2', null, j.name, el('span', null, (j.schedule ? ' \u00b7 ' + j.schedule : '') + ' \u00b7 ' + j.id)),
      sentence, meta,
      j.last_error ? el('p', {class: 'meta err'}, 'Last error: ' + j.last_error) : null),
    actions);
  if (!bar) return el('div', {class: 'job plain'}, head);
  return el('div', {class: 'job'}, head,
    el('div', {class: 'progress', role: 'progressbar', 'aria-label': 'Pause elapsed', 'aria-valuemin': 0,
      'aria-valuemax': 100, 'data-from': from, 'data-to': to}, el('i')),
    el('div', {class: 'progress-l num'}, el('span', null, 'Paused ' + when(j.paused_at)), el('span'),
      el('span', null, 'Resumes ' + when(resume.run_at))));
}
async function control(j, action, until, button) {
  if (action === 'pause' && !confirm('Pause ' + j.name + '? New mentions are not triaged until it is resumed.')) return;
  if (action === 'pause_until') {
    if (!until) return flash('Pick a date and time first.', true);
    if (!confirm('Pause ' + j.name + ' until ' + when(until) + '?')) return;
  }
  button.disabled = true;
  try {
    const r = await post('/api/control', {job: j.id, action, until});
    flash(j.name + ': ' + r.message, !r.ok);
  } catch (e) {
    flash(j.name + ': ' + e.message, true);
  }
  button.disabled = false;
  loadStatus(true);
}
async function loadStatus(force) {
  // do not rebuild the row while the user is typing a date into it
  if (!force && document.activeElement && document.activeElement.matches('#jobs input')) return tick();
  try {
    const s = await api('/api/status');
    paint('jobs', JSON.stringify(s.jobs), () => s.jobs.length ? s.jobs.map(jobRow) : empty(
      'No slack-mention cron job found. Create one (see SKILL.md) or start the dashboard with --job <id>.'));
    $('updated').textContent = 'Updated ' + HM.format(new Date());
  } catch (e) {
    fail('jobs', 'bot status', e);
    $('updated').textContent = 'Update failed ' + HM.format(new Date());
  }
  tick();
}

// --- notifications
function at(s) {  // "Fri 2026-11-20 15:11" as written by the digest script
  const m = /^\w{3} (\d{4})-(\d\d)-(\d\d) (\d\d):(\d\d)$/.exec(s || '');
  return m ? when(new Date(+m[1], m[2] - 1, +m[3], +m[4], +m[5])) : String(s || '-');
}
// Exact repeats (same sender, source, text and minute) become one row; every permalink stays.
function collapse(items) {
  const groups = new Map();
  for (const m of items) {
    const k = JSON.stringify([m.sender, m.channel, m.text, m.at]);
    if (groups.has(k)) groups.get(k).push(m); else groups.set(k, [m]);
  }
  return [...groups.values()];
}
const asksYou = g => g.some(x => /\?/.test(x.text || '') || !!x.review || /eyes/.test(x.reacted || ''));
function mentionRow(g) {
  const m = g[0], n = g.length;
  const reacted = (g.find(x => x.reacted) || m).reacted, review = (g.find(x => x.review) || m).review;
  const links = g.filter(x => typeof x.permalink === 'string' && x.permalink.startsWith('https://'));
  return el('article', {class: 'row'},
    el('span', {class: 'who'}, m.sender), el('span', {class: 'src'}, m.channel),
    el('div', {class: 'body'},
      el('p', {class: 'txt'}, asksYou(g) ? el('span', {class: 'ask caps'}, 'Asks you') : null, m.text || '(no text)'),
      n > 1 ? el('p', {class: 'extra'}, n === 2 ? 'sent twice' : 'sent ' + n + ' times') : null,
      reacted ? el('p', {class: 'extra'}, 'Reacted: ' + reacted) : null,
      review ? el('p', {class: 'extra mono'}, 'review: ' + review) : null),
    el('span', {class: 'at num'}, at(m.at), ...links.map((x, i) => el('a', {href: x.permalink,
      target: '_blank', rel: 'noopener noreferrer', 'aria-label': 'Open in Slack: ' + m.sender + ', '
      + at(m.at) + (links.length > 1 ? ' (' + (i + 1) + ' of ' + links.length + ')' : '')},
      links.length > 1 ? 'Open ' + (i + 1) : 'Open'))));
}
// Two groups, newest first: what asks the owner something, then the rest; bare "(no comment)"
// pings fold into one quiet line at the end.
function mentionGroups(items) {
  const sum = gs => gs.reduce((a, g) => a + g.length, 0);
  const head = (text, gs) => el('h3', {class: 'group'}, text, el('span', {class: 'count num'}, String(sum(gs))));
  const groups = collapse(items).sort((a, b) => (b[0].at || '').slice(4).localeCompare((a[0].at || '').slice(4)));
  const ask = groups.filter(asksYou), rest = groups.filter(g => !asksYou(g));
  const bare = rest.filter(g => g[0].text === '(no comment)'), other = rest.filter(g => g[0].text !== '(no comment)');
  const out = [head('Asks you', ask)];
  out.push(...(ask.length ? ask.map(mentionRow) : [empty('Nothing is asking you in this window.')]));
  if (rest.length) out.push(head('Everything else', rest), ...other.map(mentionRow));
  if (bare.length) {
    const n = sum(bare);
    out.push(el('details', {class: 'fold'}, el('summary', null, n + (n === 1 ? ' notification' : ' notifications')
      + ' with no comment'), ...bare.map(mentionRow)));
  }
  return out;
}
async function loadMentions() {
  const sel = $('win');
  try {
    const d = await api('/api/mentions?hours=' + sel.value);
    count('notifications', d.items.length);
    paint('mentions', JSON.stringify(d.items), () => d.items.length ? mentionGroups(d.items)
      : empty('No mentions reached the bot in this window (' + sel.selectedOptions[0].textContent.toLowerCase()
        + '). "Fetch live from Slack" asks Slack directly.'));
  } catch (e) { fail('mentions', 'mentions', e); }
}
async function fetchLive() {
  const b = $('live'), out = $('live-out');
  b.disabled = true; b.setAttribute('aria-busy', 'true'); b.textContent = 'Fetching from Slack…';
  out.hidden = false; out.textContent = 'Asking Slack. This can take up to two minutes.';
  try {
    const r = await post('/api/live?hours=' + $('win').value);
    out.textContent = (r.exit ? 'exit ' + r.exit + '\n' : '') + (r.output || '(no output)');
  } catch (e) {
    out.textContent = 'Live fetch failed: ' + e.message;
  }
  b.disabled = false; b.removeAttribute('aria-busy'); b.textContent = 'Fetch live from Slack';
}

// --- bot replies
// ponytail: wording heuristic on the first line only; a real flag needs the run status from the API
const looksFailed = s => /fail(ed|ure)|error|traceback|exception/i.test((s || '').trim().split('\n', 1)[0]);
// Light markdown for bot replies, built as DOM nodes (no innerHTML, so reply text can never become
// markup): blank-line paragraphs, "- "/"* "/"1. " lists, `code`, **bold**, bare https:// links. A
// leading "[CRON_FAILURE]"-style tag is dropped (looksFailed already flags it). Anything else is text.
function inline(s) {
  const out = [], re = /`([^`\n]+)`|\*\*([^*\n]+)\*\*|(https:\/\/[^\s<>()|]*[^\s<>()|.,;:!?'"])/g;
  let i = 0, m;
  while ((m = re.exec(s))) {
    out.push(s.slice(i, m.index), m[1] !== undefined ? el('code', null, m[1])
      : m[2] !== undefined ? el('strong', null, m[2])
      : el('a', {href: m[3], target: '_blank', rel: 'noopener noreferrer'}, m[3]));
    i = re.lastIndex;
  }
  out.push(s.slice(i));
  return out;
}
function markdown(text) {
  const blocks = [];
  for (const para of text.replace(/^\s*\[[A-Z][A-Z0-9_]*\]\s*/, '').split(/\n[ \t]*\n/)) {
    let list = null, lines = [];
    const flush = () => {
      const t = lines.join('\n').trim();
      if (t) blocks.push(el('p', null, ...inline(t)));
      lines = [];
    };
    for (const line of para.split('\n')) {
      const m = /^\s*(?:[-*]|(\d+)\.)\s+(.*)$/.exec(line), kind = m && (m[1] ? 'OL' : 'UL');
      if (m) {
        flush();
        if (!list || list.tagName !== kind) blocks.push(list = el(kind.toLowerCase()));
        list.append(el('li', null, ...inline(m[2])));
      } else if (list && /^\s+\S/.test(line)) {
        list.lastChild.append(' ', ...inline(line.trim()));  // wrapped list item
      } else {
        list = null;
        lines.push(line);
      }
    }
    flush();
  }
  return blocks;
}
function runCard(r) {
  const n = r.mentions.length;
  const d = el('details', null, el('summary', null, n + (n === 1 ? ' mention' : ' mentions') + ' in this run'),
    ...collapse(r.mentions).map(mentionRow));
  d.open = openRuns.has(r.session_id);
  d.addEventListener('toggle', () => d.open ? openRuns.add(r.session_id) : openRuns.delete(r.session_id));
  return el('article', {class: 'run'},
    el('div', {class: 'run-head'}, el('span', {class: 'who num'}, when(r.started_at)),
      el('span', {class: 'quiet'}, r.model || 'model unknown'),
      r.silent ? el('span', {class: 'caps quiet'}, 'Silent') : null,
      looksFailed(r.reply) ? el('span', {class: 'caps err'}, 'Error') : null),
    r.silent ? null : el('div', {class: 'reply'}, ...(r.reply ? markdown(r.reply) : [el('p', null,
      '(no reply recorded for this run)')])),
    n ? d : el('p', {class: 'extra'}, 'No mention blocks in this run.'));
}
async function loadReplies() {
  const q = $('q').value.trim(), silent = $('silent').checked;
  try {
    const d = await api('/api/replies?limit=' + replyLimit + '&q=' + encodeURIComponent(q));
    if (!q) count('replies', d.total);
    const items = silent ? d.items : d.items.filter(r => !r.silent);
    paint('replies', JSON.stringify([d, silent]), () => {
      if (!d.total) return empty(q ? 'No run matches "' + q + '".' : 'The bot has not replied yet: no cron run has woken the model.');
      const hiddenRuns = d.items.length - items.length;
      const note = el('p', {class: 'note num'}, 'Showing ' + items.length + ' of ' + d.total + ' runs'
        + (hiddenRuns ? ' (' + hiddenRuns + ' silent hidden)' : '') + '.');
      const more = el('button', {type: 'button'}, 'Show older runs');
      more.addEventListener('click', () => { replyLimit += 50; loadReplies(); });
      return [note, ...items.map(runCard), d.total > d.items.length ? el('p', {class: 'note'}, more) : null]
        .filter(Boolean);
    });
  } catch (e) { fail('replies', 'bot replies', e); }
}

// --- activity
async function loadActivity() {
  const errOnly = $('erronly').checked;
  try {
    const d = await api('/api/activity');
    count('activity', Object.values(d.counts).reduce((a, b) => a + b, 0));
    paint('counts', JSON.stringify(d.counts), () => Object.keys(OUTCOME).map(k =>
      el('div', null, el('dt', null, OUTCOME[k]), el('dd', null, Number(d.counts[k] || 0).toLocaleString()))));
    const items = errOnly ? d.items.filter(i => i.outcome === 'error') : d.items;
    paint('activity', JSON.stringify([items, errOnly]), () => {
      if (!items.length) return empty(errOnly ? 'No errors in the last ' + d.items.length + ' runs.' : 'No runs recorded yet.');
      const row = i => el('tr', null, el('td', {class: 'num'}, when(i.claimed_at)),
        el('td', {class: 'num'}, when(i.finished_at)),
        el('td', {class: TONE[i.outcome] || ''}, OUTCOME[i.outcome] || String(i.outcome)),
        el('td', {class: 'quiet'}, String(i.status || '-')), el('td', {class: 'err'}, i.error ? String(i.error) : ''));
      return el('div', {class: 'scroll'}, el('table', null,
        el('thead', null, el('tr', null, ...['Claimed', 'Finished', 'Outcome', 'Status', 'Error'].map(
          h => el('th', {scope: 'col'}, h)))),
        el('tbody', null, ...items.map(row))));
    });
  } catch (e) { fail('activity', 'activity', e); }
}

// --- reviews
async function loadReviews() {
  try {
    const d = await api('/api/reviews');
    count('reviews', d.rows.length);
    paint('reviews', JSON.stringify(d), () => {
      if (!d.rows.length) return empty(d.note || 'No review sessions.');
      const cols = Object.keys(d.rows[0]);
      return el('div', {class: 'scroll'}, el('table', null,
        el('thead', null, el('tr', null, ...cols.map(c => el('th', {scope: 'col'}, c)))),
        el('tbody', null, ...d.rows.map(r => el('tr', null, ...cols.map(
          c => el('td', {class: c === 'RESUME' || c === 'SESSION' ? 'mono' : ''}, String(r[c] ?? ''))))))));
    });
  } catch (e) { fail('reviews', 'review sessions', e); }
}

// --- tabs (state in the URL hash, arrow keys move between them)
const LOAD = {notifications: loadMentions, replies: loadReplies, activity: loadActivity, reviews: loadReviews};
function show(name, focus) {
  tab = TABS.includes(name) ? name : 'notifications';
  for (const t of TABS) {
    const on = t === tab;
    $('tab-' + t).setAttribute('aria-selected', on);
    $('tab-' + t).tabIndex = on ? 0 : -1;
    $('panel-' + t).hidden = !on;
  }
  if (focus) $('tab-' + tab).focus();
  if (location.hash !== '#' + tab) history.replaceState(null, '', '#' + tab);
  LOAD[tab]();
}
TABS.forEach((t, i) => {
  $('tab-' + t).addEventListener('click', () => show(t));
  $('tab-' + t).addEventListener('keydown', e => {
    const to = {ArrowRight: i + 1, ArrowLeft: i - 1, Home: 0, End: TABS.length - 1}[e.key];
    if (to === undefined) return;
    e.preventDefault();
    show(TABS[(to + TABS.length) % TABS.length], true);
  });
});
addEventListener('hashchange', () => show(location.hash.slice(1)));
$('win').addEventListener('change', loadMentions);
$('live').addEventListener('click', fetchLive);
$('silent').addEventListener('change', loadReplies);
$('erronly').addEventListener('change', loadActivity);
let typing;
$('q').addEventListener('input', () => { clearTimeout(typing); typing = setTimeout(loadReplies, 250); });

loadStatus();
show(location.hash.slice(1));
for (const t of TABS) if (t !== tab) LOAD[t]();  // once, for the tab counts
setInterval(() => { loadStatus(); LOAD[tab](); }, 30000);  // never the live fetch
</script>
</body>
</html>
"""


if __name__ == "__main__":
    sys.exit(main())
