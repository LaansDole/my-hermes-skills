---
name: slack-mention-watch
description: Use when the user asks about Slack pings, mentions or what they missed, or wants @mention alerts or a triaged digest while away; can opt-in auto-react (:eyes: to questions, :raised_hands: to thanks) and opt-in start a background read-only review agent for PRs it is asked to review.
version: 2.7.0
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
  --model <model> --provider <provider> --reasoning-effort high --deliver slack
```

Use `--reasoning-effort medium` or `high`, never `max`: on this short digest `max` made up ~88% of
the job's spend (about 9k output tokens per run).

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

## Jev shadow (opt-in)

Logs TypeSafe Jev's view of each new mention beside the deterministic result, to collect the
data needed before Jev may ever decide anything. **No behaviour change**: the output, reactions
and skips are exactly as without it. Jev's probabilities are not calibrated on Slack mentions,
so bands get picked from this log, not guessed.

Per NEW mention of a default or `--digest` tick, one Jev call (`api.typesafe.ai/v1/systemone`)
answers five yes/no questions over the mention + its thread: `request`, `thanks`, `fyi` (the
emoji classes), `handled` (the user already committed to it or it is resolved) and `review`
(the same question the review gate asks, see "Background review agent"; logged only). Policy in
code: `request >= 0.9` -> `eyes`, else `thanks >= 0.9` -> `raised_hands`, else `fyi >= 0.9` ->
`memo`, else none (Jev unsure, regex decides).

Enable in `~/.hermes/.env`: `SLACK_MENTION_JEV_SHADOW=1` and `TYPESAFE_API_KEY=...`. It sends
the mention and thread text to a third party, which is why it is off by default. One JSON line
per mention goes to `~/.hermes/scripts/.slack-mention-jev.jsonl` (mode 600; `--dry-run` prints
rows to stderr instead): `regex_emoji`, `react_status`, `p` (five probabilities), `jev_emoji`,
`jev_model`, `ms`, `error`. A Jev failure is logged as an error row; a rejected key prints one
stderr line and stops Jev calls for that tick. The tick itself never fails because of Jev.

After ~2 weeks, see where Jev and the rules disagree, then label those rows by hand:

```bash
python3 -c "import json,os;[print(r['regex_emoji'],r['jev_emoji'],r['p'],r['mention'][:80]) for r in map(json.loads,open(os.path.expanduser('~/.hermes/scripts/.slack-mention-jev.jsonl'))) if r['jev_emoji'] and r['jev_emoji']!=r['regex_emoji']]"
```

## Background review agent (opt-in)

`scripts/review_spawn.py` wraps the digest: it runs `watch_mentions.py --digest --react <args>`,
and when `SLACK_REVIEW_AGENT` is set, each new mention that asks the user to review a GitHub PR
(`github.com/<owner>/<repo>/pull/<n>`, optionally also ticket keys) starts a detached,
headless, read-only coding-agent session that reviews it. A `review:` line with the session id
and resume command goes into that mention's block, so the digest shows it. Without
`SLACK_REVIEW_AGENT` the output is byte-identical to the plain digest. Reactions only stays the
default.

**Review gate.** Only the `Mention:` text (not the thread) decides whether it is a review ask:
PTAL, "take/have a look", review/re-review asked of the reader ("can you review", "please
review", "review this ..."), check/test/verify/approve with an object after "can you" /
"please" ("could you check this", "please test it on staging"), or a PR link plus a request
word. Not: "so I can review", "in review", "check and assign", "update the list", "edit your
message". Targets come from the mention text; if it has none, from the thread's first line (its
root) only, never the rest of the thread (max 5). A non-ask gets `review: skipped (not a review
request)`, an ask without a target `review: skipped (no target in mention or thread root)`.

**Jev second opinion (opt-in).** `SLACK_REVIEW_JEV=1` plus `TYPESAFE_API_KEY` sends each
regex-positive mention (plain text, thread lines, watched user) to TypeSafe Jev (`jev-latest`,
one POST to `api.typesafe.ai`) with the same `review` question as the Jev shadow log. p(review)
below `SLACK_REVIEW_JEV_MIN` (0.8; real asks score ~0.98 with thread context, a triage false
positive 0.68) -> `review: skipped (not a review request (jev 0.68))`. Errors -> the regex
decides; HTTP 401/403 turns Jev off for the tick with one stderr line (never the key). One JSON
row per call goes to `SLACK_REVIEW_JEV_LOG` (chmod 600; `--dry-run`: stderr). Off by default:
it sends Slack text to a third party.

**Session table.** `SLACK_REVIEW_STATE` keeps one entry per target: session id, agent, first
and last run, run count, reviewed PR head commit, pid and queued updates. Per target:

- PR whose head commit equals the reviewed one -> skipped as `already reviewed <id>`, any age;
- ticket, or PR head unknown (gh failed) -> skipped while its last run is less than
  `SLACK_REVIEW_DAYS` (7) days old;
- otherwise, if an omp/claude session of the current agent owns the target, that session is
  **resumed** with a follow-up brief: the new Slack block(s) and, for PRs, only the `old..new`
  diff. Other targets get one new session; a block can get both lines.
- A session still running (pid alive) is never started twice: the block is queued
  (`review: busy <id> (update queued)`) and delivered by the first tick after the run ends, also
  a tick without new mentions; that result goes to stderr as
  `[slack-review] queued update: review: ...`. If no queued target needs a review any more
  (merged, approved, ...), the update is dropped.

Custom agents have no session id: once the dedupe lets a target through, it gets a new run.
Entries without a run for 30 days are pruned. A pre-2.7 state file (`{target: {session, at}}`)
is migrated on the next save; those entries dedupe but are never resumed (agent unknown).

`python3 scripts/review_spawn.py --sessions` prints the table, newest run first (read only: no
watcher run, no Slack call):

```
TARGET        AGENT  SESSION  RUNS  LAST RUN          REV      STATUS  RESUME
acme/api#812  omp    <id>     2     2026-11-10 09:30  5d6e7f8  idle    cd ~/code && omp --resume <id>
ABC-123       omp    <id>     1     2026-11-09 16:02  -        idle    cd ~/code && omp --resume <id>
```

STATUS is `running` while the recorded pid is alive.

### Setup interview (ask, don't assume)

Before enabling it, ask the user, one question at a time:

1. Reactions only, or reactions + background review agent? Recommend reactions only if unsure.
   Warn: every review is an unattended agent run that costs tokens and reads the code of the
   PRs (up to `SLACK_REVIEW_MAX_SPAWNS` per tick).
2. Which agent: `omp` (Oh My Pi), `claude` (Claude Code), or a custom command?
3. Workdir: the directory the agent runs in, usually the folder holding the clones of the
   repos it will review.
4. Model (and for omp, thinking effort)? Unset = the agent's default.
5. PRs only, or ticket keys too? If tickets: a regex for the keys (e.g.
   `\b[A-Z][A-Z0-9]+-\d+\b`), and optionally Jira Cloud credentials so done tickets are skipped.
6. Optional: a text file with the user's own review rules (skills to follow, focus areas).

Then:

1. Write the answers into `~/.hermes/.env`, e.g.

   ```
   SLACK_REVIEW_AGENT=omp
   SLACK_REVIEW_WORKDIR=~/code
   SLACK_REVIEW_MODEL=<model>
   SLACK_REVIEW_TICKET_RE=\b[A-Z][A-Z0-9]+-\d+\b
   ```

2. Point the digest wrapper at the review script (it adds `--digest --react` itself):

   ```bash
   cat > ~/.hermes/scripts/slack_mention_digest_cron.py <<'EOF'
   #!/usr/bin/env python3
   import os, runpy, sys
   TARGET = os.path.expanduser(
       "~/.hermes/skills/slack/slack-mention-watch/scripts/review_spawn.py")
   sys.argv = [TARGET, *sys.argv[1:]]  # extra args (e.g. --dry-run) pass through
   runpy.run_path(TARGET, run_name="__main__")
   EOF
   ```

3. Add this rule to the cron prompt (`~/.hermes/scripts/slack_mention_digest_prompt.txt`):
   `- Copy any "review:" line from a mention verbatim into that mention's item.`
4. Preview: `python3 ~/.hermes/scripts/slack_mention_digest_cron.py --dry-run` -> eligible
   mentions show `review: (dry run, would spawn for: ...)`. Nothing is spawned or saved.

Going back to reactions only: remove `SLACK_REVIEW_AGENT` (the wrapper may stay).

### Agents

| Agent | Command | Session id | Resume |
| --- | --- | --- | --- |
| `omp` | `omp -p --mode json --config <dir>/omp-noresume.yml [--model M] [--thinking E] --cwd <workdir> @<brief>` | `id` of the first `type: session` JSON line | `cd <workdir> && omp --resume <id>` |
| `claude` | `claude -p <brief text> --output-format stream-json --verbose [--model M] --permission-mode default --allowedTools <read-only list> --disallowedTools Edit Write NotebookEdit` | `session_id` of the first `type: system`, `subtype: init` line | `cd <workdir> && claude --resume <id>` |
| `custom` | `SLACK_REVIEW_CMD`, shlex-split, `{brief}` (path) and `{workdir}` replaced | none | log path shown instead |

Resumed runs add `--resume <id>`: omp right after `--mode json`, claude right after the prompt
(`claude -p <follow-up text> --resume <id> --output-format ...`, same flags). Custom agents are
never resumed.

The claude allowlist is `Read Grep Glob "Bash(gh pr view:*)" "Bash(gh pr diff:*)"
"Bash(gh pr checks:*)" "Bash(git fetch:*)" "Bash(git show:*)" "Bash(git diff:*)"
"Bash(git log:*)"` (no `gh api`: it also allows POSTs). `omp-noresume.yml` holds exactly
`autoResume: false`: with `autoResume` on, `omp -p` would resume the user's latest session in
that directory instead of starting a fresh one.

Each run is detached (own session, stdin closed), started in the workdir. The brief, stdout and
stderr go to `SLACK_REVIEW_DIR` as `<time>-<targets>.md` / `.jsonl` (custom: `.log`) / `.err`
(follow-ups: `<time>-<targets>-followup.*`). The brief holds the Slack block verbatim, the
targets, read-only rules (gh pr view/diff/checks, git fetch + show/diff/log; never edit, commit,
checkout, push, comment, approve or post anywhere) and asks for P0/P1 findings only (severity,
file:line, problem, impact, fix), else "No P0/P1 findings"; a follow-up asks for new P0/P1
findings only. The `SLACK_REVIEW_INSTRUCTIONS` file is appended to the first brief under
"Additional instructions". The review result stays in the agent session; nothing is posted.

### Skip rules and output

No spawn and no `review:` line when the mention's `Reacted:` line says `already replied` /
`already reacted` or is `:raised_hands:` / `:memo:` (dry-run variants too). Per target, checks
fail open (any error = review it):

- PR merged / closed / approved, or reviewed by `SLACK_REVIEW_GH_LOGIN` at or after its last
  commit -> `merged` / `closed` / `approved` / `already reviewed by you` (via `gh pr view`);
- ticket in a done status category -> `done (<status>)`, only when `JIRA_URL`, `JIRA_EMAIL`
  and `JIRA_TOKEN` are set (`GET /rest/api/2/issue/<key>?fields=status`).

Dedupe and resume follow the session table above. Lines, inserted after `Reacted:` (a block
with new and resumed targets gets one line each):

```
review: <id> (acme/api#12) -> cd ~/code && omp --resume <id>
review: resumed <id> (acme/api#12, 1a2b3c4..5d6e7f8) -> cd ~/code && omp --resume <id>
review: busy <id> (update queued)
review: skipped (not a review request)
review: skipped (not a review request (jev 0.41))
review: skipped (no target in mention or thread root)
review: skipped (acme/api#9 merged)
review: skipped (acme/api#12 already reviewed <id>)
review: skipped (spawn cap reached)
review: failed (<reason>; log <path>)
review: (dry run, would spawn for: acme/api#12)
review: (dry run, would resume <id> for: acme/api#12)
review: started (log <path>)                          (custom agent)
```

A resumed line shows the reviewed and current head commit (`?` = unknown). Partly skipped
mentions get ` [skipped: <target> <reason>; ...]` appended. `SLACK_REVIEW_MAX_SPAWNS` counts new
and resumed runs. Any error in the review layer prints `[slack-review] error: ...` to stderr and
the raw digest; the exit code is always `watch_mentions.py`'s.

| Variable | Default |
| --- | --- |
| `SLACK_REVIEW_AGENT` | unset -> feature off; `omp` / `claude` / `custom` |
| `SLACK_REVIEW_WORKDIR` | required when on; directory the agent runs in |
| `SLACK_REVIEW_MODEL` | unset -> agent default; passed as `--model` |
| `SLACK_REVIEW_EFFORT` | unset; omp only, passed as `--thinking` |
| `SLACK_REVIEW_CMD` | custom agent command template |
| `SLACK_REVIEW_MAX_SPAWNS` | `3` runs (new + resumed) per tick |
| `SLACK_REVIEW_TICKET_RE` | unset -> PRs only; regex for ticket keys |
| `SLACK_REVIEW_INSTRUCTIONS` | unset; text file appended to the brief |
| `SLACK_REVIEW_STATE` | `~/.hermes/scripts/.slack-review-spawn.json` (chmod 600); the session table |
| `SLACK_REVIEW_DAYS` | `7`; tickets and PRs with unknown head are not re-reviewed sooner |
| `SLACK_REVIEW_DIR` | `~/.hermes/cache/slack-review-spawns` (briefs + logs) |
| `SLACK_REVIEW_ID_TIMEOUT` | `30` s to wait for the session id |
| `SLACK_REVIEW_GH` | `gh` on PATH, else `/opt/homebrew/bin/gh`, else `/usr/local/bin/gh` |
| `SLACK_REVIEW_GH_LOGIN` | `gh api user --jq .login` |
| `JIRA_URL`, `JIRA_EMAIL`, `JIRA_TOKEN` | unset -> tickets not checked (Jira Cloud API token, basic auth) |
| `SLACK_REVIEW_JEV` | unset -> off; `1` asks Jev about regex-positive mentions (needs `TYPESAFE_API_KEY`) |
| `SLACK_REVIEW_JEV_MIN` | `0.8`; lowest p(review) that still spawns |
| `SLACK_REVIEW_JEV_LOG` | `~/.hermes/scripts/.slack-review-jev.jsonl` (chmod 600) |
| `SLACK_REVIEW_GUARD` | on; `0` removes the git/gh guard wrappers (not recommended) |
| `SLACK_REVIEW_GUARD_DIR` | `<SLACK_REVIEW_DIR>/guard-bin`; rewritten on every run |

Agent binaries are looked up on PATH, then in `~/.local/bin`.

## Write guarantee

Reads go through `api()`: HTTP GET only, and `ValueError` for any method outside `READ_METHODS`
(`auth.test`, `search.messages`, `conversations.list`, `conversations.history`,
`conversations.info`, `conversations.replies`, `users.info`, `chat.getPermalink`). The single write
goes through `api_write()`: POST, and `ValueError` for any method outside
`WRITE_METHODS` = `{reactions.add}`, only when auto-react is enabled. It never posts, marks read,
joins or replies. Covered by `tests/test_watch_mentions.py` in the source repo.

Opt-in Jev shadow mode adds one non-Slack request per new mention: a POST of the mention and
thread text to `api.typesafe.ai`. It writes nothing to Slack and changes no output.

`review_spawn.py` makes no Slack calls; its own network use is `gh pr view` / `gh api user`, the
optional Jira GET and the optional Jev POST. Every agent (omp, claude, custom) runs with `PATH`
starting with a guard dir (`SLACK_REVIEW_GUARD_DIR`) whose `git` and `gh` wrappers exec the real
binaries but refuse writes: git push, send-email, commit, reset, checkout, switch, rebase,
merge, pull, cherry-pick, revert, restore, clean, am, apply, stash, worktree, tag and
`branch -d/-D/-m/-M/-f` (also after `-C <dir>` / `-c k=v`); gh pr anything but
view/diff/checks/list/status, issue anything but view/list, release, repo anything but
view/list/clone, and `gh api` with a non-GET method or a field/input flag. The child also gets
`GIT_TERMINAL_PROMPT=0` and `PI_BASH_NO_LOGIN=1` (omp's login shell would otherwise let macOS
`path_helper` put `/usr/bin` ahead of the guard). If the wrappers cannot be written nothing is
started (`review: failed (cannot write the git/gh guard: ...)`). `claude` is also held to the
read-only tool allowlist above. The wrappers check argv, they are not a sandbox (an absolute
`/usr/bin/git`, `git -c alias.x=push x` or other gh commands pass) and agents may still write
scratch files such as `/tmp`; for a hard guarantee give the agent's gh a read-only token.
`SLACK_REVIEW_GUARD=0` removes the wrappers (not recommended).
Covered by `tests/test_review_spawn.py`.

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
| `SLACK_MENTION_JEV_SHADOW` | unset -> off; `1`/`true`/`yes` + `TYPESAFE_API_KEY` = Jev shadow log |
| `SLACK_MENTION_JEV_LOG` | `~/.hermes/scripts/.slack-mention-jev.jsonl` (chmod 600) |
| `TYPESAFE_API_KEY` | unset -> Jev shadow off |

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
| A review continued the user's own latest omp session | omp `autoResume` on: `omp -p` resumes the last session in that directory | `review_spawn.py` passes `--config <SLACK_REVIEW_DIR>/omp-noresume.yml` (`autoResume: false`) and rewrites it on every spawn; check the dir is writable and the omp version honours `--config`. |
| Claude review log shows permission denials | Headless claude only runs the allowlisted read-only tools (no `gh api`); `--permission-mode default` denies the rest | Expected for writes and other commands; the brief only needs `gh pr view/diff/checks` and git reads. |
| `slack-review guard: 'git ...' is blocked` / `'gh ...' is blocked` in a review log | The guard wrappers refused a write | Expected: reviews are read-only. |
| Merged/approved PRs still get reviewed, or `review: failed (cannot start omp: ...)` | Cron runs with a minimal PATH, so `gh` or the agent is not found (checks fail open), or gh is not logged in for the gateway user | Set `SLACK_REVIEW_GH` to the full gh path; put the agent on the gateway's PATH or in `~/.local/bin`; run `gh auth status` as the gateway user. |
| `review: failed (no session id within timeout ...)` | Agent slow to start (login prompt, update check) | Read the log path in the line; raise `SLACK_REVIEW_ID_TIMEOUT`. The agent is left running. |
| `[slack-review] error: ValueError: ...` on stderr, digest without `review:` lines | `SLACK_REVIEW_AGENT` not omp/claude/custom, or `SLACK_REVIEW_WORKDIR` / `SLACK_REVIEW_CMD` missing | Fix `~/.hermes/.env`. |
| A review was spawned for a ping that asks something else ("update the list", "check and assign") | Before 2.7 any PR link or ticket key in the block, thread included, started one | 2.7 gates on the Mention text (`review: skipped (not a review request)`); for a remaining false positive set `SLACK_REVIEW_JEV=1`. |
| The same PR is reviewed again from scratch | Before 2.7: 24 h all-or-nothing dedupe. Now: a new head commit resumes the same session; a new session only when none of the current agent owns the target (other agent, custom, pre-2.7 entry) | `review_spawn.py --sessions` shows each target's session, runs and REV. |
