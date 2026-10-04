---
name: sweeping-merged-worktrees
description: Use when a repo has accumulated worktrees under .worktrees/ from finished PRs, when asked to clean up or prune worktrees whose branches were merged or deleted on the remote, or when `git worktree list` shows stale/prunable entries
version: 1.0.0
metadata:
  hermes:
    tags: [git, worktrees, cleanup, prune, productivity]
---

# Sweeping Merged Worktrees

## Overview

Survey, salvage, and remove worktrees whose branches are merged or gone from the remote.

**Core principle:** `git worktree remove` does not touch the branch ref, so committed work always survives. The only unrecoverable loss is **uncommitted** work. Salvage it, then remove — do not leave a merged worktree standing just because it holds a stray untracked file.

## Usage

```bash
~/.agents/skills/sweeping-merged-worktrees/sweep.py <repo>...          # dry run, prints verdicts
~/.agents/skills/sweeping-merged-worktrees/sweep.py <repo>... --apply  # salvage + prune + remove
```

Dry run first. Read the table, then `--apply`. Multi-repo in one shot: `sweep.py storybook nextportal e2e`.

Baseline is `origin/<branch the main checkout sits on>` — no config needed.

## Verdicts

|Verdict|Meaning|Action taken by `--apply`|
|---|---|---|
|`merged`|Ancestor of the baseline|Salvage untracked, remove worktree|
|`gone`|Upstream deleted (squash-merged PR, or abandoned)|Salvage untracked, remove worktree|
|`prunable`|Registration points at a missing directory|`git worktree prune`|
|`blocked`|Merged/gone **but** has uncommitted edits to tracked files|Nothing — reported for you to review|
|`keep`|Neither merged nor gone|Nothing|

Non-ignored untracked files are copied into the main checkout at the same relative path before removal (`.salvaged` suffix on content conflict). Ignored files — build output, `node_modules` — are regenerable and left to die.

## Order Matters

Remove worktrees **before** deleting branches. `git branch -d/-D` refuses a branch that is checked out in any worktree, so a branch-first cleanup silently skips exactly the branches you meant to remove.

Branch deletion is a separate step with its own precondition. A `git cleanup`-style alias (`fetch -p`, `branch -D` every `[gone]`, `branch -d` every merged) runs unconditionally, so clear both footguns below before invoking one. `sweep.py` prints an `[AT RISK]` line for every `[gone]` branch whose patches are absent from the baseline — if any appear, that alias will orphan those commits.

## Footguns

**Stale local baseline.** `git branch --merged` compares against the current local HEAD. If local `dev` is behind `origin/dev`, merged branches report as unmerged and cleanup quietly under-deletes. Always compare against `origin/<base>` — the tool does. Fast-forward the baseline before running a `--merged`-based alias.

**Aliases that delete merged branches eat `main`.** `git branch --merged | xargs git branch -d` deletes *any* merged branch, including a local `main` that is an ancestor of `dev`. Check before running one:

```bash
git merge-base --is-ancestor main dev && echo "WARNING: alias would delete local main"
```

**`[gone]` is not proof of merge.** A deleted upstream usually means a squash-merged PR, but it also covers abandoned branches whose commits exist nowhere else. Removing the *worktree* is always safe (the ref survives); `branch -D` is what destroys work. Verified on the fixture: a blanket `-D` over `[gone]` branches left an abandoned commit reachable from nothing. `git cherry <base> <branch>` is the check — `-` means the patch is already upstream (safe, catches squash-merges), `+` means it only exists here.

## Verifying Changes

```bash
sweep.py --self-test
```

Builds a throwaway fixture covering every case — real merge, squash-merge, gone upstream, stale registration, untracked file, tracked modification, stale local baseline — and asserts the end state.
