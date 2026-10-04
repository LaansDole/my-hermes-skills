#!/usr/bin/env python3
"""Survey, salvage and remove git worktrees whose branches are merged or gone.

Dry run by default. --apply to act. --self-test to prove the classifier.

Never deletes a branch: `git worktree remove` leaves the ref alone, so commits
survive. The only unrecoverable loss is uncommitted work, which is why
non-ignored untracked files are copied into the main checkout before removal
and tracked modifications block removal outright.
"""

import argparse, os, shutil, subprocess, sys

KEEP, MERGED, GONE, PRUNABLE, BLOCKED = "keep", "merged", "gone", "prunable", "blocked"


def sh(cwd, *args):
    r = subprocess.run(("git",) + args, cwd=cwd, capture_output=True, text=True)
    # rstrip only: `status --porcelain` encodes state in leading columns (" M path")
    return r.returncode, (r.stdout + r.stderr).rstrip()


def worktrees(repo):
    """[(path, branch, prunable)] for linked worktrees only (main checkout excluded)."""
    out, cur, found = [], {}, sh(repo, "worktree", "list", "--porcelain")[1]
    for line in found.splitlines() + [""]:
        if not line.strip():
            if cur.get("worktree"):
                out.append(cur)
            cur = {}
            continue
        k, _, v = line.partition(" ")
        cur[k] = v or True
    main = out[0]["worktree"] if out else repo
    return main, [(w["worktree"], w.get("branch", "").replace("refs/heads/", ""), "prunable" in w)
                  for w in out[1:]]


def baseline(repo):
    """origin/<branch the main checkout sits on> - matches the per-repo baseline
    convention (storybook/nextportal=dev, e2e=main) with no config."""
    b = sh(repo, "rev-parse", "--abbrev-ref", "HEAD")[1]
    if sh(repo, "rev-parse", "--verify", "-q", f"origin/{b}")[0] == 0:
        return f"origin/{b}"
    head = sh(repo, "symbolic-ref", "--short", "-q", "refs/remotes/origin/HEAD")[1]
    return head or f"origin/{b}"


def classify(repo, base, path, branch, prunable):
    """Compare against origin/<base>, never local HEAD: a stale local baseline
    silently reports merged branches as unmerged."""
    if prunable:
        return PRUNABLE, "registration points at a missing directory", [], []
    ahead = sh(repo, "rev-list", "--count", f"{base}..{branch}")[1] if branch else "?"
    merged = branch and sh(repo, "merge-base", "--is-ancestor", branch, base)[0] == 0
    gone = "[gone]" in sh(repo, "for-each-ref", "--format=%(upstream:track)",
                          f"refs/heads/{branch}")[1] if branch else False
    if not (merged or gone):
        return KEEP, f"{ahead} commits not in {base}", [], []
    porcelain = sh(path, "status", "--porcelain", "-uall")[1].splitlines()
    tracked = [l[3:] for l in porcelain if not l.startswith("??")]
    untracked = [l[3:] for l in porcelain if l.startswith("??")]
    if tracked:
        return BLOCKED, f"uncommitted edits to tracked files: {', '.join(tracked)}", tracked, untracked
    why = f"merged into {base}" if merged else f"upstream gone (squash-merge or deleted PR branch); {ahead} commits not in {base}"
    return (MERGED if merged else GONE), why, tracked, untracked


def salvage(main, path, files, apply):
    """Copy non-ignored untracked files into the main checkout at the same
    relative path. Ignored files (build output) are regenerable and skipped by
    `status` already."""
    saved = []
    for rel in files:
        src, dst = os.path.join(path, rel), os.path.join(main, rel)
        if os.path.isdir(src):
            continue
        if os.path.exists(dst) and open(dst, "rb").read() != open(src, "rb").read():
            dst += ".salvaged"
        if os.path.exists(dst):
            saved.append(f"{rel} (already present)")
            continue
        if apply:
            os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
            shutil.copy2(src, dst)
        saved.append(os.path.relpath(dst, main))
    return saved


def at_risk(repo, base):
    """[gone] branches still holding patches absent from base. A `branch -D` sweep
    over every [gone] branch orphans these: gone upstream means merged PR *or*
    abandoned branch, and only the latter's commits live nowhere else.
    `git cherry` compares patch-ids, so squash-merged branches correctly drop out."""
    risky = []
    for line in sh(repo, "for-each-ref", "--format=%(refname:short)\t%(upstream:track)",
                   "refs/heads")[1].splitlines():
        branch, _, track = line.partition("\t")
        if "[gone]" not in track:
            continue
        unique = [l for l in sh(repo, "cherry", base, branch)[1].splitlines() if l.startswith("+")]
        if unique:
            risky.append((branch, len(unique)))
    return risky


def sweep(repo, apply=False, out=sys.stdout):
    repo = os.path.abspath(repo)
    sh(repo, "fetch", "-p", "--quiet")
    main, wts = worktrees(repo)
    base = baseline(repo)
    print(f"\n=== {repo}  (baseline {base})", file=out)
    acted = []
    for path, branch, prunable in wts:
        verdict, why, _tracked, untracked = classify(repo, base, path, branch, prunable)
        saved = salvage(main, path, untracked, apply) if verdict in (MERGED, GONE) else []
        line = f"  [{verdict:8}] {os.path.relpath(path, main):45} {branch:22} {why}"
        if saved:
            line += f"\n{'':14}salvaged -> {', '.join(saved)}"
        print(line, file=out)
        if verdict in (MERGED, GONE, PRUNABLE):
            acted.append((path, verdict))
    for branch, n in at_risk(repo, base):
        print(f"  [AT RISK ] {'':45} {branch:22} upstream gone but {n} patch(es) not in {base};"
              f" `git branch -D` would orphan them", file=out)
    if not apply:
        print(f"  -- dry run; {len(acted)} to remove. Re-run with --apply", file=out)
        return acted
    print("  " + (sh(repo, "worktree", "prune", "-v")[1] or "prune: nothing"), file=out)
    for path, verdict in acted:
        if verdict is PRUNABLE:
            continue
        rc, msg = sh(repo, "worktree", "remove", "--force", path)
        print(f"  removed {os.path.relpath(path, main)}" if rc == 0 else f"  FAILED {path}: {msg}", file=out)
    for parent in {os.path.dirname(p) for p, _ in acted}:
        if os.path.isdir(parent) and not os.listdir(parent) and os.path.basename(parent) != ".worktrees":
            os.rmdir(parent)
    return acted


# --------------------------------------------------------------------------- test

FIXTURE = r'''
set -e
ROOT="$1"; rm -rf "$ROOT"; mkdir -p "$ROOT"; cd "$ROOT"
export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@t
git init -q --bare remote.git
git init -q -b dev repo && cd repo
git remote add origin ../remote.git
printf '.worktrees/\nbuild/\n' > .gitignore; printf 'base\n' > base.txt
git add -A && git commit -qm base && git push -q -u origin dev
feature () {
  git switch -qc "$1" dev; printf '%s\n' "$1" > "$2"; git add -A; git commit -qm "work on $1"
  git push -q -u origin "$1"; git switch -q dev
}
feature merged-gone a.txt
feature merged-alive b.txt
feature merged-untracked c.txt
feature squashed-gone d.txt
feature unmerged-work e.txt
feature unmerged-dirty f.txt
feature stale-reg g.txt
feature merged-trackedmod h.txt
for b in merged-gone merged-alive merged-untracked merged-trackedmod; do git merge -q --no-ff -m "merge $b" "$b"; done
git merge -q --squash squashed-gone && git commit -qm "squash squashed-gone"
git switch -q unmerged-work && printf 'more\n' >> e.txt && git commit -qam more && git push -q && git switch -q dev
git push -q origin dev
for b in merged-gone merged-untracked squashed-gone stale-reg merged-trackedmod; do git push -q origin --delete "$b"; done
for b in merged-gone merged-alive merged-untracked squashed-gone unmerged-work unmerged-dirty stale-reg merged-trackedmod; do
  git worktree add -q ".worktrees/$b" "$b"
done
printf 'scratch notes worth keeping\n' > .worktrees/merged-untracked/notes.txt
mkdir -p .worktrees/merged-untracked/build && printf 'junk\n' > .worktrees/merged-untracked/build/out.o
printf 'local edit\n' >> .worktrees/unmerged-dirty/f.txt
printf 'uncommitted edit\n' >> .worktrees/merged-trackedmod/h.txt
rm -rf .worktrees/stale-reg
git reset -q --hard HEAD~4
git fetch -q -p origin
'''


def self_test():
    root = "/tmp/sweep-selftest"
    script = os.path.join(root + ".sh")
    os.makedirs(os.path.dirname(script) or "/tmp", exist_ok=True)
    open(script, "w").write(FIXTURE)
    assert subprocess.run(["bash", script, root], capture_output=True, text=True).returncode == 0
    repo = os.path.join(root, "remote.git", "..", "repo")
    repo = os.path.normpath(os.path.join(root, "repo"))

    stale = sh(repo, "branch", "--merged")[1].split()
    assert "merged-alive" not in stale, "fixture must have a stale local baseline"

    acted = {os.path.basename(p): v for p, v in sweep(repo, apply=False)}
    assert acted == {"merged-gone": MERGED, "merged-alive": MERGED, "merged-untracked": MERGED,
                     "squashed-gone": GONE, "stale-reg": PRUNABLE}, acted
    assert os.path.exists(f"{repo}/.worktrees/merged-untracked/notes.txt"), "dry run must not move files"
    # a data-loss warning naming the wrong file is worse than no warning
    verdict, why, _, _ = classify(repo, baseline(repo), f"{repo}/.worktrees/merged-trackedmod",
                                  "merged-trackedmod", False)
    assert (verdict, why) == (BLOCKED, "uncommitted edits to tracked files: h.txt"), (verdict, why)

    sweep(repo, apply=True)
    left = {b for _, b, _ in worktrees(repo)[1]}
    assert left == {"unmerged-work", "unmerged-dirty", "merged-trackedmod"}, left
    assert open(f"{repo}/notes.txt").read() == "scratch notes worth keeping\n", "untracked file lost"
    assert not os.path.exists(f"{repo}/build/out.o"), "ignored junk must not be salvaged"
    assert "local edit" in open(f"{repo}/.worktrees/unmerged-dirty/f.txt").read()
    assert sh(repo, "rev-parse", "--verify", "-q", "stale-reg")[0] == 0, "branch refs must survive"
    assert not sh(repo, "worktree", "list")[1].count("prunable")
    # stale-reg is gone upstream AND abandoned: a blanket `branch -D` over [gone]
    # branches orphans its only commit. squash-merged branches must NOT be flagged.
    assert [b for b, _ in at_risk(repo, baseline(repo))] == ["stale-reg"], at_risk(repo, baseline(repo))
    print("\nself-test OK")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("repos", nargs="*", default=["."])
    ap.add_argument("--apply", action="store_true", help="actually salvage + remove (default: dry run)")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        self_test()
    else:
        for r in a.repos or ["."]:
            sweep(r, a.apply)
