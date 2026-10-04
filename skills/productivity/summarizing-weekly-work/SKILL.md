---
name: summarizing-weekly-work
description: Use when asked what was done, left pending, in progress, blocked, or waiting for review over the past week or N days; for a weekly recap, wrap-up, or standup (including the weekly worktree cleanup); "where did I leave off", "what should I continue"; or instead of clicking through old sessions with /resume.
version: 1.0.0
metadata:
  hermes:
    tags: [weekly, recap, standup, resume, github, worktrees, omp, productivity]
---

# Summarizing Weekly Work

## Overview

Sessions record what was asked and attempted; GitHub and git record what actually happened. The report joins both per work item and tells the user, for each item, whose move it is and how to jump back in.

## Collect

```bash
~/.agents/skills/summarizing-weekly-work/week.py [--days 7] [--cwd substring] [--no-worktrees] [--no-gh]
```

One read-only run (~45s) prints:
- **Sessions** (every top-level omp session active in the window, grouped by cwd): title, first/last asks, open todos, last compaction summary, final reply, and a `resume:` command.
- **GitHub**: your open PRs (branch, review decision, requested reviewers, latest reviews, checks, mergeable, opened/updated dates), your PRs merged in the window, PRs requesting your review, PRs you reviewed.
- **Worktrees**, across every repo with linked worktrees that any omp session ever ran in (not only this week's, since idle worktrees sit in repos you didn't touch): a `sweeping-merged-worktrees` dry run (merged / gone / prunable / blocked / keep, `[AT RISK]` branches) and an `auditing-worktrees` audit with a 21-day window, so every worktree has a last-active date.

"Last 3 days" → `--days 3`. "Just folktale" → `--cwd folktale` (filters sessions and repos). Output is large; page it rather than skipping sessions.

## Classify

One work item = one branch/PR/topic; several sessions and both repos of a backend+frontend pair can be one item. Join on PR number, branch name, or worktree folder in the cwd.

Later and harder evidence wins: **GitHub/git state > open todos > compaction summary > final reply.** A session saying "not started" is overridden by a merged PR.

|Evidence|Bucket|
|---|---|
|PR merged in window (audit Shipped rows count only if Active is in the window)|Done|
|Open PR: CHANGES_REQUESTED, checks failing, CONFLICTING, or APPROVED but unmerged|Your move|
|Open PR, REVIEW_REQUIRED, no reviewer requested|Your move (request one)|
|Open todos (`in_progress`/`pending`) and no merged PR|Your move|
|Local-only branch, unpushed commits, or audit Attention row, active in window|Your move|
|Newest session on the item ends asking the user a question or offering a choice|Your move (answer it)|
|Open PR, REVIEW_REQUIRED, reviewer requested|Waiting on others (name the reviewer)|
|`blocked` todo, or waiting on a named person (PO, reviewer, secret, access)|Waiting on others|
|PRs under "Review requested from you"|Your review queue|
|Q&A / explanation sessions, nothing left open|Done (one line, or omit)|
|Open PR not updated in window; Attention rows last active before the window|Parked|

## Verify before filing

Session text is a snapshot. When a "Your move" row rests only on session text ("not pushed", "ticket still owed", "will enable X"), or a session's final reply stops mid-work, check it with one `git -C <worktree> status -sb` / `git ls-remote` / `gh` call. Do the same for audit Attention rows: a closed-unmerged PR may have been cherry-picked elsewhere, and dirty files may be untracked notes. Read a session's `log:` only when neither check decides it.

## Report

Write it in this order:

1. **Header**: date range, one-line TL;DR with counts per bucket.
2. **Next up**: the single most urgent "Your move" item, one sentence.
3. **Your move**: table `Item | State (evidence) | Next step | Resume`. Resume = the `cd … && omp -r <id>` of the newest session on that item, or `—` when no session in the window touched it.
4. **Waiting on others**: table `Item | Waiting on | Since | Nudge?`.
5. **Your review queue**: one line per PR with link and days since opened.
6. **Done this week**: grouped by project, one line per item with PR links.
7. **Parked**: one line per stale open PR or idle unmerged branch.
8. **Worktree cleanup**: see below.

Every PR is a link. Mark anything inferred rather than observed as `(unverified)`.

## Worktree cleanup

The weekly report ends with cleanup, using the user's removal rule: **merged into the baseline (sweep `merged`/`gone`) and last active ≥ 21 days ago, or ≥ 14 days for `hotfix/*` branches.** Take last-active from the audit (`Active` date or `Idle` days); eligible date = last active + 21 (or 14) days. The sweep verdict decides "merged"; a row the audit calls shipped but the sweep keeps goes under Needs a look.

|Sub-list|Rows|
|---|---|
|Remove now|Sweep `merged`/`gone` meeting the age rule, and every `prunable` registration. One `git -C <repo> worktree remove <path>` per row; `git -C <repo> worktree prune` for prunable|
|Not yet|Merged but too recent: count plus the earliest date one becomes eligible|
|Needs a look|Sweep `blocked` (merged, tracked edits; name the files), merged rows with a `salvaged ->` line (untracked files make `worktree remove` refuse), audit rows with uncommitted files, sweep/audit disagreements, main checkouts off their baseline branch|
|Idle, unmerged|Audit Purgeable rows with status ready/local: list them; the user decides|
|At-risk branches|Sweep `[AT RISK]` lines verbatim: never `git branch -D` these|

Commands are proposals, even when the user asked to "clean up": show the list, ask once, and on yes run only the Remove-now rows. `git worktree remove` refuses dirty worktrees, which is the safety you want, so never add `--force`. Don't use `sweep.py --apply` to carry out this list: it removes every merged worktree in the repo, whatever its age. Salvage and removal details: `sweeping-merged-worktrees`.

## Common Mistakes

|Mistake|Fix|
|---|---|
|One row per session|One row per work item; list the newest session's resume command|
|Trusting a session's last reply over GitHub|Status comes from PR/audit state first|
|Hand-parsing session JSONL with jq|Run `week.py`; it already extracts todos and summaries|
|Listing years-old open PRs in the main tables|They go in Parked|
|Pasting the raw audit tables|Fold audit rows into the work items|
|"Shipped" from the 21-day audit listed under Done this week|Done needs a merge or activity inside the window|
|Running `sweep.py --apply` for the cleanup list|It ignores the age rule; remove row by row|
