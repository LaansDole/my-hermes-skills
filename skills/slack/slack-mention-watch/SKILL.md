---
name: slack-mention-watch
description: Use when the user asks about Slack pings, mentions, notifications or what they missed, or wants @mention alerts or a triaged mention digest while away. Read-only.
version: 2.1.0
author: LaansDole
license: MIT
metadata:
  hermes:
    tags: [slack, notifications, monitoring, cron]
    category: slack
    requires_toolsets: [terminal]
---

# Slack @mention watch

Lists Slack messages that `@`-mention the user, on demand or as background alerts. Strictly
read-only toward Slack. Not for: summarizing a day of Slack (use `slack-scan`), replying, keyword
watches, or `@here`/`@channel` pings.

The script lives at `~/.hermes/skills/slack/slack-mention-watch/scripts/watch_mentions.py`. If the
skill is installed elsewhere, `skill_view` returns its `skill_dir`; use `<skill_dir>/scripts/watch_mentions.py`.

## On demand: what pinged me?

When the user asks "any notifications?", "who pinged me?", "what did I miss?" or similar, run the
script with the **`execute_code` tool** (preferred -- it has no background/foreground options to
get wrong, and returns the full output):

```python
import os, subprocess
r = subprocess.run(["python3", os.path.expanduser(
    "~/.hermes/skills/slack/slack-mention-watch/scripts/watch_mentions.py"), "--recent", "24"],
    capture_output=True, text=True, timeout=120)
print(r.stdout or r.stderr)
```

Only if `execute_code` is unavailable, use ONE `terminal` call with `command` only:
`python3 ~/.hermes/skills/slack/slack-mention-watch/scripts/watch_mentions.py --recent 24`
-- and if it returns "notify/heartbeat only apply to background commands", do NOT retry it
unchanged; switch to `execute_code`.

- Hours match the question: "last hour" = `1`, floats are fine, "today" = `24` (don't compute
  midnight with extra commands).
- Relay the output as-is. It lists every mention in the window, newest first (max 50), and
  never touches the background job's state. With none it prints `No @<name> mentions in the last N h.`
- **Never claim you can't see Slack** -- this script is how you see it.

## Quick command `/pings`

Most reliable option: a quick command runs the script directly and bypasses the LLM. Add to
`~/.hermes/config.yaml`, then `hermes gateway restart`:

```yaml
quick_commands:
  pings:
    type: exec
    command: python3 ~/.hermes/skills/slack/slack-mention-watch/scripts/watch_mentions.py --recent 24
```

On Slack, quick commands are NOT in the app manifest, so typing `/pings` makes Slack itself reply
"not a valid command", and `!pings` is NOT rewritten either (the `!` prefix only maps built-in
commands). Use **`/hermes /pings`** -- the `/hermes` slash command forwards `/pings` to the
gateway, which runs the quick command (reply is ephemeral, "only visible to you"). Slack blocks
slash commands inside threads, so send it from a DM or channel. Telegram/Discord/CLI accept
`/pings` directly.

## Setup

Install: copy or symlink this folder to `~/.hermes/skills/slack/slack-mention-watch`.

1. https://api.slack.com/apps -> your Hermes bot's app -> **OAuth & Permissions** -> **User Token
   Scopes** -> add `search:read`.
2. **Reinstall to Workspace**, approving as the Slack user to watch.
3. Put the **User OAuth Token** (`xoxp-...`) in `~/.hermes/.env`:
   `SLACK_USER_READ_TOKEN=xoxp-...`
4. Verify:

   ```bash
   python3 ~/.hermes/skills/slack/slack-mention-watch/scripts/watch_mentions.py --check
   ```

   Expect `mode: search` and `watching: <@U...>` = your Slack user. Touches no state.

| Mode | Token | Coverage |
| --- | --- | --- |
| `search` (preferred) | `SLACK_USER_READ_TOKEN` (xoxp, `search:read`) | Every channel, DM and group DM the user can see, threads included. |
| `history` (fallback) | `SLACK_BOT_TOKEN` (xoxb) | Only channels the bot was `/invite`d to; top-level messages only, no DMs. |

Fallback without a user token: `/invite` your Hermes bot into each channel to watch.

Names resolve via `users.info` on `SLACK_BOT_TOKEN` (needs `users:read`), so no extra user scope.

## Background alerts

A Hermes cron job runs the script every 5 minutes with `--no-agent`. It prints one block per NEW
mention and nothing otherwise, so nothing is delivered when nothing is new. No LLM involved.

`--script` must be a real file under `~/.hermes/scripts/` (symlinks are rejected as path
traversal), so install a wrapper:

```bash
cat > ~/.hermes/scripts/slack_mention_watch_cron.py <<'EOF'
#!/usr/bin/env python3
import os, runpy, sys
TARGET = os.path.expanduser(
    "~/.hermes/skills/slack/slack-mention-watch/scripts/watch_mentions.py")
sys.argv[0] = TARGET
runpy.run_path(TARGET, run_name="__main__")
EOF
python3 ~/.hermes/skills/slack/slack-mention-watch/scripts/watch_mentions.py  # set baseline once
hermes cron create "every 5m" --name slack-mention-watch \
  --script slack_mention_watch_cron.py --no-agent --deliver slack
```

Alerts go to `SLACK_HOME_CHANNEL` (your Hermes bot's DM) -- the only write in the flow. `--dry-run`
runs a real tick without saving state.

## Triage digest (LLM)

Alternative to the verbatim alerts: an LLM cron agent sorts each new mention into no action /
review / action plan, using the surrounding thread. Use it *instead of* the alert job, not beside
it -- both advance the same state file, so whichever runs first would hide mentions from the other.

`watch_mentions.py --digest` runs the same tick as the default mode (same filters, dedupe and state;
`--dry-run` still saves nothing), then:

- nothing new (or a rate-limited/offline tick) -> prints only `{"wakeAgent": false}`. Hermes treats
  that last stdout line as a gate and skips the agent run: no LLM call, nothing delivered.
- otherwise -> a plain-text context block, oldest mention first:

  ```
  NEW MENTIONS: N   (watched user: @name)
  ### Mention 1 -- #channel -- from <sender> at <local time>
  Permalink: <url>
  Mention: <text>
  Thread (k messages):
  [HH:MM] sender: text
  ```

  The thread comes from `conversations.replies` (thread root + up to 19 latest replies, 600 chars
  per message, ~12k chars total; oldest thread lines are dropped first, mentions always stay). If
  the call fails the mention shows `(thread context unavailable: <error>)` and the tick goes on.

Thread context needs these extra **User Token Scopes** on the same app (reinstall after adding):
`channels:history`, `groups:history`, `im:history`, `mpim:history`. Without them the digest still
works, each mention just shows the `missing_scope` note.

Hermes runs cron scripts as `python <script>` with **no arguments** (`--script` takes a file path
only), so `--digest` goes into a second wrapper:

```bash
cat > ~/.hermes/scripts/slack_mention_digest_cron.py <<'EOF'
#!/usr/bin/env python3
import os, runpy, sys
TARGET = os.path.expanduser(
    "~/.hermes/skills/slack/slack-mention-watch/scripts/watch_mentions.py")
sys.argv = [TARGET, "--digest", *sys.argv[1:]]  # extra args (e.g. --dry-run) pass through
runpy.run_path(TARGET, run_name="__main__")
EOF
python3 ~/.hermes/scripts/slack_mention_digest_cron.py --dry-run  # preview, saves nothing
hermes cron create "every 5m" "$(cat ~/.hermes/scripts/slack_mention_digest_prompt.txt)" \
  --name slack-mention-digest --script slack_mention_digest_cron.py \
  --model <model> --provider <provider> --reasoning-effort max --deliver slack
```

Save the prompt below as `~/.hermes/scripts/slack_mention_digest_prompt.txt` first (or paste it
as the quoted prompt argument). The script output is injected into it on every run. No `--no-agent`:
the agent writes the delivered message. If an alert job already exists, remove it
(`hermes cron remove <id>`) once the digest job works.

Cron agent prompt:

```text
You receive new Slack @mentions of the user, each with its thread context, in the script output
above. Triage each mention into exactly one bucket and write a Slack-friendly digest (plain text,
short):

1. NO ACTION -- thanks, FYI, "approved", acknowledgements. One line each.
2. REVIEW -- PR/link review requests. One line: what to review + links.
3. ACTION PLAN -- requests needing work. For each:
   - Goal (1 line)
   - Context (problem, current workaround, concrete numbers from the thread)
   - Questions to clarify (2-5, aimed at who to ask)
   - Tasks (3-6 concrete steps)
   - Where it could live (suggestion)
   Never invent facts not in the thread; mark assumptions.

Order: ACTION PLAN, REVIEW, NO ACTION. Include each item's permalink. Even if every item is
NO ACTION, still send the one-line list so nothing is hidden. Reply exactly [SILENT] only if the
script output contains no mentions. Read-only: never suggest posting on the user's behalf.
```

## Read-only guarantee

Every request goes through `api()`: HTTP GET only, and `ValueError` for any method outside
`READ_METHODS` (`auth.test`, `search.messages`, `conversations.list`, `conversations.history`,
`conversations.info`, `conversations.replies`, `users.info`, `chat.getPermalink`). It never posts,
reacts, marks read, joins or replies. Covered by `tests/test_watch_mentions.py` in the source repo.

## Config

Settings come from the process env, then `~/.hermes/.env` directly.

| Variable | Default |
| --- | --- |
| `SLACK_USER_READ_TOKEN` | unset -> history mode |
| `SLACK_MENTION_USER_ID` | owner of `SLACK_USER_READ_TOKEN` (`auth.test`), else first id in `SLACK_ALLOWED_USERS` |
| `SLACK_MENTION_LOOKBACK_MINS` | `60` (first background run only) |
| `SLACK_MENTION_IGNORE_USERS` | empty; comma list of extra author ids to drop (bot user always dropped) |
| `SLACK_HOME_CHANNEL` | alert channel; matches in it are dropped |
| `SLACK_MENTION_STATE_FILE` | `~/.hermes/scripts/.slack-mention-watch.json` (chmod 600) |
| `HERMES_DOTENV` | `~/.hermes/.env` |

## Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| `ERROR: search.messages: not_allowed_token_type` | An `xoxb-` bot token was pasted as `SLACK_USER_READ_TOKEN` | Use the `xoxp-` **User** OAuth Token. |
| `ERROR: ...: missing_scope` | `search:read` not granted | Add the user scope, reinstall. |
| `ERROR: ...: invalid_auth` / `token_revoked` | Token wrong or app reinstalled | Copy the current token into `~/.hermes/.env`. |
| `--check` says `member channels: 0` | History mode, bot invited nowhere | Add the user token, or `/invite` your bot. |
| Same mention re-alerts every tick / alert quotes its own alert | Self-alert loop: search sees the bot's alert DM as a new mention | Set `SLACK_HOME_CHANNEL` and `SLACK_BOT_TOKEN` in `~/.hermes/.env`; add other relaying ids to `SLACK_MENTION_IGNORE_USERS`. |
| `notify/heartbeat only apply to background commands`, then `identical_call_streak_halt` | The model passes background-only args on a foreground call and retries it | Use `/pings`, or a different model. |
| Names show as `U...` | `users.info` failed: no `SLACK_BOT_TOKEN` or no `users:read` | Check the bot token in `~/.hermes/.env`. |
| `$SLACK_BOT_TOKEN` empty in the terminal | Hermes strips gateway `SLACK_*` vars from subprocesses | Nothing; the script reads `~/.hermes/.env` itself. |
| Mention in a thread never alerts | History mode skips thread replies | Use the user token. |
| Stderr `rate limited` / `network error` | 429 after one retry, or offline | Tick skipped, state not advanced; next tick catches up. |
