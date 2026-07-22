---
name: slack-scan
description: On-demand Slack channel scan that pulls today's messages from a channel and extracts action items/TODOs, without waiting for the hourly cron job. Works in any interactive chat (DM or channel) the moment the user asks. Uses the Slack Web API directly through the terminal tool -- Hermes has no built-in `slack_*` tool, unlike Discord.
trigger:
  - scan slack
  - check channel for todos
  - what's in #
  - today's todos from
  - look into channel
  - what happened in
---

# Slack channel scan -> today's TODOs

## When to use this

The hourly `slack-digest.py` cron job (see `slack-todo-bot/README.md` in this repo) only covers
channels listed in `SLACK_WATCH_CHANNELS` and only reports messages since its last run. Use this
skill instead when the user asks **right now, in chat**, about a channel -- named or not yet
watched -- and wants today's action items immediately. No cron round-trip, no state file.

## Prerequisites

- The bot is a member of the target channel (`/invite @hermes_bot` in it). Without membership,
  `conversations.history` returns `not_in_channel` for public channels bots aren't in, or
  `missing_scope`/`channel_not_found` for private ones.
- `SLACK_BOT_TOKEN` is set in `~/.hermes/.env` and readable to the terminal tool's environment.
- Bot scopes `channels:history` (public) and/or `groups:history` (private) are granted -- already
  part of the standard manifest (see `slack-todo-bot/README.md` step 2).

There is no `slack_history` or similar agent-callable tool. Every step below goes through the
`terminal` tool calling Slack's Web API directly with `curl` + `SLACK_BOT_TOKEN`.

## Steps

1. **Resolve the channel ID.** If the user gave `#channel-name`, resolve it (paginate if needed):

   ```bash
   curl -s -H "Authorization: Bearer $SLACK_BOT_TOKEN" \
     "https://slack.com/api/conversations.list?types=public_channel,private_channel&limit=200" \
     | python3 -c "import json,sys; d=json.load(sys.stdin); print([c['id'] for c in d['channels'] if c['name']=='channel-name'])"
   ```

   If the user already gave a channel ID (`C0123...`), skip straight to step 2.

2. **Compute "today" as a Unix timestamp.** Use the user's local timezone if known from context,
   otherwise the machine's local time. `oldest` = midnight today:

   ```bash
   python3 -c "from datetime import datetime; print(datetime.now().replace(hour=0,minute=0,second=0,microsecond=0).timestamp())"
   ```

3. **Fetch history since that timestamp**, paginating on `response_metadata.next_cursor`:

   ```bash
   curl -s -H "Authorization: Bearer $SLACK_BOT_TOKEN" \
     "https://slack.com/api/conversations.history?channel=CHANNEL_ID&oldest=OLDEST_TS&limit=200"
   ```

4. **Filter**: drop messages where `subtype == "bot_message"` (avoids echoing digests/other bots).
   Keep `user`, `ts`, `text` for the rest.

5. **Extract action items** from the remaining text via reasoning, not regex -- look for:
   - explicit asks directed at someone ("@user can you...", "someone needs to...")
   - deadline language ("by EOD", "today", "ASAP", "before standup")
   - open questions blocking someone's work
   - anything phrased as a decision/task that has no visible follow-up message resolving it

6. **Respond immediately** in the current chat with a short prioritized list (urgent first). Do
   **not** silently write to `~/tasks/inbox.md` -- this is a pull, not the cron's push. Only append
   to the task file if the user explicitly asks ("add these to my list"), tagging entries the same
   way the cron job does (`[d:t]`, dedup by a stable marker like the Slack message `ts`).

## Errors

| Response | Meaning | Action |
| --- | --- | --- |
| `not_in_channel` | Bot isn't a member | Tell the user to `/invite @hermes_bot` in that channel, stop. |
| `missing_scope` | `channels:history`/`groups:history` not granted | Point to `slack-todo-bot/README.md` step 2, stop. |
| `channel_not_found` | Bad ID or private channel bot can't see | Ask the user to confirm the channel name/ID. |
| Empty `messages` | No activity today | Say so plainly -- don't fabricate items. |
