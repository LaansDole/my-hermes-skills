# summarizing-weekly-work

Weekly recap for oh-my-pi users: what you did, what's pending or blocked, what's waiting for review, and which git worktrees are ready to remove. Use it instead of clicking through old sessions with `/resume`.

## What it does

`week.py` is a read-only evidence collector. It reads `~/.omp/agent/sessions`, GitHub (`gh search prs`), and your worktrees. The agent then sorts the evidence into: next up, your move (with an `omp -r <id>` resume command), waiting on others, review queue, done, parked, and a worktree cleanup list. Cleanup commands are only proposals: nothing is removed until you say yes.

## Setup

1. Requires `python3`, `git`, and an authenticated `gh` (or pass `--no-gh`).
2. Symlink into your skills dir: `ln -s <repo>/skills/productivity/summarizing-weekly-work ~/.agents/skills/summarizing-weekly-work`
3. Optional, for the worktree section: symlink `skills/productivity/auditing-worktrees` and `skills/productivity/sweeping-merged-worktrees` from this repo into the same skills dir. Without them the report skips cleanup.

## Usage

```bash
week.py [--days 7] [--cwd substring] [--no-worktrees] [--no-gh]
```
