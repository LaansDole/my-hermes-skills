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
- Auto-react (opt-in): `--react` or `SLACK_MENTION_REACT=1` adds `:raised_hands:` to thanks, `:memo:`
  to a clear FYI (fyi, done, merged, lgtm, ...), and `:eyes:` to every other ping, as you, on each new mention of a tick, never sooner than 60 s
  after the mention was posted (`SLACK_MENTION_REACT_DELAY_SECS`). Needs the user scope
  `reactions:write`; skipped if you already reacted to or replied to it; `--dry-run` previews it
  (rules and setup in `SKILL.md`).
- Background review agent (opt-in): `scripts/review_spawn.py` wraps the digest; with
  `SLACK_REVIEW_AGENT=omp|claude|custom` each new mention that names a GitHub PR (optionally a
  ticket key) starts a detached, headless, read-only review session in `SLACK_REVIEW_WORKDIR`,
  and the digest item gets a `review: <id> (...) -> cd <workdir> && <agent> --resume <id>` line.
  Merged/closed/approved/already-reviewed PRs and thanks/FYI mentions are skipped; 24 h dedupe,
  max 3 spawns per tick; `--dry-run` previews. Off = digest unchanged (setup interview, config
  and skip rules in `SKILL.md`).

## System design

### Components

| Component | Where | Role |
| --- | --- | --- |
| `watch_mentions.py` | this skill, `scripts/` | Stdlib-only Slack client. Finds new mentions, dedupes, renders output; GET to an allowlisted read method, plus `reactions.add` when auto-react is on. |
| `review_spawn.py` | this skill, `scripts/` | Opt-in digest wrapper: runs `watch_mentions.py --digest --react`, starts a read-only review agent per new PR mention, annotates the digest. No Slack calls. |
| Cron wrapper(s) | `~/.hermes/scripts/slack_mention_{watch,digest}_cron.py` | Real files (cron rejects symlinks) that `runpy` the skill script; the digest wrapper injects `--digest` because cron passes no args. |
| Hermes cron job | `~/.hermes/cron/jobs.json` | Runs the wrapper on a schedule (`every 5m`), optionally wakes an LLM, delivers to Slack. |
| State file | `~/.hermes/scripts/.slack-mention-watch.json` (600) | `last_ts` high-water mark + last 500 `channel:ts` keys. No message text. |
| Hermes gateway | launchd/systemd service | Owns the bot's Socket Mode connection; the scheduler that runs cron jobs lives inside it. |
| Slack app | api.slack.com/apps | One app, two tokens: `xoxp-` user token (read: search + history) and `xoxb-` bot token (names, delivery). |

### Data flow (digest mode)

```
 every 5 min (Hermes gateway scheduler)
        |
        v
 slack_mention_digest_cron.py --runpy--> watch_mentions.py --digest
        |
        |  1. config(): watched user = SLACK_MENTION_USER_ID
        |       > owner of SLACK_USER_READ_TOKEN (auth.test) > first SLACK_ALLOWED_USERS id
        |  2. search.messages "<@USER>" since last_ts - 10 min      (xoxp, search:read)
        |       (no user token -> conversations.history on channels the bot is in)
        |  3. drop: home DM channel, bot's own posts, SLACK_MENTION_IGNORE_USERS
        |  4. dedupe against state.seen
        |  5. per new mention: conversations.replies -> thread context (xoxp, *:history)
        |     users.info -> display names (xoxb, users:read); chat.getPermalink
        |     --react: classify(text) -> reactions.add (xoxp, reactions:write)
        |  6. save new last_ts + seen                              (state advances HERE,
        |                                                           before the LLM runs)
        v
 stdout
   nothing new / offline / rate-limited  -> {"wakeAgent": false}  -> no LLM, nothing sent
   new mentions -> "NEW MENTIONS: N ... now: <weekday date>" + dated threads
        |
        v
 LLM cron agent (pinned model/provider; toolsets = todo,no_mcp -> cannot message anyone)
   triage prompt -> ACTION PLAN | REVIEW | REPLY | NO ACTION
        |
        v
 Hermes delivers final reply -> SLACK_HOME_CHANNEL (your DM with the bot)  <- delivery write
```

Alert mode (`--no-agent`) is the same pipeline minus thread context and the LLM: stdout is posted verbatim,
empty stdout posts nothing. Run one mode or the other, never both -- they share the state file.

### Design decisions

- **Polling, not events.** The bot only receives events for channels it's in and for its own
  `@bot` mentions; a user's mentions everywhere are only reachable via `search.messages`, which
  needs a *user* token. Hence cron polling.
- **Script gate before the LLM.** The script decides whether there is anything to say; the model
  never fetches data or runs commands. Idle ticks cost zero tokens, and models that misuse tools
  can't break the pipeline.
- **Least-privilege everywhere.** Read scopes only unless you grant `reactions:write`, `api()`
  refuses non-allowlisted methods and `api_write()` accepts exactly one, and the agent's toolsets
  are pinned to `todo,no_mcp` (an empty list would mean the default toolset, including messaging
  as the bot). Delivery is done by the scheduler, not the model.
- **Rules, not an LLM, pick the emoji.** The digest agent stays toolless; classification runs in
  the same tick and is unit-tested.
- **Overlap + dedupe.** Each tick re-scans 10 minutes behind `last_ts` because search indexing lags;
  `seen` keys prevent duplicates.
- **Self-loop guard.** Alerts quote the mention, so search would find them again; the home channel
  and bot user are always filtered out.
- **Dated context.** Every line carries weekday + date and a `now:` header, so the model never
  infers days.
- **One item per thread, four buckets.** ACTION PLAN only for new, unstarted work; REVIEW for
  PRs/verification; REPLY for direct questions; NO ACTION for thanks/FYI/resolved.

### Failure modes

| Failure | Behaviour |
| --- | --- |
| Slack 429 / offline (`URLError`) | Tick skipped, state not advanced, `{"wakeAgent": false}`; next tick catches up. |
| Slack read timeout on wake from sleep (`TimeoutError`) | Not caught as a network error: script exits 1 and the agent is woken with the traceback. Next tick recovers. Known gap. |
| Thread fetch fails | Mention kept with `(thread context unavailable: <error>)`. |
| LLM provider error (403/5xx, exhausted key) | State already advanced at step 6, so those mentions are **not** retried. Recover with `--recent`, or rewind `last_ts`/remove keys from `seen` and `hermes cron run <id>`. Clear a stuck credential with `hermes auth reset <provider>`. |
| Machine asleep / logged out | Nothing runs (user services start only after login; disk encryption usually blocks auto-login); on wake the gateway reconnects Socket Mode and the first tick picks up everything since `last_ts`. |

## Privacy

Reads only: GET requests to an 8-method allowlist (search, history, thread, user/permalink
lookups). The one write is opt-in auto-react (`reactions.add`, POST, the only method `api_write()`
accepts); without `--react`/`SLACK_MENTION_REACT` nothing is written at all. It never posts, marks
read or joins channels. The cron alert itself is sent by Hermes to your own bot DM. State
(`~/.hermes/scripts/.slack-mention-watch.json`, mode 600) holds timestamps and message keys, no
message text.

Opt-in Jev shadow mode (`SLACK_MENTION_JEV_SHADOW=1` + `TYPESAFE_API_KEY`) is the only non-Slack
request the script itself makes: each new mention and its thread go to `api.typesafe.ai`, and a
local log (`~/.hermes/scripts/.slack-mention-jev.jsonl`, mode 600) **does** hold message text.
Off by default; changes no output or reaction.
