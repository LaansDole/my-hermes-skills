# Changelog — slack-mention-watch

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Bump `version:` in SKILL.md and add a matching section; the release workflow publishes it.

## [2.6.0] - 2026-11-07

### Added
- Opt-in Jev shadow mode (`SLACK_MENTION_JEV_SHADOW=1` + `TYPESAFE_API_KEY`): logs TypeSafe Jev's
  emoji verdict for each new mention to `~/.hermes/scripts/.slack-mention-jev.jsonl` beside the
  regex result. Sends mention and thread text to `api.typesafe.ai`; off by default; changes no
  output or reaction.

### Changed
- Digest cron example uses `--reasoning-effort high`, not `max` (`max` was ~88% of the job's spend).

## [2.5.0] - 2026-11-07

- Initial tracked version.
