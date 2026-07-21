# Hermes Covidence Title & Abstract Screening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Hermes Agent skill pack that autonomously screens references at the title & abstract stage of a Covidence systematic review, voting Yes/Maybe/No per the user's PICO criteria, in the user's Chrome session via CDP.

**Architecture:** Hermes Agent's `browser` toolset attaches to the user's already-logged-in Chrome (CDP port 9222). A prose skill pack at `~/.hermes/skills/covidence-screening/` drives a screen-loop state machine: observe -> classify (Review Summary / T&A Screening / Unknown) -> read reference -> classify vs CRITERIA.md -> vote (Yes/Maybe/No + optional rationale note) -> advance -> repeat. Vision-capable model via Nous Portal, fallback only. No application code; pure markdown. Approve-first-N onboarding implemented in-skill prose; no global config patch.

**Tech Stack:** Hermes Agent v0.18+ (MIT, Nous Research), Chrome with `--remote-debugging-port=9222`, vision-capable LLM via Nous Portal subscription, Covidence web app at `app.covidence.org`.

## Global Constraints

- **Deliverable is prose (markdown skill files), not code.** "Tests" in this plan are behavioral smoke checks against a real Covidence review (or the Covidence Demo review); there is no unit-test framework for skill prose. Each task's verification is a file-existence check, a frontmatter parse check, or a live run, not pytest.
- **No credentials in the agent.** The user logs into Covidence in Chrome themselves (institutional SSO, 2FA); the agent attaches via CDP. No SSO/2FA automation.
- **No anti-detection / stealth.** Out of scope by design.
- **Title & abstract stage only.** Agent must not navigate to Full Text, Data Extraction, Risk of Bias, or Settings. Strict allowlist: T&A screening screen + Review Summary page.
- **Single-reviewer mode required.** The user must switch the Covidence review to single-screener before running the agent. The agent does not configure this; SETUP.md documents it as a prerequisite.
- **Approve-first-N implemented in-skill.** No `~/.hermes/config.yaml` patch for this skill — keeps iLearning runs untouched.
- **Skill paths are absolute in this plan:** `~/.hermes/skills/covidence-screening/SKILL.md`, `~/.hermes/skills/covidence-screening/CRITERIA.md`, `~/.hermes/skills/covidence-screening/STATE.md`, `~/.hermes/skills/covidence-screening/SETUP.md`, `~/Projects/auto-learn-for-me/covidence-screening.md`.
- **Casing note:** `covidence-screening` (lowercase, hyphenated) in paths and directory names (filesystem-safe, matches Hermes skill conventions); `Covidence` (title case) in user-facing prose.
- **macOS only** for initial implementation (user's workstation).
- **Approvals default off for `browser.click`/`browser.type`** — but the skill gates the first N votes through an in-skill pause+confirm loop. The global Hermes config is NOT patched by this skill; if the user already patched it for iLearning, that stays as-is.

---

## File Structure

- **`~/.hermes/skills/covidence-screening/SKILL.md`** — The skill the agent loads. Contains: frontmatter, trigger, parameters, prerequisites, screen loop, state classification, decision step, action policy, approve-first-N onboarding, loop control, safety rules, logging format, error recovery. One file, one responsibility: tell the agent how to run the T&A screening loop.
- **`~/.hermes/skills/covidence-screening/CRITERIA.md`** — Template the user fills in with PICO + inclusion/exclusion bullets. Loaded fresh each session by the agent. Ships empty (template-only) so the agent refuses to run until the user has filled it in.
- **`~/.hermes/skills/covidence-screening/STATE.md`** — Persisted daily counter for the optional daily cap. Auto-created on first run; user can reset by deleting.
- **`~/.hermes/skills/covidence-screening/SETUP.md`** — Human-facing install/launch steps. Separate from SKILL.md so the agent does not load setup prose into its context every run.
- **`~/Projects/auto-learn-for-me/covidence-screening.md`** — Repo-level launch cheat sheet (sibling to the existing `README.md` for iLearning).

---

### Task 1: Verify Hermes Agent prerequisites

**Files:**
- Verify only: `~/.hermes/config.yaml`, `~/.hermes/.env`

**Interfaces:**
- Consumes: nothing
- Produces: confirmed working `hermes` CLI on `$PATH` with `browser` toolset registered and a vision-capable model configured. (If the user already completed the iLearning install, this task is a re-verification and should complete in one step.)

- [ ] **Step 1: Verify the binary is reachable**

Run: `hermes --version`
Expected: prints a version string >= `0.18.0`. If lower or missing, stop and surface to the user — they need to install/upgrade Hermes per the iLearning plan Task 1, or the browser toolset won't support the primitives this skill relies on.

- [ ] **Step 2: Verify the browser toolset is registered**

Run: `hermes tools list`
Expected: output includes `browser` in the enabled toolsets column. If not, the user needs to run `hermes setup tools` and select `Browser Automation` → `Local Chromium-family CDP` (per iLearning plan Task 1 Step 4).

- [ ] **Step 3: Verify Nous Portal / vision-capable model is configured**

Run: `hermes config show`
Expected: parsed config shows a model endpoint (Nous Portal or OpenAI-compatible). If missing, the user needs `hermes setup --portal` (per iLearning plan Task 1 Step 3).

No commit here — verification only. If all three steps pass, proceed. If any fails, surface to the user that the iLearning install plan must be completed first.

---

### Task 2: Author the skill — `SKILL.md` frontmatter, parameters, prerequisites

**Files:**
- Create: `~/.hermes/skills/covidence-screening/SKILL.md`

**Interfaces:**
- Consumes: Hermes `browser` toolset primitives (`tab.observe`, `tab.evaluate`, `tab.click`, `tab.fill`, `tab.screenshot`). Provided by Hermes at runtime — no code to write.
- Produces: a skill the agent auto-discovers and loads when the user mentions "covidence", "screen references", or "title and abstract screening". Subsequent tasks append sections to this same file.

- [ ] **Step 1: Create the skill directory**

Run:
```bash
mkdir -p ~/.hermes/skills/covidence-screening
```
Expected: directory exists. Verify with `ls -ld ~/.hermes/skills/covidence-screening`.

- [ ] **Step 2: Write `SKILL.md` header — frontmatter, parameters, prerequisites**

Write `~/.hermes/skills/covidence-screening/SKILL.md` with this content (subsequent steps append to the same file):

```markdown
---
name: covidence-screening
description: Autonomously screen references at the title & abstract stage of a Covidence systematic review in the user's Chrome session via CDP. Votes Yes/Maybe/No per the user's PICO criteria, writes a one-line rationale for Maybe votes, and runs unattended after an approve-first-N onboarding phase.
trigger:
  - covidence
  - screen references
  - title and abstract
  - T&A screening
---

# Covidence Title & Abstract Screening

## Parameters

- `max_refs` (int, default 200): hard cap on the number of references to vote on before stopping.
- `max_time` (int, default 90): hard cap on session wall-clock in minutes. Whichever of `max_refs` or `max_time` fires first stops the session.
- `daily_cap` (int, default 500): hard cap on total references voted across sessions in a single UTC day. `0` disables the daily cap. Persisted in `STATE.md`.
- `approve_first_n` (int, default 5): number of votes at the start of the session for which the agent pauses and waits for user confirmation before casting. After N approvals, the agent sets `auto_mode=true` and votes unattended for the rest of the session.
- `dry_run` (bool, default false): when true, observe each reference, reason through the decision, and *describe* the vote you would cast (with rationale for Maybe) WITHOUT clicking any vote button or writing to the notes field. Use for first-pass validation against a real review or the Covidence Demo review.

## Prerequisites

- A Chrome instance is running with `--remote-debugging-port=9222`.
- The user has logged into Covidence at `app.covidence.org` in that Chrome and is on the Review Summary page of the target review (not the dashboard).
- The target review is set to **single-reviewer mode** (Settings → Switch to single reviewer). In dual mode the agent's vote alone will not advance references; do not run in dual mode.
- `CRITERIA.md` in this skill directory has been filled in by the user with the PICO + inclusion/exclusion bullets. If it still contains the template placeholder text, REFUSE TO RUN and tell the user to edit it first.
- Hermes is attached to that Chrome via `/browser connect` (run this once per Hermes session before invoking the skill).
```

- [ ] **Step 3: Verify the file parses as valid YAML frontmatter**

Run:
```bash
hermes skills list
```
Expected: `covidence-screening` appears in the list of available skills. If not, verify the frontmatter has no tabs (use spaces), correct 2-space indentation under `trigger:`, and a single `---` delimiter on its own line before and after.

No commit here — `~/.hermes/skills/` is outside the project repo and is a user-local config directory. The skill is the deliverable; it lives in the user's home, not in git.

---

### Task 3: Append Screen Loop + State Classification to `SKILL.md`

**Files:**
 - Modify: `~/.hermes/skills/covidence-screening/SKILL.md` (append)

**Interfaces:**
 - Consumes: Task 2's `SKILL.md` header + parameters.
 - Produces: the observe→classify→act→sleep loop prose and the three-signal state classifier (URL / a11y tree / screenshot+vision).

- [ ] **Step 1: Append the Screen Loop section**

Append to `~/.hermes/skills/covidence-screening/SKILL.md`:

```markdown
## Screen Loop

Repeat until a stop condition (see Loop Control) fires:

1. **Observe** -- call `tab.observe()` to get the accessibility tree of the current tab. Also call `tab.evaluate` with the snippet below to get the current URL and hostname. Keep both results in context.

   ```js
   (() => ({hostname: location.hostname, pathname: location.pathname, href: location.href}))()
   ```

2. **Classify** the screen into one of: `REVIEW_SUMMARY`, `TA_SCREENING`, `UNKNOWN`.
3. **Act** per the action policy below.
4. **Sleep** `tick_seconds` (default 5) if no action was taken this tick; otherwise immediately repeat from step 1 (the page needs time to react to a vote before re-reading).
```

- [ ] **Step 2: Append State Classification section**

Append to `~/.hermes/skills/covidence-screening/SKILL.md`:

```markdown
## State Classification

Three signals, in order of preference:

1. **URL + page landmark** (primary, deterministic) -- the `tab.evaluate` snippet above returns `hostname` and `pathname`. Classify by matching against known Covidence routes:
   - `REVIEW_SUMMARY`: hostname is `app.covidence.org` AND the page shows the "Review Summary" heading with a "Title and Abstract Screening" section.
   - `TA_SCREENING`: hostname is `app.covidence.org` AND the accessibility tree contains the three vote buttons `Yes`, `Maybe`, `No` (or the "No more references" / queue-empty banner).
   - If hostname is not `app.covidence.org`, classify as `UNKNOWN` and apply the off-domain safety rule.

2. **Accessibility tree scan** (`tab.observe()`) -- look for:
   - The three vote buttons: `Yes`, `Maybe`, `No` (with their `@eN` refs).
   - The reference metadata block: title, abstract, authors, journal, MeSH tags.
   - The per-reference notes textarea (if present).
   - The "No more references" / queue-empty banner.
   - A vote-confirmation banner (indicates the reference is already voted; see re-vote guard).

3. **Screenshot + vision** (fallback only) -- invoked when the tree is ambiguous:
   - Icon-only vote buttons (no accessible name).
   - Shadow-DOM notes popup not exposed in the tree.
   - An unexpected modal or overlay.
   The vision pass describes what is on screen and returns a ref or coordinate. Never use vision for the decision itself -- the decision is text reasoning over title+abstract.

### `UNKNOWN` handling

Increment an `unknown_streak` counter. If `unknown_streak > 2`: take a screenshot via `tab.screenshot()`, describe what you see, log the observation, and keep polling (NO clicks) until a known state reappears or a stop condition fires. Do **not** click blindly.
```

- [ ] **Step 3: Verify the file is still valid**

Run: `hermes skills list`
Expected: `covidence-screening` still appears; no parse error. If a parse error appears, the appended markdown likely broke a code fence — check that every ` ``` ` has a matching closer.

No commit.

---

### Task 4: Append Decision Step + Action Policy to `SKILL.md`

**Files:**
 - Modify: `~/.hermes/skills/covidence-screening/SKILL.md` (append)

**Interfaces:**
 - Consumes: Task 3's state classifier (knows when we're on `TA_SCREENING` with a reference loaded).
 - Produces: the text-reasoning decision step that turns a reference + CRITERIA.md into a Yes/Maybe/No vote, and the action policy that casts it.

- [ ] **Step 1: Append the Decision Step section**

Append to `~/.hermes/skills/covidence-screening/SKILL.md`:

```markdown
## Decision Step

This is pure text reasoning, not a UI action. Run it only when state is `TA_SCREENING` with a reference loaded.

1. Read reference metadata from the accessibility tree: title, abstract, authors, journal, MeSH keywords (with Covidence's keyword highlighting if the tree exposes it).
2. Load `CRITERIA.md` from this skill directory (`~/.hermes/skills/covidence-screening/CRITERIA.md`) into context. Apply any inline overrides from the user's invocation (e.g. "also exclude studies published before 2010").
3. Reason per criterion: which PICO elements does this reference satisfy / violate / leave unclear? Show the reasoning briefly in the log.
4. Decide:
   - **Include (Yes)** -- meets all inclusion criteria, violates no exclusion criterion.
   - **Exclude (No)** -- violates a clear exclusion criterion (wrong population, wrong study design, not in the specified language, etc.).
   - **Maybe** -- borderline: meets some criteria but the title/abstract leaves a PICO element ambiguous (e.g. population unclear, study type not stated).
5. If Maybe: compose a one-line rationale citing the specific ambiguity (e.g. "Population unclear -- abstract says 'adults' but doesn't specify whether surgical patients"). This rationale will be written to the per-reference notes field before the vote is cast.

The model does this reasoning -- "attempt seriously" per the user's intent. No external lookups (PubMed, DOI, publisher PDFs). Covidence metadata only.
```

- [ ] **Step 2: Append the Action Policy section**

Append to `~/.hermes/skills/covidence-screening/SKILL.md`:

```markdown
## Action Policy

### `REVIEW_SUMMARY`

1. Find the "Continue" button under the "Title and Abstract Screening" section in the accessibility tree.
2. If found, click it via its `@eN` ref. This lands the tab on the T&A screening screen.
3. If `dry_run` is true, describe the navigation intent and do NOT click (dry-run mode only screens references, not navigation). Otherwise click.

### `TA_SCREENING` with a reference loaded

1. Run the **Decision Step** above. Get a decision: Yes, Maybe, or No (Maybe comes with a one-line rationale).
2. Extract the current reference's stable ID. Preferred: the Covidence reference ID exposed in the tree or URL. Fallback: hash of `title + first-author + year` (synthetic ID). Store as `current_ref_id`.
3. **Idempotency guard**: if `current_ref_id` is already in the `voted_ref_ids` set, do NOT vote again. Log "already voted, skipping" and poll for the next reference. (This should not happen in normal flow -- Covidence advances on vote -- but guards against double-clicks and re-opens.)
4. **Approve-first-N onboarding**: if `votes_approved_this_session < approve_first_n` AND `auto_mode` is false:
   - Print to the terminal: the `current_ref_id`, the title (short), the decision (Yes/Maybe/No), and the rationale (if Maybe).
   - Wait for user input. Accept three responses only:
     - `approve` -- cast this vote as decided. Increment `votes_approved_this_session`. If `votes_approved_this_session == approve_first_n`, set `auto_mode = true` and announce "Onboarding complete, switching to unattended mode."
     - `skip` -- leave this reference unvoted. Do NOT increment `votes_approved_this_session`. The agent advances to the next reference (Covidence will not auto-advance without a vote; in skip mode, the agent clicks the "Next" or "Skip reference" affordance if Covidence exposes one, otherwise it logs "cannot skip -- no affordance" and stops). Log the skip.
     - `stop` -- end the session immediately. Log summary including which references were skipped.
5. **Cast the vote** (or describe it if `dry_run`):
   - If **Maybe**: first type the rationale into the per-reference notes field. Find the notes textarea via `tab.observe()` (its `@eN` ref). If not found in the tree, fall back to screenshot+vision to locate it. If still not found after 1 retry, SKIP this Maybe vote entirely -- do NOT vote without the rationale. Log the reference ID and "notes field unavailable, skipped" so the user can review manually.
   - Then click the vote button (`Yes`, `Maybe`, or `No`) via its `@eN` ref. If the vote button is icon-only or missing from the tree, fall back to screenshot+vision to locate it.
   - In `dry_run`: print the vote + rationale instead of clicking or filling.
6. After the click, Covidence auto-advances to the next reference. Add `current_ref_id` to `voted_ref_ids`. Increment `refs_screened` and the daily counter in `STATE.md`.
7. Poll the next tick immediately (no sleep) so the page has time to react.

### `TA_SCREENING` with queue-empty banner

If the accessibility tree shows "No more references" / queue-empty banner (no title/abstract block, no vote buttons): stop the loop, log "queue empty", print summary.

### `UNKNOWN`

Increment `unknown_streak`. Screenshot + vision to classify. If genuinely a transient page transition (Covidence loading), wait one tick and re-observe. If a modal/error overlay is blocking, log and STOP -- do not click through modals.
```

- [ ] **Step 3: Verify the file is still valid**

Run: `hermes skills list`
Expected: `covidence-screening` still appears; no parse error.

No commit.

---

### Task 5: Append Loop Control, Safety, Logging, Error Recovery to `SKILL.md`

**Files:**
 - Modify: `~/.hermes/skills/covidence-screening/SKILL.md` (append)

**Interfaces:**
 - Consumes: Task 4's action policy and counters (`voted_ref_ids`, `votes_approved_this_session`, `refs_screened`).
 - Produces: the stop conditions, safety rules, logging format, and error recovery table.

- [ ] **Step 1: Append Loop Control section**

Append to `~/.hermes/skills/covidence-screening/SKILL.md`:

```markdown
## Loop Control

Track these counters across the session:
- `refs_screened` (int, starts 0): references voted on this session.
- `voted_ref_ids` (set): reference IDs voted this session (idempotency guard).
- `last_3_ref_ids` (list of last 3 `current_ref_id` values, infinite-loop guard).
- `votes_approved_this_session` (int, starts 0): approvals received in onboarding.
- `auto_mode` (bool, starts false): whether onboarding is complete.
- `session_start_ts` (ISO timestamp): for `max_time` enforcement.

Stop the loop when any of:
- `refs_screened >= max_refs`.
- `now - session_start_ts >= max_time * 60` seconds.
- Daily cap: read `STATE.md`; if today's counter >= `daily_cap` (and `daily_cap != 0`), stop with "daily cap reached (N/N)".
- Queue-empty banner detected.
- `last_3_ref_ids` are all identical AND the last action was a vote click (infinite-loop guard).
- Unrecoverable error: CDP connection dropped, page navigates outside `covidence.org`, vote buttons missing for > 30 s, model API failure after 3 backoffs.
- Approve-first-N: user responded `stop`.

### Re-vote guard

Covidence allows re-opening a voted reference in single mode to change the vote. This agent MUST NOT re-open already-voted references -- only operate on the "Awaiting my vote" queue. Detected by the presence of a vote-confirmation banner (already voted) vs. fresh vote buttons (awaiting vote). If a vote-confirmation banner is present, do not click anything; log and poll for the next reference.
```

- [ ] **Step 2: Append Safety Rules section**

Append to `~/.hermes/skills/covidence-screening/SKILL.md`:

```markdown
## Safety Rules

Hard rules the agent MUST follow:
- Never type into any field of `type="password"` (Hermes hard-blocks this anyway).
- Never click any element whose accessible name contains: logout, sign out, sign-out, signout, log off.
- Never click into Full Text, Data Extraction, Risk of Bias, or Settings -- strict allowlist of T&A screen + Review Summary page. If the page navigates elsewhere inside `covidence.org`, stop and log.
- If the page URL navigates outside the `covidence.org` domain (check via `tab.evaluate(() => location.hostname)`), stop the loop immediately and log.
- Never modify the review's inclusion/exclusion criteria, team members, or settings -- the agent is read-only on everything except vote buttons and the per-reference notes field.
- Hermes's built-in destructive-action blocklists (`sudo rm -rf`, `curl | bash`, fork bombs, lock-screen combos) remain active and are NOT overridden by this skill.
```

- [ ] **Step 3: Append Logging section**

Append to `~/.hermes/skills/covidence-screening/SKILL.md`:

```markdown
## Logging

Every tick, write a JSON line to `~/.hermes/logs/covidence-screening-<session-id>.jsonl` (create the logs dir if missing). The `<session-id>` is the ISO timestamp at session start.

```json
{"ts":"2026-07-18T12:34:56Z","ref_id":"<covidence-ref-id>","title":"<short title>","state":"TA_SCREENING","decision":"maybe","rationale":"Population unclear -- abstract says 'adults' but not whether surgical","action":"vote Maybe + note","ok":true}
```

Fields: `ts` (ISO), `ref_id`, `title` (truncated), `state` (REVIEW_SUMMARY/TA_SCREENING/UNKNOWN), `decision` (yes/maybe/no/skip), `rationale` (only for maybe), `action` (what was clicked or "dry-run describe"), `ok` (bool).

At loop end, print a summary to the terminal: refs screened, votes cast (Yes/Maybe/No counts), Maybe rationales list, time elapsed, any stuck points, daily-cap remaining.
```

- [ ] **Step 4: Append Error Recovery section**

Append to `~/.hermes/skills/covidence-screening/SKILL.md`:

```markdown
## Error Recovery

| Failure | Detection | Recovery |
|---|---|---|
| CDP connection dropped | `tab.observe()` returns connection error | Stop, log, surface to user. Cannot auto-recover (user must restart Chrome). |
| Session/login expired | Page navigates to institutional SSO login URL, or vote buttons missing for > 30 s | Stop loop, log URL, surface to user. No auto-relogin (credentials out of scope). |
| Vote landed wrong / no state change | `current_ref_id` unchanged 2 ticks after a vote click | Re-screenshot, re-classify, retry once. If still stuck, log and skip to next tick (do not spam clicks). |
| Maybe notes field write failed | Notes textarea `@eN` not found, or `tab.fill` returns error | Screenshot+vision to locate notes field. If still not found after 1 retry, SKIP the Maybe vote entirely -- do NOT vote without the rationale. Log the reference ID; user reviews manually. |
| Queue-empty banner missing but no reference loads | "No more references" not detected, but no title/abstract in tree for > 3 ticks | Screenshot + vision to classify. If genuinely empty, stop with summary. If a modal/error overlay is blocking, log and STOP rather than clicking through it. |
| Page JS error / blank render | Screenshot returns empty canvas or error overlay | Wait 2 ticks; if persists, log and STOP. Do not attempt to advance. |
| Model API failure / rate limit | Model call times out or 429 | Backoff 10 s -> 30 s -> 60 s; after 3 failures, stop and surface to user. |
| Infinite loop (same `current_ref_id` 3×) | `last_3_ref_ids` identical after actions | Stop, log, surface to user. |
| Daily cap hit | `STATE.md` counter >= `daily_cap` (and `daily_cap != 0`) | Stop, log "daily cap reached (N/N)", surface to user. Does not count toward `max_refs` for the next session. |
| Approve-first-N: user says `skip` | User response during onboarding | Leave reference unvoted, advance if Covidence exposes a skip affordance (otherwise stop and log), continue onboarding with the next reference. Do NOT auto-vote. Onboarding counter does NOT advance. |
| Approve-first-N: user says `stop` | User response during onboarding | End session immediately. Log summary including which references were skipped. |
```

- [ ] **Step 5: Verify the complete SKILL.md parses**

Run: `hermes skills list`
Expected: `covidence-screening` appears with no parse error. Open the file in an editor and eyeball that every ` ``` ` code fence has a matching closer and the YAML frontmatter is intact.

No commit.

---

### Task 6: Author `CRITERIA.md` (template)

**Files:**
 - Create: `~/.hermes/skills/covidence-screening/CRITERIA.md`

**Interfaces:**
 - Consumes: nothing.
 - Produces: a template the user fills in; the SKILL.md Decision Step loads it fresh each session and refuses to run if the template placeholder text is still present.

- [ ] **Step 1: Write `CRITERIA.md` template**

Write `~/.hermes/skills/covidence-screening/CRITERIA.md` with this content:

```markdown
# Screening Criteria

<!-- DO NOT REMOVE THIS LINE. The skill refuses to run while this placeholder is present.
     Replace everything below with your actual PICO + inclusion/exclusion bullets. -->

## PICO

- **Population**:
- **Intervention**:
- **Comparison**:
- **Outcome(s)**:

## Inclusion criteria

- (add bullets, e.g. "RCTs and controlled cohort studies", "English language", "2010-present")

## Exclusion criteria

- (add bullets, e.g. "Conference abstracts only", "Pediatric populations")

## Study types to include

- (e.g. RCTs, quasi-experimental, cohort, case-control, qualitative)
```

- [ ] **Step 2: Verify the file exists and is readable**

Run: `cat ~/.hermes/skills/covidence-screening/CRITERIA.md | head -5`
Expected: prints the first 5 lines including the `<!-- DO NOT REMOVE` marker.

No commit.

---

### Task 7: Author `STATE.md` (daily counter scaffold)

**Files:**
 - Create: `~/.hermes/skills/covidence-screening/STATE.md`

**Interfaces:**
 - Consumes: nothing at authoring time.
 - Produces: a scaffold the agent reads/writes at runtime to track the daily vote count. The agent updates it after every vote; this task just creates the initial structure.

- [ ] **Step 1: Write initial `STATE.md`**

Write `~/.hermes/skills/covidence-screening/STATE.md` with this content:

```markdown
# Daily screening counter

<!-- The agent updates this file after every vote. Delete the file to reset the counter. -->

date: 1970-01-01
screened_today: 0
```

The agent's runtime contract (documented in SKILL.md Loop Control): after each successful vote, it reads `STATE.md`, and if `date` matches today's UTC date it increments `screened_today`; otherwise it resets `date` to today and `screened_today` to 1. Before each vote, if `screened_today >= daily_cap` (and `daily_cap != 0`), it stops.

- [ ] **Step 2: Verify the file exists**

Run: `cat ~/.hermes/skills/covidence-screening/STATE.md`
Expected: prints the scaffold content above.

No commit.

---

### Task 8: Author `SETUP.md`

**Files:**
 - Create: `~/.hermes/skills/covidence-screening/SETUP.md`

**Interfaces:**
 - Consumes: the SKILL.md parameters and the CRITERIA.md template.
 - Produces: human-facing install + launch instructions the user reads once, not every run.

- [ ] **Step 1: Write `SETUP.md`**

Write `~/.hermes/skills/covidence-screening/SETUP.md` with this content:

```markdown
# Covidence Screening — Setup

## One-time setup

1. Install Hermes Agent v0.18+ and enable the `browser` toolset in local CDP mode (see the iLearning plan Task 1 if not already done).
2. Confirm `hermes setup --portal` is complete (vision-capable model configured).

## Per-review setup

1. Log into `app.covidence.org` in Chrome.
2. Open the target review. In Settings, switch the review to **single-reviewer mode** (dual mode is not supported by this skill -- your vote alone will not advance references).
3. Edit `~/.hermes/skills/covidence-screening/CRITERIA.md` -- fill in the PICO + inclusion/exclusion bullets. Remove the `<!-- DO NOT REMOVE` placeholder line. The skill refuses to run while the placeholder is present.

## Launch a session

1. Start Chrome with remote debugging:
   ```bash
   open -na "Google Chrome" --args --remote-debugging-port=9222
   ```
2. In Chrome, navigate to the review's Review Summary page (not the dashboard).
3. Start Hermes:
   ```bash
   hermes -t browser chat
   ```
4. In the Hermes prompt:
   ```
   /browser connect
   ```
   Then:
   ```
   run the covidence-screening skill on my current review, max_refs=200, max_time=90, dry_run=false
   ```
   Adjust `max_refs`, `max_time`, `approve_first_n`, `daily_cap`, and `dry_run` as needed. For first-pass validation, use `dry_run=true` against the Covidence Demo review.
   ```

## First-run safety

Always do the first run as `dry_run=true` on the Covidence Demo review (or a test review), then a single-reference live run (`max_refs=1`), then an approve-first-N run (`max_refs=10, approve_first_n=5`) before going fully unattended. See SKILL.md Testing Strategy (or the design spec Section 6).
```

- [ ] **Step 2: Verify the file exists**

Run: `cat ~/.hermes/skills/covidence-screening/SETUP.md | head -3`
Expected: prints the `# Covidence Screening — Setup` heading.

No commit.

---

### Task 9: Author repo-level launch cheat sheet `covidence-screening.md`

**Files:**
 - Create: `~/Projects/auto-learn-for-me/covidence-screening.md`

**Interfaces:**
 - Consumes: the skill pack from Tasks 2-8.
 - Produces: a short repo-side cheat sheet so the user can launch a session without re-reading SETUP.md.

- [ ] **Step 1: Write the cheat sheet**

Write `~/Projects/auto-learn-for-me/covidence-screening.md` with this content:

```markdown
# Covidence T&A Screening — Launch Cheat Sheet

Skill: `~/.hermes/skills/covidence-screening/`
Design spec: `docs/superpowers/specs/2026-07-18-hermes-covidence-screening-design.md`
Implementation plan: `docs/superpowers/plans/2026-07-18-hermes-covidence-screening.md`

## One-time per review

1. In Covidence, set the review to **single-reviewer mode** (Settings → Switch to single reviewer).
2. Edit `~/.hermes/skills/covidence-screening/CRITERIA.md` -- fill in PICO + inclusion/exclusion; remove the `<!-- DO NOT REMOVE` placeholder.

## Launch

```bash
# 1. Chrome with remote debugging
open -na "Google Chrome" --args --remote-debugging-port=9222

# 2. In Chrome, navigate to the review's Review Summary page.

# 3. Start Hermes
hermes -t browser chat
```

In the Hermes prompt:
```
/browser connect
run the covidence-screening skill on my current review, max_refs=200, max_time=90, dry_run=false
```

## First-run ladder (do all three before full unattended)

1. Dry run on Demo review: `dry_run=true, max_refs=10`.
2. Single-ref live: `max_refs=1`.
3. Approve-first-N: `max_refs=10, approve_first_n=5`.

## Stop conditions

- `max_refs` or `max_time` hit.
- Daily cap (in `STATE.md`) hit.
- Queue empty.
- Approve-first-N `stop` response.
- CDP drop / login expired / 3 consecutive identical ref IDs.

## Audit trail

- Log: `~/.hermes/logs/covidence-screening-<session-id>.jsonl` (one line per tick).
- Maybe rationales are in the per-reference notes field in Covidence (visible in the UI).
- End-of-session summary is printed to the Hermes terminal.
```

- [ ] **Step 2: Commit the cheat sheet**

Run:
```bash
cd ~/Projects/auto-learn-for-me
git add covidence-screening.md
git commit -m "docs: launch cheat sheet for Covidence T&A screening skill"
```
Expected: commit succeeds.

---

### Task 10: End-to-end smoke — dry run against Covidence Demo review

**Files:**
 - No file changes. Verifies the skill pack from Tasks 2-9 works against a real Covidence DOM.

**Interfaces:**
 - Consumes: the complete skill pack at `~/.hermes/skills/covidence-screening/` and a logged-in Chrome attached via CDP.
 - Produces: behavioral confirmation that the screen loop classifies states and reasons correctly on real Covidence DOM, without casting any votes.

**Prerequisites:**
 - Task 1 verified Hermes is installed.
 - Tasks 2-8 authored the skill pack.
 - User has filled in `CRITERIA.md` with at least a PICO + 2 inclusion + 2 exclusion bullets.
 - User is logged into Covidence in Chrome (with `--remote-debugging-port=9222`) and has opened the **Demo review** (bottom of the Covidence dashboard) at its Review Summary page.
 - Hermes attached via `/browser connect`.

- [ ] **Step 1: Run the skill in dry-run mode**

In the Hermes prompt:
```
run the covidence-screening skill on my current review, max_refs=10, dry_run=true
```

Expected: the agent navigates from Review Summary to the T&A screen, reads each of up to 10 references, reasons through the decision per CRITERIA.md, and PRINTS the vote it would cast (with rationale for Maybe) WITHOUT clicking. The log file `~/.hermes/logs/covidence-screening-<session-id>.jsonl` has one line per reference with `"action":"dry-run describe"`.

- [ ] **Step 2: Inspect the log**

Run:
```bash
ls -t ~/.hermes/logs/covidence-screening-*.jsonl | head -1 | xargs cat
```
Expected: 1-10 JSON lines, each with a populated `title` and `decision` field. If any line has `"state":"UNKNOWN"`, the state classifier is mis-detecting -- note which references tripped it for SKILL.md revision.

- [ ] **Step 3: Verify no votes were actually cast**

In Chrome, refresh the Demo review's Review Summary page. The "Awaiting my vote" count should be unchanged. If it dropped, `dry_run` did not suppress clicks -- this is a SKILL.md bug; fix the action policy's dry-run branch and re-run.

No commit.

---

### Task 11: End-to-end smoke — single-reference live run

**Files:**
 - No file changes.

**Interfaces:**
 - Consumes: the dry-run-validated skill pack.
 - Produces: confirmation that one live vote lands correctly and Covidence advances.

**Prerequisites:**
 - Task 10 dry run passed with no UNKNOWN states and no accidental votes.
 - Still on the Demo review (or a real review the user is willing to cast one vote on).

- [ ] **Step 1: Run the skill with `max_refs=1`**

In the Hermes prompt:
```
run the covidence-screening skill on my current review, max_refs=1, dry_run=false, approve_first_n=1
```

Expected: the agent reads the first reference, reasons, prints its decision + rationale, and PAUSES for onboarding approval (because `approve_first_n=1`). User responds `approve`. The agent clicks the vote button (writes the note first if Maybe), Covidence advances to the next reference. The loop stops because `max_refs=1`.

- [ ] **Step 2: Verify the vote landed**

In Chrome, open the Demo review's "Decisions" / PRISMA view. The first reference should show the agent's vote. If Maybe, the notes field should contain the agent's one-line rationale.

- [ ] **Step 3: Inspect the log**

Run:
```bash
ls -t ~/.hermes/logs/covidence-screening-*.jsonl | head -1 | xargs cat
```
Expected: 1 JSON line with `"action":"vote Yes"` (or `Maybe`/`No`) and `"ok":true`. If Maybe, a second line for the note write.

No commit.

---

### Task 12: End-to-end smoke — approve-first-N live run

**Files:**
 - No file changes.

**Interfaces:**
 - Consumes: the live-vote-validated skill pack.
 - Produces: confirmation that the onboarding loop pauses correctly and transitions to auto mode.

**Prerequisites:**
 - Task 11 passed.
 - At least 10 references remaining in the Demo review's T&A queue (if fewer, pick a real review the user is willing to test on).

- [ ] **Step 1: Run with `max_refs=10, approve_first_n=5`**

In the Hermes prompt:
```
run the covidence-screening skill on my current review, max_refs=10, max_time=30, dry_run=false, approve_first_n=5
```

Expected: the agent pauses on each of the first 5 references, prints decision + rationale, waits for user input. For each of the 5, respond `approve` (or `skip` for one to confirm skip works). After the 5th approval, the agent announces "Onboarding complete, switching to unattended mode" and casts the remaining 5 votes without pausing. Loop stops at `refs_screened == 10`.

- [ ] **Step 2: Verify the auto-mode transition landed**

Inspect the log:
```bash
ls -t ~/.hermes/logs/covidence-screening-*.jsonl | head -1 | xargs cat
```
Expected: first 5 lines have a `decision`/`action` reflecting approvals (and one skip if you tested skip). Remaining lines show votes cast without a pause marker. Confirm no double-votes (each `ref_id` appears at most once in `voted_ref_ids`).

- [ ] **Step 3: Verify the PRISMA flow in Covidence**

In Chrome, open the Demo review's PRISMA view. The T&A counts should reflect exactly the 10 votes cast (Yes+No+Maybe counts sum to 10, or 9 if you skipped one and the agent left it unvoted).

No commit.

---

### Task 13: Full unattended run on a real review

**Files:**
 - No file changes.

**Interfaces:**
 - Consumes: the onboarding-validated skill pack.
 - Produces: confirmation the agent runs unattended to a session bound without drift or loop.

**Prerequisites:**
 - Task 12 passed; the user is comfortable with the agent's decision quality.
 - User has filled in `CRITERIA.md` for a REAL review (not Demo) and switched it to single-reviewer mode.

- [ ] **Step 1: Run fully unattended with small bounds**

In the Hermes prompt:
```
run the covidence-screening skill on my current review, max_refs=20, max_time=15, dry_run=false, approve_first_n=0
```

Expected: the agent votes on up to 20 references (or 15 minutes, whichever first) without pausing. Stop conditions: `refs_screened == 20`, or `now - session_start_ts >= 900s`, or queue empty, or an unrecoverable error.

- [ ] **Step 2: Inspect the log for drift**

Run:
```bash
ls -t ~/.hermes/logs/covidence-screening-*.jsonl | head -1 | xargs cat | jq -r '. | "\(.ref_id) \(.decision)"' | sort | uniq -c | sort -rn
```
Expected: each `ref_id` appears exactly once (no double-votes). If any appears twice, the idempotency guard failed -- investigate SKILL.md's `voted_ref_ids` logic.

- [ ] **Step 3: Spot-check 3 decisions**

Pick three references at random from the log. For each, read the title/abstract in Covidence, compare to `CRITERIA.md`, and confirm the agent's decision matches what a human reviewer would vote. If any decision is clearly wrong (e.g. voted Yes on a pediatric study when the population is explicitly adults), the CRITERIA.md bullets are ambiguous -- refine them and re-run.

No commit.

---

### Task 14: Regression check — stop conditions

**Files:**
 - No file changes.

**Interfaces:**
 - Consumes: the skill pack.
 - Produces: confirmation each documented stop condition fires correctly and no spurious clicks happen after stop.

**Prerequisites:**
 - Task 13 passed.
 - User can manipulate the Covidence session / Chrome to force each condition.

- [ ] **Step 1: Force queue-empty stop**

On a review with only 1-2 references left in T&A, run `max_refs=50`. Expected: agent stops on queue-empty banner, not on `max_refs`.

- [ ] **Step 2: Force `max_time` stop**

Run `max_refs=50, max_time=1`. Expected: agent stops after ~1 minute regardless of `max_refs`.

- [ ] **Step 3: Force daily cap stop**

Edit `~/.hermes/skills/covidence-screening/STATE.md` to set `screened_today` to `daily_cap - 1` (and `date` to today's UTC date). Run `max_refs=10`. Expected: agent votes 1 reference, then stops with "daily cap reached".

- [ ] **Step 4: Force CDP drop**

Run with `max_refs=10`. After the first vote, close Chrome (Cmd-Q, not just the tab). Expected: next `tab.observe()` returns connection error; agent stops and surfaces the error. No crash, no infinite retry.

- [ ] **Step 5: Verify no spurious post-stop clicks**

For each stop above, inspect the log. Expected: the final log line is the stop event; no further vote clicks after it.

No commit.

---

## Self-Review

**Spec coverage:**
 - §1 Goal: covered by SKILL.md frontmatter + Decision Step (Task 4).
 - §2 Background: documented in SKILL.md Prerequisites + SETUP.md (Task 8).
 - §3 Architecture / Components 1-5: skill pack (Tasks 2-8), Chrome+CDP (SETUP.md Task 8), vision-capable model (Task 1 Step 3), approve-first-N in-skill (Task 4 Step 2). No `~/.hermes/config.yaml` patch — explicitly noted in Global Constraints.
 - §4 Screen-Loop State Machine: Tasks 3-5.
 - §4 Decision Step: Task 4 Step 1.
 - §4 Action Policy (incl. Approve-first-N, Maybe+note, queue-empty, re-vote guard): Task 4 Step 2.
 - §4 Loop Control (counters, max_refs/max_time, daily cap, idempotency, infinite-loop guard): Task 5 Step 1.
 - §4 Safety guardrails: Task 5 Step 2.
 - §5 Error Handling & Recovery table: Task 5 Step 4.
 - §5 Logging format: Task 5 Step 3.
 - §6 Testing Strategy items 1-7: Tasks 10-14 (dry run, single-ref, approve-first-N, full unattended, maybe-rationale check folded into Task 11 Step 2, stop-condition regression Task 14).
 - §7 Deliverables 1-6: Tasks 2, 6, 7, 8, (no config patch — Deliverable 5 N/A), 9.
 - §8 Non-Goals: enforced by Safety Rules (Task 5 Step 2) and Global Constraints.
 - §9 Risk Callouts: mitigations are in the action policy (screenshot+vision fallback, synthetic ref ID hash, jsonl audit trail, bounded session).

**Placeholder scan:** No TBD/TODO. CRITERIA.md ships with template placeholder text by design (the agent refuses to run while it's present) — this is intentional behavior, not a plan placeholder.

**Type/name consistency:** skill name `covidence-screening` used consistently in frontmatter, paths, config, and invocations. Parameters `max_refs`, `max_time`, `daily_cap`, `approve_first_n`, `dry_run`, `tick_seconds` used consistently in SKILL.md and in the test invocations (Tasks 10-13). Counters `refs_screened`, `voted_ref_ids`, `last_3_ref_ids`, `votes_approved_this_session`, `auto_mode`, `session_start_ts` introduced in Task 4, formalized in Task 5, consumed by Tasks 10-14. `STATE.md` fields `date`, `screened_today` introduced in Task 7, consumed in Task 5 and verified in Task 14.