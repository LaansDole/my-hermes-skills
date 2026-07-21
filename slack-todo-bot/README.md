# slack-todo-bot

A Hermes Agent skill that turns Slack notifications into a private daily TODO digest. The bot runs two cron jobs on your laptop: one that scans Slack hourly and extracts action items into a Markdown task file, and one that posts a "today" priority digest to your private Slack DM at 9 AM. No public channel posts, no inbound ports, no cloud -- just Socket Mode + local files.

Built on [Hermes Agent](https://hermes-agent.nousresearch.com/) (Nous Research, MIT). Uses the built-in Slack gateway (Socket Mode / WebSocket), so it works behind your firewall with no public URL.

## How it works

```
[Slack workspace]
       |  Socket Mode (WebSocket, outbound only)
       v
[Hermes gateway]  <-- launchd service on your Mac, holds 1 persistent WSS
       |
       |-- per-chat AIAgent sessions (interactive DMs)
       |-- cron scheduler (ticks every 60s)
       |       |
       |       |-- hourly: slack-digest.py  -->  pulls new msgs via Web API
       |       |                                      |
       |       |                                      v
       |       |                          agent summarizes + extracts actions
       |       |                                      |
       |       |                                      v
       |       |                          ~/tasks/inbox.md  (Markdown checkboxes)
       |       |                                      |
       |       |                                      v
       |       `-- 09:00 daily: today-digest.py  -->  runs `today` CLI
       |                                                      |
       |                                                      v
       |                                          agent posts priority plan to your DM
       |
       `-- delivery to SLACK_HOME_CHANNEL (your DM with the bot -- private)
```

**The mental model:**

1. **One process, one gateway.** A single Python process (`hermes gateway`) runs as a macOS launchd service. It holds a persistent WebSocket to Slack (Socket Mode) -- no public URL, no inbound ports. Works behind your firewall, on your laptop, anywhere.

2. **Per-chat sessions.** DM `@hermes_bot` or @mention it in a channel and the gateway routes the message to a per-chat `AIAgent` session. Each Slack user gets an isolated conversation history.

3. **The agent has tools.** Inside a session the agent can call terminal commands, read/write files, search the web, run code -- all on your local filesystem. When you ask "add a TODO", it writes to `~/tasks/inbox.md` using its file tools.

4. **Cron rides the gateway.** The gateway runs a background ticker (every 60s) that fires due cron jobs. Each job spawns a fresh agent session with a script's stdout as context, runs the agent, and delivers the response to Slack. Cron jobs run with `cronjob`/`messaging`/`clarify` toolsets disabled -- no recursive cron, no direct DM sending (delivery is the scheduler's job), no interactive prompts. But terminal/file tools stay available.

5. **Deny-by-default.** Without `SLACK_ALLOWED_USERS`, the gateway refuses all messages. Only the user IDs you list can talk to the bot.

6. **Private by default.** `SLACK_HOME_CHANNEL` points at the DM channel between you and the bot (a `D...` ID), so cron output lands privately -- like a GitHub App bot's DM, not in a public channel.

## Prerequisites

- **macOS** (tested target; the launchd service commands are macOS-specific. Linux/Windows work with equivalent systemd / service scripts.)
- [Hermes Agent](https://hermes-agent.nousresearch.com/) v0.18+
- A Slack workspace where you can create apps (or admin permission to install one)
- [uv](https://docs.astral.sh/uv/) (for installing the `today` CLI)
- Python 3.11+ (ships with Hermes; used for the two cron scripts)

## One-time setup

### 1. Install Hermes Agent

```bash
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
```

Open a new shell (or `source ~/.zshrc`) so `hermes` is on `$PATH`. Verify:

```bash
hermes --version   # must be >= 0.18.0
```

### 2. Create the Slack app

Go to https://api.slack.com/apps and click **Create New App** -> **From an app manifest**. Use this manifest (replace `<your-workspace>` is implicit -- manifest is workspace-agnostic):

```yaml
_metadata:
  major_version: 1
  minor_version: 0
display_information:
  name: Hermes Bot
  description: Personal TODO assistant -- scans Slack and posts daily digests
  icon_url: https://hermes-agent.nousresearch.com/logo.png
features:
  agent_view: {}
  app_home:
    messages_tab_enabled: true
oauth_config:
  scopes:
    bot:
      - chat:write
      - app_mentions:read
      - channels:history
      - channels:read
      - groups:history
      - groups:read
      - im:history
      - im:read
      - im:write
      - mpim:history
      - mpim:read
      - files:read
      - files:write
      - users:read
      - assistant:write
settings:
  event_subscriptions:
    bot_events:
      - app_mention
      - app_home_opened
      - app_context_changed
      - message.im
      - message.channels
      - message.groups
      - message.mpim
  socket_mode_enabled: true
  always_view_workspace: true
```

Key points (earlier iterations got these wrong -- Slack rejects mis-placed fields):

- `event_subscriptions` lives under `settings:` (NOT under `features:`).
- `scopes` lives under `oauth_config:` (NOT under `features:`).
- `_metadata.major_version: 1` is required for YAML manifests.
- `features.agent_view: {}` enables the modern Agent messaging surface and the `app_context_changed` event. It is **irreversible** once enabled. (Use `agent_view`, not the deprecated `assistant_view`.)
- `features.app_home.messages_tab_enabled: true` is required or DMs are blocked.
- `assistant:write` scope is required for the working-state status line in the Agent view.
- `socket_mode_enabled: true` is the whole point -- no HTTP URL needed.

Click **Create** -> **Install to Workspace** -> **Allow**.

### 3. Generate the two tokens

You need exactly two secrets for Socket Mode (the signing secret and client secret are NOT needed):

1. **App-Level Token** (`xapp-...`, scope `connections:write`) -- Settings -> Basic Information -> App-Level Tokens -> Generate a New Token. Name it `hermes-socket`, add the scope `connections:write`, generate, copy.

   > This scope is mandatory. Without it, `apps.connections.open` returns `missing_scope: connections:write` and Socket Mode cannot connect. This is the single most common setup failure.

2. **Bot Token** (`xoxb-...`) -- Settings -> Install App (or OAuth & Permissions -> Install to Workspace). Copy the `xoxb-` token.

Also grab your own Slack Member ID: in Slack, click your name -> **...** (more) -> **Copy Member ID**. It starts with `U` (e.g. `U0BJAUSC83Y`).

### 4. Open the DM channel with the bot (for private delivery)

The home channel is a 1:1 DM between you and the bot. Find its channel ID (starts with `D`) by opening a DM with the bot in Slack, then right-click the conversation -> **View conversation details** -> the channel ID is in the URL. Or, programmatically with the bot token:

```bash
curl -s -X POST https://slack.com/api/conversations.open \
  -H "Authorization: Bearer xoxb-YOUR-BOT-TOKEN" \
  -H "Content-Type: application/json; charset=utf-8" \
  -d '{"users":"U_YOUR_MEMBER_ID"}' | python3 -m json.tool
# -> channel.id  is your D... DM channel
```

### 5. Write `~/.hermes/.env`

```bash
# Append or merge into the existing ~/.hermes/.env (which has a commented
# SLACK INTEGRATION block -- uncomment and fill):

SLACK_BOT_TOKEN=xoxb-...
SLACK_APP_TOKEN=xapp-1-...with-connections:write...
SLACK_ALLOWED_USERS=U0YOURMEMBERID
SLACK_HOME_CHANNEL=D0YOURDMCHANNELID
SLACK_HOME_CHANNEL_NAME=hermes_bot
TODAY_DIR=~/tasks
```

Lock down permissions (Hermes refuses to load the file otherwise):

```bash
chmod 600 ~/.hermes/.env
```

If your `~/.hermes/.env` is the default template (with a large commented `# SLACK INTEGRATION` block), find it and replace the commented `# SLACK_BOT_TOKEN=...` lines with the real values above (uncommented).

### 6. Install the `today` CLI

```bash
uv tool install todo-today-cli
# -> installs ~/.local/bin/today
today --version
```

This is what the 9 AM digest cron job runs to read your task files.

### 7. Copy the two scripts into place

```bash
mkdir -p ~/.hermes/scripts
cp slack-todo-bot/scripts/slack-digest.py ~/.hermes/scripts/
cp slack-todo-bot/scripts/today-digest.py  ~/.hermes/scripts/
chmod +x ~/.hermes/scripts/slack-digest.py ~/.hermes/scripts/today-digest.py
```

Verify they compile:

```bash
python3 -m py_compile ~/.hermes/scripts/slack-digest.py ~/.hermes/scripts/today-digest.py && echo OK
```

### 8. Seed the task file

```bash
mkdir -p ~/tasks
cat > ~/tasks/inbox.md <<'EOF'
# Inbox

Auto-populated by Hermes from Slack action items. Each run prepends a new
dated section. Edit freely -- `today` reads this file as-is.

## From Slack - 2026-07-21 00:00
- [ ] Replace this line with your first real task [d:t]
EOF
```

The `[d:t]` tag tells the `today` CLI "due today". See [todo-today-cli on PyPI](https://pypi.org/project/todo-today-cli/) for the full tag syntax (`[d:YYYY-MM-DD]`, `[s]` for started, etc.).

### 9. Make sure the gateway service can find `today` on PATH

The launchd service does NOT inherit your shell PATH by default. If `~/.local/bin` (where `uv tool install` puts `today`) is not on the service PATH, `today-digest.py` will report "not installed". Either:

- Add to `~/.hermes/config.yaml`:
  ```yaml
  gateway:
    extra_env:
      PATH: "/Users/<you>/.local/bin:/usr/local/bin:/usr/bin:/bin"
  ```
  Then `hermes gateway install --force` to re-write the launchd plist.

- Or symlink `today` into `/usr/local/bin` (if you have write access).

### 10. Install and start the gateway

```bash
hermes gateway install        # install as macOS launchd user service (one-time)
hermes gateway start          # start the service
hermes gateway status         # check it's supervised + PID
```

Verify the Slack connection:

```bash
hermes logs | grep -i slack | tail -10
```

Look for:
```
[Slack] Authenticated as @hermes_bot in workspace <name> (team: T...)
[Slack] Socket Mode connected (1 workspace(s))
slack connected
```

If you see `missing_scope: connections:write`, go back to step 3.1 -- the app-level token lacks the `connections:write` scope.

If you see `missing_scope: groups:read` on the channel directory, that is non-fatal (Socket Mode still works) but means Hermes can't auto-discover private channels. To fix, add `groups:read` to the bot scopes and reinstall the app.

### 11. Invite the bot to any channels you want it to scan

```
# In Slack, inside each channel:
/invite @hermes_bot
```

The bot will not auto-join. For the hourly scan to read a channel's history, the bot must be a member. DMs (the home channel) need no invite.

## Add the cron jobs

Two jobs, both `--deliver slack` (routes to `SLACK_HOME_CHANNEL`, i.e. your private DM).

### Job 1 -- hourly Slack scan + TODO extraction

```bash
hermes cron add "every 1h" \
  "You receive script output describing new Slack messages since the last run, grouped by channel.

Do TWO things:

1. POST A SUMMARY to Slack: flag anything needing my attention today at the top, then list the rest grouped by channel.

2. EXTRACT ACTION ITEMS to /Users/<you>/tasks/inbox.md. For any message implying something I need to DO, append a Markdown checkbox with [d:t]. Prepend a new section:

## From Slack - <YYYY-MM-DD HH:MM>
- [ ] <concise action item> [d:t]

Rules: create file if missing; prepend new section if exists; do not duplicate items already present; skip FYI messages; one line per item under 80 chars.

If the script output says NO_CHANGE, respond with only [SILENT] and do not modify any file.
Otherwise end your Slack reply with one line: 'Added N TODO(s) to today's list.'" \
  --script ~/.hermes/scripts/slack-digest.py \
  --name "Slack scan + TODO extract" \
  --deliver slack
```

### Job 2 -- 9 AM today digest

```bash
hermes cron add "0 9 * * *" \
  "You receive the output of the 'today' CLI showing all tasks due or overdue today. Give me a 3-line priority plan for what to tackle first, then the remaining task list grouped by heading. If the script output says NO_CHANGE, respond with only [SILENT]." \
  --script ~/.hermes/scripts/today-digest.py \
  --name "Today TODO digest" \
  --deliver slack
```

## Verify

```bash
hermes cron list                              # both jobs [active] with next_run times
hermes cron run <slack-job-id>                # fires on next tick (~60s)
cat ~/tasks/inbox.md                          # new section appended
hermes cron run <today-job-id>                # 9 AM digest fires immediately for testing
hermes logs | grep -i cron | tail -20
```

Open your DM with the bot in Slack. You should see the hourly summary and the 9 AM digest arrive there -- privately, not in a public channel.

## Day-to-day usage

- **DM the bot** any time: "add TODO: buy milk" -> it appends to `~/tasks/inbox.md` using file tools in the live session.
- **@mention in a channel** the bot's been invited to: "@hermes_bot what's my day look like?" -> it can run `today --dir ~/tasks` itself and answer.
- **Hourly**: new Slack messages -> agent reads, posts summary to your DM, prepends action items to `inbox.md`.
- **9 AM**: `today` reads everything due (auto-extracted + anything you added) -> priority plan posted to your DM.
- **Edit tasks directly**: open `~/tasks/inbox.md` in your editor; `today` reads it as-is next run.

## How "private" works at each layer

| Surface | Who sees it | Configured by |
|---|---|---|
| Cron job delivery (`--deliver slack`) | You only -- lands in your DM (`D...`) | `SLACK_HOME_CHANNEL=D0...` |
| Interactive DM with the bot | You only -- 1:1 DM | Always private; no config needed |
| `@mention` in a public channel | Everyone in the channel sees the reply | Don't @mention in public if you want privacy -- DM instead |
| `group_sessions_per_user: true` (default) | Each user's channel session is isolated | Already the default |
| `unauthorized_dm_behavior: pair` (default) | Unknown DMers get a pairing code; you approve | Already set |

The key behavior: **anything you say to the bot in DM stays in DM**. Cron jobs that `--deliver slack` go to `SLACK_HOME_CHANNEL`, which is your DM. The only way cron output leaks publicly is if you `--deliver slack:C...` explicitly -- don't do that.

Optional further lockdown in `~/.hermes/config.yaml`:

```yaml
slack:
  allowed_channels:
    - "D0YOURDMCHANNELID"     # your DM only; everything else dropped
  unauthorized_dm_behavior: "ignore"   # no pairing flow; unknown DMers silently dropped
```

## Files

```
slack-todo-bot/
|-- README.md                      # this file
`-- scripts/
    |-- slack-digest.py            # hourly: pull new Slack msgs via Web API
    `-- today-digest.py            # 9 AM: run `today` CLI over ~/tasks/*.md
```

The runtime copies live in `~/.hermes/scripts/`, outside this repo. Hermes cron `--script` points there.

## Troubleshooting

- **`missing_scope: connections:write` on `apps.connections.open`** -- the app-level `xapp-` token lacks the `connections:write` scope. Settings -> Basic Information -> App-Level Tokens -> generate a new one WITH the scope. Update `~/.hermes/.env` `SLACK_APP_TOKEN`, `hermes gateway restart`.
- **`missing_scope: groups:read` on `users.conversations`** -- non-fatal. Socket Mode still works, but Hermes can't list private channels. Add `groups:read` to bot scopes, reinstall app, restart gateway.
- **Bot doesn't respond in `#general`** -- you haven't invited it. `/invite @hermes_bot` in the channel.
- **Cron job silently does nothing** -- check `hermes cron list` shows the job `[active]` with a next_run time. Check `hermes logs | grep -i cron`. If `today-digest.py` reports "not installed", the launchd service PATH doesn't include `~/.local/bin` (see step 9).
- **`NO_CHANGE` every run** -- for `slack-digest.py`, this means no new messages since the last run in the watched channels. Check `SLACK_WATCH_CHANNELS` is set to channel IDs the bot is a member of. For `today-digest.py`, it means `today` produced no output (no tasks due today).
- **Secrets leaked in chat** -- if you pasted Slack secrets in a logged conversation, rotate all of them: reinstall the app (rotates `xoxb-`), regenerate signing secret + client secret, delete and regenerate the `xapp-` token. Update `~/.hermes/.env` lines 345-346, `hermes gateway restart`.

## Security notes

- The two scripts are stdlib-only (no third-party packages). They read `SLACK_BOT_TOKEN` from the environment and never log it.
- `~/.hermes/.env` must be `chmod 600`. Hermes refuses to load it otherwise.
- State files (`.slack-state.json`) are written with `0o600` permissions.
- Hermes has built-in secret redaction: tool output, logs, and chat responses are scrubbed before delivery (visible in gateway logs as "Secret redaction: ENABLED").
- The bot is deny-by-default: without `SLACK_ALLOWED_USERS`, nobody can talk to it.
- Never commit `~/.hermes/.env` to git. This repo contains only the scripts and docs -- no secrets.

## Design and implementation

- **Architecture**: Hybrid two-job -- hourly Slack scan extracts action items to `~/tasks/inbox.md` with `[d:t]` + posts summary; 9 AM `today` digest posts priority plan. Chosen over a single combined job (different cadences) or two read-only jobs (extraction needs file write).
- **No separate "Slack skill" needed**: Slack is a built-in Hermes gateway; cron uses a script to pull history (since cron agent can't call Slack interactively).
- **`agent_view` not `assistant_view`**: `assistant_view` is deprecated; `agent_view` is required for `app_context_changed` and the modern DM surface. Irreversible once enabled.
- **Generate manifest via `hermes slack manifest --agent-view --write`** rather than hand-maintaining, to stay in sync after `hermes update`. The manifest above is the hand-authored equivalent.

## License

This repo's contents (scripts, README) inherit the project's default. Hermes Agent itself is MIT-licensed by Nous Research.
