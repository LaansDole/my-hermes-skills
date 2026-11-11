#!/usr/bin/env python3
"""Digest wrapper with an opt-in background PR-review agent.

Runs `watch_mentions.py --digest --react <args>` (stderr inherited, exit code passed through).
If SLACK_REVIEW_AGENT is set (omp / claude / custom), every new mention whose Mention text asks
the user to review (PTAL, "could you review ...", "can you check this", ...) starts a detached,
read-only review session for the GitHub PRs (and ticket keys matching SLACK_REVIEW_TICKET_RE)
named in the Mention text, else in the thread root only; a `review:` line with its resume
command goes into that mention's block.
Feature off -> the digest is printed unchanged. Any error in the review layer -> one stderr
line `[slack-review] error: ...` and the raw digest.

Skipped without a spawn: thanks/FYI/already handled mentions (`Reacted:` line), mentions that
are no review request (`review: skipped (not a review request)`), and targets
that are merged/closed/approved/already reviewed by you (PRs, via gh) or done (tickets, only
with JIRA_URL/JIRA_EMAIL/JIRA_TOKEN). Checks fail open. Targets are deduped for 24 h.

Optional second opinion, off by default (it sends mention + thread text to a third party):
SLACK_REVIEW_JEV=1 + TYPESAFE_API_KEY asks TypeSafe Jev about regex-positive mentions only;
p(review) < SLACK_REVIEW_JEV_MIN (0.8) -> `skipped (not a review request (jev p))`. Jev
errors -> the regex decides. One row per call in SLACK_REVIEW_JEV_LOG.

Env (process env first, then ~/.hermes/.env): SLACK_REVIEW_AGENT, SLACK_REVIEW_WORKDIR,
SLACK_REVIEW_MODEL, SLACK_REVIEW_EFFORT (omp --thinking), SLACK_REVIEW_CMD (custom, with
{brief} and {workdir}), SLACK_REVIEW_MAX_SPAWNS (3), SLACK_REVIEW_TICKET_RE,
SLACK_REVIEW_INSTRUCTIONS, SLACK_REVIEW_STATE, SLACK_REVIEW_DIR, SLACK_REVIEW_ID_TIMEOUT (30),
SLACK_REVIEW_GH, SLACK_REVIEW_GH_LOGIN, JIRA_URL, JIRA_EMAIL, JIRA_TOKEN, SLACK_REVIEW_JEV,
SLACK_REVIEW_JEV_MIN (0.8), SLACK_REVIEW_JEV_LOG (~/.hermes/scripts/.slack-review-jev.jsonl),
TYPESAFE_API_KEY.

Stdlib only. Flags: all passed through to watch_mentions.py; --dry-run also spawns nothing.
"""
import base64
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from functools import lru_cache

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import watch_mentions as wm  # noqa: E402  (shared env/dotenv lookup, Jev URL + question)

TAG = "[slack-review]"
AGENTS = ("omp", "claude", "custom")
TTL = 24 * 3600
MAX_TARGETS = 5
CHECK_TIMEOUT = 15
BLOCK_SPLIT = re.compile(r"\n\n(?=### Mention )")
PR_RE = r"(?i:github\.com/(?P<o>[\w.-]+)/(?P<r>[\w.-]+)/pull/(?P<n>\d+))"
NO_RESUME = "autoResume: false\n"
CLAUDE_ALLOW = ("Read", "Grep", "Glob", "Bash(gh pr view:*)", "Bash(gh pr diff:*)",
                "Bash(gh pr checks:*)", "Bash(gh api:*)", "Bash(git fetch:*)",
                "Bash(git show:*)", "Bash(git diff:*)", "Bash(git log:*)")
CLAUDE_DENY = ("Edit", "Write", "NotebookEdit")


class SpawnError(Exception):
    def __init__(self, reason, log=None):
        super().__init__(reason)
        self.log = log


def cfg(name, default=None):
    return wm.env(name) or default


def _path(name, default):
    return os.path.expanduser(cfg(name, default))


def state_path():
    return _path("SLACK_REVIEW_STATE", "~/.hermes/scripts/.slack-review-spawn.json")


def workdir():
    return os.path.expanduser(cfg("SLACK_REVIEW_WORKDIR", ""))


# Parsing --------------------------------------------------------------------

def parse(text):
    """(header, blocks); assemble(header, blocks) == text byte for byte."""
    parts = BLOCK_SPLIT.split(text)
    return parts[0], parts[1:]


def assemble(header, blocks):
    return "\n\n".join([header, *blocks])


def targets(block):
    """PRs as owner/repo#n, plus ticket keys if SLACK_REVIEW_TICKET_RE is set; unique, max 5."""
    ticket = cfg("SLACK_REVIEW_TICKET_RE")
    pattern = PR_RE + (f"|(?:{ticket})" if ticket else "")
    out = []
    for m in re.finditer(pattern, block):
        t = f"{m['o']}/{m['r']}#{m['n']}" if m["n"] else m.group(0)
        if t not in out:
            out.append(t)
            if len(out) == MAX_TARGETS:
                break
    return out


SKIP_REACTED = ("already replied", "already reacted", ":raised_hands:", ":memo:")


def eligible(block):
    """Has targets and the mention was not a thanks/FYI ping or already handled."""
    r = next((l for l in block.split("\n") if l.startswith("Reacted:")), "")
    return bool(targets(block)) and not any(s in r for s in SKIP_REACTED)


def annotate(block, line):
    """Insert line after Reacted:, else after Mention: and its 4-space continuations."""
    lines = block.split("\n")
    idx = next((i for i, l in enumerate(lines) if l.startswith("Reacted:")), None)
    if idx is None:
        idx = next((i for i, l in enumerate(lines) if l.startswith("Mention:")), 0)
        while idx + 1 < len(lines) and lines[idx + 1].startswith("    "):
            idx += 1
    lines.insert(idx + 1, line)
    return "\n".join(lines)


# Review intent (deterministic gate over the Mention text only) ---------------

SLACK_LINK = re.compile(r"<((?:https?|mailto):[^|>]*)(?:\|([^>]*))?>")
URL_RE = re.compile(r"https?://\S+")
_OBJ = (r"(?:this|that|it|the\s+(?:PRs?|pull\s+requests?|fix(?:es)?|hotfix(?:es)?|tickets?"
        r"|changes?|builds?)|on\s+(?:staging|prod|dev))")
# Must NOT match "Review to move:", "update the list", "edit message", "reviewed with comment",
# "check and assign ... so I can review" (tests pin both sides).
INTENT_RES = tuple(re.compile(p, re.I) for p in (
    r"\bptal\b",
    r"\b(?:take|have) a (?:quick )?look\b",
    r"\b(?:can|could|would|will) you\b[^.?!\n]{0,40}\b(?:re-?)?review(?!ed)",
    r"\b(?:please|pls|plz|help(?: me)?(?: to)?)\b[^.?!\n]{0,30}\b(?:re-?)?review(?!ed)",
    r"\b(?:re-?)?review\s+(?:this|that|it|the|my|our|these|those|PRs?|pull|tickets?"
    r"|hotfix(?:es)?|fix(?:es)?|changes?)\b",
    # check/test/verify/approve only with an object ("check and assign" is triage)
    r"\b(?:(?:can|could|would|will) you|please|pls|plz)\b[^.?!\n]{0,40}"
    r"\b(?:check|test|verify|approve)\s+" + _OBJ + r"\b",
))
# A review whose subject is not the reader never counts: removed before matching.
NOT_MINE_RE = re.compile(
    r"\b(?:I|we|they|he|she)(?:['’](?:ll|d)|\s+(?:can|could|will|would|should|may|might|shall))?"
    r"\s+(?:re-?)?review|\bin\s+review\b|\breview\s+to\s+move\b", re.I)
PR_ASK_RE = re.compile(r"\b(?:review|ptal|look|check|approve|verify|test)|\?", re.I)


def mention_text(block):
    """The `Mention:` line + its 4-space continuation lines (never the thread)."""
    lines = block.split("\n")
    i = next((i for i, l in enumerate(lines) if l.startswith("Mention:")), None)
    if i is None:
        return ""
    out = [lines[i][len("Mention:"):].strip()]
    for l in lines[i + 1:]:
        if not l.startswith("    "):
            break
        out.append(l[4:])
    return "\n".join(out)


def thread_msgs(block):
    """Thread messages, each with its continuation lines; [0] is the thread root."""
    lines = block.split("\n")
    i = next((i for i, l in enumerate(lines) if l.startswith("Thread (")), None)
    msgs = []
    for l in lines[i + 1:] if i is not None else ():
        if l.startswith("    ") and msgs:
            msgs[-1] += "\n" + l[4:]
        elif l.startswith("["):
            msgs.append(l)
        else:
            break
    return msgs


def review_intent(block):
    """The request phrase if the Mention text asks the reader to review/check, else None."""
    raw = mention_text(block)
    # link labels stay, URLs go (a URL's `?` is no question)
    ask = NOT_MINE_RE.sub(" ", URL_RE.sub(" ", SLACK_LINK.sub(lambda m: m[2] or " ", raw)))
    for r in ((PR_ASK_RE,) if re.search(PR_RE, raw) else ()) + INTENT_RES:
        m = r.search(ask)
        if m:
            return m.group(0)
    return None


def scoped_targets(block):
    """Targets in the Mention text, else in the thread root only; never the rest of the thread."""
    return targets(mention_text(block)) or targets((thread_msgs(block) or [""])[0])


# Jev second opinion (opt-in: SLACK_REVIEW_JEV + TYPESAFE_API_KEY) -----------

WATCHED_RE = re.compile(r"\(watched user: (@?[^)\s]+)\)")


def _plain(text):
    """Slack `<url|label>` -> `label url`."""
    return SLACK_LINK.sub(lambda m: f"{m[2]} {m[1]}" if m[2] else m[1], text)


def jev_min():
    # 0.8: with mention + thread context real asks score ~0.98, a "check and assign ... so I
    # can review" triage ask 0.68. The intent regex is the primary guard; Jev the second.
    return float(cfg("SLACK_REVIEW_JEV_MIN", "0.8"))


def jev_p(block, watched, hit, dry_run, tick):
    """Jev p(review) for a regex-positive block, or None (off, no key, error: regex alone).
    One log row per call. A 401/403 turns Jev off for the rest of the tick (tick["off"])."""
    key = cfg("TYPESAFE_API_KEY")
    if (tick.get("off") or not key
            or (cfg("SLACK_REVIEW_JEV") or "").lower() not in ("1", "true", "yes")):
        return None
    mention = _plain(mention_text(block))
    body = {"state": {"watched_user": watched, "mention": mention,
                      "thread": [_plain(m) for m in thread_msgs(block)]},
            "model": "jev-latest", "questions": {"review": wm.JEV_Q["review"]}}
    req = urllib.request.Request(wm.JEV_URL, data=json.dumps(body).encode(), method="POST",
                                 headers={"Authorization": f"Bearer {key}",
                                          "Content-Type": "application/json"})
    row = {"logged_at": datetime.now().astimezone().isoformat(timespec="seconds"),
           "permalink": next((l[len("Permalink:"):].strip() for l in block.split("\n")
                              if l.startswith("Permalink:")), None),
           "mention": mention[:300], "regex": hit, "p_review": None, "decision": "review",
           "model": None, "ms": 0, "error": None}
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode("utf-8"))
        p = float(data["answers"]["review"]["noul"])
        if not 0 <= p <= 1:  # also NaN
            raise ValueError("p out of range")
        row.update(p_review=p, model=data.get("model"),
                   decision="review" if p >= jev_min() else "skip")
    except Exception as e:
        code = e.code if isinstance(e, urllib.error.HTTPError) else None
        if code in (401, 403):
            tick["off"] = True
            print(f"{TAG} jev: auth rejected (HTTP {code})", file=sys.stderr)
        # only the type name: str(e) can echo request headers, i.e. the key
        row["error"] = type(e).__name__ + (f" {code}" if code else "")
    row["ms"] = int((time.monotonic() - t0) * 1000)
    line = json.dumps(row, ensure_ascii=False)
    if dry_run:
        print(f"{TAG} {line}", file=sys.stderr)
        return row["p_review"]
    path = _path("SLACK_REVIEW_JEV_LOG", "~/.hermes/scripts/.slack-review-jev.jsonl")
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600), "a") as f:
            f.write(line + "\n")
    except OSError as e:  # ponytail: the log is diagnostics only, never blocks the digest
        print(f"{TAG} jev: log write failed: {type(e).__name__}", file=sys.stderr)
    return row["p_review"]


# Target checks (read only, fail open) ---------------------------------------

def _run(argv):
    """stdout of argv, or None on any failure."""
    try:
        r = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                           stdin=subprocess.DEVNULL, text=True, timeout=CHECK_TIMEOUT)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout if r.returncode == 0 else None


def gh_bin():
    return (cfg("SLACK_REVIEW_GH") or shutil.which("gh")
            or next((p for p in ("/opt/homebrew/bin/gh", "/usr/local/bin/gh")
                     if os.path.exists(p)), "gh"))


@lru_cache(maxsize=None)
def _gh_login(gh):
    return (_run([gh, "api", "user", "--jq", ".login"]) or "").strip() or None


def _ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _check_pr(t):
    repo, n = t.rsplit("#", 1)
    gh = gh_bin()
    pr = json.loads(_run([gh, "pr", "view", n, "-R", repo, "--json",
                          "state,reviewDecision,reviews,commits"]) or "null")
    state = pr["state"]
    if state in ("MERGED", "CLOSED"):
        return state.lower()
    if pr.get("reviewDecision") == "APPROVED":
        return "approved"
    login = cfg("SLACK_REVIEW_GH_LOGIN") or _gh_login(gh)
    last = max(_ts(c["committedDate"]) for c in pr["commits"])
    for r in pr.get("reviews") or ():
        if (login and (r.get("author") or {}).get("login", "").lower() == login.lower()
                and r.get("submittedAt") and _ts(r["submittedAt"]) >= last):
            return "already reviewed by you"
    return None


def _check_ticket(key):
    url, email, token = cfg("JIRA_URL"), cfg("JIRA_EMAIL"), cfg("JIRA_TOKEN")
    if not (url and email and token):
        return None
    auth = base64.b64encode(f"{email}:{token}".encode()).decode()
    req = urllib.request.Request(
        f"{url.rstrip('/')}/rest/api/2/issue/{urllib.parse.quote(key)}?fields=status",
        headers={"Authorization": "Basic " + auth, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=CHECK_TIMEOUT) as r:
        st = json.loads(r.read())["fields"]["status"]
    return f"done ({st['name']})" if st["statusCategory"]["key"] == "done" else None


def check_target(t):
    """Skip reason if the target needs no review, else None. Any error -> None (fail open)."""
    try:
        return _check_pr(t) if "#" in t else _check_ticket(t)
    except Exception:  # ponytail: fail open on any malformed/unexpected output
        return None


# State ----------------------------------------------------------------------

def load_state(path, now):
    try:
        with open(path) as f:
            st = json.load(f)
        return {k: v for k, v in st.items() if now - float(v["at"]) <= TTL}
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return {}


def save_state(path, state):
    d = os.path.dirname(path) or "."
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".srs-")  # mkstemp creates it 0600
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(state, f, indent=1, sort_keys=True)
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


# Spawn ----------------------------------------------------------------------

BRIEF = """\
# Review request from Slack (headless, READ ONLY)

You were started automatically because a Slack @mention asked the user to look at the
targets below. Produce a concise review report for the user. You work READ ONLY.

## Slack context (raw digest block)

{block}

## Targets

{target_list}

## How to review

- GitHub PRs (owner/repo#n): read them with gh, read-only: `gh pr view`, `gh pr diff`,
  `gh pr checks`, `gh api` GET requests. For more context, `git fetch origin pull/<n>/head`
  in the matching clone under the current directory, then `git show` / `git diff` / `git log`
  on the fetched refs.
- Tickets: read the ticket with whatever read-only access is configured. GET/search only.
- NEVER edit files, commit, checkout/switch branches, add/remove worktrees, or change any
  state in the user's checkouts. NEVER push, comment, approve or request changes.
- Never post to Slack, GitHub or the ticket tracker.

## Report (your final message, plain text, concise)

Per target: one-line summary of what it is / its status, then ONLY critical/high (P0 and P1)
findings, each with: severity, file:line, problem, why it matters (impact), suggested fix.
If there are none, say "No P0/P1 findings".
"""


def build_brief(block, tgts):
    text = BRIEF.format(block=block.rstrip("\n"),
                        target_list="\n".join(f"- {t}" for t in tgts))
    extra = cfg("SLACK_REVIEW_INSTRUCTIONS")
    if extra:
        with open(os.path.expanduser(extra)) as f:
            text += "\n## Additional instructions\n\n" + f.read()
    return text


def _bin(name):
    return shutil.which(name) or os.path.expanduser(f"~/.local/bin/{name}")


def _argv(agent, brief, d, wd):
    if agent == "omp":
        overlay = os.path.join(d, "omp-noresume.yml")
        if _read(overlay) != NO_RESUME:  # without it `omp -p` resumes the user's last session
            with open(overlay, "w") as f:
                f.write(NO_RESUME)
        model, effort = cfg("SLACK_REVIEW_MODEL"), cfg("SLACK_REVIEW_EFFORT")
        return [_bin("omp"), "-p", "--mode", "json", "--config", overlay,
                *(["--model", model] if model else []),
                *(["--thinking", effort] if effort else []),
                "--cwd", wd, "@" + brief]
    if agent == "claude":
        model = cfg("SLACK_REVIEW_MODEL")
        # prompt right after -p: --allowedTools/--disallowedTools are variadic and would eat it
        return [_bin("claude"), "-p", _read(brief), "--output-format", "stream-json",
                "--verbose", *(["--model", model] if model else []),
                "--permission-mode", "default", "--allowedTools", *CLAUDE_ALLOW,
                "--disallowedTools", *CLAUDE_DENY]
    return [a.replace("{brief}", brief).replace("{workdir}", wd)
            for a in shlex.split(cfg("SLACK_REVIEW_CMD"))]


def _session_id(path, agent):
    try:
        with open(path) as f:
            for line in f:
                if not line.endswith("\n"):
                    break  # partial write; retry next poll
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(rec, dict):
                    continue
                if agent == "omp" and rec.get("type") == "session" and rec.get("id"):
                    return rec["id"]
                if (agent == "claude" and rec.get("type") == "system"
                        and rec.get("subtype") == "init" and rec.get("session_id")):
                    return rec["session_id"]
    except OSError:
        pass
    return None


def _tail(path, n=300):
    try:
        with open(path, errors="replace") as f:
            return " ".join(f.read()[-n:].split())
    except OSError:
        return ""


def _read(path):
    try:
        with open(path) as f:
            return f.read()
    except OSError:
        return None


def spawn(block, tgts, now):
    """Start a detached review session. Returns its session id (custom agent: its log path);
    raises SpawnError."""
    agent, wd = cfg("SLACK_REVIEW_AGENT"), workdir()
    d = _path("SLACK_REVIEW_DIR", "~/.hermes/cache/slack-review-spawns")
    os.makedirs(d, exist_ok=True)
    slug = re.sub(r"[^A-Za-z0-9]+", "-", "_".join(tgts)).strip("-")[:60] or "review"
    base = os.path.join(d, f"{datetime.fromtimestamp(now).strftime('%Y%m%d-%H%M%S')}-{slug}")
    brief, err = base + ".md", base + ".err"
    out = base + (".log" if agent == "custom" else ".jsonl")
    with open(brief, "w") as f:
        f.write(build_brief(block, tgts))
    try:
        with open(out, "w") as o, open(err, "w") as e:
            proc = subprocess.Popen(_argv(agent, brief, d, wd), stdout=o, stderr=e,
                                    stdin=subprocess.DEVNULL, start_new_session=True, cwd=wd)
    except OSError as e:
        raise SpawnError(f"cannot start {agent}: {e}", err)
    if agent == "custom":
        return out
    deadline = time.time() + float(cfg("SLACK_REVIEW_ID_TIMEOUT", "30"))
    while True:
        sid = _session_id(out, agent)
        if sid:
            return sid
        rc = proc.poll()
        if rc is not None:
            sid = _session_id(out, agent)
            if sid:
                return sid
            raise SpawnError(f"{agent} exited {rc} before session id: {_tail(err)}".rstrip(": "),
                             err)
        if time.time() >= deadline:
            # ponytail: left running on purpose, it may still be fine; log path tells the user
            raise SpawnError(f"no session id within timeout, {agent} left running", out)
        time.sleep(0.25)


# Orchestration --------------------------------------------------------------

def _started(agent, sid, names, running=False):
    if agent == "custom":
        return f"already running ({names}; log {sid})" if running else f"started (log {sid})"
    shown = workdir().replace(os.path.expanduser("~"), "~", 1)
    return (f"{'already running ' if running else ''}{sid} ({names}) -> "
            f"cd {shown} && {agent} --resume {sid}")


def process(text, dry_run=False, now=None, spawner=spawn, checker=check_target):
    agent = cfg("SLACK_REVIEW_AGENT")
    if not agent:
        return text
    header, blocks = parse(text)
    if not blocks:
        return text
    if agent not in AGENTS:
        raise ValueError(f"SLACK_REVIEW_AGENT={agent!r}, expected one of {', '.join(AGENTS)}")
    if not workdir():
        raise ValueError("SLACK_REVIEW_WORKDIR is required")
    if agent == "custom" and not cfg("SLACK_REVIEW_CMD"):
        raise ValueError("SLACK_REVIEW_CMD is required for SLACK_REVIEW_AGENT=custom")
    now = time.time() if now is None else now
    path = state_path()
    state = load_state(path, now)
    cap = int(cfg("SLACK_REVIEW_MAX_SPAWNS", "3"))
    w = WATCHED_RE.search(header)
    watched = "@" + w[1].lstrip("@") if w else "the watched user"
    spawned, tick = 0, {}
    for i, block in enumerate(blocks):
        if not eligible(block):
            continue
        hit = review_intent(block)
        cands = scoped_targets(block) if hit else []
        p = jev_p(block, watched, hit, dry_run, tick) if cands else None
        why = ("not a review request" if not hit else
               "no target in mention or thread root" if not cands else
               f"not a review request (jev {p:.2f})" if p is not None and p < jev_min()
               else None)
        if why:
            blocks[i] = annotate(block, f"review: skipped ({why})")
            continue
        tgts, skipped = [], []
        for t in cands:
            reason = checker(t)
            if reason:
                skipped.append(f"{t} {reason}")
            else:
                tgts.append(t)
        if not tgts:
            blocks[i] = annotate(block, f"review: skipped ({'; '.join(skipped)})")
            continue
        names = ", ".join(tgts)
        if all(t in state for t in tgts):
            sid = max((state[t] for t in tgts), key=lambda v: v["at"])["session"]
            line = "review: " + _started(agent, sid, names, running=True)
        elif dry_run:
            line = f"review: (dry run, would spawn for: {names})"
        elif spawned >= cap:
            line = "review: skipped (spawn cap reached)"
        else:
            spawned += 1
            try:
                sid = spawner(block, tgts, now)
            except SpawnError as e:
                line = f"review: failed ({str(e)[:200]}; log {e.log})"
            else:
                for t in tgts:
                    state[t] = {"session": sid, "at": now}
                line = "review: " + _started(agent, sid, names)
        if skipped:
            line += f" [skipped: {'; '.join(skipped)}]"
        blocks[i] = annotate(block, line)
    if not dry_run:
        save_state(path, state)
    return assemble(header, blocks)


def main():
    args = sys.argv[1:]
    child = subprocess.run([sys.executable, os.path.join(HERE, "watch_mentions.py"),
                            "--digest", "--react", *args],
                           stdout=subprocess.PIPE, text=True)  # no timeout: react may sleep
    out = child.stdout
    try:
        out = process(out, dry_run="--dry-run" in args)
    except Exception as e:  # the digest must never break
        print(f"{TAG} error: {type(e).__name__}: {e}", file=sys.stderr)
        out = child.stdout
    sys.stdout.write(out)
    return child.returncode


if __name__ == "__main__":
    sys.exit(main())
