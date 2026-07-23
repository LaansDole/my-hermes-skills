# slack-todo-bot

A Hermes Agent skill that makes your Slack bot summarize today's activity on demand -- ask it "summarize today's Slack" or "what's in #channel today?" and it recaps every channel/DM it's in, right now, no scheduling required. Optional cron automation (hourly Slack/Jira/GitHub scans + a 9 AM "today" digest) can be layered on top for unattended delivery, but isn't required to get value. No public channel posts, no inbound ports, no cloud -- just Socket Mode + local files.

Built on [Hermes Agent](https://hermes-agent.nousresearch.com/) (Nous Research, MIT). Uses the built-in Slack gateway (Socket Mode / WebSocket), so it works behind your firewall with no public URL.

## How it works

```
[Slack workspace]        [Jira Cloud]              [GitHub]
       |  Socket Mode           |  REST API (optional)     |  REST API (optional)
       v  (WebSocket)           v                           v
[Hermes gateway]  <-- launchd service on your Mac, holds 1 persistent WSS
       |
       |-- per-chat AIAgent sessions (interactive DMs / channels)
       |       |
       |       `-- on demand: skills/slack-scan  -->  "summarize today" / "what's in #x?"
       |                          |
       |                          v
       |            fetches today's history via Slack Web API, replies in chat
       |            (nothing persisted unless you ask it to save)
       |
       |-- cron scheduler (ticks every 60s, optional -- see "Add the cron jobs")
       |       |
       |       |-- hourly: slack-digest.py   -->  pulls new Slack msgs
       |       |-- hourly: jira-digest.py    -->  pulls new Jira activity
       |       |-- hourly: github-digest.py  -->  pulls new GitHub activity
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
- (Optional) A Jira Cloud site with an API token, and/or a GitHub personal access token -- only needed if you enable the Jira/GitHub digests in step 8.

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

Optional Jira/GitHub vars (`JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`, `GITHUB_TOKEN`, ...) are documented in [`.env.example`](.env.example) and covered in step 8 below -- skip them for now if you only want the Slack + `today` digests.

### 6. Install the `today` CLI

```bash
uv tool install todo-today-cli
# -> installs ~/.local/bin/today
today --version
```

This is what the 9 AM digest cron job runs to read your task files.

### 7. Copy the scripts into place

```bash
mkdir -p ~/.hermes/scripts
cp slack-todo-bot/scripts/slack-digest.py  ~/.hermes/scripts/
cp slack-todo-bot/scripts/today-digest.py  ~/.hermes/scripts/
cp slack-todo-bot/scripts/jira-digest.py   ~/.hermes/scripts/
cp slack-todo-bot/scripts/github-digest.py ~/.hermes/scripts/
chmod +x ~/.hermes/scripts/{slack,today,jira,github}-digest.py
```

Verify they compile:

```bash
python3 -m py_compile ~/.hermes/scripts/{slack,today,jira,github}-digest.py && echo OK
```

### 8. Get Jira and GitHub API credentials (optional)

Skip this step entirely if you only want the Slack + `today` digests -- `jira-digest.py` and `github-digest.py` degrade to `NO_CHANGE` when unconfigured, so leaving them out breaks nothing.

**Jira** (priority integration):

1. Go to https://id.atlassian.com/manage-profile/security/api-tokens -> **Create API token** -> name it `hermes-cron` -> copy the token.
2. Note your Jira Cloud site URL (e.g. `https://yourcompany.atlassian.net`) and the email you log into Jira with.

**GitHub:**

1. Go to https://github.com/settings/tokens -> **Generate new token (classic)** -> scope: `repo` (or `public_repo` if you only care about public repos) -> generate -> copy the token.
2. Fine-grained tokens work too: grant `Issues: Read-only` and `Pull requests: Read-only` on the repos you want covered.

Add both sets of credentials to `~/.hermes/.env` per [`.env.example`](.env.example):

```bash
JIRA_BASE_URL=https://yourcompany.atlassian.net
JIRA_EMAIL=you@yourcompany.com
JIRA_API_TOKEN=...
GITHUB_TOKEN=ghp_...
```

```bash
chmod 600 ~/.hermes/.env
```

### 9. Seed the task file

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

### 10. Make sure the gateway service can find `today` on PATH

The launchd service does NOT inherit your shell PATH by default. If `~/.local/bin` (where `uv tool install` puts `today`) is not on the service PATH, `today-digest.py` will report "not installed". Either:

- Add to `~/.hermes/config.yaml`:
  ```yaml
  gateway:
    extra_env:
      PATH: "/Users/<you>/.local/bin:/usr/local/bin:/usr/bin:/bin"
  ```
  Then `hermes gateway install --force` to re-write the launchd plist.

- Or symlink `today` into `/usr/local/bin` (if you have write access).

### 11. Install and start the gateway

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

### 12. Invite the bot to any channels you want it to scan

```
# In Slack, inside each channel:
/invite @hermes_bot
```

The bot will not auto-join. For the hourly scan to read a channel's history, the bot must be a member. DMs (the home channel) need no invite.

### 13. Install the on-demand summary skill (`slack-scan`)

Hermes only auto-discovers skills under `~/.hermes/skills/` -- `SKILL.md` files that live inside
this git repo are **not** picked up automatically, no matter how much the bot's system prompt
references them. Copy the skill across and restart the gateway so it's actually loaded:

```bash
mkdir -p ~/.hermes/skills/slack-scan
cp ../skills/slack-scan/SKILL.md ~/.hermes/skills/slack-scan/SKILL.md
hermes skills list | grep slack-scan     # expect: local | enabled
hermes gateway restart
```

If you edit `skills/slack-scan/SKILL.md` in this repo later, re-run the `cp` and
`hermes gateway restart` -- the repo copy and the live copy under `~/.hermes/skills/` do not sync
automatically; they're two separate files.

Skip this step only if you're setting up the cron jobs exclusively and don't want the on-demand
"summarize today" ability -- cron jobs use plain scripts, not this skill.

## After setup

Once the gateway is connected and `~/.hermes/.env` is in place, the minimum to get value is:

1. **Invite the bot to `#general`** (and any other channel you want it to be able to summarize):

   ```
   # In Slack, inside #general:
   /invite @hermes_bot
   ```

   The bot will not auto-join. DMs (the home channel) need no invite. See step 12 above for details.

2. **Install the `slack-scan` skill** -- step 13 above. Without it the bot will tell you it "doesn't
   have access to Slack's API" instead of summarizing anything (see [Troubleshooting](#troubleshooting)
   if this happens after you thought you'd already done this).

3. **DM it**: "summarize today's Slack" or "what's in #general today?" -- see
   [`skills/slack-scan`](../skills/slack-scan/SKILL.md). That's it; no cron required.

The cron jobs below (hourly Slack/Jira/GitHub scan + 9 AM digest) are optional automation on top
of that -- set them up whenever you want scheduled, unattended delivery instead of asking on
demand. Skip straight to [Verify](#verify) if you're not setting up cron yet.

## Add the cron jobs

Four jobs (or two, if you skipped Jira/GitHub), all `--deliver slack` (routes to `SLACK_HOME_CHANNEL`, i.e. your private DM).

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

### Job 3 -- hourly Jira scan + TODO extraction

```bash
hermes cron add "every 1h" \
  "You receive script output describing Jira issues assigned to me with new activity since the last run.

Do TWO things:

1. POST A SUMMARY to Slack: flag anything urgent or blocking at the top (by priority/status), then list the rest.

2. EXTRACT ACTION ITEMS to /Users/<you>/tasks/inbox.md. For any issue that isn't already Done, append a Markdown checkbox with [d:t], tagged with its Jira key so re-runs don't duplicate it. Prepend a new section:

## From Jira - <YYYY-MM-DD HH:MM>
- [ ] [PROJ-123] <concise summary> [d:t]

Rules: create file if missing; prepend new section if exists; do not duplicate an item whose Jira key already appears anywhere in the file; one line per item under 80 chars.

If the script output says NO_CHANGE, respond with only [SILENT] and do not modify any file.
Otherwise end your Slack reply with one line: 'Added N TODO(s) to today's list.'" \
  --script ~/.hermes/scripts/jira-digest.py \
  --name "Jira scan + TODO extract" \
  --deliver slack
```

### Job 4 -- hourly GitHub scan + TODO extraction

```bash
hermes cron add "every 1h" \
  "You receive script output describing GitHub issues/PRs assigned to me or awaiting my review, with new activity since the last run.

Do TWO things:

1. POST A SUMMARY to Slack: flag PRs awaiting my review at the top, then assigned issues/PRs.

2. EXTRACT ACTION ITEMS to /Users/<you>/tasks/inbox.md. For any item needing action from me, append a Markdown checkbox with [d:t], tagged with its repo#number so re-runs don't duplicate it. Prepend a new section:

## From GitHub - <YYYY-MM-DD HH:MM>
- [ ] [owner/repo#123] <concise action item> [d:t]

Rules: create file if missing; prepend new section if exists; do not duplicate an item whose repo#number already appears anywhere in the file; one line per item under 80 chars.

If the script output says NO_CHANGE, respond with only [SILENT] and do not modify any file.
Otherwise end your Slack reply with one line: 'Added N TODO(s) to today's list.'" \
  --script ~/.hermes/scripts/github-digest.py \
  --name "GitHub scan + TODO extract" \
  --deliver slack
```

## Verify

```bash
hermes cron list                              # every job you added is [active] with next_run times
hermes cron run <slack-job-id>                # fires on next tick (~60s)
hermes cron run <jira-job-id>                 # if Jira credentials are set
hermes cron run <github-job-id>               # if GitHub credentials are set
cat ~/tasks/inbox.md                          # new section(s) appended
hermes cron run <today-job-id>                # 9 AM digest fires immediately for testing
hermes logs | grep -i cron | tail -20
```

Open your DM with the bot in Slack. You should see the hourly summary and the 9 AM digest arrive there -- privately, not in a public channel.

## Day-to-day usage

**Cron jobs (Job 1/2/3/4 below) are optional and not required to get value from the bot.** If you
haven't set any up yet, the bot is still useful right now:

- **Ask for today's summary any time**: "@hermes_bot summarize today's Slack" or "what did I miss
  today?" -> the [`slack-scan`](../skills/slack-scan/SKILL.md) skill recaps every channel/DM the
  bot is in since midnight, in the reply, immediately. Name a channel ("what's in #eng-team
  today?") to scope it to just that one. No cron, no `SLACK_WATCH_CHANNELS`, nothing persisted.
- **DM the bot** any time: "add TODO: buy milk" -> it appends to `~/tasks/inbox.md` using file tools in the live session.
- **@mention in a channel** the bot's been invited to: "@hermes_bot what's my day look like?" -> it can run `today --dir ~/tasks` itself and answer.

If you do turn the cron jobs on later:

- **Hourly**: new Slack messages, Jira activity, and GitHub activity -> agent reads each, posts a summary to your DM, prepends action items to `inbox.md`.
- **9 AM**: `today` reads everything due (auto-extracted from all three sources + anything you added) -> priority plan posted to your DM.
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
|-- .env.example                   # annotated env var reference (Slack + Jira + GitHub)
`-- scripts/
    |-- slack-digest.py            # hourly: pull new Slack msgs via Web API
    |-- jira-digest.py             # hourly: pull new Jira activity via REST API (optional)
    |-- github-digest.py           # hourly: pull new GitHub activity via REST API (optional)
    `-- today-digest.py            # 9 AM: run `today` CLI over ~/tasks/*.md
```

Plus, one directory up: `../skills/slack-scan/SKILL.md` -- the on-demand summary skill. It must be
copied to `~/.hermes/skills/slack-scan/` (step 13); files under this repo path are never
auto-discovered by Hermes.

The runtime copies live in `~/.hermes/scripts/`, outside this repo. Hermes cron `--script` points there.

## Troubleshooting

- **`missing_scope: connections:write` on `apps.connections.open`** -- the app-level `xapp-` token lacks the `connections:write` scope. Settings -> Basic Information -> App-Level Tokens -> generate a new one WITH the scope. Update `~/.hermes/.env` `SLACK_APP_TOKEN`, `hermes gateway restart`.
- **`missing_scope: groups:read` on `users.conversations`** -- non-fatal. Socket Mode still works, but Hermes can't list private channels. Add `groups:read` to bot scopes, reinstall app, restart gateway.
- **Bot doesn't respond in `#general`** -- you haven't invited it. `/invite @hermes_bot` in the channel.
- **Cron job silently does nothing** -- check `hermes cron list` shows the job `[active]` with a next_run time. Check `hermes logs | grep -i cron`. If `today-digest.py` reports "not installed", the launchd service PATH doesn't include `~/.local/bin` (see step 10).
- **`NO_CHANGE` every run** -- for `slack-digest.py`, this means no new messages since the last run in the watched channels; check `SLACK_WATCH_CHANNELS` is set to channel IDs the bot is a member of. For `today-digest.py`, it means `today` produced no output (no tasks due today). For `jira-digest.py`/`github-digest.py`, either there's no new activity, or the credentials aren't set yet -- both scripts print a one-line hint instead of bare `NO_CHANGE` when unconfigured.
- **`jira-digest.py` prints a 401/403 API error** -- the API token is wrong, expired, or the email doesn't match the token's owner. Regenerate at https://id.atlassian.com/manage-profile/security/api-tokens.
- **`github-digest.py` prints a 401 "Bad credentials"** -- the token is invalid or expired. Regenerate at https://github.com/settings/tokens. A 403 usually means the token lacks `Issues`/`Pull requests` read access on a repo it's trying to list.
- **Secrets leaked in chat** -- if you pasted Slack/Jira/GitHub secrets in a logged conversation, rotate all of them: reinstall the Slack app (rotates `xoxb-`), regenerate the Slack signing secret + client secret, delete and regenerate the `xapp-` token, and regenerate the Jira API token / GitHub PAT. Update `~/.hermes/.env`, `hermes gateway restart`.
- **Bot says "I don't have access to Slack's API to search channel history..."** -- the
  `slack-scan` skill isn't installed at `~/.hermes/skills/slack-scan/`. Repo files are never
  auto-discovered. Run step 13, confirm with `hermes skills list | grep slack-scan` (expect
  `local | enabled`), then `hermes gateway restart`.
- **Bot returns a vague `:warning: The model provider failed after retries` in Slack** -- Hermes
  deliberately keeps raw provider errors out of chat. Check `~/.hermes/logs/gateway.error.log` for
  the actual error. Model selection (`/model`) is scoped **per chat/session**, not global -- a
  Slack thread can be stuck pointing at a model your local backend (e.g. LM Studio) refuses to
  load, commonly reported as "insufficient system resources" for models too large for your
  machine's RAM. Fix it in that same Slack chat with `/model` and pick a smaller model confirmed
  loadable (e.g. via `curl http://127.0.0.1:1234/v1/models`) -- editing `~/.hermes/config.yaml`
  only changes the default for brand-new sessions, not the stuck thread.

## Security notes

- All four scripts are stdlib-only (no third-party packages). They read their tokens from the environment and never log them.
- `~/.hermes/.env` must be `chmod 600`. Hermes refuses to load it otherwise.
- State files (`.slack-state.json`, `.jira-state.json`, `.github-state.json`) are written with `0o600` permissions.
- Hermes has built-in secret redaction: tool output, logs, and chat responses are scrubbed before delivery (visible in gateway logs as "Secret redaction: ENABLED").
- The bot is deny-by-default: without `SLACK_ALLOWED_USERS`, nobody can talk to it.
- Jira/GitHub credentials are read-only in scope (API token / PAT with read scopes) -- neither script writes back to Jira or GitHub.
- Never commit `~/.hermes/.env` to git. This repo contains only the scripts and docs -- no secrets.

## Design and implementation

- **Architecture**: Hybrid multi-source -- hourly Slack/Jira/GitHub scans each extract action items to `~/tasks/inbox.md` with `[d:t]` + post a per-source summary; 9 AM `today` digest posts the combined priority plan. Jira/GitHub are additive and optional (graceful `NO_CHANGE` when unconfigured) so the original two-job Slack setup keeps working unmodified.
- **`skills/slack-scan` is a real Hermes skill, not just a script**: unlike the cron jobs (which
  use plain Python scripts because the cron agent can't call Slack interactively), the on-demand
  "summarize today" ability is implemented as a `SKILL.md` loaded via Hermes's skills system --
  it must be installed under `~/.hermes/skills/` (step 13) to be discoverable at all.
- **`agent_view` not `assistant_view`**: `assistant_view` is deprecated; `agent_view` is required for `app_context_changed` and the modern DM surface. Irreversible once enabled.
- **Generate manifest via `hermes slack manifest --agent-view --write`** rather than hand-maintaining, to stay in sync after `hermes update`. The manifest above is the hand-authored equivalent.

## License

This repo's contents (scripts, README) inherit the project's default. Hermes Agent itself is MIT-licensed by Nous Research.
