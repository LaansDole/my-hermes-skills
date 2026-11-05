---
name: slack-mention-watch
description: Use when the user asks about Slack pings, mentions or what they missed, or wants @mention alerts or a triaged digest while away; can opt-in auto-react (:eyes: to questions, :raised_hands: to thanks).
version: 2.4.1
author: LaansDole
license: MIT
metadata:
  hermes:
    tags: [slack, notifications, monitoring, cron]
    category: slack
    requires_toolsets: [terminal]
---

# Slack @mention watch

Lists Slack messages that `@`-mention the user, on demand or as background alerts. Reads only,
apart from one opt-in write: `--react` adds an emoji to each new mention (see "Auto-react"). Not
for: summarizing a day of Slack (use `slack-scan`), replying, keyword watches, or
`@here`/`@channel` pings.

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

Alternative to the verbatim alerts: an LLM cron agent sorts each new mention into action plan /
review / reply / no action, using the surrounding thread. Use it *instead of* the alert job, not beside
it -- both advance the same state file, so whichever runs first would hide mentions from the other.

`watch_mentions.py --digest` runs the same tick as the default mode (same filters, dedupe and state;
`--dry-run` still saves nothing), then:

- nothing new (or a rate-limited/offline tick) -> prints only `{"wakeAgent": false}`. Hermes treats
  that last stdout line as a gate and skips the agent run: no LLM call, nothing delivered.
- otherwise -> a plain-text context block, oldest mention first:

  ```
  NEW MENTIONS: N   (watched user: @name)   now: Tue 2026-10-13 08:30 +07
  ### Mention 1 -- #channel -- from <sender> at Mon 2026-10-12 14:49
  Permalink: <url>
  Mention: <text>
  Thread (k messages):
  [Mon 10-12 14:39] sender: text
  ```

  All times are local; every line carries its weekday and date, and `now:` gives the model
  "today", so it never has to infer days.

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

`--model <model> --provider <provider>` pin the job's model. Anthropic-family models on a gateway
that exposes both OpenAI-chat and Anthropic-messages APIs may need the provider's Anthropic
variant: e.g. Claude models via Command Code use `--provider commandcode-anthropic`; with plain
`commandcode` they fail with HTTP 400 'must be called via /provider/v1/messages'.

Restrict the job's tools: the agent only needs the script output it is given. `hermes cron
create`/`edit` have no toolset flag, and a job without `enabled_toolsets` (or with an empty list)
gets the default cron toolset -- including `terminal`, which can reach Slack with the bot token in
`~/.hermes/.env` and post as the bot. Either create/update the job through the agent's cronjob tool
(`cronjob_manage`) with `enabled_toolsets=["todo","no_mcp"]`, or set
`"enabled_toolsets": ["todo", "no_mcp"]` on the job in `~/.hermes/cron/jobs.json`. (`no_mcp` keeps
MCP servers from being merged back in.)

Save the prompt below as `~/.hermes/scripts/slack_mention_digest_prompt.txt` first (or paste it
as the quoted prompt argument). The script output is injected into it on every run. No `--no-agent`:
the agent writes the delivered message. If an alert job already exists, remove it
(`hermes cron remove <id>`) once the digest job works.

Cron agent prompt:

```text
You receive new Slack @mentions of the user, each with its thread context, in the script output
above. Triage them into a short Slack-friendly digest (plain text). Sort each thread into exactly
one bucket:

1. ACTION PLAN -- ONLY when the user is asked to do new work that needs planning (build, document,
   investigate, decide) and the thread does not show it already done or in progress by the user.
   For each:
   - Goal (1 line)
   - Context (problem, current workaround, concrete numbers from the thread)
   - Questions to clarify (2-5, aimed at who to ask)
   - Tasks (3-6 concrete steps)
   - Where it could live (suggestion)
2. REVIEW -- review a PR or link, approve, check a fix or verify on staging; includes the user's own
   open PRs waiting on someone. One line: what + links.
3. REPLY -- a direct question that just needs an answer from the user (status, yes/no, "have you
   tested X?"). One line: who asked, what; add a short suggested answer only if the thread makes
   it obvious, marked "(suggestion)".
4. NO ACTION -- thanks, FYI, "approved", resolved, or already handled by the user. One line each.

Rules:
- Use the dates and weekdays exactly as given in the input (the first line has "now"). Never
  infer or compute a weekday.
- If the user already replied in the thread with a commitment ("will do", "on it"), it is not
  NO ACTION unless the thread shows it resolved.
- At most one item per thread: merge mentions from the same thread into one item.
- Order: ACTION PLAN, REVIEW, REPLY, NO ACTION. Include each item's permalink.
- Never invent facts not in the thread; mark assumptions.
- Output plain text only. Do not call tools.
- Even if every item is NO ACTION, still send the one-line list so nothing is hidden. Reply
  exactly [SILENT] only if the script output contains no mentions.
- Read-only: never suggest posting on the user's behalf. Reactions shown as `Reacted:` were
  applied by the script; do not mention adding more.
```

## Auto-react (opt-in)

`--react` (or `SLACK_MENTION_REACT=1`) makes the script add one emoji, as the user, to every NEW
mention of a default or `--digest` tick. Off by default; never in `--recent`, `--check` or history
mode. Rules are deterministic (no LLM), first match wins, and Slack link/user markup is stripped
before matching so a URL's `?` is not read as a question:

| Mention | Signal | Reaction |
| --- | --- | --- |
| Question or request | `?`, or can/could/would/will you, please, pls, review, check, take a look, help, need you, PTAL, any update, lmk, let me know, question* (question, questions, ...), let's/lets, can/could/should we, can/could I, is it ok(ay), are you able, wdyt, thoughts | `:eyes:` |
| Thanks | thanks, thank you, thx, ty, tks, cam on | `:raised_hands:` |
| Clear FYI | fyi, I've/I have/I commented, commented on/in, done, merged, deployed, released, approved, lgtm, resolved, nvm | `:memo:` |
| Anything else | a direct ping is a request by default (follow-ups like "one UX question. I expected..." or "Let's ... use X") | `:eyes:` |

Skipped (one `conversations.replies` call, checked after the wait below), output
`Reacted: none (...)`:

- `already reacted` -- the user's own emoji, any name, is already on the mention itself (a
  reaction on the thread root does not count, someone else's reaction does not count);
- `already replied` -- the user posted in that thread after the mention.

The lookup is `conversations.replies(ts=<thread root>, oldest=<mention ts>, inclusive=true)`.
`search.messages` matches never carry `thread_ts` -- the root is only in the permalink's
`?thread_ts=` -- and `conversations.replies` with a reply's own ts returns just that one message,
so passing the mention ts would never see the user's later replies.

A reaction is never sent sooner than 60 s after the mention was posted
(`SLACK_MENTION_REACT_DELAY_SECS`, `0` disables) -- an instant reply looks like a bot; the tick
sleeps out the remainder. Cron ticks every 5 min, so the usual delay is 1-5 min and most mentions
are already older than a minute, so nothing sleeps. `already_reacted` counts as success. A failed
write prints one stderr line `react failed on <channel>:<ts>: <error>`, the tick still advances
state, and the output line reads `Reacted: failed (...)` -- no retry storms, no duplicate digest.

Setup:

1. https://api.slack.com/apps -> your app -> **OAuth & Permissions** -> **User Token Scopes** ->
   add `reactions:write`, then **Reinstall to Workspace**.
2. `watch_mentions.py --check` now prints `react scope: yes`.
3. Preview without writing:
   `python3 ~/.hermes/scripts/slack_mention_digest_cron.py --dry-run --react`
   -> each mention shows `Reacted: :eyes: (dry run, not sent)`.
4. Enable in the cron wrapper: `sys.argv = [TARGET, "--digest", "--react", *sys.argv[1:]]`
   (or put `SLACK_MENTION_REACT=1` in `~/.hermes/.env`).

Reactions use `SLACK_USER_REACT_TOKEN` if set, else `SLACK_USER_READ_TOKEN`; a separate token lets
the read scope stay on a token you never grant writes to.

## Write guarantee

Reads go through `api()`: HTTP GET only, and `ValueError` for any method outside `READ_METHODS`
(`auth.test`, `search.messages`, `conversations.list`, `conversations.history`,
`conversations.info`, `conversations.replies`, `users.info`, `chat.getPermalink`). The single write
goes through `api_write()`: POST, and `ValueError` for any method outside
`WRITE_METHODS` = `{reactions.add}`, only when auto-react is enabled. It never posts, marks read,
joins or replies. Covered by `tests/test_watch_mentions.py` in the source repo.

## Config

Settings come from the process env, then `~/.hermes/.env` directly.

| Variable | Default |
| --- | --- |
| `SLACK_USER_READ_TOKEN` | unset -> history mode |
| `SLACK_USER_REACT_TOKEN` | `SLACK_USER_READ_TOKEN`; the token `reactions.add` is sent with |
| `SLACK_MENTION_REACT` | unset -> no reactions; `1`/`true`/`yes` = same as `--react` |
| `SLACK_MENTION_REACT_DELAY_SECS` | `60`; a reaction waits until the mention is this old (`0` = send at once) |
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
| Stderr `react failed on C...:...: reactions.add: missing_scope` | `reactions:write` user scope not granted (or the token predates it) | Add the scope, reinstall, re-check with `--check`; mentions themselves are unaffected. |
| `ERROR: ...: invalid_auth` / `token_revoked` | Token wrong or app reinstalled | Copy the current token into `~/.hermes/.env`. |
| `--check` says `member channels: 0` | History mode, bot invited nowhere | Add the user token, or `/invite` your bot. |
| Same mention re-alerts every tick / alert quotes its own alert | Self-alert loop: search sees the bot's alert DM as a new mention | Set `SLACK_HOME_CHANNEL` and `SLACK_BOT_TOKEN` in `~/.hermes/.env`; add other relaying ids to `SLACK_MENTION_IGNORE_USERS`. |
| `notify/heartbeat only apply to background commands`, then `identical_call_streak_halt` | The model passes background-only args on a foreground call and retries it | Use `/pings`, or a different model. |
| Names show as `U...` | `users.info` failed: no `SLACK_BOT_TOKEN` or no `users:read` | Check the bot token in `~/.hermes/.env`. |
| `$SLACK_BOT_TOKEN` empty in the terminal | Hermes strips gateway `SLACK_*` vars from subprocesses | Nothing; the script reads `~/.hermes/.env` itself. |
| Only one of several close pings got an emoji | Not a queue/timing bug (every new mention of a tick is processed oldest first); the others were skipped -- check their `Reacted:` line (`none (already reacted/replied)` = you had already handled it) | Expected; every ping now gets `:eyes:`, `:raised_hands:` or `:memo:` unless already handled. Run `classify()` on the text to check the emoji. |
| Mention in a thread never alerts | History mode skips thread replies | Use the user token. |
| Stderr `rate limited` / `network error` | 429 after one retry, or offline | Tick skipped, state not advanced; next tick catches up. |
