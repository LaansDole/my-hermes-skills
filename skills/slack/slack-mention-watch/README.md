# slack-mention-watch

A [Hermes Agent](https://hermes-agent.nousresearch.com/) skill for the Slack gateway: ask "who
pinged me?" and get every Slack message that `@`-mentions you, or get a DM from your Hermes bot
for each new mention while you're away. Python stdlib only.

## Setup

1. Copy or symlink this folder to `~/.hermes/skills/slack/slack-mention-watch`.
2. https://api.slack.com/apps -> your Hermes bot's app -> OAuth & Permissions -> User Token
   Scopes -> add `search:read`.
3. Reinstall the app to the workspace, approving as yourself.
4. Put the `xoxp-` User OAuth Token in `~/.hermes/.env` as `SLACK_USER_READ_TOKEN=xoxp-...`.
   (Without it the script falls back to the bot token and only sees channels the bot was
   `/invite`d to.)
5. `python3 ~/.hermes/skills/slack/slack-mention-watch/scripts/watch_mentions.py --check` ->
   expect `mode: search`.

## Use

- Ask Hermes "any Slack pings today?" -- it runs `watch_mentions.py --recent 24`.
- `/pings`: a `quick_commands` exec entry in `~/.hermes/config.yaml` that runs the script without
  the LLM (snippet in `SKILL.md`).
- Away alerts: a `hermes cron create "every 5m" ... --no-agent --deliver slack` job; silent when
  nothing is new (wrapper + command in `SKILL.md`).
- Triage digest: instead of verbatim alerts, `watch_mentions.py --digest` feeds new mentions plus
  their threads (each line dated with weekday) to an LLM cron agent that sorts them into action
  plan / review / reply / no action; no LLM run when nothing is new. Thread context needs the user
  scopes `channels:history`, `groups:history`, `im:history`, `mpim:history` (wrapper, prompt,
  command, model/provider and tool-restriction notes in `SKILL.md`).

## Privacy

Read-only: GET requests to an 8-method allowlist (search, history, thread, user/permalink lookups). It never
posts, reacts, marks read or joins channels. The only write is the cron alert, sent by Hermes to
your own bot DM. State (`~/.hermes/scripts/.slack-mention-watch.json`, mode 600) holds timestamps
and message keys, no message text.
