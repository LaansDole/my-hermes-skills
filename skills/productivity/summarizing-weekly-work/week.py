#!/usr/bin/env python3
"""Collect a week's evidence: omp sessions (title, prompts, open todos, last
compaction summary, last reply) + GitHub PRs (yours open/merged, your review
queue). Read-only. Output: markdown on stdout for the agent to classify."""
import argparse, json, os, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

SESSIONS = Path.home() / ".omp/agent/sessions"
OPEN = ("in_progress", "pending", "blocked")
# absolute(), not resolve(): a symlinked install must find its siblings in the install dir, not the repo.
AUDIT = Path(__file__).absolute().parent.parent / "auditing-worktrees/audit.py"
SWEEP = Path(__file__).absolute().parent.parent / "sweeping-merged-worktrees/sweep.py"


def clip(s, n):
    s = " ".join((s or "").split())
    return s if len(s) <= n else s[: n - 1] + "…"


def text_of(content):
    if isinstance(content, str):
        return content
    return " ".join(c.get("text", "") for c in content or [] if c.get("type") == "text")


def parse(path):
    s = {"file": str(path), "title": None, "cwd": None, "start": None, "last": None,
         "prompts": [], "todo": None, "summary": None, "reply": None, "turns": 0}
    for line in path.open(errors="replace"):
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if not isinstance(e, dict):
            continue
        t, ts = e.get("type"), e.get("timestamp")
        if t == "session":
            s["cwd"], s["start"], s["id"] = e.get("cwd"), ts, e.get("id")
            s["title"] = s["title"] or e.get("title")
        elif t in ("title", "title_change") and e.get("title"):
            s["title"] = e["title"]
        elif t == "compaction" and e.get("summary") and not e["summary"].startswith("Resume prior conversation"):
            s["summary"] = e["summary"]
        elif t == "custom_message" and e.get("customType") == "skill-prompt":
            d = e.get("details") or {}
            s["prompts"].append(f"/skill:{d.get('name')} {d.get('args') or ''}")
            s["turns"] += 1
            s["last"] = ts
        elif t == "message":
            m = e.get("message") or {}
            role = m.get("role")
            if role in ("user", "assistant"):  # notifications/checkpoints also stamp the log; ignore them
                s["last"] = ts
            if role == "user":
                txt = text_of(m.get("content"))
                if txt.strip():
                    s["prompts"].append(txt)
                    s["turns"] += 1
            elif role == "assistant":
                txt = text_of(m.get("content"))
                if txt.strip():
                    s["reply"] = txt
            elif role == "toolResult" and m.get("toolName") == "todo":
                d = m.get("details") or {}
                if "phases" in d:
                    s["todo"] = d["phases"]
    return s


def sessions(since, only):
    out = []
    for f in SESSIONS.glob("*/*.jsonl"):  # top level only; subagent logs live in per-session dirs
        if datetime.fromtimestamp(f.stat().st_mtime, timezone.utc) < since:
            continue
        s = parse(f)
        self_run = any(p.startswith("/skill:summarizing-weekly-work") for p in s["prompts"])
        if not s["turns"] or self_run or (s["last"] or "") < f"{since:%Y-%m-%dT%H:%M:%S}" \
                or (only and only not in (s["cwd"] or "")):
            continue
        out.append(s)
    return sorted(out, key=lambda s: (s["cwd"] or "", s["last"] or ""))


def gh(args):
    try:
        r = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=60)
        return json.loads(r.stdout) if r.returncode == 0 and r.stdout.strip() else None
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


def prs(since_day):
    f = "repository,number,title,url,createdAt,updatedAt,isDraft"
    q = {
        "Your open PRs": ["--author=@me", "--state=open"],
        "Your PRs merged in window": ["--author=@me", f"--merged-at=>={since_day}"],
        "Review requested from you (open)": ["--review-requested=@me", "--state=open"],
        "PRs you reviewed, updated in window": ["--reviewed-by=@me", f"--updated=>={since_day}", "--", "-author:@me"],
    }
    with ThreadPoolExecutor(8) as ex:
        res = dict(zip(q, ex.map(lambda a: gh(["search", "prs", "--json", f, "--limit", "50", *a]), q.values())))
        if res["Your open PRs"] is None:
            return None
        detail = lambda p: gh(["pr", "view", str(p["number"]), "-R", p["repository"]["nameWithOwner"],
                               "--json", "headRefName,reviewDecision,mergeable,statusCheckRollup,"
                                         "reviewRequests,latestReviews"])
        for k in ("Your open PRs", "Review requested from you (open)"):
            for p, d in zip(res[k] or [], ex.map(detail, res[k] or [])):
                p["detail"] = d or {}
    return res


def checks(rollup):
    st = [(c.get("conclusion") or c.get("state") or c.get("status") or "").upper() for c in rollup or []]
    if not st:
        return "no checks"
    bad = sum(x in ("FAILURE", "ERROR", "CANCELLED", "TIMED_OUT") for x in st)
    run = sum(x in ("PENDING", "IN_PROGRESS", "QUEUED", "EXPECTED") for x in st)
    return f"{bad} failing" if bad else f"{run} running" if run else "green"


def render(ss, pr, since, n):
    o = [f"# Week evidence since {since:%Y-%m-%d %H:%M} UTC ({len(ss)} sessions)\n"]
    cwd = None
    for s in ss:
        if s["cwd"] != cwd:
            cwd = s["cwd"]
            gone = "" if cwd and os.path.isdir(cwd) else "  ⚠ cwd no longer exists (worktree removed?)"
            o.append(f"\n## {cwd}{gone}\n")
        o.append(f"### {s['title'] or '(untitled)'}")
        o.append(f"- when: {(s['start'] or '')[:16]} → {(s['last'] or '')[:16]}, {s['turns']} user turns")
        o.append(f"- resume: `cd {s['cwd']} && omp -r {s.get('id')}` (log: {s['file']})")
        o.append(f"- first ask: {clip(s['prompts'][0], n)}")
        if s["turns"] > 1:
            o.append(f"- last asks: " + " ⏵ ".join(clip(p, 160) for p in s["prompts"][-3:]))
        if s["todo"]:
            tasks = [(ph["name"], t) for ph in s["todo"] for t in ph.get("tasks", [])]
            done = sum(t["status"] == "completed" for _, t in tasks)
            o.append(f"- todos: {done}/{len(tasks)} done")
            for ph, t in tasks:
                if t["status"] in OPEN:
                    why = f" (blocker: {clip(t['blocker'], 140)})" if t.get("blocker") else ""
                    o.append(f"  - [{t['status']}] {ph}: {clip(t['content'], 140)}{why}")
        if s["summary"]:
            o.append(f"- last compaction summary: {clip(s['summary'], n * 2)}")
        o.append(f"- ended with: {clip(s['reply'], n)}\n")
    if pr is None:
        o.append("\n## GitHub\n(gh unavailable or unauthenticated — PR state unknown)")
        return "\n".join(o)
    for k, rows in pr.items():
        o.append(f"\n## {k} ({len(rows or [])})")
        for p in rows or []:
            d = p.get("detail", {})
            extra = ""
            if d:
                asked = ",".join(r.get("login") or r.get("name") or "?" for r in d.get("reviewRequests") or []) or "none"
                done = ",".join(f"{r['author']['login']}:{r['state']}" for r in d.get("latestReviews") or []) or "none"
                extra = f" — branch `{d.get('headRefName')}`, review {d.get('reviewDecision') or 'NONE'} " \
                        f"(requested: {asked}; reviews: {done}), checks {checks(d.get('statusCheckRollup'))}, " \
                        f"mergeable {d.get('mergeable')}"
            o.append(f"- {p['repository']['nameWithOwner']}#{p['number']} {'[draft] ' if p.get('isDraft') else ''}"
                     f"{p['title']} (opened {p['createdAt'][:10]}, updated {p['updatedAt'][:10]}){extra} {p['url']}")
    return "\n".join(o)


def repos(only):
    """Every repo with linked worktrees that any omp session ever ran in (or, for a
    multi-repo root like folktale/, under). Idle worktrees live in repos you did NOT
    touch this week, so the window must not narrow this."""
    cwds = set()
    for f in SESSIONS.glob("*/*.jsonl"):
        with f.open(errors="replace") as fh:
            for line in (fh.readline(), fh.readline(), fh.readline()):
                if '"type":"session"' in line:
                    cwds.add(json.loads(line).get("cwd"))
                    break
    out = set()
    for c in (Path(c) for c in cwds if c and os.path.isdir(c)):
        r = subprocess.run(["git", "-C", str(c), "rev-parse", "--path-format=absolute", "--git-common-dir"],
                           capture_output=True, text=True)
        out.update([str(Path(r.stdout.strip()).parent)] if r.returncode == 0
                   else (str(p) for p in c.iterdir() if (p / ".git").exists()))
    linked = lambda r: subprocess.run(["git", "-C", r, "worktree", "list", "--porcelain"],
                                      capture_output=True, text=True).stdout.count("\nworktree ") > 0
    return sorted(r for r in out if (not only or only in r) and linked(r))


def worktrees(rs, days):
    if not rs:
        return "(no repos with linked worktrees)"
    run = lambda cmd: subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    out = []
    # Sequential: sweep fetches first, so the audit can skip its own fetch (parallel fetches race on ref locks).
    if SWEEP.exists():
        r = run([str(SWEEP), *rs])
        out.append(f"## Sweep dry run (sweeping-merged-worktrees, all ages)\n{(r.stdout or r.stderr).strip()}")
    if AUDIT.exists():
        # --days ≥ 21 so every worktree is listed with a last-active date (cleanup ages need 7–20d ones too).
        r = run([str(AUDIT), "--no-fetch", "--days", str(max(21, round(days))), *rs])
        out.append(f"## Audit (auditing-worktrees)\n{(r.stdout or r.stderr).strip()}")
    return "\n\n".join(out) or "(auditing-worktrees / sweeping-merged-worktrees skills missing)"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--days", type=float, default=7)
    ap.add_argument("--cwd", help="only sessions/repos whose path contains this substring")
    ap.add_argument("--no-gh", action="store_true")
    ap.add_argument("--no-worktrees", action="store_true", help="skip the worktree sweep dry run + audit")
    ap.add_argument("--width", type=int, default=300, help="chars kept per prompt/reply")
    a = ap.parse_args()
    since = datetime.now(timezone.utc) - timedelta(days=a.days)
    ss = sessions(since, a.cwd)
    with ThreadPoolExecutor(2) as ex:
        pr = None if a.no_gh else ex.submit(prs, f"{since:%Y-%m-%d}")
        wt = None if a.no_worktrees else ex.submit(lambda: worktrees(repos(a.cwd), a.days))
        print(render(ss, pr and pr.result(), since, a.width))
        if wt:
            print(f"\n# Worktrees (weekly housekeeping, read-only)\n\n{wt.result()}")


if __name__ == "__main__":
    sys.exit(main())
