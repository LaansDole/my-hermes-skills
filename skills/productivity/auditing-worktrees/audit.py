#!/usr/bin/env python3
"""Audit git worktrees into Ready to review / Shipped / Local only (recently
active) and Purgeable (idle >= --stale-days). Prints a markdown report.

Read-only apart from `git fetch --prune` and throwaway commit objects used for
squash detection (unreferenced; gc collects them). --self-test proves it.
"""

import argparse, json, os, subprocess, sys, time

BASES = ("dev", "main")
DAY = 86400


def git(cwd, *args, env=None):
    r = subprocess.run(("git",) + args, cwd=cwd, capture_output=True, text=True,
                       env={**os.environ, **(env or {})})
    return r.returncode, r.stdout.rstrip()  # rstrip only: porcelain status uses leading columns


def ok(cwd, *args):
    return git(cwd, *args)[0] == 0


def worktrees(repo):
    blocks = git(repo, "worktree", "list", "--porcelain")[1].split("\n\n")
    wts = [dict(l.partition(" ")[::2] for l in b.splitlines()) for b in blocks if b.strip()]
    return wts[0], [w for w in wts[1:] if os.path.isdir(w["worktree"])]  # missing dir = `git worktree prune`


def pull_requests(repo):
    """{branch: best PR} via gh. Merged beats open beats closed. {} if gh unavailable."""
    try:
        r = subprocess.run(["gh", "pr", "list", "--state", "all", "--limit", "1000", "--json",
                            "number,headRefName,baseRefName,state"],
                           cwd=repo, capture_output=True, text=True, timeout=60)
        prs = json.loads(r.stdout) if r.returncode == 0 else []
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        prs = []
    rank = {"MERGED": 0, "OPEN": 1, "CLOSED": 2}
    best = {}
    for p in sorted(prs, key=lambda p: (rank.get(p["state"], 3), -p["number"])):
        best.setdefault(p["headRefName"], p)
    return best


def last_active(path):
    """Newest of: worktree creation, this worktree's HEAD reflog, uncommitted file mtimes.
    NOT the index mtime - any `git status` (including this audit) rewrites it."""
    gitdir = git(path, "rev-parse", "--absolute-git-dir")[1]
    ts = [os.path.getmtime(os.path.join(gitdir, "commondir"))]
    sel = git(path, "reflog", "-1", "--date=unix", "--format=%gd")[1]  # HEAD@{1759000000}
    if "{" in sel:
        ts.append(int(sel[sel.index("{") + 1:-1]))
    dirty = [l[3:].split(" -> ")[-1] for l in git(path, "status", "--porcelain", "-uall")[1].splitlines()]
    ts += [os.path.getmtime(os.path.join(path, f)) for f in dirty if os.path.exists(os.path.join(path, f))]
    return max(ts), len(dirty)


def has_work(repo, br):
    """False for a branch only ever created off a baseline - it is an ancestor of
    dev but that is not 'shipped'. Created from anything else carries work."""
    lines = git(repo, "reflog", "show", "--format=%gs", f"refs/heads/{br}")[1].splitlines()
    bases = {"HEAD", *BASES, *(f"origin/{b}" for b in BASES)}
    return not lines or any(not l.startswith("branch: Created from ")
                            or l.removeprefix("branch: Created from ") not in bases for l in lines)


def shipped(repo, br, pr, bases):
    if pr and pr["state"] == "MERGED":
        return f"PR #{pr['number']} → {pr['baseRefName']}"
    if not has_work(repo, br):
        return None
    for b in bases:
        if ok(repo, "merge-base", "--is-ancestor", br, b):
            return f"in {b}"
    for b in bases:
        # per-commit patch-ids catch cherry-picks/rebases; the squashed virtual
        # commit catches squash-merges (one combined patch-id upstream)
        c = git(repo, "cherry", b, br)[1].splitlines()
        if c and all(l.startswith("-") for l in c):
            return f"patches in {b}"
        fork = git(repo, "merge-base", b, br)[1]
        if fork:
            virt = git(repo, "commit-tree", f"{br}^{{tree}}", "-p", fork, "-m", "audit", env={
                "GIT_AUTHOR_NAME": "audit", "GIT_AUTHOR_EMAIL": "audit@local",
                "GIT_COMMITTER_NAME": "audit", "GIT_COMMITTER_EMAIL": "audit@local"})[1]
            if virt and git(repo, "cherry", b, virt)[1].startswith("-"):
                return f"squashed into {b}"
    return None


def audit_repo(repo, fetch=True, now=None):
    now = now or time.time()
    repo = os.path.realpath(repo)  # worktree list reports resolved paths (/tmp -> /private/tmp)
    if fetch:
        git(repo, "fetch", "--prune", "--quiet", "origin")
    main, wts = worktrees(repo)
    bases = [f"origin/{b}" for b in BASES if ok(repo, "rev-parse", "-q", "--verify", f"refs/remotes/origin/{b}")]
    prs = pull_requests(repo)
    rows = []
    for w in wts:
        path, br = w["worktree"], w.get("branch", "").removeprefix("refs/heads/")
        active, dirty = last_active(path)
        pr = prs.get(br) if br else None
        on_origin = bool(br) and ok(repo, "rev-parse", "-q", "--verify", f"refs/remotes/origin/{br}")
        unpushed = int(git(repo, "rev-list", "--count", f"origin/{br}..{br}")[1]) if on_origin else None
        how = shipped(repo, br, pr, bases) if br else None
        status = "shipped" if how else "ready" if on_origin else "local"
        rows.append(dict(repo=os.path.basename(repo), path=os.path.relpath(path, repo), branch=br or "(detached)",
                         active=active, idle=int((now - active) // DAY), dirty=dirty, unpushed=unpushed,
                         pr=pr, status=status, how=how))
    return dict(repo=os.path.basename(repo), main_branch=main.get("branch", "").removeprefix("refs/heads/")
                or "(detached)", expected=BASES[0] if f"origin/{BASES[0]}" in bases else "main", rows=rows)


def pr_cell(pr):
    return f"#{pr['number']} → {pr['baseRefName']} ({pr['state'].lower()})" if pr else "—"


def table(head, rows):
    return "\n".join(["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
                     + ["| " + " | ".join(map(str, r)) + " |" for r in rows])


def report(audits, days, stale_days):
    rows = [r for a in audits for r in a["rows"]]
    recent = sorted((r for r in rows if r["idle"] < days), key=lambda r: (r["repo"], r["idle"]))
    ready = [r for r in recent if r["status"] == "ready"]
    ship = [r for r in recent if r["status"] == "shipped"]
    local = [r for r in recent if r["status"] == "local"]
    purge = sorted((r for r in rows if r["idle"] >= stale_days), key=lambda r: (r["repo"], -r["idle"]))
    middle = len(rows) - len(recent) - len(purge)
    d = lambda t: time.strftime("%m-%d", time.localtime(t))

    attn = []
    for a in audits:
        if a["main_branch"] != a["expected"]:
            attn.append(f"{a['repo']}: main checkout on `{a['main_branch']}`, baseline is `{a['expected']}`")
    for r in recent:
        tag = f"{r['repo']} `{r['branch']}`"
        if r["unpushed"]:
            attn.append(f"{tag}: {r['unpushed']} commit(s) not pushed")
        if r["status"] == "ready" and not r["pr"]:
            attn.append(f"{tag}: on origin, no PR")
        if r["status"] == "ready" and r["pr"] and r["pr"]["state"] == "CLOSED":
            attn.append(f"{tag}: PR #{r['pr']['number']} closed unmerged, work not in any baseline")
        if r["dirty"] and r["status"] == "shipped":
            attn.append(f"{tag}: shipped but {r['dirty']} uncommitted file(s) — salvage before removing")

    out = [f"**TL;DR** (active < {days}d): {len(ready)} ready to review, {len(ship)} shipped, "
           f"{len(local)} local-only. {len(purge)} purgeable (idle ≥ {stale_days}d, "
           f"{sum(1 for r in purge if not r['dirty'])} clean). {middle} idle {days}–{stale_days - 1}d not listed.", ""]
    out += [f"## Ready to review ({len(ready)})", table(
        ["Repo", "Branch", "PR", "Active", "Dirty", "Unpushed"],
        [(r["repo"], f"`{r['branch']}`", pr_cell(r["pr"]), d(r["active"]), r["dirty"] or "", r["unpushed"] or "")
         for r in ready]), ""]
    out += [f"## Shipped ({len(ship)})", table(
        ["Repo", "Branch", "Evidence", "Active", "Dirty"],
        [(r["repo"], f"`{r['branch']}`", r["how"], d(r["active"]), r["dirty"] or "") for r in ship]), ""]
    if local:
        out += [f"## Local only — never pushed ({len(local)})", table(
            ["Repo", "Branch", "Active", "Dirty"],
            [(r["repo"], f"`{r['branch']}`", d(r["active"]), r["dirty"] or "") for r in local]), ""]
    out += [f"## Purgeable — idle ≥ {stale_days}d ({len(purge)})", table(
        ["Repo", "Worktree", "Branch", "Idle", "Status", "PR", "Dirty", "Safe to remove"],
        [(r["repo"], r["path"], f"`{r['branch']}`", f"{r['idle']}d", r["status"], pr_cell(r["pr"]),
          r["dirty"] or "", "no — uncommitted" if r["dirty"] else "yes") for r in purge]), ""]
    if attn:
        out += ["## Attention", *(f"- {x}" for x in attn), ""]
    return "\n".join(out)


def default_repos():
    if ok(".", "rev-parse", "--git-dir"):
        return ["."]
    return sorted(e.path for e in os.scandir(".") if e.is_dir() and os.path.exists(os.path.join(e.path, ".git")))


# --------------------------------------------------------------------------- test

FIXTURE = r'''
set -e
ROOT="$1"; rm -rf "$ROOT"; mkdir -p "$ROOT"; cd "$ROOT"
export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@t
git init -q --bare remote.git
git init -q -b dev repo && cd repo
git remote add origin "$ROOT/remote.git"
printf '.worktrees/\n' > .gitignore; printf 'base\n' > base.txt
git add -A && git commit -qm base && git push -q -u origin dev && git push -q origin dev:main
wt () { git worktree add -q -b "$1" ".worktrees/$1" dev; }
commit () { (cd ".worktrees/$1" && for i in 1 2; do printf '%s %s\n' "$1" "$i" >> "$1.txt"; git add -A; git commit -qm "$1 $i"; done); }
for b in merged squashed picked ready local empty; do wt $b; done
for b in merged squashed picked ready local; do commit $b; done
for b in merged squashed picked ready; do git -C ".worktrees/$b" push -q -u origin "$b"; done
git merge -q --no-ff -m "merge merged" merged
git merge -q --squash squashed && git commit -qm "squash squashed"
git cherry-pick $(git rev-list --reverse dev..picked) >/dev/null
git push -q origin dev
git push -q origin --delete squashed
printf 'wip\n' >> .worktrees/ready/ready.txt
# stale: all activity 30 days ago
OLD="$(date -v-30d +%s 2>/dev/null || date -d '30 days ago' +%s) +0000"
GIT_COMMITTER_DATE="$OLD" GIT_AUTHOR_DATE="$OLD" git worktree add -q -b stale .worktrees/stale dev
(cd .worktrees/stale && printf 's\n' > s.txt && git add -A && GIT_COMMITTER_DATE="$OLD" GIT_AUTHOR_DATE="$OLD" git commit -qm stale && GIT_COMMITTER_DATE="$OLD" git push -q -u origin stale)
touch -t "$(date -v-30d +%Y%m%d%H%M 2>/dev/null || date -d '30 days ago' +%Y%m%d%H%M)" "$(git -C .worktrees/stale rev-parse --absolute-git-dir)/commondir"
git fetch -q -p origin
'''


def self_test():
    root = "/tmp/audit-worktrees-selftest"
    script = root + ".sh"
    open(script, "w").write(FIXTURE)
    r = subprocess.run(["bash", script, root], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    repo = os.path.join(root, "repo")
    git(os.path.join(repo, ".worktrees/stale"), "status")  # rewrite the index: must NOT count as activity

    a = audit_repo(repo, fetch=False)
    got = {r["branch"]: (r["status"], r["how"]) for r in a["rows"]}
    want = {"merged": ("shipped", "in origin/dev"), "squashed": ("shipped", "squashed into origin/dev"),
            "picked": ("shipped", "patches in origin/dev"), "ready": ("ready", None),
            "local": ("local", None), "empty": ("local", None), "stale": ("ready", None)}
    assert got == want, got
    idle = {r["branch"]: r["idle"] for r in a["rows"]}
    assert idle["stale"] >= 29 and all(v == 0 for k, v in idle.items() if k != "stale"), idle
    assert next(r["dirty"] for r in a["rows"] if r["branch"] == "ready") == 1

    text = report([a], days=7, stale_days=21)
    assert "3 shipped" in text and "2 ready to review" not in text and "1 ready to review" in text, text
    assert "1 purgeable" in text and "`stale`" in text.split("## Purgeable")[1], text
    assert "on origin, no PR" in text, text
    print(text + "\nself-test OK")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("repos", nargs="*", help="repos to audit (default: cwd, or its git subdirectories)")
    ap.add_argument("--days", type=int, default=7, help="recent window for ready/shipped/local (default 7)")
    ap.add_argument("--stale-days", type=int, default=21, help="idle threshold for purgeable (default 21)")
    ap.add_argument("--no-fetch", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        self_test()
        sys.exit()
    print(report([audit_repo(r, not a.no_fetch) for r in a.repos or default_repos()], a.days, a.stale_days))
