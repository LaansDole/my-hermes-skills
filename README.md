# auto-learn-for-me

A Hermes Agent skill pack that autonomously watches and advances HCL iLearning Success web courses in your own Chrome session. The agent resumes paused videos, answers in-video quizzes, and navigates to the next module -- fully unattended.

Built on [Hermes Agent](https://hermes-agent.nousresearch.com/) (Nous Research, MIT). The agent attaches to your already-logged-in Chrome via the Chrome DevTools Protocol (CDP), so no HCL SSO/2FA automation or credentials-in-the-agent is needed.

## How it works

```
[Your Chrome, logged into HCL iLearning]
       |  CDP via --remote-debugging-port=9222
       |  Hermes attaches with /browser connect
       v
[Hermes Agent]  <-- ~/.hermes/skills/ilearning-autoadvance/SKILL.md
       |
       |  vision-capable model (via Nous Portal)
       v
[Watch loop: observe -> classify state -> act -> sleep -> repeat]
```

The skill runs a polling loop. Each tick it observes the page (accessibility tree + `<video>` element state), classifies the player into one of `VIDEO_PLAYING`, `VIDEO_PAUSED`, `QUIZ_POPUP`, `VIDEO_ENDED`, or `UNKNOWN`, dispatches the matching action, and sleeps. See the [design spec](docs/superpowers/specs/2026-07-18-hermes-iLearning-autoadvance-design.md) for the full state machine.

## Prerequisites

- **macOS** (tested target; Linux/Windows should work since Hermes is cross-platform, but the Chrome launch command in this README is macOS-specific)
- [Hermes Agent](https://hermes-agent.nousresearch.com/) v0.18+
- A [Nous Portal](https://portal.nousresearch.com) subscription (gives the agent a vision-capable model via the Tool Gateway -- no separate API keys)
- Google Chrome (Chromium-family; Brave/Edge also work)
- An HCL iLearning Success account with at least one course assigned to you

## One-time setup

### 1. Install Hermes Agent

```bash
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
```

Open a new shell (or `source ~/.zshrc`) so `hermes` is on `$PATH`. Verify:

```bash
hermes --version   # must be >= 0.18.0
```

### 2. Install the skill pack

Hermes auto-discovers skills in `~/.hermes/skills/`. Create the directory and the logs directory:

```bash
mkdir -p ~/.hermes/skills/ilearning-autoadvance
mkdir -p ~/.hermes/logs
```

The skill files (`SKILL.md` and `SETUP.md`) are part of this repo's deliverables but live outside the repo at runtime. If they aren't already in place (check with `ls ~/.hermes/skills/ilearning-autoadvance/`), create them per [Task 2](docs/superpowers/plans/2026-07-18-hermes-iLearning-autoadvance.md) and [Task 4](docs/superpowers/plans/2026-07-18-hermes-iLearning-autoadvance.md) of the implementation plan.

Verify Hermes sees the skill:

```bash
hermes skills list
```

`ilearning-autoadvance` should appear in the list.

### 3. Log in to Nous Portal

```bash
hermes setup --portal
```

A browser flow opens for Nous Portal login. After completing it, the terminal confirms the subscription is active and the Tool Gateway tools are enabled.

### 4. Enable the browser toolset in local CDP mode

```bash
hermes setup tools
```

In the interactive menu, select **Browser Automation** -> **Local Chromium-family CDP**.

Do NOT pick Browserbase / Browser Use / Firecrawl / Camofox -- those are cloud providers and out of scope for this project.

Verify:

```bash
hermes tools list
```

`browser` should appear in the enabled toolsets column.

### 5. Patch `~/.hermes/config.yaml` for unattended operation

Back up the existing config first:

```bash
cp ~/.hermes/config.yaml ~/.hermes/config.yaml.bak.$(date +%Y%m%d-%H%M%S)
```

Then merge the patch snippet from this repo into `~/.hermes/config.yaml`:

```bash
$EDITOR ~/Projects/auto-learn-for-me/.hermes-config/config-patch.yaml   # read what it sets
$EDITOR ~/.hermes/config.yaml                                            # paste the approvals + browser blocks in
```

The patch sets:

```yaml
approvals:
  mode: scoped
  auto_approve:
    - browser.click
    - browser.type
    - browser.fill
    - browser.evaluate
    - browser.screenshot
    - browser.observe

browser:
  cloud_provider: local    # local CDP only -- no cloud provider
```

If your Hermes version rejects `mode: scoped`, fall back to `mode: auto` (acceptable here -- the design spec explicitly accepts unattended operation).

Validate:

```bash
hermes config show    # or `hermes config validate` on newer versions
```

## Per-session launch

### 1. Start Chrome with remote debugging

Quit Chrome fully first (Cmd-Q) -- the flag only takes effect on a fresh launch:

```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port=9222 \
  --user-data-dir="$HOME/Library/Application Support/Google/Chrome" &
```

Using your normal `--user-data-dir` preserves your existing HCL iLearning login.

Verify the debug port is listening:

```bash
curl -s http://127.0.0.1:9222/json/version | head -1
```

Expected: JSON containing `"webSocketDebuggerUrl"`. If empty, Chrome didn't start with the flag -- make sure no other Chrome process is running first.

### 2. Log in and open a course

In Chrome: navigate to HCL iLearning Success, log in via SSO/2FA, open a course, and click into the first lesson so the video element is visible.

### 3. Start Hermes and attach

```bash
hermes -t browser chat
```

In the Hermes prompt:

```
/browser connect
```

Hermes confirms attachment and lists open tabs. Your HCL iLearning tab should be in the list.

### 4. Invoke the skill

```
Run the ilearning-autoadvance skill on my current tab, max_modules=10.
```

The watch loop begins. Per-tick logs land at `~/.hermes/logs/ilearning-autoadvance-<session-id>.jsonl`. A summary (modules completed, quizzes attempted, stuck points) prints at the end.

## First-run safety pattern

Before the first unattended run, do these two validation passes:

**Dry run** -- the agent observes and describes each action it *would* take, without clicking:

```
Run the ilearning-autoadvance skill on my current tab, max_modules=1, dry_run=true.
```

Watch the descriptions. If it misclassifies state (e.g. calls a paused video "ended"), edit `~/.hermes/skills/ilearning-autoadvance/SKILL.md` (State Classification section) and re-run. The skill is prose -- tuning is the work, not code.

**Single-module live run with approvals on** -- temporarily set `approvals.mode: manual` in `~/.hermes/config.yaml` and restart Hermes:

```
Run the ilearning-autoadvance skill on my current tab, max_modules=1.
```

Approve each click yourself. Confirm: video resumes, quiz answered, next-module clicked. If clean, flip approvals back to `scoped`/`auto` and do the full unattended run.

## Parameters

The skill accepts these parameters in the natural-language invocation:

| Parameter | Type | Default | Description |
|---|---|---|---|
| `max_modules` | int | 50 | Hard cap on modules to advance before stopping. |
| `dry_run` | bool | false | When true, observe and describe actions without clicking. |
| `tick_seconds` | int | 5 | Idle polling interval. After an action, poll again immediately. |

## Logs and troubleshooting

- **Per-tick logs:** `~/.hermes/logs/ilearning-autoadvance-<session-id>.jsonl`
  ```json
  {"ts":"2026-07-18T12:34:56Z","module":"<lesson title>","state":"VIDEO_PAUSED","action":"click @e14","video_pos":"123.4/456.7","ok":true}
  ```
- **Stuck on `UNKNOWN` for more than 2 ticks:** check the screenshot the agent logged -- HCL iLearning may have pushed a modal not covered by the classification rules. Edit `SKILL.md` to add the new state and re-run.
- **CDP connection dropped:** Chrome closed or crashed. Restart Chrome with the flag (per-session launch step 1) and re-run the skill.
- **Session/login expired:** the page navigated to SSO login or the `<video>` element disappeared for > 30 s. Log back into HCL iLearning in Chrome and re-run the skill. No auto-relogin by design.
- **Quiz submit stays disabled:** the agent re-scans for unanswered questions and answers them. If still stuck, kill the session and inspect the page -- HCL may have added a required field the skill doesn't recognize.

## Repository layout

```
.
|-- README.md                                    # this file
|-- .hermes-config/
|   `-- config-patch.yaml                        # merge into ~/.hermes/config.yaml after install
`-- docs/superpowers/
    |-- specs/
    |   `-- 2026-07-18-hermes-iLearning-autoadvance-design.md   # design spec
    `-- plans/
        `-- 2026-07-18-hermes-iLearning-autoadvance.md           # implementation plan
```


## Design and implementation

- **Design spec:** `docs/superpowers/specs/2026-07-18-hermes-iLearning-autoadvance-design.md` -- architecture, watch-loop state machine, error handling, risks.
- **Implementation plan:** `docs/superpowers/plans/2026-07-18-hermes-iLearning-autoadvance.md` -- 7-task build plan with exact commands and content.

## Safety and non-goals

**Safety guardrails (built into the skill):**

- Never types into password fields (Hermes hard-blocks this anyway).
- Never clicks elements named logout / sign out / sign-out / signout / log off.
- Stops the loop if the page navigates outside the HCL iLearning domain.
- Hermes's built-in destructive-action blocklists (`sudo rm -rf`, `curl | bash`, fork bombs, lock-screen combos) remain active.
- Bounded session via `max_modules` (default 50, configurable).
- Idempotency guards: never clicks "submit" twice on the same quiz; never clicks "Next" if the URL hasn't changed since the last "Next" click.
- Infinite-loop guard: stops if the last 3 URLs are identical after actions.

**Explicit non-goals:**

- HCL SSO login automation -- you stay logged in via your real Chrome.
- Anti-detection / stealth -- if HCL detects automation, that's a policy problem for you, not a design problem. No stealth added.
- Multi-course parallelism -- one course at a time.
- Tracking learning progress across sessions -- HCL itself tracks completion; this skill does not duplicate that.

## License

This repo's contents (skill prose, design docs, config patch) inherit the project's default. Hermes Agent itself is MIT-licensed by Nous Research.

---

## Other skills in this repo

- [`slack-todo-bot/`](slack-todo-bot/README.md) -- Hermes Agent bot that scans Slack notifications hourly, extracts action items to a Markdown TODO file, and posts a 9 AM "today" digest to your private Slack DM. Uses Socket Mode (no public URL needed).
- [`skills/covidence-screening/`](skills/covidence-screening/SKILL.md) -- Hermes Agent skill that autonomously screens Covidence systematic-review references at the title & abstract stage, voting Yes/Maybe/No against your PICO criteria. Uses CDP to attach to your logged-in Chrome.