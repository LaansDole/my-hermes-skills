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
    """The only SQLite open in this file: read-only, so it can never create or change a DB."""
    return sqlite3.connect(f"file:{quote(str(path))}?mode=ro", uri=True, timeout=5)


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
<meta name="color-scheme" content="dark light">
<title>Slack mention watch</title>
<style>
:root {
  --ground: #141416; --ink: #ece9e0; --muted: #9a968b; --hairline: #38373a; --tint: #1e1e21;
  --green: #4f9e63; --amber: #e8a33a; --rose: #db5f92; --on-fill: #17171b;
  --sans: "Helvetica Neue", Helvetica, Arial, system-ui, sans-serif;
  --mono: ui-monospace, Menlo, Consolas, monospace;
}
@media (prefers-color-scheme: light) {
  :root { --ground: #f6f4ee; --ink: #17171b; --muted: #5d5a52; --hairline: #cfcabd;
          --tint: #ebe7dc; --rose: #b0325f; }
}
* { box-sizing: border-box; }
body { margin: 0; padding: 24px 48px 96px; background: var(--ground); color: var(--ink);
       font: 16px/24px var(--sans); }
@media (width <= 720px) { body { padding: 16px 16px 64px; } }
header { display: flex; flex-wrap: wrap; align-items: baseline; justify-content: space-between;
         gap: 8px 24px; border-bottom: 3px solid var(--ink); padding-bottom: 8px; }
h1 { margin: 0; font-size: 32px; line-height: 40px; font-weight: 900; letter-spacing: -0.02em; }
h2 { margin: 0; font-size: 20px; line-height: 24px; font-weight: 800; }
.label, th, [role=tab], dt { font-size: 13px; line-height: 20px; font-weight: 800;
                             letter-spacing: 0.08em; text-transform: uppercase; }
.muted, dt { color: var(--muted); }
.num { font-variant-numeric: tabular-nums; }
button, input, select { font: inherit; color: inherit; border-radius: 0; }
button, select, input[type=datetime-local], input[type=search] {
  min-height: 40px; padding: 6px 12px; background: transparent; border: 2px solid var(--ink); }
button { font-weight: 800; cursor: pointer; }
button:hover:not(:disabled) { background: var(--ink); color: var(--ground); }
button:disabled { opacity: 0.5; cursor: progress; }
:focus-visible { outline: 3px solid var(--ink); outline-offset: 2px; }
a { color: inherit; font-weight: 700; text-underline-offset: 3px; }

.job { display: grid; grid-template-columns: minmax(200px, 1fr) minmax(280px, 3fr);
       gap: 16px 40px; padding: 24px 0; border-bottom: 1px solid var(--hairline); }
@media (width <= 900px) { .job { grid-template-columns: 1fr; } }
.badge { display: inline-block; margin-top: 8px; padding: 8px 16px; color: var(--on-fill);
         font-size: 20px; line-height: 24px; font-weight: 900; }
.badge.running { background: var(--green); }
.badge.paused { background: var(--amber); }
dl { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 8px 24px;
     margin: 0 0 16px; }
dd { margin: 0; overflow-wrap: anywhere; }
.err { color: var(--rose); }
.controls, .bar { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 16px; }
.bar { margin: 0 0 24px; }
.bar label { display: inline-flex; align-items: center; gap: 8px; }
input[type=checkbox] { width: 20px; height: 20px; accent-color: var(--ink); }
input[type=search] { flex: 1 1 320px; }
#flash { min-height: 24px; margin: 16px 0 0; font-weight: 700; }

[role=tablist] { display: flex; flex-wrap: wrap; gap: 0 24px; margin: 24px 0;
                 border-bottom: 1px solid var(--ink); }
[role=tab] { min-height: 44px; padding: 8px 0; border: 0; border-bottom: 3px solid transparent;
             color: var(--muted); }
[role=tab]:hover:not(:disabled) { background: transparent; color: var(--ink); }
[role=tab][aria-selected=true] { color: var(--ink); border-bottom-color: var(--ink); }

.card { padding: 16px 0; border-top: 1px solid var(--hairline); }
.card:last-child { border-bottom: 1px solid var(--hairline); }
.card .head { display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 16px; }
.card .who { font-weight: 800; }
.text, pre { margin: 8px 0; white-space: pre-wrap; overflow-wrap: anywhere; }
pre, .mono { font: 13px/20px var(--mono); }
pre { padding: 16px; background: var(--tint); border-left: 3px solid var(--ink); }
.tag { padding: 0 8px; border: 1px solid var(--ink); font-size: 12px; font-weight: 800;
       letter-spacing: 0.08em; }
details { margin-top: 8px; }
summary { cursor: pointer; font-weight: 700; padding: 8px 0; }
details .card { padding-left: 24px; }
.counts { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 16px;
          margin: 0 0 24px; }
.counts div { border-top: 3px solid var(--ink); padding-top: 8px; }
.counts b { display: block; font-size: 40px; line-height: 44px; font-weight: 900; }
.scroll { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; }
th, td { padding: 8px 16px 8px 0; text-align: left; vertical-align: top;
         border-bottom: 1px solid var(--hairline); }
th { border-bottom: 1px solid var(--ink); color: var(--muted); white-space: nowrap; }
.state { padding: 24px 0; color: var(--muted); }
.state.err { color: var(--rose); font-weight: 700; }
.spin::before { content: ""; display: inline-block; width: 12px; height: 12px; margin-right: 8px;
                border: 2px solid currentColor; border-right-color: transparent;
                border-radius: 50%; animation: spin 0.8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) { .spin::before { animation: none; } }
[hidden] { display: none !important; }
</style>
</head>
<body>
<header>
  <h1>Slack mention watch</h1>
  <span class="muted num" id="updated" aria-live="off">loading…</span>
</header>
<section id="jobs" aria-label="Bot status"><p class="state">Loading bot status…</p></section>
<p id="flash" role="status" aria-live="polite"></p>

<div role="tablist" aria-label="Views">
  <button role="tab" id="tab-notifications" aria-controls="panel-notifications">Notifications</button>
  <button role="tab" id="tab-replies" aria-controls="panel-replies">Bot replies</button>
  <button role="tab" id="tab-activity" aria-controls="panel-activity">Activity</button>
  <button role="tab" id="tab-reviews" aria-controls="panel-reviews">Reviews</button>
</div>

<section role="tabpanel" id="panel-notifications" aria-labelledby="tab-notifications" tabindex="0">
  <div class="bar">
    <label>Window
      <select id="win">
        <option value="1">Last hour</option><option value="24">Last 24 hours</option>
        <option value="168" selected>Last 7 days</option><option value="720">Last 30 days</option>
      </select>
    </label>
    <button id="live">Fetch live from Slack</button>
    <span class="muted">Listed here: mentions the bot was given. A live fetch asks Slack directly.</span>
  </div>
  <pre id="live-out" hidden></pre>
  <div id="mentions"><p class="state">Loading mentions…</p></div>
</section>

<section role="tabpanel" id="panel-replies" aria-labelledby="tab-replies" tabindex="0" hidden>
  <div class="bar">
    <input type="search" id="q" placeholder="Search replies and mentions" aria-label="Search replies and mentions">
    <label><input type="checkbox" id="silent"> Show silent runs</label>
  </div>
  <div id="replies"><p class="state">Loading replies…</p></div>
</section>

<section role="tabpanel" id="panel-activity" aria-labelledby="tab-activity" tabindex="0" hidden>
  <div class="counts" id="counts"></div>
  <div class="bar"><label><input type="checkbox" id="erronly"> Errors only</label></div>
  <div id="activity"><p class="state">Loading activity…</p></div>
</section>

<section role="tabpanel" id="panel-reviews" aria-labelledby="tab-reviews" tabindex="0" hidden>
  <div id="reviews"><p class="state">Loading review sessions…</p></div>
</section>

<script nonce="__NONCE__">
'use strict';
// All data reaches the DOM through textContent / text nodes, never as markup.
const $ = id => document.getElementById(id);
const csrf = document.querySelector('meta[name=csrf]').content;
const TABS = ['notifications', 'replies', 'activity', 'reviews'];
const OUTCOME = {nothing_new: 'Nothing new', sent: 'Sent', error: 'Error', missed: 'Missed'};
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
function when(iso) {
  if (!iso) return '-';
  const d = new Date(iso);
  return isNaN(d) ? String(iso) : d.toLocaleString(undefined, {weekday: 'short', year: 'numeric',
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'});
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
  $(id).replaceChildren(el('p', {class: 'state err', role: 'alert'},
    'Could not load ' + what + ': ' + e.message));
}
const empty = text => el('p', {class: 'state'}, text);

// --- status bar and controls
function jobRow(j) {
  const paused = !j.enabled || j.state === 'paused';
  const resume = j.scheduled_resume;
  const badge = paused ? (resume ? 'Paused until ' + when(resume.run_at) : 'Paused') : 'Running';
  const fact = (k, v, cls) => el('div', null, el('dt', null, k), el('dd', {class: cls || ''}, v));
  const facts = el('dl', null,
    fact('Schedule', j.schedule || '-'),
    fact('Next run', paused ? 'none while paused' : when(j.next_run_at)),
    fact('Last run', when(j.last_run_at) + (j.last_status ? ' (' + j.last_status + ')' : '')),
    j.last_error ? fact('Last error', String(j.last_error), 'err') : null);
  const btn = (label, action, getUntil) => {
    const b = el('button', {type: 'button'}, label);
    b.addEventListener('click', () => control(j, action, getUntil && getUntil(), b));
    return b;
  };
  const until = el('input', {type: 'datetime-local', 'aria-label': 'Pause ' + j.name + ' until'});
  const controls = el('div', {class: 'controls'},
    paused ? btn('Resume', 'resume') : btn('Pause', 'pause'),
    until, btn('Pause until', 'pause_until', () => until.value),
    resume ? btn('Cancel scheduled resume', 'cancel_resume') : null);
  return el('div', {class: 'job'},
    el('div', null, el('h2', null, j.name), el('div', {class: 'mono muted'}, j.id),
      el('div', {class: 'badge ' + (paused ? 'paused' : 'running')}, badge)),
    el('div', null, facts, controls));
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
  if (!force && document.activeElement && document.activeElement.matches('#jobs input')) return;
  try {
    const s = await api('/api/status');
    paint('jobs', JSON.stringify(s.jobs), () => s.jobs.length ? s.jobs.map(jobRow) : empty(
      'No slack-mention cron job found. Create one (see SKILL.md) or start the dashboard with --job <id>.'));
    $('updated').textContent = 'updated ' + new Date().toLocaleTimeString([], {hour12: false});
  } catch (e) {
    fail('jobs', 'bot status', e);
    $('updated').textContent = 'update failed ' + new Date().toLocaleTimeString([], {hour12: false});
  }
}

// --- notifications
function mentionCard(m) {
  const link = typeof m.permalink === 'string' && m.permalink.startsWith('https://')
    ? el('a', {href: m.permalink, target: '_blank', rel: 'noopener noreferrer'}, 'Open in Slack') : null;
  return el('article', {class: 'card'},
    el('div', {class: 'head'}, el('span', {class: 'who'}, m.sender), el('span', null, m.channel),
      el('span', {class: 'muted num'}, m.at), link),
    el('div', {class: 'text'}, m.text || '(no text)'),
    m.reacted ? el('div', {class: 'muted'}, 'Reacted: ' + m.reacted) : null,
    m.review ? el('div', {class: 'muted mono'}, 'review: ' + m.review) : null);
}
async function loadMentions() {
  const sel = $('win');
  try {
    const d = await api('/api/mentions?hours=' + sel.value);
    paint('mentions', JSON.stringify(d.items), () => d.items.length ? d.items.map(mentionCard)
      : empty('No mentions reached the bot in this window (' + sel.selectedOptions[0].textContent.toLowerCase()
        + '). "Fetch live from Slack" asks Slack directly.'));
  } catch (e) { fail('mentions', 'mentions', e); }
}
async function fetchLive() {
  const b = $('live'), out = $('live-out');
  b.disabled = true; b.classList.add('spin'); b.textContent = 'Fetching from Slack…';
  out.hidden = false; out.textContent = 'Asking Slack. This can take up to two minutes.';
  try {
    const r = await post('/api/live?hours=' + $('win').value);
    out.textContent = (r.exit ? 'exit ' + r.exit + '\n' : '') + (r.output || '(no output)');
  } catch (e) {
    out.textContent = 'Live fetch failed: ' + e.message;
  }
  b.disabled = false; b.classList.remove('spin'); b.textContent = 'Fetch live from Slack';
}

// --- bot replies
function runCard(r) {
  const n = r.mentions.length;
  const d = el('details', null, el('summary', null, n + (n === 1 ? ' mention' : ' mentions') + ' in this run'),
    ...r.mentions.map(mentionCard));
  d.open = openRuns.has(r.session_id);
  d.addEventListener('toggle', () => d.open ? openRuns.add(r.session_id) : openRuns.delete(r.session_id));
  return el('article', {class: 'card'},
    el('div', {class: 'head'}, el('span', {class: 'who num'}, when(r.started_at)),
      el('span', {class: 'muted mono'}, r.model || 'model unknown'),
      r.silent ? el('span', {class: 'tag'}, 'SILENT') : null),
    r.silent ? null : el('div', {class: 'text'}, r.reply || '(no reply recorded for this run)'),
    n ? d : el('div', {class: 'muted'}, 'No mention blocks in this run.'));
}
async function loadReplies() {
  const q = $('q').value.trim(), silent = $('silent').checked;
  try {
    const d = await api('/api/replies?limit=' + replyLimit + '&q=' + encodeURIComponent(q));
    const items = silent ? d.items : d.items.filter(r => !r.silent);
    paint('replies', JSON.stringify([d, silent]), () => {
      if (!d.total) return empty(q ? 'No run matches "' + q + '".' : 'The bot has not replied yet: no cron run has woken the model.');
      const hiddenRuns = d.items.length - items.length;
      const note = el('p', {class: 'muted'}, 'Showing ' + items.length + ' of ' + d.total + ' runs'
        + (hiddenRuns ? ' (' + hiddenRuns + ' silent hidden)' : '') + '.');
      const more = el('button', {type: 'button'}, 'Show older runs');
      more.addEventListener('click', () => { replyLimit += 50; loadReplies(); });
      return [note, ...items.map(runCard), d.total > d.items.length ? el('p', null, more) : null]
        .filter(Boolean);
    });
  } catch (e) { fail('replies', 'bot replies', e); }
}

// --- activity
async function loadActivity() {
  const errOnly = $('erronly').checked;
  try {
    const d = await api('/api/activity');
    paint('counts', JSON.stringify(d.counts), () => Object.keys(OUTCOME).map(k =>
      el('div', null, el('b', {class: 'num'}, String(d.counts[k] || 0)), el('span', {class: 'label'}, OUTCOME[k]))));
    const items = errOnly ? d.items.filter(i => i.outcome === 'error') : d.items;
    paint('activity', JSON.stringify([items, errOnly]), () => {
      if (!items.length) return empty(errOnly ? 'No errors in the last ' + d.items.length + ' runs.' : 'No runs recorded yet.');
      const row = i => el('tr', null, el('td', {class: 'num'}, when(i.claimed_at)),
        el('td', {class: 'num'}, when(i.finished_at)),
        el('td', {class: i.outcome === 'error' ? 'err' : ''}, OUTCOME[i.outcome] || String(i.outcome)),
        el('td', null, String(i.status || '-')), el('td', {class: 'err'}, i.error ? String(i.error) : ''));
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
setInterval(() => { loadStatus(); LOAD[tab](); }, 30000);  // never the live fetch
</script>
</body>
</html>
"""


if __name__ == "__main__":
    sys.exit(main())
