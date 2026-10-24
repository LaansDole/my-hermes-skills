---
name: multi-repo-pr-review-merge-round
description: "Use when burning a metered omp model budget on PR/worktree review across repos. Coordinator queues omp -p review lanes, verifies, merges, re-spawns each usage window until month end."
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [omp, oh-my-pi, pr-review, merge, worktrees, audit, usage-budget, coordinator]
    related_skills: [omp-implementation-dispatch, github-code-review, auditing-worktrees, oh-my-pi]
---

# Multi-repo PR review + merge round (budget burner)

## Goal

The user has a metered omp provider plan (e.g. Command Code, `commandcode/<model>`)
with usage that expires at the end of the month. Spend it all on useful work:
reviewing, fixing and merging the user's open PRs, then auditing and finishing
leftover worktrees. Hermes is the COORDINATOR: it inventories, writes briefs,
launches `omp -p` lanes, verifies results, merges, and keeps spawning new tasks
every usage window until the month ends or the work queue is empty. Hermes does
not write the review fixes itself.

Trigger phrases: "use up my <provider> usage", "have <model> review all PRs in
<dirs> and merge them", "pick up leftover worktrees", "keep the omp agents busy
until the end of the month".

## Loop (one round per usage window)

1. Inventory (scripts/inventory.sh <repo>...). Build the queue.
2. Smoke-test the exact model id (step 2 below). Stop if it is rejected.
3. Write or refresh briefs into `~/.hermes/cache/merge-round/<tag>.md`.
4. Launch 2 lanes (scripts/lane.sh) plus a watchdog (scripts/watchdog.sh).
5. On every lane notification: read the transcript's last assistant texts,
   verify pushed work yourself, then merge.
6. On `USAGE-EXHAUSTED`: kill every lane, the omp children and the watchdog,
   then prove nothing is left running. Report state plus the reset time.
7. After the reset (the user says "continue", or a scheduled restart fires): write
   CONTINUATION briefs from the on-disk state and go to step 4. When the PR queue
   is empty, refill it from the "Refill" list below.

## 1. Inventory

- For a FORK, `gh pr list` with no `--repo` lists the UPSTREAM repo's PRs
  (research-harness showed can1357/oh-my-pi's 40+ PRs). Always pass the
  origin explicitly: `--repo $(git remote get-url origin | sed -E 's|.*github\.com[:/]||; s|\.git$||')`.
- Directories like `medvoice-all/` are not repos: iterate their children.
- EXCLUDE third-party clones (origin owner is neither the user nor the user's
  org; e.g. `semif` -> TheoLeeCJ/SemIf-OpenJev). Their PRs are not the user's
  to merge.
- Record the base of each PR. Stacked PRs (B based on A) are merged in order:
  merge A, `gh pr edit B --base main`, then merge B.
- `git worktree list` per repo. A leftover worktree is a candidate when it is
  ahead of its upstream or dirty. Check what it feeds. A branch that backs an
  UPSTREAM PR on someone else's repo (`gh pr list --repo <upstream> --author
  <user>`) gets review, fixes and tests LOCALLY ONLY, with no push. The user
  pushes it.
- `mergeable: CONFLICTING` means the brief must include "merge origin/main
  (merge, not rebase) and resolve".

## 2. Model smoke test

`omp -p --model <provider>/<id> "Reply with exactly: PONG"` from `$TMPDIR`.
- `403 MODEL_NOT_IN_PLAN` (gpt-6.1-sol on the user's Command Code plan): pick the
  closest model that answers. `commandcode/gpt-6-sol:xhigh` works. Tell the user
  about the substitution in the first report.
- `omp models | awk '/^[a-z-]+ \([0-9]+\)/{p=$1} /<id>/{print p, $0}'` shows
  which provider owns an id and its effort ladder (`-` means no effort suffix).
- macOS has no `timeout(1)`. Run the smoke test bare, with the tool's own timeout.

## 3. Worktrees and briefs

- Give each agent its OWN worktree. Never point an agent at the user's checkout:
  it may carry untracked benchmark files or a modified Podfile.lock.
- The PR branch may already be checked out in the user's checkout, and git
  refuses a second checkout. Use `git worktree add --detach .worktrees/review
  <sha>` and tell the agent to push with `git push origin HEAD:<branch>`.
- A narrowed fetch refspec can leave `origin/<branch>` missing even though the
  branch exists on the remote (`git ls-remote` shows it). Run `git fetch origin
  <branch>...` explicitly before creating the worktree.
- If `.worktrees/` is not gitignored, append it to `.git/info/exclude`. That file
  is local and never committed.
- Brief template: `templates/review-brief.md`. Required elements: working dir,
  push authorization scope, PR list with bases, ordered tasks (install -> merge
  base if conflicting -> review checklist -> fix -> gates with counts and
  pre-existing failures proved on a temp worktree -> push -> report file at
  `~/.hermes/cache/merge-round/<tag>-REPORT.md`), plus the HARD RULES block (no
  rebase, force-push, stash or branch deletion; no GitHub comments or merges;
  commits ARE requested; never weaken tests).
- Medical, mobile and other repo-specific notes go into the brief: `fvm flutter`
  only, no PHI in logs, cross-check the backend JSON field names against the
  sibling repo (read-only).

## 4. Lanes and watchdog

- `scripts/lane.sh <lane> <round_dir> <model> <tag>:<cwd> ...` runs its jobs
  serially and prints `JOB-DONE`, `LANE-DONE` or `USAGE-EXHAUSTED <lane> at
  <tag>: resets at <iso>`. Launch each lane with `terminal(background=true,
  notify=["USAGE-EXHAUSTED","JOB-DONE","LANE-DONE"])`.
- Run 2 lanes, each pairing repos that do not collide (lane A: backend then
  research; lane B: mobile then research worktree B). Two agents in different
  worktrees of the same repo is fine. Two in the same worktree is not.
- Budget reality: 4 parallel xhigh agents exhausted a Command Code 5-hour window
  in about 12 minutes. 2 lanes lasted about 12 minutes too. Order every lane by
  priority (merge-ready PRs first, then big PRs, then local-only worktrees). The
  window usually dies inside the first job.
- `scripts/watchdog.sh <round_dir> <tag>:<cwd> ...` is a zsh script because macOS
  bash 3 has no associative arrays. It samples every 180s and prints `STALLED`,
  `QUOTA-SUSPECT` or `EXITED-ALL`. Jobs with no log yet count as queued, not
  stalled. Kill the watchdog yourself when a lane exits early; queued jobs then
  never start.

## Context caps: 27% global, 40% for reviewers

- Global: `compaction.thresholdPercent: 27` in `~/.omp/agent/config.yml`
  (`compaction.midTurnEnabled: true`, so it also fires inside a long `-p` run).
- Reviewer task agents: `task.agentCompactionThresholdOverrides =
  {"reviewer":"40%","reviewer-deep":"40%","security-reviewer":"40%"}` (whole-record
  setting, entries are percentage strings or token counts).
- Review lanes: `scripts/lane.sh` exports `PI_CONFIG_FILES=scripts/review-compaction.yml`
  (`compaction.thresholdPercent: 40`). Check with
  `PI_CONFIG_FILES=<that file> omp config get compaction.thresholdPercent` -> 40.
  `omp --config <file> config get` does NOT show the overlay (it prints 27), so use the env var to check.
Lanes resume the same session per worktree, so context accumulates across rounds.
Before a continuation, compare the last assistant `usage` (input + cacheRead +
cacheWrite) in the session jsonl with the window (`omp models`). Over 40%: compact
first, or start a fresh session and put the state in the brief.

## 5. Progress and verification

- `omp -p` RESUMES the newest session in the same cwd. A re-run in the same
  worktree continues with the prior context, which is good for continuations.
  The session file is therefore an OLD jsonl that keeps growing, so do not look
  for a new file.
- When the window dies mid-run, report files are never written. Read progress
  from the transcript with `scripts/last-texts.py <cwd>...`, which prints the last
  assistant texts per session. Agents narrate milestones there: "#6's fixes are
  pushed at 9c474c8; make unit-test passed 249/249".
- The transcript is a self-report. Before merging, verify independently:
  - `git ls-remote origin <branch>` equals the claimed sha.
  - Rerun the CI's own test command in a fresh detached worktree (read it from
    `.github/workflows/*.yaml`).
  - Compare the analyzer or lint count to main's baseline.
  - Remove the verify worktrees afterwards.
- uv picks the system CPython 3.14, which can break wheels (ctranslate2 has
  cp310-312 only). Use `uv sync --python 3.12` and `uv run --python 3.12 pytest`.
- A CI job pending for 30+ minutes while the same command passes locally:
  merge on the local result, and tell the user that the CI job looks hung.

## 6. Merging

- Use `gh pr merge <n> --repo <owner/repo> --merge`, a merge commit that keeps
  the stacked history clean. Then retarget the next stacked PR to main.
- `the base branch policy prohibits the merge` means branch protection, for
  example `required_approving_review_count: 2` (check with
  `gh api repos/<o>/<r>/branches/main/protection`). Do NOT use `--admin`: it
  overrides team policy. Report the PR as "verified, needs N approvals or your
  --admin" and move on.
- research-harness (the user's fork) push is authorized. For upstream-facing
  branches, never push.

## 7. Stop-down when usage is exhausted

Kill the lane shells, the omp children (`pgrep -fl "omp -p --model <provider>"`)
and the watchdog. Then `ps aux | grep -E "omp -p|lane.sh|merge-round"` must be
empty. Late `DISPATCH-DONE`/`USAGE-EXHAUSTED` notifications from killed lanes
arrive afterwards. Acknowledge them in one line, with no re-investigation.

Report per item: merged (sha) / verified-blocked (why) / partial (unpushed
commits, uncommitted files with paths) / not started. Include the reset time
in local time (+07): `resets at 2026-10-23T12:43Z` is 19:43 local.

## Refill: keep the agents busy until month end

When no open PRs remain, queue (in this order):
1. Leftover worktrees: finish, test, and port fixes between twin branches with
   cherry-pick (not rebase). Upstream-facing branches stay local.
2. Worktree audit (`auditing-worktrees` skill): merged, stale and purgeable
   branches across all repos. The agent only reports and never deletes.
3. Post-merge audit of the round's merged PRs on main: run the full suite, check
   for regressions, open follow-up branches with fixes, then PR them yourself.
   The user opens PRs unless the repo pre-authorizes it.
4. Test-coverage and security audits of the most recently changed modules, one
   report file each.

## Auto-continue across windows (optional cron + monitor gate)

Optional; the user dismissed it on first use. Offer it, don't install it by default.
Shape: one cron job runs every 30 minutes and is gated by
`scripts/cron-monitor.sh`, copied to `~/.hermes/scripts/merge-round-monitor.sh`.
Command Code also has a WEEKLY usage limit ("You've reached your weekly usage
limit ... resets at <iso>"), several days out. The 5-hour window is not the
only cap, so report the weekly reset date when it appears.
Edit END_EPOCH to the month end. The gate prints deterministic state
(`month-ended` | `busy` | `exhausted-until-<iso>` | `available`) parsed from the
lane logs' "resets at" times, so the LLM wakes only on state changes. A
reset that flips the state to `available` starts one coordinator round.
- The ledger is `~/.hermes/cache/merge-round/STATE.md` (see
  `templates/STATE.example.md`): repos in scope, exclusions, and a per-item table
  (tag | where | status | next). The cron agent has no chat context, so the
  ledger is its memory. Update it at the end of every round.
- Cron prompt essentials: per-state actions; the round is verify+merge previous
  work -> smoke test -> continuation briefs with a fresh round suffix
  `<tag>-r<N>.md` -> 2 lanes. Launch the lanes with
  `terminal(background=true, persist_on_release=true)` so they outlive the cron
  session. Repeat the hard rules (never `--admin`, never push upstream-facing
  branches, never touch the user's main checkouts).
  `month-ended` means remove the job itself (list first, then remove).
- Use `deliver=local` in the CLI. The user checks progress with
  `cronjob action=list` or by reading STATE.md.

## Files

- `scripts/inventory.sh`: PRs (on the origin repo), worktrees, ahead/dirty state.
- `scripts/lane.sh`: serial job lane with usage-exhaustion detection.
- `scripts/watchdog.sh`: zsh composite watchdog (stall and quota).
- `scripts/last-texts.py`: last assistant texts from omp sessions, per cwd.
- `templates/review-brief.md`: the brief skeleton plus the HARD RULES block.
- `scripts/cron-monitor.sh`: deterministic cron gate (month-ended/busy/exhausted/available).
- `templates/STATE.example.md`: example ledger the cron coordinator reads and updates.
