---
name: auditing-worktrees
description: Use when asked for the status of worktrees, which worktree branches are ready to review, pushed, merged or shipped, which worktrees are stale, idle or purgeable, or for a periodic worktree audit across one or several repos
version: 1.0.0
metadata:
  hermes:
    tags: [git, worktrees, audit, review, productivity]
---

# Auditing Worktrees

## Overview

Read-only report that sorts every linked worktree into **Ready to review**, **Shipped**, **Local only** (recently active) and **Purgeable** (idle). The script does the classification. You don't redo it by hand. The only state it changes is `git fetch --prune`, which updates remote-tracking refs. That is expected, so leave the fetch on unless the user forbids network or ref updates (`--no-fetch`).

## Usage

```bash
~/.agents/skills/auditing-worktrees/audit.py [repo...] [--days 7] [--stale-days 21] [--no-fetch]
```

No repos → cwd if it is a git repo, else every git repo directly under cwd (e.g. `~/Projects/folktale` → storybook, nextportal, e2e, portal). User says "last N days" → `--days N`. "idle N weeks" → `--stale-days 7N`.

## Buckets

|Bucket|Rule|
|---|---|
|Shipped|Merged PR (gh) **or** ancestor of `origin/dev`/`origin/main` **or** every patch already upstream (cherry-pick/rebase) **or** squash-equivalent upstream|
|Ready to review|Not shipped, branch exists on origin|
|Local only|Not shipped, never pushed (incl. detached HEAD, branches with no commits)|
|Purgeable|Last active ≥ `--stale-days`, any of the above. "Safe to remove" = no uncommitted files|

Ready/Shipped/Local only list worktrees active within `--days`. Worktrees idle between the two thresholds are counted in the TL;DR but not listed.

**Last active** = newest of worktree creation, that worktree's HEAD reflog, and mtimes of uncommitted files.

## Report Shape

Pass the script's output through, in this order:
1. The script's **TL;DR** line, rewritten as 2–3 plain-English sentences.
2. **One next step**, the most urgent item from the Attention list (unpushed commits > closed-unmerged PR > shipped-but-dirty > no PR).
3. The tables and the Attention list, unchanged.

## Purging

The audit only reports; it removes nothing. Remove worktrees only after the user asks:
- Shipped rows → `~/.agents/skills/sweeping-merged-worktrees/sweep.py <repo> --apply` (salvages untracked files first).
- Idle, unshipped rows that are safe to remove → `git -C <repo> worktree remove <path>`. The branch ref survives, so no commits are lost.
- Rows with uncommitted files → show the user what is dirty (`git -C <path> status`). Never use `--force`.

## Footguns (why the script exists)

|Wrong shortcut|Why it's wrong|
|---|---|
|Index or directory mtime as "last active"|`git status` rewrites the index, so any audit makes every worktree look active today|
|Ancestor of dev ⇒ shipped|A branch created off dev with no commits is an ancestor. Check that it has work first|
|Only `merge-base --is-ancestor`|Misses cherry-picked and squash-merged branches|
|Deleted upstream ⇒ not ready/shipped|Merged PRs often delete the branch. PR state and patch-ids still prove it shipped|
|`git cherry` alone for squash|A squash is one combined patch-id, so per-commit `cherry` shows `+`. The script compares a squashed virtual commit|

Without `gh`, PR columns show `—`, and Shipped falls back to git evidence only.

## Verifying Changes

```bash
audit.py --self-test
```

Builds a fixture covering merged, squash-merged, cherry-picked, pushed-unmerged, never-pushed, empty-branch and 30-day-stale worktrees (the stale one gets an index rewrite), then checks the buckets and the report.
