# Hermes iLearning Auto-Advance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Hermes Agent skill pack that autonomously watches and advances HCL iLearning Success web courses in the user's Chrome session via CDP.

**Architecture:** Hermes Agent's `browser` toolset attaches to the user's already-logged-in Chrome (CDP port 9222). A prose skill pack at `~/.hermes/skills/ilearning-autoadvance/` drives a watch-loop state machine: observe -> classify (video paused / quiz popup / video ended / unknown) -> act -> sleep -> repeat. Vision-capable model via Nous Portal. No application code; pure markdown.

**Tech Stack:** Hermes Agent v0.18+ (MIT, Nous Research), Chrome with `--remote-debugging-port=9222`, vision-capable LLM via Nous Portal subscription.

## Global Constraints

- **Deliverable is prose (markdown skill files), not code.** "Tests" in this plan are behavioral smoke checks against a real HCL iLearning course; there is no unit-test framework for skill prose. Each task's verification is a file-existence check or a live run, not pytest.
- **No credentials in the agent.** The user logs into HCL iLearning in Chrome themselves; the agent attaches via CDP. No SSO/2FA automation.
- **No anti-detection / stealth.** Out of scope by design.
- **Skill paths are absolute in this plan:** `~/.hermes/skills/ilearning-autoadvance/SKILL.md`, `~/.hermes/skills/ilearning-autoadvance/SETUP.md`, `~/.hermes/config.yaml`, `~/Projects/auto-learn-for-me/README.md`.
- **Casing note:** `iLearning` (camelCase) in user-facing strings; `ilearning-autoadvance` (lowercase, hyphenated) in paths and directory names (filesystem-safe, matches Hermes skill conventions).
- **macOS only** for initial implementation (user's workstation). Computer-use fallback path is documented but not built.
- **Approvals default off for `browser.click`/`browser.type`** -- user explicitly accepted unattended operation in the spec.

---

## File Structure

- **`~/.hermes/skills/ilearning-autoadvance/SKILL.md`** -- The skill the agent loads. Contains: trigger, parameters, watch-loop state machine, state classification, action policy, loop control, safety rules, logging format, error recovery. One file, one responsibility: tell the agent how to run the loop.
- **`~/.hermes/skills/ilearning-autoadvance/SETUP.md`** -- Human-facing install/launch steps. Separate from SKILL.md so the agent does not load setup prose into its context every run.
- **`~/.hermes/config.yaml`** -- Patched: approvals scoped so browser click/type do not require confirmation. Not created from scratch -- user already has this file after `hermes setup --portal`; we patch it.
- **`~/Projects/auto-learn-for-me/README.md`** -- Repo-level launch cheat sheet.

---

### Task 1: Install Hermes Agent and verify browser toolset

**Files:**
- Modify: `~/.hermes/config.yaml` (created by installer if absent)
- Modify: `~/.hermes/.env` (created by installer if absent)

**Interfaces:**
- Consumes: nothing
- Produces: a working `hermes` CLI on `$PATH`; `browser` toolset registered; a vision-capable model configured via Nous Portal

- [ ] **Step 1: Install Hermes Agent**

Run:
```bash
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
```
Expected: installer completes, prints confirmation, adds `hermes` to shell PATH. Open a new shell or `source ~/.zshrc` so `hermes` is on `$PATH`.

- [ ] **Step 2: Verify the binary is reachable**

Run: `hermes --version`
Expected: prints a version string >= `0.18.0`. If lower, re-run the installer; if still < 0.18, stop and surface to the user (spec requires v0.18+).

- [ ] **Step 3: Log in to Nous Portal and enable the Tool Gateway**

Run: `hermes setup --portal`
Expected: opens a browser flow for Nous Portal login. After completing it, the terminal prints confirmation that the subscription is active and the Tool Gateway tools are enabled (vision-capable model access without separate API keys).

- [ ] **Step 4: Enable the `browser` toolset interactively**

Run: `hermes setup tools`
Expected: interactive menu. Select `Browser Automation`, choose `Local Chromium-family CDP` as the provider (NOT Browserbase / Browser Use / Firecrawl / Camofox -- those are cloud and out of scope). Exit the menu.

- [ ] **Step 5: Verify the browser toolset is registered**

Run: `hermes tools list`
Expected: output includes `browser` in the enabled toolsets column. If not, re-run Step 4.

- [ ] **Step 6: Commit a marker file noting the install state**

In the project repo:
```bash
cd ~/Projects/auto-learn-for-me
mkdir -p .install-state
hermes --version > .install-state/hermes-installed.txt
printf '\nBrowser toolset: local CDP mode\nPortal: logged in via hermes setup --portal\n' >> .install-state/hermes-installed.txt
git add .install-state/hermes-installed.txt
git commit -m "chore: record Hermes install state"
```
Expected: commit succeeds. (This file is a marker for reproducibility, not a runtime dependency.)

---

### Task 2: Author the skill -- `SKILL.md`

**Files:**
- Create: `~/.hermes/skills/ilearning-autoadvance/SKILL.md`

**Interfaces:**
- Consumes: Hermes `browser` toolset primitives (`tab.observe`, `tab.evaluate`, `tab.click`, `tab.screenshot`, `tab.fill` for text inputs). Provided by Hermes at runtime -- no code to write.
- Produces: a skill the agent auto-discovers and loads when the user mentions "iLearning", "auto-advance", or "continue video".

- [ ] **Step 1: Create the skill directory**

Run:
```bash
mkdir -p ~/.hermes/skills/ilearning-autoadvance
```
Expected: directory exists. Verify with `ls -ld ~/.hermes/skills/ilearning-autoadvance`.

- [ ] **Step 2: Write `SKILL.md` with frontmatter, trigger, parameters**

Write `~/.hermes/skills/ilearning-autoadvance/SKILL.md` with this content (steps 2-7 build the file section by section; this step writes the header):

```markdown
---
name: ilearning-autoadvance
description: Autonomously watch and advance HCL iLearning Success courses in the user's Chrome session via CDP. Resumes paused videos, answers quizzes, navigates to the next module.
trigger:
  - iLearning
  - auto-advance
  - course
  - continue video
  - next module
---

# iLearning Auto-Advance

## Parameters

- `max_modules` (int, default 50): hard cap on the number of modules to advance through before stopping.
- `dry_run` (bool, default false): when true, observe and *describe* the action you would take, but do NOT call any click/type/fill tool. Use for first-pass validation against a real course.
- `tick_seconds` (int, default 5): idle polling interval. After an action, poll again immediately (the page needs time to react).

## Prerequisites

- A Chrome instance is running with `--remote-debugging-port=9222`.
- The user has logged into HCL iLearning Success in that Chrome and has a course open on a lesson page (not the dashboard).
- Hermes is attached to that Chrome via `/browser connect` (run this once per Hermes session before invoking the skill).
```

- [ ] **Step 3: Append the Watch Loop and State Classification sections**

Append to `~/.hermes/skills/ilearning-autoadvance/SKILL.md`:

```markdown
## Watch Loop

Repeat until a stop condition (see Loop Control) fires:

1. **Observe** -- call `tab.observe()` to get the accessibility tree of the current tab. Also call `tab.evaluate` with the snippet below to get the `<video>` element state. Keep both results in context.

   ```js
   (() => {
     const v = document.querySelector('video');
     return v ? {paused: v.paused, ended: v.ended, currentTime: v.currentTime, duration: v.duration} : null;
   })()
   ```

2. **Classify** the player into one of: `VIDEO_PLAYING`, `VIDEO_PAUSED`, `QUIZ_POPUP`, `VIDEO_ENDED`, `UNKNOWN`.
3. **Act** per the action policy below.
4. **Sleep** `tick_seconds` if no action was taken this tick; otherwise immediately repeat from step 1 (the page needs time to react).
```

- [ ] **Step 4: Append State Classification**

Append to `~/.hermes/skills/ilearning-autoadvance/SKILL.md`:

```markdown
## State Classification

- `VIDEO_PLAYING`: `video.paused === false` and `video.ended === false`. No action.
- `VIDEO_PAUSED`: `video.paused === true` and `video.ended === false` AND no quiz form is visible. Look for a resume/play button in the accessibility tree.
- `QUIZ_POPUP`: `video.paused === true` AND the accessibility tree contains a form block with radio buttons, checkboxes, or a text input labeled as a question. (The video may also be playing underneath but with a modal quiz overlay -- treat the quiz as authoritative.)
- `VIDEO_ENDED`: `video.ended === true`. Look for a "Next" / "Mark complete" / "Next module" button.
- `UNKNOWN`: none of the above match (e.g. no `<video>` element, or page navigated away). Increment an `unknown_streak` counter.

If `UNKNOWN` persists for > 2 consecutive ticks: take a screenshot via `tab.screenshot()`, describe what you see, log the observation, and keep polling (NO clicks) until a known state reappears or `max_modules` is reached.
```

- [ ] **Step 5: Append Action Policy**

Append to `~/.hermes/skills/ilearning-autoadvance/SKILL.md`:

```markdown
## Action Policy

All actions run unattended (approvals are off for `browser.click` / `browser.type`).

### `VIDEO_PAUSED`

1. Find the resume/play button in the accessibility tree (look for labels: resume, play, continue, play video).
2. If found, click it via its `@eN` ref. If `dry_run` is true, describe the action instead and skip the click.
3. If no resume button is visible, take a screenshot and use vision to locate the play affordance, then click at the identified ref/coordinate.

### `QUIZ_POPUP`

1. Read every question and every option in the quiz form from the accessibility tree. If the tree is sparse (e.g. options render as images or shadow-DOM), take a screenshot and use vision to read them.
2. For each question: reason about the correct answer. Show your reasoning briefly in the log, then pick the best option.
3. Click the chosen option's `@eN` ref. For free-text answers, use `tab.fill` on the input ref.
4. After all questions are answered, find the submit button. If it is disabled (`aria-disabled` or `disabled` attr), re-scan for unanswered questions and answer them. Do NOT submit until submit is enabled.
5. Click submit. Never click submit twice for the same quiz (track a `submitted_quiz_ids` set keyed by the quiz's heading text or position).

### `VIDEO_ENDED`

1. Look for a button labeled: Next, Mark complete, Complete, Next module, Next lesson, Continue.
2. If found, click it. Track `last_next_url` = current URL BEFORE the click.
3. After the click, poll. If the URL has NOT changed within 2 ticks, do NOT click "Next" again (idempotency guard). Instead, take a screenshot + use vision to find an alternative affordance, click that once.
4. Increment `modules_advanced` counter. If `modules_advanced >= max_modules`, stop the loop.

### `VIDEO_PLAYING`

No action. Sleep `tick_seconds` and re-observe.
```

- [ ] **Step 6: Append Loop Control, Safety, Logging, Error Recovery**

Append to `~/.hermes/skills/ilearning-autoadvance/SKILL.md`:

```markdown
## Loop Control

Stop the loop when any of:
- `modules_advanced >= max_modules`.
- No "Next" affordance found for 60 seconds after `VIDEO_ENDED` was first detected.
- `last_3_urls` are all identical AND the last action was a "Next" click (infinite-loop guard).
- Unrecoverable error: CDP connection dropped, page navigates outside the HCL iLearning domain, `<video>` element missing for > 30 s, model API failure after 3 backoffs.

## Safety Rules

Hard rules the agent MUST follow:
- Never type into any field of `type="password"` (Hermes hard-blocks this anyway).
- Never click any element whose accessible name contains: logout, sign out, sign-out, signout, log off.
- If the page URL navigates outside the HCL iLearning domain (check via `tab.evaluate(() => location.hostname)`), stop the loop immediately and log.
- Hermes's built-in destructive-action blocklists (`sudo rm -rf`, `curl | bash`, fork bombs, lock-screen combos) remain active and are NOT overridden by this skill.

## Logging

Every tick, write a JSON line to `~/.hermes/logs/ilearning-autoadvance-<session-id>.jsonl` (create the logs dir if missing):

```json
{"ts":"2026-07-18T12:34:56Z","module":"<lesson title>","state":"VIDEO_PAUSED","action":"click @e14","video_pos":"123.4/456.7","ok":true}
```

At loop end, print a summary to the terminal: modules completed, quizzes attempted (right/wrong if gradable from the page), total time elapsed, any stuck points.

## Error Recovery

| Failure | Detection | Recovery |
|---|---|---|
| CDP connection dropped | `tab.observe()` returns connection error | Stop, log, surface to user. Cannot auto-recover. |
| Session/login expired | Page navigates to SSO login URL, or `<video>` missing > 30 s | Stop, log URL, surface to user. No auto-relogin. |
| Click landed wrong | URL + `video.currentTime` unchanged 2 ticks after a click | Re-screenshot, re-classify, retry once with a different ref. If still stuck, log and skip to next tick. |
| Quiz submit disabled | Submit button has `disabled` / `aria-disabled` | Re-scan for unanswered questions, answer them, then submit. |
| Page JS error / blank render | Screenshot returns empty canvas or error overlay | Wait 2 ticks; if persists, log and advance to next module if possible, else stop. |
| Model API failure | Model call times out or 429 | Backoff 10 s -> 30 s -> 60 s; after 3 failures, stop and surface to user. |
| Infinite loop | `last_3_urls` identical after actions | Stop, log, surface to user. |
```

- [ ] **Step 7: Verify the skill is discoverable**

Run: `hermes skills list`
Expected: `ilearning-autoadvance` appears in the list of available skills. If not, verify the frontmatter is valid YAML (no tabs, correct indentation) and re-run.

No commit here -- `~/.hermes/skills/` is outside the project repo and is a user-local config directory. The skill is the deliverable; it lives in the user's home, not in git.

---

### Task 3: Patch `~/.hermes/config.yaml` for unattended approvals

**Files:**
- Modify: `~/.hermes/config.yaml`

**Interfaces:**
- Consumes: Task 1's working Hermes install.
- Produces: a config where `browser.click` and `browser.type` do not require interactive approval.

- [ ] **Step 1: Back up the existing config**

Run:
```bash
cp ~/.hermes/config.yaml ~/.hermes/config.yaml.bak.$(date +%Y%m%d-%H%M%S)
```
Expected: backup file exists. Verify with `ls ~/.hermes/config.yaml.bak.* | tail -1`.

- [ ] **Step 2: Patch the approvals section**

Open `~/.hermes/config.yaml` in an editor. Locate (or add) the `approvals` section. Set it so browser click and type are auto-approved:

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
```

If Hermes reports `mode: scoped` is unsupported on your version, fall back to `mode: auto` (auto-approve everything) -- acceptable for this use case since the user explicitly accepted unattended operation. Document the fallback in SETUP.md.

Expected: config file parses as valid YAML. Verify with:
```bash
hermes config validate
```
(If `hermes config validate` is not a subcommand on your version, run `hermes config show` and eyeball the parsed output -- the `approvals` block should reflect the patch.)

- [ ] **Step 3: Confirm no cloud browser provider is set**

In `~/.hermes/config.yaml`, ensure `browser.cloud_provider` is UNSET or set to `local`. If a cloud provider (browserbase / browser_use / firecrawl) was set previously, comment it out:

```yaml
browser:
  # cloud_provider: browserbase   # disabled -- using local CDP
```

Expected: `hermes tools list` shows the browser toolset in local CDP mode.

No commit -- `~/.hermes/config.yaml` is outside the repo.

---

### Task 4: Author `SETUP.md`

**Files:**
- Create: `~/.hermes/skills/ilearning-autoadvance/SETUP.md`

**Interfaces:**
- Consumes: Tasks 1-3.
- Produces: a human-facing runbook for launching the auto-advance loop.

- [ ] **Step 1: Write `SETUP.md`**

Write `~/.hermes/skills/ilearning-autoadvance/SETUP.md` with this content:

```markdown
# iLearning Auto-Advance -- Setup & Launch

## One-time setup

1. Install Hermes Agent:
   ```bash
   curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
   ```
2. Log in to Nous Portal:
   ```bash
   hermes setup --portal
   ```
3. Enable the browser toolset in local CDP mode:
   ```bash
   hermes setup tools
   ```
   Pick `Browser Automation` -> `Local Chromium-family CDP`.
4. Patch `~/.hermes/config.yaml` for unattended approvals (see the implementation plan, Task 3).

## Per-session launch

1. Start Chrome with remote debugging:
   ```bash
   /Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222 --user-data-dir="$HOME/Library/Application Support/Google/Chrome"
   ```
   (Use your normal user-data-dir so your existing HCL iLearning login persists. If Chrome is already running, quit it first -- the flag only takes effect on a fresh launch.)

2. In Chrome, navigate to your HCL iLearning course and open the first lesson's video page. Make sure the video is visible (not on a dashboard index).

3. Start Hermes with the browser toolset:
   ```bash
   hermes -t browser chat
   ```

4. In the Hermes prompt, attach to your Chrome:
   ```
   /browser connect
   ```

5. Invoke the skill:
   ```
   Run the ilearning-autoadvance skill on my current tab, max_modules=10.
   ```

## First-run safety pattern

Before the first unattended run, do a dry run to validate state classification:

``+   Run the ilearning-autoadvance skill on my current tab, max_modules=1, dry_run=true.
   ```

Watch the agent describe each action it WOULD take. If it misclassifies (e.g. calls a paused video "ended"), edit the SKILL.md classification rules and re-run.

Then do a single-module live run with approvals back on (temporarily set `approvals.mode: manual` in config):

```
   Run the ilearning-autoadvance skill on my current tab, max_modules=1.
   ```

Approve each click yourself. Confirm: video resumes, quiz answered, next-module clicked. If clean, flip approvals back to `scoped`/`auto` and do the full unattended run.

## Logs and troubleshooting

- Per-tick logs: `~/.hermes/logs/ilearning-autoadvance-<session-id>.jsonl`
- Run `hermes computer-use doctor` only if you suspect platform-level issues (not used by this skill, but good triage).
- If the agent gets stuck on "UNKNOWN" state for > 2 ticks, check the screenshot it logged -- HCL iLearning may have pushed a modal not covered by the classification rules. Edit SKILL.md to add the new state and re-run.
```

- [ ] **Step 2: Verify SETUP.md is readable**

Run: `cat ~/.hermes/skills/ilearning-autoadvance/SETUP.md | head -5`
Expected: prints the first 5 lines including the title. If empty, the write failed -- retry.

No commit -- file lives in `~/.hermes/skills/`, outside the repo.

---

### Task 5: Author the repo `README.md`

**Files:**
- Create: `~/Projects/auto-learn-for-me/README.md`

**Interfaces:**
- Consumes: Tasks 1-4.
- Produces: a repo-level cheat sheet pointing at the skill and SETUP.md.

- [ ] **Step 1: Write `README.md`**

Write `~/Projects/auto-learn-for-me/README.md`:

```markdown
# auto-learn-for-me

Autonomously advance HCL iLearning Success courses with Hermes Agent.

## What this is

A Hermes Agent skill pack that watches course videos in your own Chrome session (via CDP) and autonomously clicks "continue"/"next" to advance through modules, answers in-video quizzes, and navigates between lessons. Fully unattended.

## Quick start

1. One-time: follow `~/.hermes/skills/ilearning-autoadvance/SETUP.md`.
2. Per session:
   ```bash
   # Start Chrome with remote debugging, log into HCL iLearning, open a lesson
   /Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222 --user-data-dir="$HOME/Library/Application Support/Google/Chrome"

   # Start Hermes
   hermes -t browser chat
   # then: /browser connect
   # then: Run the ilearning-autoadvance skill on my current tab, max_modules=10
   ```

## Design

See `docs/superpowers/specs/2026-07-18-hermes-iLearning-autoadvance-design.md`.

## Implementation plan

See `docs/superpowers/plans/2026-07-18-hermes-iLearning-autoadvance.md`.

## First-run safety

Do a dry run first (`dry_run=true`, `max_modules=1`) to validate state classification against the real HCL iLearning DOM. Then a single-module live run with approvals on. Then the full unattended run.
```

- [ ] **Step 2: Commit**

```bash
cd ~/Projects/auto-learn-for-me
git add README.md
git commit -m "docs: add repo README for iLearning auto-advance"
```
Expected: commit succeeds.

---

### Task 6: Dry-run smoke test against a real HCL iLearning course

**Files:**
 None modified. This task validates the skill end-to-end.

**Interfaces:**
- Consumes: Tasks 1-5 (working Hermes, skill authored, config patched, SETUP.md, README).
- Produces: confidence that the skill's state classification matches the real HCL iLearning DOM.

- [ ] **Step 1: Start Chrome with remote debugging**

Quit Chrome fully (Cmd-Q). Then:
```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222 --user-data-dir="$HOME/Library/Application Support/Google/Chrome" &
```
Expected: Chrome opens. Verify the debug port is listening:
```bash
curl -s http://127.0.0.1:9222/json/version | head -1
```
Expected: JSON containing `"webSocketDebuggerUrl"`. If empty, Chrome did not start with the flag -- make sure no other Chrome process is running first.

- [ ] **Step 2: Log in and open a course**

In the Chrome window, navigate to HCL iLearning Success, log in via SSO/2FA, open a course, and click into the first lesson so the video element is visible. Note the lesson URL.

- [ ] **Step 3: Start Hermes and attach**

```bash
hermes -t browser chat
```
In the Hermes prompt:
```
/browser connect
```
Expected: Hermes confirms it attached to the Chrome instance and lists the open tabs. Confirm your HCL iLearning tab is in the list.

- [ ] **Step 4: Invoke the skill in dry-run mode**

In the Hermes prompt:
```
Run the ilearning-autoadvance skill on my current tab, max_modules=1, dry_run=true.
```
Expected: the agent begins polling, observes, and DESCRIBES each action it would take WITHOUT clicking. Watch the log output. Success criteria:
- It correctly classifies the state as `VIDEO_PLAYING` when the video is playing.
- When you pause the video manually, it reclassifies as `VIDEO_PAUSED` within ~5 seconds and identifies the correct resume button ref.
- If a quiz is visible, it reads the question and options and reasons about an answer.

If classification is wrong, edit `~/.hermes/skills/ilearning-autoadvance/SKILL.md` (State Classification section) and re-run. This is the expected iteration -- the skill is prose, not code; tuning is the work.

- [ ] **Step 5: Stop the run and capture findings**

Stop the Hermes session (Ctrl-C or `/quit`). Save the session log:
```bash
cp ~/.hermes/logs/ilearning-autoadvance-*.jsonl ~/Projects/auto-learn-for-me/.install-state/dry-run-$(date +%Y%m%d).jsonl 2>/dev/null || true
```
(If no log file was written, that itself is a finding -- the Logging section of SKILL.md needs fixing.)

Expected: you have a dry-run transcript proving the agent classifies state correctly on the real HCL iLearning DOM. Proceed to Task 7 only if classification is clean. If not, iterate on SKILL.md until it is.

No commit -- this is a verification step, not a code change. (The `.install-state` log is gitignored noise.)

---

### Task 7: Single-module live run, then full unattended run

**Files:**
- None modified.

**Interfaces:**
- Consumes: Task 6 clean dry-run.
- Produces: confidence the full loop works end-to-end on a real course.

- [ ] **Step 1: Temporarily flip approvals to manual**

In `~/.hermes/config.yaml`:
```yaml
approvals:
  mode: manual
```
This is the single-module live run -- you want to approve each click the first time through a real module.

Restart Hermes so the config reloads:
```bash
hermes -t browser chat
```

- [ ] **Step 2: Attach and invoke single-module live run**

In Hermes:
```
/browser connect
Run the ilearning-autoadvance skill on my current tab, max_modules=1.
```
Approve each click when prompted. Expected: the agent completes one full module -- video plays to end (or you let it), quiz answered (if present), "Next" clicked, new lesson loads. If anything goes wrong, kill the session and re-edit SKILL.md.

+- [ ] **Step 3: Flip approvals back to scoped/auto**

In `~/.hermes/config.yaml`:
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
```
Restart Hermes:
```bash
hermes -t browser chat
```

- [ ] **Step 4: Full unattended run**

In Hermes:
```
/browser connect
Run the ilearning-autoadvance skill on my current tab, max_modules=10.
```
Expected: the agent runs unattended for up to 10 modules. Watch the terminal summary at the end -- modules completed, quizzes attempted, any stuck points. Check `~/.hermes/logs/ilearning-autoadvance-<session-id>.jsonl` for per-tick detail.

Success criteria:
- No stuck loops (no 3-identical-URL pattern in the log).
- No double-clicks on submit/next (idempotency guards held).
- No logout/sign-out clicks.
- Agent stopped cleanly at `max_modules` or on a real terminal condition.

If any failure: edit SKILL.md, re-run the dry run (Task 6) to re-validate classification, then re-run this task.

- [ ] **Step 5: Commit a run-report marker**

```bash
cd ~/Projects/auto-learn-for-me
mkdir -p .install-state
cat > .install-state/first-full-run.md <<EOF
# First full unattended run
Date: $(date)
Modules completed: <fill in from terminal summary>
Quizzes attempted: <fill in>
Stuck points: <fill in or "none">
Skill version: ilearning-autoadvance as of $(date)
EOF
git add .install-state/first-full-run.md
git commit -m "chore: record first full unattended run outcome"
```
Expected: commit succeeds. This is the final deliverable marker -- the skill is live and proven.

---

## Self-Review (post-plan)

**Spec coverage:**
- Spec §1 Goal -- covered by all tasks.
- Spec §2 Background -- documented in SKILL.md (not a task; reference material).
- Spec §3 Architecture -- Task 1 (Hermes install), Task 2 (skill), Task 3 (config).
- Spec §4 Watch-Loop State Machine -- Task 2 Steps 3-6.
- Spec §5 Error Handling & Recovery -- Task 2 Step 6 (Error Recovery table in SKILL.md).
- Spec §6 Testing -- Task 6 (dry run), Task 7 (single-module live + full run).
- Spec §7 Deliverables -- Tasks 2, 3, 4, 5 produce the four deliverables.
- Spec §8 Non-Goals -- documented in SKILL.md (Safety Rules section).
- Spec §9 Risk Callouts -- mitigated by Task 6 dry-run before Task 7.

**Placeholder scan:** no TBD, TODO, or "implement later". Every step shows exact content or exact commands.

**Type/name consistency:** skill name `ilearning-autoadvance` used consistently in frontmatter, paths, config, and invocations. Parameters `max_modules`, `dry_run`, `tick_seconds` used consistently in SKILL.md and in the test invocations.