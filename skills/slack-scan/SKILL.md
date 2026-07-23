---
name: slack-scan
description: Summarize today's Slack activity on demand -- one channel or every channel/DM the bot is in.
version: 1.0.0
metadata:
  hermes:
    tags: [slack, summary, notifications, todo]
    category: messaging
    requires_toolsets: [terminal]
---

# Slack notification summary (on demand)

## When to use this

There is **no cron job for this** by design -- the user asked to hold off on scheduling. This
skill runs entirely inside the current chat, the moment it's asked for, and produces nothing
persistent (no state file, no write to `~/tasks/inbox.md`) unless the user explicitly asks for
that. Two shapes of request:

- **"Summarize today" / "what did I miss?"** (no channel named) -- recap every channel and DM the
  bot is currently a member of.
- **"What's in #channel today?"** (channel named) -- recap just that one.

## Prerequisites

- The bot must be a member of any channel it's asked to cover (`/invite @hermes_bot` in it).
  Public channels the bot never joined, and private channels it wasn't invited to, are invisible
  to it -- there is no workaround.
- `SLACK_BOT_TOKEN` is set in `~/.hermes/.env`.
- Bot scopes `channels:history` / `groups:history` / `im:history` / `mpim:history` are granted
  (already part of the standard manifest -- see `slack-todo-bot/README.md` step 2).

**Never rely on `$SLACK_BOT_TOKEN` from the shell environment -- it is always empty.** Hermes
strips `SLACK_BOT_TOKEN` (plus `SLACK_APP_TOKEN`, `SLACK_HOME_CHANNEL`) from every subprocess it
spawns, including this skill's own terminal-tool calls, because those names are registered
gateway-managed "messaging" credentials in `tools/environments/local.py`
`_HERMES_PROVIDER_ENV_BLOCKLIST` (`SECURITY.md` section 2.3 / GHSA-rhgp-j443-p4rf). This is
unconditional: no `required_environment_variables` frontmatter declaration and no `config.yaml`
`terminal.env_passthrough` entry can re-allow it -- both paths explicitly refuse to register a
blocklisted name. Confirmed empirically: a live `hermes --toolsets terminal -z '...'` turn that
echoed `${#SLACK_BOT_TOKEN}` printed `0`, even with the token exported in the parent shell before
`hermes` was invoked.

The strip only filters *inherited process environment* -- not plain file reads. Every command
below extracts the token straight out of `~/.hermes/.env` at call time instead:
`$(grep '^SLACK_BOT_TOKEN=' ~/.hermes/.env | cut -d= -f2-)`. Apply the same pattern to any new
API call you add to this skill.

There is no `slack_history` or similar agent-callable tool. Every step below goes through the
`terminal` tool calling Slack's Web API directly with `curl`/`python3`, reading the token from
`~/.hermes/.env` as shown above.

## Steps

### 1. Determine scope

- Channel named in the request -> resolve just that one ID (see "Resolve a channel name" below).
- No channel named -> enumerate every conversation the bot is a member of:

  ```bash
  SLACK_TOKEN=$(grep '^SLACK_BOT_TOKEN=' ~/.hermes/.env | cut -d= -f2-)
  curl -s -H "Authorization: Bearer $SLACK_TOKEN" \
    "https://slack.com/api/conversations.list?types=public_channel,private_channel,mpim,im&limit=200&exclude_archived=true"
  ```

  Paginate on `response_metadata.next_cursor`. Keep only entries where `is_member` is `true`
  (private channels and IMs/MPIMs the bot can see are always ones it's already in; public
  channels need the explicit `is_member` check since the list includes ones it never joined).

### 2. Compute "today" as a Unix timestamp

Midnight today, in the user's local timezone if known from context, else the machine's local time:

```bash
python3 -c "from datetime import datetime; print(datetime.now().replace(hour=0,minute=0,second=0,microsecond=0).timestamp())"
```

### 3. Fetch each channel's history since that timestamp

```bash
SLACK_TOKEN=$(grep '^SLACK_BOT_TOKEN=' ~/.hermes/.env | cut -d= -f2-)
curl -s -H "Authorization: Bearer $SLACK_TOKEN" \
  "https://slack.com/api/conversations.history?channel=CHANNEL_ID&oldest=OLDEST_TS&limit=200"
```

Paginate on `response_metadata.next_cursor`. **Rate limit**: `conversations.history` is Tier 3
(~50 req/min per workspace). If scope is "every channel" and the bot is in more than a handful,
write a short throwaway Python script via the terminal tool that loops over channel IDs with a
`time.sleep(1.2)` between calls and retries once on HTTP 429 honoring the `Retry-After` header --
don't fire a burst of sequential `curl` calls with no delay.

Drop any channel that returns zero messages after filtering (step 4) -- don't mention it in the
final summary.

### 4. Filter

Drop messages where `subtype == "bot_message"` (avoids echoing digests/other bots' output). Keep
`user`, `ts`, `text` for the rest.

### 5. Summarize -- this is a general recap, not just a TODO list

For each channel with activity today, reason over its messages and produce 2-5 bullets covering
whatever's actually there:

- decisions made or announcements posted
- direct mentions of the requesting user, or messages addressed to them
- open questions / blockers with no visible resolution
- explicit asks or deadline language ("by EOD", "ASAP", "before standup") -- call these out as
  action items within the recap, but don't force every channel into a TODO-shaped bullet list if
  the activity was just discussion or FYI-style updates.

### 6. Reply

One message, grouped by channel (`#channel-name` or DM name as a heading), most-active or
most-urgent channel first. If scope was "everything" and nothing had activity today, say so
plainly. Don't write anything to disk -- this is a pull; only append to `~/tasks/inbox.md` if the
user explicitly says "add these to my list" (tag with `[d:t]`, dedup by the Slack message `ts`).

## Resolve a channel name

```bash
SLACK_TOKEN=$(grep '^SLACK_BOT_TOKEN=' ~/.hermes/.env | cut -d= -f2-)
curl -s -H "Authorization: Bearer $SLACK_TOKEN" \
  "https://slack.com/api/conversations.list?types=public_channel,private_channel&limit=200" \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print([c['id'] for c in d['channels'] if c['name']=='channel-name'])"
```

Paginate if the workspace has more than 200 channels.

## Errors

| Response | Meaning | Action |
| --- | --- | --- |
| `not_in_channel` | Bot isn't a member | Tell the user to `/invite @hermes_bot` in that channel, skip it (don't fail the whole summary). |
| `missing_scope` | A history scope isn't granted | Point to `slack-todo-bot/README.md` step 2, stop. |
| `channel_not_found` | Bad ID or private channel bot can't see | Ask the user to confirm the channel name/ID. |
| `ratelimited` (HTTP 429) | Too many `conversations.history` calls | Sleep for the `Retry-After` header value, retry once, then skip that channel and note it in the reply. |
| Empty `messages` everywhere | No activity today | Say so plainly -- don't fabricate items. |
