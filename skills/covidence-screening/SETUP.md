# Covidence Screening — Setup

## One-time setup

1. Install Hermes Agent v0.18+ and enable the `browser` toolset in local CDP mode (see the iLearning plan Task 1 if not already done).
2. Confirm `hermes setup --portal` is complete (vision-capable model configured).

## Per-review setup

1. Log into `app.covidence.org` in Chrome.
2. Open the target review. In Settings, switch the review to **single-reviewer mode** (dual mode is not supported by this skill -- your vote alone will not advance references).
3. Edit `~/.hermes/skills/covidence-screening/CRITERIA.md` -- fill in the PICO + inclusion/exclusion bullets. Remove the `<!-- DO NOT REMOVE` placeholder line. The skill refuses to run while the placeholder is present.

## Launch a session

1. Start Chrome with remote debugging:
   ```bash
   open -na "Google Chrome" --args --remote-debugging-port=9222
   ```
2. In Chrome, navigate to the review's Review Summary page (not the dashboard).
3. Start Hermes:
   ```bash
   hermes -t browser chat
   ```
4. In the Hermes prompt:
   ```
   /browser connect
   ```
   Then:
   ```
   run the covidence-screening skill on my current review, max_refs=200, max_time=90, dry_run=false
   ```
   Adjust `max_refs`, `max_time`, `approve_first_n`, `daily_cap`, and `dry_run` as needed. For first-pass validation, use `dry_run=true` against the Covidence Demo review.

## First-run safety

Always do the first run as `dry_run=true` on the Covidence Demo review (or a test review), then a single-reference live run (`max_refs=1`), then an approve-first-N run (`max_refs=10, approve_first_n=5`) before going fully unattended. See the design spec Section 6 (Testing Strategy).
