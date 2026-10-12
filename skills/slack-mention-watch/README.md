# slack-mention-watch

Alerts tony in his Hermes DM when someone new `@tony`-mentions him on Slack. A Hermes cron job
runs `scripts/watch_mentions.py` every 5 minutes with `--no-agent`; the script prints nothing when
there's nothing new, so nothing is sent. Strictly read-only toward Slack (GET-only allowlist of
read methods).

## Quick start

1. Slack app -> OAuth & Permissions -> User Token Scopes -> add `search:read`, reinstall, put the
   `xoxp-` token in `~/.hermes/.env` as `SLACK_USER_READ_TOKEN`.
   Without it, the script falls back to the bot token and only sees channels the bot was
   `/invite`d to (no DMs, no thread replies).
2. `python3 scripts/watch_mentions.py --check` -- should say `mode: search`.
3. Link into `~/.hermes/scripts/` and create the cron job (exact commands in `SKILL.md`).

## Files

- `scripts/watch_mentions.py` -- the poller (python3 stdlib only). Flags: `--check`, `--dry-run`.
- `SKILL.md` -- setup, config variables, troubleshooting.
- `../../tests/test_watch_mentions.py` -- unit tests, no network.

State: `~/.hermes/scripts/.slack-mention-watch.json` (mode 600).
