---
name: slack-mention-watch
description: Use when monitoring Slack for new @tony mentions while away. Read-only poller + cron alert.
version: 1.0.0
metadata:
  hermes:
    tags: [slack, notifications, monitoring, cron]
    category: messaging
    requires_toolsets: [terminal]
---

# Slack @tony mention watch

## When to use this

The user (Slack "tony", `U0BJAUSC83Y`, workspace "folktale") is away and wants to know when
someone pings `@tony`. A cron job runs `scripts/watch_mentions.py` every 5 minutes with
`--no-agent`: the script prints one block per NEW mention (channel, sender, local time, text with
`<@U..>` resolved to `@name`, permalink) and prints **nothing** when there is nothing new, so the
cron delivers nothing. No LLM is involved.

Not for: summarizing a day of Slack (use `slack-scan`), replying, keyword watches, or
`@here`/`@channel` pings.

## How it reads Slack

The script auto-selects a mode:

| Mode | Token | Coverage |
| --- | --- | --- |
| `search` (preferred) | `SLACK_USER_READ_TOKEN` (xoxp, user scope `search:read`) | Every public/private channel, DM and group DM tony can see. One `search.messages` call per tick. |
| `history` (fallback) | `SLACK_BOT_TOKEN` (xoxb) | Only channels/group DMs the bot is a **member** of, top-level messages only (thread replies skipped -- each would cost an extra Tier-3 call). Never sees DMs between other people and tony. |

The bot token has no `search:read`; `search.messages` with it returns `not_allowed_token_type`.
`app_mentions:read` events only fire for `@hermes_bot`, never `@tony`, so the gateway can't do this.

**Never rely on `$SLACK_BOT_TOKEN` from the shell environment -- it is always empty.** Hermes
strips `SLACK_BOT_TOKEN` (and the other gateway-managed `SLACK_*` names) from every subprocess it
spawns (see `slack-scan/SKILL.md` for the full explanation). The script therefore reads every
setting from the process env first, then falls back to `~/.hermes/.env` directly.

## Setup

### A. User token (recommended)

1. https://api.slack.com/apps -> the Hermes app -> **OAuth & Permissions** -> **User Token Scopes**
   -> add `search:read`. Names resolve via `users.info` on `SLACK_BOT_TOKEN` (which has
   `users:read`), so no extra user scope is needed.
2. **Reinstall to Workspace** (banner at the top of the page), approve as tony.
3. Copy the **User OAuth Token** (`xoxp-...`) into `~/.hermes/.env`:

   ```
   SLACK_USER_READ_TOKEN=xoxp-...
   ```

### B. Fallback: bot token only

Nothing to add -- `SLACK_BOT_TOKEN` is already in `~/.hermes/.env`. In every channel to watch,
run `/invite @hermes_bot`. Until then the bot is in 0 channels and history mode sees nothing.

### Verify

```bash
python3 ~/Projects/auto-learn-for-me/skills/slack/slack-mention-watch/scripts/watch_mentions.py --check
```

Prints mode, token type, `auth.test` identity, granted scopes, the watched user id, and either
the indexed mention count (search) or member channel count (history). Touches no state.
`--dry-run` runs a real tick and prints what would be delivered without saving state.

### Cron

`--script` must be a real file under `~/.hermes/scripts/`. A symlink pointing into this repo is
rejected ("Script path escapes the scripts directory via traversal"), so install a tiny wrapper:

```bash
cat > ~/.hermes/scripts/slack_mention_watch_cron.py <<'EOF'
#!/usr/bin/env python3
import os, runpy, sys
TARGET = os.path.expanduser(
    "~/Projects/auto-learn-for-me/skills/slack/slack-mention-watch/scripts/watch_mentions.py")
sys.argv[0] = TARGET
runpy.run_path(TARGET, run_name="__main__")
EOF
hermes cron create "every 5m" --name slack-mention-watch \
  --script slack_mention_watch_cron.py --no-agent --deliver slack \
  --paused --paused-reason "waiting for SLACK_USER_READ_TOKEN"
```

If the skill folder moves, update `TARGET` in the wrapper or the job errors every tick.

Resume it once `--check` reports `mode: search`. Delivery goes to the Hermes home DM with tony
(`SLACK_HOME_CHANNEL`) -- the only write in the whole flow, and it never touches a monitored
channel. Because the alert quotes the mention, `search.messages` would find it again next tick;
the script drops every match in `SLACK_HOME_CHANNEL`, every match authored by the bot user
(`auth.test` on `SLACK_BOT_TOKEN`) or by `SLACK_MENTION_IGNORE_USERS`, and renders the watched
user as plain `@name` text (never `<@U...>`).

## Config

| Variable | Default |
| --- | --- |
| `SLACK_MENTION_USER_ID` | first id in `SLACK_ALLOWED_USERS` |
| `SLACK_MENTION_LOOKBACK_MINS` | `60` (first run only) |
| `SLACK_MENTION_IGNORE_USERS` | empty; comma list of extra author ids to drop (bot user always dropped) |
| `SLACK_HOME_CHANNEL` | read from `~/.hermes/.env`; matches in it are dropped |
| `SLACK_MENTION_STATE_FILE` | `~/.hermes/scripts/.slack-mention-watch.json` (chmod 600) |
| `HERMES_DOTENV` | `~/.hermes/.env` |

State is `{"last_ts", "seen"}`. Each tick re-scans 10 minutes behind `last_ts` (search indexing
lags) and dedupes by `channel:ts` against the last 500 `seen` keys.

## Read-only guarantee

Every request goes through `api()`, which issues HTTP GET only and raises `ValueError` for any
method outside `READ_METHODS`: `auth.test`, `search.messages`, `conversations.list`,
`conversations.history`, `conversations.info`, `users.info`, `chat.getPermalink`. It never posts,
reacts, marks read, joins channels or replies. Covered by `tests/test_watch_mentions.py`
(`python3 -m unittest -v tests.test_watch_mentions`).

## Troubleshooting

| Symptom | Meaning | Action |
| --- | --- | --- |
| `[slack-mention-watch] ERROR: search.messages: not_allowed_token_type` | A bot token was put in `SLACK_USER_READ_TOKEN` | Use the `xoxp-` **User** OAuth Token. |
| `ERROR: ...: missing_scope` | `search:read` not granted | Add the user scope, reinstall (setup A). |
| `ERROR: ...: invalid_auth` / `token_revoked` | Token wrong or app reinstalled | Copy the current token into `~/.hermes/.env`. |
| `--check` says `member channels: 0` | History mode, bot invited nowhere | Setup A, or `/invite @hermes_bot`. |
| Sender shows as `U...` | `users.info` failed: no `SLACK_BOT_TOKEN`, or it lacks `users:read` | Check the bot token in `~/.hermes/.env`. |
| Same mention re-alerts every tick / alert quotes its own alert (duplicate/self-alert loop) | Search returns the bot's alert DM as a new `@tony` mention (search matches carry no `bot_id`) | Ensure `SLACK_HOME_CHANNEL` and `SLACK_BOT_TOKEN` are in `~/.hermes/.env`; add any other relaying user/bot id to `SLACK_MENTION_IGNORE_USERS`. |
| Mention in a thread never alerts | History mode skips thread replies | Use setup A (search covers threads). |
| Nothing for a while, stderr `rate limited` / `network error` | 429 after one retry, or offline | Tick skipped, state not advanced; next tick catches up. Not delivered on purpose. |
| Flood of old mentions on first run | No state yet -> `SLACK_MENTION_LOOKBACK_MINS` window | Run the script once by hand (no flags) before resuming the cron to set the baseline, or lower the lookback. |
