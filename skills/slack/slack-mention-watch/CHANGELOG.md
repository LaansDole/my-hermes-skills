# Changelog — slack-mention-watch

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Bump `version:` in SKILL.md and add a matching section; the release workflow publishes it.

## [2.7.0] - 2026-11-10

### Fixed
- Review agent: only explicit review asks in the `Mention:` text start a review (PTAL, "can you
  review", "please check this", ...), not any PR link or ticket key in the block. Targets come
  from the mention, else the thread root only. Other pings get
  `review: skipped (not a review request)`; asks without a target
  `review: skipped (no target in mention or thread root)`.
- Review dedupe is per target: one new target no longer re-reviews the others, and nothing is
  reviewed again just because 24 h passed (PRs: until the head commit changes; tickets:
  `SLACK_REVIEW_DAYS`, 7).
- Review runs are read-only for every agent: git/gh guard wrappers first on the agent's PATH
  run only an allowlist of read-only git/gh commands (gh api: GET only) and block the rest,
  aliases included; claude no longer allows `gh api` (it allowed POSTs, e.g. PR comments).
  Argv checks, not a sandbox (see "Write guarantee"). `SLACK_REVIEW_GUARD=0` turns them off.

### Added
- Follow-ups resume the target's existing omp/claude session (`review: resumed <id> (...,
  old..new)`) with a brief holding the new Slack block(s) and, for PRs, only the `old..new` diff.
  A session still running gets the update queued (`review: busy <id> (update queued)`), delivered
  on a later tick.
- `review_spawn.py --sessions` prints the session table (read only).
- Opt-in Jev second opinion for review asks (`SLACK_REVIEW_JEV=1` + `TYPESAFE_API_KEY`,
  `SLACK_REVIEW_JEV_MIN` 0.8, log in `SLACK_REVIEW_JEV_LOG`); the Jev shadow log asks the same
  `review` question.

### Changed
- `SLACK_REVIEW_STATE` holds a session table per target (session, agent, runs, reviewed head
  commit, pid, queued updates); entries are pruned after 30 days without a run. Pre-2.7 files are
  migrated on the next save; migrated entries are never resumed. The `review: already running`
  line is gone.

## [2.6.0] - 2026-11-07

### Added
- Opt-in Jev shadow mode (`SLACK_MENTION_JEV_SHADOW=1` + `TYPESAFE_API_KEY`): logs TypeSafe Jev's
  emoji verdict and already-handled probability for each new mention to
  `~/.hermes/scripts/.slack-mention-jev.jsonl` beside the regex result. Sends mention and
  thread text to `api.typesafe.ai`; off by default; changes no output or reaction.

### Changed
- Digest cron example uses `--reasoning-effort high`, not `max` (`max` was ~88% of the job's spend).

## [2.5.0] - 2026-11-07

- Initial tracked version.
