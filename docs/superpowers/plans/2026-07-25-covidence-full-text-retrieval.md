# Covidence Full-Text Retrieval Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Hermes Agent skill pack that autonomously retrieves full-text PDFs for references at the full-text review stage of a Covidence systematic review, uploading each one it finds and leaving a note for manual follow-up on the rest. The skill never casts an Include/Exclude decision -- that stays 100% manual, per explicit user instruction.

**Architecture:** Hermes Agent's `browser` toolset attaches to the user's already-logged-in Chrome (CDP port 9222) and walks the Covidence "Full text review -> Screen references" list, same list-walking pattern as the existing `covidence-screening` skill. For each unresolved reference, a **Full-Text Discovery Step** runs three free, keyless, no-scraping open-access lookups over the `terminal` toolset (Unpaywall by DOI, then Semantic Scholar by DOI/title, then arXiv by ID). If all three miss and the optional `notebooklm_topic` parameter is set, a fourth, AI-assisted fallback drives NotebookLM's "Discover sources" feature in a second tab of the same Chrome session, searching the web for the specific paper and extracting a candidate URL from whatever it surfaces. Every layer's candidate URL is validated (must serve `application/pdf`), downloaded, and uploaded into Covidence via `tab.uploadFile`. References with no locatable full text get a note logged in Covidence's per-reference notes field instead, and are skipped. Approve-first-N onboarding gates the first few consequential actions (upload or note) before switching to unattended.

**Tech Stack:** Hermes Agent v0.18+ (MIT, Nous Research), Chrome with `--remote-debugging-port=9222`, `curl` + `python3` (terminal toolset), Unpaywall API, Semantic Scholar Graph API, arXiv, NotebookLM ("Discover sources" web UI feature), Covidence web app at `app.covidence.org`.

## Global Constraints

- **Deliverable is prose (markdown skill files), not code.** "Tests" in this plan are frontmatter-parse checks, grep verifications of appended content, and live dry-run/small-N smoke checks against a real Covidence review (or the Covidence Demo review) -- there is no unit-test framework for skill prose.
- **Never casts Include/Exclude at the full-text stage.** This is an explicit, hard requirement from the user: full-text review decisions stay entirely manual. The skill's only actions are uploading a found PDF or writing a not-found note.
- **Only legitimate, keyless, no-scraping open-access sources for Layers 1-3.** Unpaywall, Semantic Scholar Graph API, and arXiv direct PDF URLs. No sci-hub/libgen/annas-archive/z-lib, no search-engine scraping, no paywall circumvention, no captcha-solving.
- **Layer 4 (NotebookLM Discover) is optional and additive, never a replacement.** It only runs when Layers 1-3 all miss AND the user supplied `notebooklm_topic`. Omitting that parameter reproduces the exact Layers-1-3-only behavior with zero NotebookLM footprint -- no new tab opened, no toolset requirement beyond what Layers 1-3 already need.
- **No cookie-export hack, no third-party NotebookLM API wrapper.** Layer 4 drives NotebookLM's real web UI through the same CDP-attached Chrome already used for Covidence -- a second tab, not a separate script or `nlm` CLI dependency.
- **Exactly one NotebookLM notebook, reused by title, never persisted to a state file.** Named by `notebooklm_topic`; found-or-created fresh each session by scanning the NotebookLM home page. No new file tracks a notebook ID.
- **`contact_email` is required, no default.** Unpaywall's usage policy requires a real contact email on every request. The skill refuses to run without one, same placeholder-refusal pattern `covidence-screening` uses for `CRITERIA.md`.
- **No credentials in the agent.** The user logs into Covidence (and, if using Layer 4, NotebookLM) in Chrome themselves; the agent attaches via CDP. No SSO/2FA automation, no auto-login anywhere.
- **No anti-detection / stealth.** Out of scope by design.
- **Full text review, "Screen references" tab only, on the Covidence side.** The agent must not navigate to `Resolve conflicts`, `Awaiting other reviewer`, `Excluded references`, Data Extraction, Risk of Bias, or Settings. Strict allowlist: the Full text review -> Screen references list. On the NotebookLM side (Layer 4 only): strict allowlist of the Discover-sources flow within the one resolved notebook -- no other notebook, no delete/rename/share.
- **Reviewer mode is irrelevant here** (unlike `covidence-screening`) -- this skill never votes, so single vs. dual reviewer mode does not block it. SETUP.md must say this explicitly to avoid the user assuming the T&A prerequisite carries over.
- **No PICO/criteria file.** This skill makes no inclusion/exclusion judgment, so it ships without a `CRITERIA.md`-equivalent file.
- **Requires both `browser` and `terminal` Hermes toolsets** -- broader than `covidence-screening` (browser-only), because discovery lookups and PDF downloads run as `curl`/`python3` over `terminal`. Layer 4 adds no new toolset -- NotebookLM automation runs over the same already-required `browser` toolset (a second tab), and its candidate-URL validation/download reuses the same already-required `terminal` toolset.
- **Skill lives in-repo, deployed via symlink.** Matches the current (post-refactor) convention for `covidence-screening`: canonical files live at `skills/covidence-full-text-retrieval/*.md` under version control; SETUP.md documents symlinking into `~/.hermes/skills/covidence-full-text-retrieval/` for Hermes to auto-discover.
- **Casing:** `covidence-full-text-retrieval` (lowercase, hyphenated) in paths and directory names; "Covidence Full-Text Retrieval" (title case) in user-facing prose.
- **macOS only** for initial implementation (user's workstation; `curl`/`python3` ship by default).

---

## File Structure

- **`skills/covidence-full-text-retrieval/SKILL.md`** -- The skill the agent loads. Frontmatter, parameters, prerequisites, screen loop, state classification, full-text discovery step (Layers 1-3, then Layer 4's tab management / notebook reuse / discovery flow), action policy, loop control, safety rules, logging format, error recovery. One file, one responsibility: tell the agent how to run the full-text retrieval loop. No separate file for Layer 4 -- it is a section within this same file, since it shares every counter, log schema, and action-policy branch Layers 1-3 already define.
- **`skills/covidence-full-text-retrieval/STATE.md`** -- Persisted daily counter for the optional daily cap. Auto-created on first run; user can reset by deleting. Layer 4 does NOT add anything here -- the NotebookLM notebook is found-or-created fresh each session, never persisted.
- **`skills/covidence-full-text-retrieval/SETUP.md`** -- Human-facing install/launch steps, including the extra `terminal`-toolset approval scope, the symlink-into-`~/.hermes/skills/` step, and (new) the NotebookLM login prerequisite + `notebooklm_topic` launch example.
- **`README.md`** -- Modify: add a bullet under "Other skills in this repo".

---

### Task 1: Verify Hermes Agent prerequisites for this skill

**Files:**
- Verify only: Hermes CLI, `~/.hermes/config.yaml`

**Interfaces:**
- Consumes: nothing.
- Produces: confirmed working `hermes` CLI with BOTH `browser` and `terminal` toolsets registered, and `curl`/`python3` on `$PATH`. (If `covidence-screening` is already set up, `browser` is already enabled; this task additionally confirms `terminal`.) No separate verification step for NotebookLM -- Layer 4 reuses these same two toolsets; its only additional prerequisite (being logged into `notebooklm.google.com`) is a per-session, per-review condition, checked live by the skill itself (see SKILL.md Prerequisites in Task 2 and the Error Recovery table in Task 6), not a one-time install-time check.

- [ ] **Step 1: Verify the binary is reachable**

Run: `hermes --version`
Expected: prints a version string >= `0.18.0`. If lower or missing, stop and surface to the user.

- [ ] **Step 2: Verify both toolsets are registered**

Run: `hermes tools list`
Expected: output includes both `browser` and `terminal` in the enabled toolsets column. If `terminal` is missing, the user needs to run `hermes setup tools` and enable Terminal / Shell Access.

- [ ] **Step 3: Verify `curl` and `python3` are on PATH**

Run:
```bash
curl --version | head -1
python3 --version
```
Expected: both print a version string with no "command not found" error. macOS ships both by default; if either is missing, stop and surface to the user (they'll need Xcode CLI tools or a Python install).

No commit here -- verification only. If all three steps pass, proceed. If any fails, surface to the user before continuing.

---

### Task 2: Author the skill -- `SKILL.md` frontmatter, parameters, prerequisites

**Files:**
- Create: `skills/covidence-full-text-retrieval/SKILL.md`

**Interfaces:**
- Consumes: Hermes `browser` toolset primitives (`tab.observe`, `tab.evaluate`, `tab.click`, `tab.fill`, `tab.uploadFile`, `tab.screenshot`) and `terminal` toolset (`curl`, `python3`). Provided by Hermes at runtime -- no application code to write.
- Produces: a skill Hermes auto-discovers once symlinked (Task 8). Subsequent tasks append/insert sections into this same file.

- [ ] **Step 1: Create the skill directory**

Run:
```bash
mkdir -p skills/covidence-full-text-retrieval
```
Expected: directory exists. Verify with `ls -ld skills/covidence-full-text-retrieval`.

- [ ] **Step 2: Write `SKILL.md` header -- frontmatter, parameters, prerequisites**

Write `skills/covidence-full-text-retrieval/SKILL.md` with this content (subsequent tasks append/insert into the same file):

```markdown
---
name: covidence-full-text-retrieval
description: Autonomously retrieve full-text PDFs for references in the full-text review stage of a Covidence systematic review, in the user's Chrome session via CDP. Looks up open-access copies via Unpaywall, Semantic Scholar, and arXiv, with an optional NotebookLM-assisted last-resort web search, then uploads any PDF it finds through Covidence's "Upload full text" action. References with no locatable full text get a note logged for manual follow-up. Never casts an Include/Exclude decision -- that stays manual.
version: 1.0.0
metadata:
  hermes:
    tags: [covidence, systematic-review, full-text, open-access, notebooklm, browser-automation]
    requires_toolsets: [browser, terminal]
---

# Covidence Full-Text Retrieval

## Parameters

- `max_refs` (int, default 100): hard cap on the number of references to process before stopping.
- `max_time` (int, default 60): hard cap on session wall-clock in minutes. Whichever of `max_refs` or `max_time` fires first stops the session.
- `daily_cap` (int, default 300): hard cap on total references processed across sessions in a single UTC day. `0` disables the daily cap. Persisted in `STATE.md`.
- `approve_first_n` (int, default 5): number of consequential actions (an upload or a not-found note) at the start of the session for which the agent pauses and waits for user confirmation before acting. After N approvals, the agent sets `auto_mode=true` and acts unattended for the rest of the session.
- `contact_email` (string, REQUIRED, no default): a real email address sent as the `email` query parameter on every Unpaywall API call, per Unpaywall's usage policy (https://unpaywall.org/products/api). If missing, or does not contain both `@` and `.`, REFUSE TO RUN and tell the user to supply it (e.g. `contact_email=you@example.org`).
- `download_dir` (string, default `~/.hermes/downloads/covidence-full-text-retrieval`): local scratch directory for PDFs fetched before upload. Created on first use if missing.
- `notebooklm_topic` (string, optional, no default): when set, enables Layer 4 of the Full-Text Discovery Step -- an AI-assisted last-resort web search via NotebookLM's "Discover sources" feature, run only for references Layers 1-3 (Unpaywall / Semantic Scholar / arXiv) could not resolve. Also names the single shared NotebookLM notebook used for this research topic (found by exact title match, or created if none exists). When omitted, Layer 4 is skipped entirely -- no NotebookLM tab is opened, and a Layer 1-3 miss goes straight to `NOT_FOUND`.
- `notebooklm_max_candidates` (int, default 3): only relevant when `notebooklm_topic` is set. How many of NotebookLM Discover's recommendation cards to evaluate per reference, best-ranked first, before declaring a Layer 4 miss for that reference.
- `dry_run` (bool, default false): when true, run full-text discovery for real (the lookups, including Layer 4's Discover search and source-add, are read-only-ish informational calls) but *describe* the upload or note action WITHOUT downloading past the validation check, clicking "Upload full text", calling `tab.uploadFile`, or opening the Covidence notes dialog. Use for first-pass validation against a real review or the Covidence Demo review.
- `tick_seconds` (int, default 5): idle polling interval between ticks when no action was taken. After an action, poll again immediately (the page needs time to react).

## Prerequisites

- A Chrome instance is running with `--remote-debugging-port=9222`.
- The user has logged into Covidence at `app.covidence.org` in that Chrome and is on the **Full text review -> Screen references** tab of the target review (NOT Resolve conflicts, Awaiting other reviewer, or Excluded references -- those are out of scope; see Safety Rules).
- Hermes's `terminal` toolset is enabled alongside `browser` (this skill shells out to `curl` and `python3` for open-access lookups -- see Full-Text Discovery Step). Verify with `hermes tools list`; both `browser` and `terminal` must show as enabled.
- `curl` and `python3` are on `$PATH` (macOS ships both by default).
- Hermes is attached to that Chrome via `/browser connect` (run this once per Hermes session before invoking the skill).
- Unlike `covidence-screening`, this skill does NOT require single-reviewer mode -- it never casts an Include/Exclude vote, so the reviewer-mode setting is irrelevant here.
- No PICO criteria file is needed -- this skill makes no inclusion/exclusion judgment. Full-text review decisions remain entirely manual.
- **If `notebooklm_topic` is set**: the user is already logged into `notebooklm.google.com` in the SAME Chrome instance (the one Hermes is attached to via CDP). No separate NotebookLM credential setup, no cookie export. If the NotebookLM tab redirects to a Google sign-in page when Layer 4 first tries to use it, the skill disables Layer 4 for the rest of the session (logs once, falls back to Layers 1-3 only) rather than blocking the whole run.
```

- [ ] **Step 3: Verify the file is present and well-formed**

Run:
```bash
grep -c '^---$' skills/covidence-full-text-retrieval/SKILL.md
```
Expected: `2` (opening and closing frontmatter fence). Then, once symlinked (Task 8), run `hermes skills list` and confirm `covidence-full-text-retrieval` appears with no parse error.

- [ ] **Step 4: Commit**

```bash
git add skills/covidence-full-text-retrieval/SKILL.md
git commit -m "feat: scaffold covidence-full-text-retrieval skill (frontmatter, params, prerequisites)"
```

---

### Task 3: Append Screen Loop + State Classification to `SKILL.md`

**Files:**
- Modify: `skills/covidence-full-text-retrieval/SKILL.md` (append)

**Interfaces:**
- Consumes: Task 2's header + parameters.
- Produces: the observe -> classify -> act -> sleep loop prose and the `FULL_TEXT_REVIEW`/`UNKNOWN` state classifier, including the reference-block layout and the "already has full text" detection heuristic. This section covers the Covidence tab only -- Layer 4's NotebookLM tab has its own, separate flow described in Task 5 and is not part of this state machine.

- [ ] **Step 1: Append the Screen Loop section**

Append to `skills/covidence-full-text-retrieval/SKILL.md`:

```markdown
## Screen Loop

Repeat until a stop condition (see Loop Control) fires:

1. **Observe** -- call `tab.observe()` to get the accessibility tree of the current tab. Also call `tab.evaluate` with the snippet below to get the current URL, hostname, and scroll position. Keep both results in context.

   ```js
   (() => ({
     hostname: location.hostname,
     pathname: location.pathname,
     href: location.href,
     scrollY: window.scrollY,
     innerHeight: window.innerHeight,
     docHeight: document.documentElement.scrollHeight
   }))()
   ```

2. **Classify** the screen into one of: `FULL_TEXT_REVIEW`, `UNKNOWN`.
3. **Act** per the action policy below.
4. **Sleep** `tick_seconds` if no action was taken this tick; otherwise immediately repeat from step 1 (so the page has time to react to an upload/note before re-reading).

## State Classification

Two signals, in order of preference:

1. **URL + page landmark** (primary, deterministic) -- the `tab.evaluate` snippet above returns `hostname` and `pathname`. Classify:
   - `FULL_TEXT_REVIEW`: hostname is `app.covidence.org` AND the page heading reads `Full text review` with a `Screen references N` tab active (bold/underlined), alongside `Resolve conflicts`, `Awaiting other reviewer`, and `Excluded references` tabs, and a `Bulk upload missing full texts` button top-right. The accessibility tree contains at least one reference block matching the structure below.
   - If hostname is not `app.covidence.org`, OR the active tab is anything other than `Screen references` (e.g. the user navigated to `Resolve conflicts`), classify as `UNKNOWN` and apply the off-domain/off-tab safety rule -- do NOT act.

2. **Accessibility tree scan** (`tab.observe()`) -- the Full text review "Screen references" tab is a **single scrollable list of reference blocks** (NOT one reference per screen), same layout family as `covidence-screening`'s T&A list. Each reference block contains, in order:
   - A header line like `#82 - Agarwal 2026` (Covidence's own ref number + first author + year). Use the numeric part after `#` as `current_ref_id` if a `Ref ID:` line is not present; otherwise prefer the `Ref ID:` value, same way `covidence-screening` does.
   - Right-aligned **`Include`** / **`Exclude`** buttons -- present on this page too. This skill MUST NEVER click either (see Safety Rules); their presence is not a signal to act on, only to avoid.
   - The article **title** (large bold text).
   - The **authors** line.
   - The **journal/venue + year** line -- for preprints this may be two lines, e.g. `arXiv preprint arXiv:2602.08254 // 2026;(Query date: 2026-05-23 15:57:58): arxiv.org 2026 //`. Keep the full citation text; the Full-Text Discovery Step regexes it for an arXiv ID.
   - A **`DOI:`** line with the DOI text and an external-link icon, e.g. `DOI: 10.1609/aaai.v40i36.40246 ↗`. Not every reference has one (preprint-only entries often omit it).
   - A primary action row: **`Upload full text`** button (cloud-upload icon) and an **`Abstract`** disclosure toggle.
   - A per-reference footer with `Note`, `History`, `Duplicate`, `Move to screening` links. `Note` opens a notes dialog -- it is NOT an inline textarea (same as `covidence-screening`).
   - **Already-resolved detection**: a reference block already has full text attached when its primary action button's accessible name is anything other than exactly `Upload full text` (Covidence swaps the button/label once a file exists). Treat any block whose primary button does not read exactly `Upload full text` as already resolved and skip it.
   - Look across the whole visible list, not just the top of the page. Multiple ref blocks are on screen at once; the agent must walk them top-to-bottom.
   - Do not click `Sort`, `Filter`, `Show criteria`, `More options`, or `Tag` in the top toolbar, and do not click `All` (select-all checkbox) or `Bulk upload missing full texts`.

3. **Screenshot + vision** (fallback only) -- invoked when the tree is ambiguous:
   - The primary action button is icon-only (no accessible name) so the already-resolved heuristic can't be applied from the tree alone.
   - The notes dialog or file-chooser input is not exposed in the tree (shadow DOM).
   - An unexpected modal or overlay.
   The vision pass describes what is on screen and returns a ref or coordinate. Never use vision for the discovery decision itself -- discovery is the deterministic Unpaywall / Semantic Scholar / arXiv / NotebookLM-Discover lookup in the Full-Text Discovery Step, not visual reasoning over the page.

### `UNKNOWN` handling

Increment an `unknown_streak` counter. If `unknown_streak > 2`: take a screenshot via `tab.screenshot()`, describe what you see, log the observation, and keep polling (NO clicks) until `FULL_TEXT_REVIEW` reappears or a stop condition fires. Do **not** click blindly, and do NOT navigate the tab yourself -- if the user is on the wrong tab, log and wait rather than clicking `Screen references` for them.
```

- [ ] **Step 2: Verify the file is still well-formed**

Run:
```bash
grep -c '^```' skills/covidence-full-text-retrieval/SKILL.md
```
Expected: an even number (every opening fence has a closer). Odd count means a broken fence -- find and fix it before proceeding.

- [ ] **Step 3: Commit**

```bash
git add skills/covidence-full-text-retrieval/SKILL.md
git commit -m "feat: append screen loop and state classification to covidence-full-text-retrieval"
```

---

### Task 4: Append Full-Text Discovery Step (Layers 1-3) + Action Policy to `SKILL.md`

**Files:**
- Modify: `skills/covidence-full-text-retrieval/SKILL.md` (append)

**Interfaces:**
- Consumes: Task 3's state classifier and reference-block field extraction (`current_ref_id`, DOI line, citation text, title).
- Produces: the three-layer open-access lookup (Unpaywall -> Semantic Scholar -> arXiv) with PDF validation, and the action policy that downloads + uploads a found PDF or writes a not-found note. Layer 4 (NotebookLM Discover) is deliberately NOT part of this task -- it is inserted as its own task (Task 5) so a reviewer can accept the deterministic API layers independently of the AI-assisted fallback. This task's "no candidate" step is written so Task 5 can insert Layer 4 directly above it without any other edits to this section.

- [ ] **Step 1: Append the Full-Text Discovery Step section**

Append to `skills/covidence-full-text-retrieval/SKILL.md`:

```markdown
## Full-Text Discovery Step

Pure terminal lookups, not UI actions, unless noted otherwise. Run once per unresolved reference block, top-to-bottom. Layers are tried in order; the first one that resolves to a validated PDF wins.

1. **Extract identifiers** from the block's text (already in context from the Observe step):
   - `doi`: the text after `DOI:` up to (not including) the trailing `↗` glyph or whitespace, e.g. `10.1609/aaai.v40i36.40246`. Empty string if no `DOI:` line.
   - `arxiv_id`: regex the full citation text (header + journal/venue lines) for `arXiv:(\d{4}\.\d{4,5})`. Empty string if no match.
   - `title`: the block's title text, used as a Semantic Scholar search fallback query and (if Layer 4 is enabled) as the NotebookLM Discover search query.

2. **Layer 1 -- Unpaywall** (only if `doi` is non-empty):
   ```bash
   curl -s --max-time 20 "https://api.unpaywall.org/v2/${DOI}?email=${CONTACT_EMAIL}" \
     | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    print('')
    sys.exit()
loc = d.get('best_oa_location') or {}
print(loc.get('url_for_pdf') or loc.get('url') or '')
"
   ```
   Non-empty stdout -> `candidate_url`, `source=unpaywall`. Empty, or a JSON `{"error":true,...}` body -> fall through to Layer 2.

3. **Layer 2 -- Semantic Scholar** (if Layer 1 produced nothing):
   ```bash
   Q="${DOI:-$TITLE}"
   ENC_Q=$(python3 -c "import urllib.parse, sys; print(urllib.parse.quote(sys.argv[1]))" "$Q")
   curl -s --max-time 20 "https://api.semanticscholar.org/graph/v1/paper/search?query=${ENC_Q}&fields=title,openAccessPdf&limit=1" \
     | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    print('')
    sys.exit()
data = d.get('data') or []
if not data:
    print('')
    sys.exit()
oa = data[0].get('openAccessPdf') or {}
print(oa.get('url') or '')
"
   ```
   If `doi` is set, query `DOI:${doi}` as `Q` for a precise match; otherwise query the title text directly. Non-empty stdout -> `candidate_url`, `source=semantic_scholar`. Empty -> fall through to Layer 3.

4. **Layer 3 -- arXiv direct** (only if `arxiv_id` is non-empty and Layers 1-2 produced nothing):
   `candidate_url="https://arxiv.org/pdf/${arxiv_id}"`, `source=arxiv`.

5. **No candidate from Layers 1-3**: if `notebooklm_topic` is set, run **Layer 4 -- NotebookLM Discover** (see the dedicated section below) before concluding. If `notebooklm_topic` is not set, or Layer 4 also produces nothing, discovery result is `NOT_FOUND` (`source=none`, or `source=notebooklm` if Layer 4 ran but missed). Go to the Action Policy's Not-Found branch.

6. **Validate** whichever `candidate_url` was produced (Layer 1, 2, 3, or 4) actually serves a PDF, not an HTML landing/paywall page:
   ```bash
   curl -sIL --max-time 20 "$candidate_url" | grep -i '^content-type:' | tail -1
   ```
   Expected: a line containing `application/pdf`. If the header is missing, times out, or reads anything else (e.g. `text/html`), this candidate is invalid:
   - If it came from Layer 1, retry Layer 2, then Layer 3, then Layer 4 (if enabled).
   - If it came from Layer 2, retry Layer 3, then Layer 4 (if enabled).
   - If it came from Layer 3 (arXiv direct), retry Layer 4 (if enabled) -- otherwise `NOT_FOUND` overall.
   - If it came from Layer 4, try Layer 4's next candidate per its own internal retry rule (see the dedicated section); if all of Layer 4's candidates are exhausted, `NOT_FOUND` overall.
   If valid: discovery result is `FOUND` with this `candidate_url` and its `source`.

Never construct a `candidate_url` on a domain containing `sci-hub`, `libgen`, `annas-archive`, or `z-lib` (defensive check that applies to every layer, including Layer 4, even though none of the four legitimate sources used here can produce one) -- see Safety Rules.
```

- [ ] **Step 2: Append the Action Policy section**

Append to `skills/covidence-full-text-retrieval/SKILL.md`:

```markdown
## Action Policy

### `FULL_TEXT_REVIEW` -- walk the list top-to-bottom

The Screen references list is a scrollable list of reference blocks, many visible at once. The agent walks them top-to-bottom, resolving the first unresolved block it finds, then re-observing and continuing.

1. **Scan the visible reference blocks** top-to-bottom. For each block, determine `current_ref_id` and whether it is already resolved (primary button does not read exactly `Upload full text`; see State Classification).
2. **Find the first unresolved block.** If all visible blocks are already resolved, scroll down (`tab.evaluate(() => window.scrollBy(0, window.innerHeight * 0.8))`) to reveal more, and re-observe. If scrolling produces no new unresolved blocks after 2 attempts, the queue is empty -- see "Queue empty" below.
3. **Idempotency guard**: if `current_ref_id` is already in `processed_ref_ids`, skip this block (do NOT process it again). Continue scanning down the list.
4. Run the **Full-Text Discovery Step** for the target block (including Layer 4 if enabled and Layers 1-3 missed). Result is `FOUND` (with `candidate_url`, `source`) or `NOT_FOUND`.
5. **Approve-first-N onboarding**: if `actions_approved_this_session < approve_first_n` AND `auto_mode` is false:
   - Print to the terminal: the `current_ref_id`, the ref header, the title (short), the discovery result (`FOUND` + `candidate_url` + `source`, or `NOT_FOUND`), and the action about to be taken (`upload` or `note`).
   - Wait for user input. Accept three responses only:
     - `approve` -- take the action as decided. Increment `actions_approved_this_session`. If it now equals `approve_first_n`, set `auto_mode = true` and announce "Onboarding complete, switching to unattended mode."
     - `skip` -- do not act on this reference. Do NOT increment `actions_approved_this_session`. Add `current_ref_id` to `skipped_ref_ids` and continue scanning down. Log the skip.
     - `stop` -- end the session immediately. Log summary including which references were skipped.
6. **If `FOUND`** (or describing it under `dry_run`):
   - Download: `mkdir -p "${DOWNLOAD_DIR}"` then `curl -sL --max-time 60 -o "${DOWNLOAD_DIR}/${current_ref_id}.pdf" "$candidate_url"`.
   - Verify the download: the file must exist and be larger than 1024 bytes (`stat -f%z` on macOS). A file at or under that size is a truncated response or an error page that slipped past the Content-Type check -- treat as `NOT_FOUND` instead and fall through to step 7's Not-Found handling for this reference (log the discrepancy).
   - In `dry_run`: skip the actual `curl` download and print "would download `$candidate_url` and upload it" instead; do not touch the browser.
   - Otherwise, in the browser (Covidence tab): click the target block's `Upload full text` button via its `@eN` ref -- make sure it's the button belonging to THIS block, not the one above or below. This reveals a file input (possibly inside a small modal). Find that file input via `tab.observe()` and call `tab.uploadFile` on it with the local path `${DOWNLOAD_DIR}/${current_ref_id}.pdf`. If the input isn't directly exposed (e.g. a "Choose file" sub-button opens it first), click through, then call `tab.uploadFile`.
   - Re-observe within 3 ticks to confirm: the block's primary button no longer reads `Upload full text` (per the already-resolved heuristic). If confirmed: log `ok:true`, add `current_ref_id` to `uploaded_ref_ids`.
   - If not confirmed after 3 ticks: screenshot+vision fallback once to check for a stuck modal or error toast. If still unresolved, log "upload did not confirm, needs manual check", add `current_ref_id` to `upload_failed_ref_ids` -- do NOT retry the click a second time (avoid double-uploading).
7. **If `NOT_FOUND`** (or describing it under `dry_run`):
   - Compose a note: `"[covidence-full-text-retrieval] No full text found via automated lookup on <ISO date>. Tried: Unpaywall<if doi present>, Semantic Scholar, arXiv<if arxiv_id present><, NotebookLM Discover (N sources added to notebook '<notebooklm_topic>') if Layer 4 ran>. Needs manual retrieval."` (include only the sources actually attempted per the identifiers extracted and whether Layer 4 was enabled).
   - In `dry_run`: print the note text instead of opening the dialog.
   - Otherwise: click the target block's `Note` link via its `@eN` ref. Find the textarea inside the opened dialog via `tab.observe()`, type the note with `tab.fill`, then click the dialog's save/submit button. If the dialog or textarea is not exposed in the tree, fall back to screenshot+vision to locate it. If still not found after 1 retry, log "notes dialog unavailable, skipped note" and move on without a note -- do NOT click `Upload full text` or either vote button as a substitute action.
   - Add `current_ref_id` to `not_found_ref_ids`.
8. In all cases (uploaded, upload-failed, note written, or note-skipped): add `current_ref_id` to `processed_ref_ids`, increment `refs_processed` and the daily counter in `STATE.md`.
9. Poll the next tick immediately (no sleep) so the page has time to register the action before re-reading.

### `FULL_TEXT_REVIEW` -- queue empty

The Screen references list does NOT show a "No more references" banner. The queue is empty when:
- Scrolling reveals no new unresolved reference blocks after 2 scroll attempts, AND
- The top tab count confirms (e.g. `Screen references 0` remaining, or the count matches `refs_processed` this session).

When both hold, stop the loop, log "queue empty", print summary. If the tab count shows unresolved refs remain but none render, log and STOP -- do not click blindly.

### `UNKNOWN`

Increment `unknown_streak`. Screenshot + vision to classify. If genuinely a transient page transition (Covidence loading), wait one tick and re-observe. If a modal/error overlay is blocking, or the user has navigated to a different tab (`Resolve conflicts`, `Awaiting other reviewer`, `Excluded references`) or a different Covidence section, log and STOP -- do not click through modals or navigate the tab back yourself.
```

- [ ] **Step 3: Verify the file is still well-formed**

Run:
```bash
grep -c '^```' skills/covidence-full-text-retrieval/SKILL.md
```
Expected: an even number. Fix any unmatched fence before proceeding.

- [ ] **Step 4: Commit**

```bash
git add skills/covidence-full-text-retrieval/SKILL.md
git commit -m "feat: append full-text discovery step (layers 1-3) and action policy to covidence-full-text-retrieval"
```

---

### Task 5: Insert NotebookLM Discover Layer 4 (tab management, notebook reuse, discovery flow) into `SKILL.md`

**Files:**
- Modify: `skills/covidence-full-text-retrieval/SKILL.md` (insert into the middle of the file, between the Full-Text Discovery Step section from Task 4 and the Action Policy section from Task 4)

**Interfaces:**
- Consumes: Task 4's Full-Text Discovery Step (specifically step 5, "No candidate from Layers 1-3", which already says "run Layer 4 -- NotebookLM Discover ... before concluding" and step 6's validation retry chain, which already accounts for a Layer 4 candidate). Also consumes Task 2's `notebooklm_topic` / `notebooklm_max_candidates` parameters.
- Produces: the `Tab Management`, `NotebookLM Notebook Reuse`, and `Layer 4 -- NotebookLM Discover` subsections that Task 4's discovery step and Task 6's Logging section reference. Produces no new action-policy branches -- Layer 4 only ever emits the same `candidate_url`/`source` pair Layers 1-3 already emit, which Task 4's existing Action Policy already consumes uniformly.
- Full design rationale: `docs/superpowers/specs/2026-07-25-covidence-notebooklm-fulltext-discovery-design.md`.

- [ ] **Step 1: Insert the Tab Management + Notebook Reuse subsections**

Insert this content into `skills/covidence-full-text-retrieval/SKILL.md` immediately after the "## Full-Text Discovery Step" section's step 4 (the arXiv layer) and its introductory numbered list, but BEFORE its step 5 ("No candidate from Layers 1-3..."). Concretely: insert right before the line beginning `5. **No candidate from Layers 1-3**`:

```markdown
### Tab Management (Layer 4 only)

Only relevant when `notebooklm_topic` is set. The skill coordinates two tabs on the same CDP-attached Chrome:
- **Tab A (Covidence)** -- the tab used by every other section of this skill. Default target for every action unless a step explicitly says otherwise.
- **Tab B (NotebookLM)** -- opened once, lazily, the first time Layer 4 actually fires this session (the first reference where Layers 1-3 all miss). Stays open and is reused for every subsequent Layer 4 attempt in the session.

Every Layer 4 step below explicitly names which tab it acts on. Never issue a click/fill intended for one tab while the other is active -- address the tab explicitly via Hermes' tab list from `/browser connect`, never implicitly by "whichever tab was last used."

### NotebookLM Notebook Reuse (Layer 4 only)

The first time Tab B is opened in a session:
1. Navigate Tab B to the NotebookLM home page (the notebook list) at `notebooklm.google.com`.
2. If Tab B lands on a Google sign-in page instead: log "NotebookLM not authenticated, Layer 4 disabled for this session" once, set an in-memory `notebooklm_disabled_this_session = true`, and skip Layer 4 for every reference for the rest of the session (Layers 1-3 still run normally).
3. Otherwise, scan the notebook list for a notebook whose title exactly matches `notebooklm_topic`. Found -> open it, set `notebook_ready = true`. Not found -> create a new notebook and set its title to `notebooklm_topic` exactly, then set `notebook_ready = true`.
4. If step 3 finds MORE than one notebook with an exact title match: log a warning naming both, use the first match, do NOT create a third. Surface this in the end-of-session summary so the user can clean up manually.

This lookup runs once per session (cached as `notebook_ready` in memory) and is repeated fresh next session -- nothing about the notebook's identity is written to `STATE.md` or any other file.
```

- [ ] **Step 2: Insert the Layer 4 discovery flow subsection**

Immediately after the content from Step 1 (still before the original step 5 line), insert:

```markdown
### Layer 4 -- NotebookLM Discover (only if `notebooklm_topic` is set and `notebooklm_disabled_this_session` is not true)

Runs only when Layers 1-3 (per the Full-Text Discovery Step above) produced no candidate for the current reference.

1. Ensure `notebook_ready` (run NotebookLM Notebook Reuse above if this is the first Layer 4 call this session). If that sets `notebooklm_disabled_this_session = true`, stop here -- this reference's Layer 4 is a miss, proceed to the Full-Text Discovery Step's step 5 conclusion with `source=none`.
2. On Tab B, open **Discover sources** (the button next to "Add source" in the Sources panel of the resolved notebook).
3. Type a search query into the "Describe something you'd like to learn about" box: the reference's exact `title`, plus the first author's surname for disambiguation (e.g. `MAMA-Memeia! Multi-Aspect Multi-Agent Collaboration for Depressive Symptoms Identification in Memes Agarwal`). Submit.
4. Wait for the recommendation cards to render (each has a title and an AI-generated summary), up to 20s. No cards render -> Layer 4 miss for this reference (`notebook_sources_added=0`), do not retry the same query -- go to step 7.
5. Read up to `notebooklm_max_candidates` cards, best-ranked first. For each, in order:
   a. **Title-match check**: normalize both the candidate's title and the target reference's `title` (lowercase, strip punctuation, collapse whitespace) and require high token overlap. Not a confident match -> do not add it, move to the next candidate.
   b. Confident match -> click the card's **Add** action to import it as a source into the notebook. Increment a per-reference `notebook_sources_added` counter.
   c. On Tab B, open the newly added source's "view original" affordance (external-link icon, same pattern as Covidence's own DOI links). This opens the source's real URL in a new tab, Tab C (ephemeral). Read `location.href` from Tab C via `tab.evaluate(() => location.href)`. Close Tab C. Switch back to Tab B.
   d. That URL is `candidate_url`, `source=notebooklm`. Validate it per the Full-Text Discovery Step's step 6 (`curl -sIL` Content-Type check, run over `terminal`, not either browser tab). Valid PDF -> discovery result is `FOUND`, stop trying further candidates for this reference, go to step 6 below. Invalid -> continue to the next candidate in this loop (the invalid source stays added to the notebook regardless -- it's still a relevant byproduct source for later human reading).
   e. If `notebooklm_max_candidates` candidates have all been tried (added-but-invalid, or skipped on title-match) with no valid PDF: Layer 4 is a miss for this reference. Go to step 7.
6. **Layer 4 hit**: switch back to Tab A. Discovery result is `FOUND` with this `candidate_url`, `source=notebooklm`. Resume the Full-Text Discovery Step's step 6 conclusion / Action Policy's `FOUND` branch exactly as Layers 1-3 would.
7. **Layer 4 miss**: switch back to Tab A. Discovery result is `NOT_FOUND`, `source=notebooklm` if any candidates were evaluated (even if none added), else `source=none`. Log `notebook_sources_added` (may be 0). Resume the Full-Text Discovery Step's step 5 conclusion / Action Policy's `NOT_FOUND` branch exactly as a Layers-1-3-only miss would, except the composed note additionally credits however many sources landed in the notebook (see Task 4's Action Policy step 7, which already has this wording).
```

- [ ] **Step 3: Verify the insertion landed in the right place and the file is still well-formed**

Run:
```bash
grep -n '^5\. \*\*No candidate from Layers 1-3\*\*\|^### Tab Management\|^### NotebookLM Notebook Reuse\|^### Layer 4 -- NotebookLM Discover' skills/covidence-full-text-retrieval/SKILL.md
grep -c '^```' skills/covidence-full-text-retrieval/SKILL.md
```
Expected: the three new `###` headings appear, in order, all BEFORE the `5. **No candidate from Layers 1-3**` line (confirming the insertion point). Fence count is even.

- [ ] **Step 4: Commit**

```bash
git add skills/covidence-full-text-retrieval/SKILL.md
git commit -m "feat: insert NotebookLM Discover layer 4 (tab management, notebook reuse, discovery flow) into covidence-full-text-retrieval"
```

---

### Task 6: Append Loop Control, Safety Rules, Logging, Error Recovery to `SKILL.md`

**Files:**
- Modify: `skills/covidence-full-text-retrieval/SKILL.md` (append)

**Interfaces:**
- Consumes: Task 4's action policy and counters (`processed_ref_ids`, `uploaded_ref_ids`, `not_found_ref_ids`, `actions_approved_this_session`) and Task 5's Layer 4 concepts (`notebooklm_disabled_this_session`, `notebook_sources_added`, Tab B/C).
- Produces: the stop conditions, hard safety rules (including the never-vote, never-paywall-circumvent, and NotebookLM-allowlist rules), logging format (with the `source=notebooklm` and `notebook_sources_added` additions), and error recovery table (with the four Layer 4-specific rows).

- [ ] **Step 1: Append Loop Control section**

Append to `skills/covidence-full-text-retrieval/SKILL.md`:

```markdown
## Loop Control

Track these counters across the session:
- `refs_processed` (int, starts 0): references resolved (uploaded, note-written, or note-skipped) this session.
- `current_ref_id` (string or null): the reference currently being processed.
- `processed_ref_ids` (set): ref IDs resolved this session (idempotency guard).
- `uploaded_ref_ids` (set): ref IDs whose full text was successfully uploaded.
- `not_found_ref_ids` (set): ref IDs with a note logged for manual follow-up.
- `upload_failed_ref_ids` (set): ref IDs where a PDF was found and downloaded but the Covidence upload did not confirm.
- `skipped_ref_ids` (set): ref IDs skipped during onboarding (so they aren't re-targeted next tick).
- `last_3_ref_ids` (list of last 3 `current_ref_id` values, infinite-loop guard).
- `actions_approved_this_session` (int, starts 0): approvals received in onboarding.
- `auto_mode` (bool, starts false): whether onboarding is complete.
- `session_start_ts` (ISO timestamp): for `max_time` enforcement.
- `unknown_streak` (int, starts 0): consecutive UNKNOWN classifications; screenshot threshold for the UNKNOWN handling rule.
- `notebook_ready` (bool, starts false): whether Layer 4's notebook find-or-create has run this session (Layer 4 only).
- `notebooklm_disabled_this_session` (bool, starts false): set true if Tab B ever hits a Google sign-in page; disables Layer 4 for the rest of the session without stopping the whole run (Layer 4 only).

Stop the loop when any of:
- `refs_processed >= max_refs`.
- `now - session_start_ts >= max_time * 60` seconds.
- Daily cap: read `STATE.md`; if today's counter >= `daily_cap` (and `daily_cap != 0`), stop with "daily cap reached (N/N)".
- Queue empty (per the queue-empty rule above).
- `last_3_ref_ids` are all identical AND the last action was an upload or note attempt (infinite-loop guard).
- Unrecoverable error: CDP connection dropped, page navigates outside `covidence.org` (Tab A) or an unrecoverable state on Tab B that isn't the sign-in redirect covered by `notebooklm_disabled_this_session`, primary action button missing for > 30 s, `curl`/API failure after 3 backoffs.
- Approve-first-N: user responded `stop`.
```

- [ ] **Step 2: Append Safety Rules section**

Append to `skills/covidence-full-text-retrieval/SKILL.md`:

```markdown
## Safety Rules

Hard rules the agent MUST follow:
- Never click `Include` or `Exclude` on any reference -- the full-text include/exclude decision is entirely manual, by explicit user instruction. This skill only retrieves and uploads full text, or notes that it could not.
- Never type into any field of `type="password"` (Hermes hard-blocks this anyway).
- Never click any element whose accessible name contains: logout, sign out, sign-out, signout, log off.
- Never click `Move to screening`, `Duplicate`, `Bulk upload missing full texts`, `Sort`, `Filter`, `Show criteria`, `More options`, `Tag`, or the `All` select-all checkbox.
- Never navigate to the `Resolve conflicts`, `Awaiting other reviewer`, or `Excluded references` tabs, nor into Data Extraction, Risk of Bias, or Settings -- strict allowlist of the Full text review -> Screen references tab. If Tab A navigates elsewhere inside `covidence.org`, stop and log.
- If Tab A navigates outside the `covidence.org` domain (check via `tab.evaluate(() => location.hostname)`), stop the loop immediately and log.
- Never fetch or construct a `candidate_url` on a domain containing `sci-hub`, `libgen`, `annas-archive`, or `z-lib` -- this applies to every discovery layer, including Layer 4, even though none of the four legitimate sources used here can produce one, but the check stays as a hard backstop.
- Never modify the review's inclusion/exclusion criteria, team members, or settings -- the agent is read-only on everything except the `Upload full text` file input and the per-reference notes dialog.
- **Layer 4 / NotebookLM only**: strict allowlist on Tab B of the Discover-sources flow, the Add-source action, and opening a source's "view original" link, all confined to the one notebook resolved for `notebooklm_topic`. Never delete, rename, or share that notebook. Never touch any OTHER notebook in the account. Never remove a source once added, even one that didn't validate as a PDF. If Tab B ever navigates outside `notebooklm.google.com` (other than the deliberate, immediately-closed Tab C for reading a source's original URL), disable Layer 4 for the rest of the session (log, set `notebooklm_disabled_this_session = true`) and continue with Layers 1-3 only -- do not stop the whole run over a Layer 4-only problem.
- Hermes's built-in destructive-action blocklists (recursive force-delete, piped-shell installers, fork bombs, lock-screen combos) remain active and are NOT overridden by this skill.

## Logging

Every tick, write a JSON line to `~/.hermes/logs/covidence-full-text-retrieval-<session-id>.jsonl` (create the logs dir if missing). The `<session-id>` is the ISO timestamp at session start.

```json
{"ts":"2026-07-25T12:34:56Z","ref_id":"82","ref_header":"#82 - Agarwal 2026","title":"<short title>","state":"FULL_TEXT_REVIEW","discovery":"found","source":"notebooklm","candidate_url":"https://.../paper.pdf","action":"upload","ok":true,"notebook_sources_added":1}
```

Fields: `ts` (ISO), `ref_id`, `ref_header` (the `#82 - ...` line), `title` (truncated), `state` (FULL_TEXT_REVIEW/UNKNOWN), `discovery` (found/not_found), `source` (unpaywall/semantic_scholar/arxiv/notebooklm/none), `candidate_url` (empty string if `not_found`), `action` (upload/note/skip/dry-run describe), `ok` (bool), `notebook_sources_added` (int, default 0 -- only nonzero when Layer 4 ran and added at least one source to the notebook for this reference, regardless of whether one validated as a PDF).

At loop end, print a summary to the terminal: refs processed, uploaded/not-found/upload-failed counts, the not-found reference list (for manual follow-up), time elapsed, any stuck points, daily-cap remaining, the local path to `download_dir`, and (if `notebooklm_topic` was set) the notebook's title, how many references triggered Layer 4, and the total `notebook_sources_added` across the session.

## Error Recovery

| Failure | Detection | Recovery |
|---|---|---|
| CDP connection dropped | `tab.observe()` returns connection error | Stop, log, surface to user. Cannot auto-recover (user must restart Chrome). |
| Session/login expired (Covidence) | Page navigates to institutional SSO login URL, or no reference blocks render for > 30 s | Stop loop, log URL, surface to user. No auto-relogin. |
| Unpaywall/Semantic Scholar rate limit or timeout | `curl` returns non-2xx, empty body, or times out | Fall through to the next discovery layer immediately (do not retry the same layer) rather than failing the whole session. Only stop if ALL layers fail for 3 consecutive references in a row -- log and surface to user (likely a network-wide outage). |
| Download produced a truncated/error file | Downloaded file <= 1024 bytes despite a `application/pdf` Content-Type header | Treat as `NOT_FOUND` for this reference; log the discrepancy; continue with the Not-Found note action. |
| Upload did not confirm | Target block still reads `Upload full text` 3 ticks after `tab.uploadFile` | Screenshot+vision once to check for a stuck modal/toast. If still unresolved, log, add to `upload_failed_ref_ids`, do NOT retry the click. Continue scanning down. |
| Notes dialog write failed | `Note` link `@eN` not found, dialog didn't open, or `tab.fill` returns error | Screenshot+vision to locate the Note link / dialog. If still not found after 1 retry, log "notes dialog unavailable, skipped note" and move on without writing it -- do NOT vote or upload as a substitute. |
| Queue-empty detection false negative | Tab count shows unresolved refs remain but scrolling yields no unresolved blocks after 2 attempts | Screenshot + vision to classify. If genuinely empty, stop with summary. If a modal/error overlay is blocking, log and STOP rather than clicking through it. |
| Page JS error / blank render | Screenshot returns empty canvas or error overlay | Wait 2 ticks; if persists, log and STOP. |
| Infinite loop (same `current_ref_id` targeted 3x without landing) | `last_3_ref_ids` identical after action attempts | Stop, log, surface to user. |
| Daily cap hit | `STATE.md` counter >= `daily_cap` (and `daily_cap != 0`) | Stop, log "daily cap reached (N/N)", surface to user. |
| Approve-first-N: user says `skip` | User response during onboarding | Leave reference unresolved, add to `skipped_ref_ids`, continue scanning down. Do NOT auto-act. Onboarding counter does NOT advance. |
| Approve-first-N: user says `stop` | User response during onboarding | End session immediately. Log summary including which references were skipped. |
| NotebookLM tab (Tab B) not authenticated | Tab B navigates to a Google sign-in URL | Log once, set `notebooklm_disabled_this_session = true`, continue with Layers 1-3 only for the rest of the session. Do not stop the whole run. |
| Discover sources produces no cards / times out | No recommendation cards render within 20s of submitting the query | Treat as a Layer 4 miss for this reference (no candidates to evaluate); do not retry the same query. |
| "View original" doesn't open a new tab / URL unreadable | `tab.evaluate` on the expected Tab C errors or times out | Skip this candidate, try the next one (up to `notebooklm_max_candidates`); if all fail, Layer 4 miss for this reference. |
| Notebook-list scan finds two notebooks matching `notebooklm_topic` | More than one exact-title match on the NotebookLM home page | Log a warning, use the first match, do not create a third. Surface this in the end-of-session summary so the user can clean up manually. |
```

- [ ] **Step 3: Verify the complete `SKILL.md` is well-formed**

Run:
```bash
grep -c '^```' skills/covidence-full-text-retrieval/SKILL.md
grep -c '^---$' skills/covidence-full-text-retrieval/SKILL.md
```
Expected: an even fence count, and exactly `2` for the frontmatter delimiter count. Once symlinked (Task 8), also run `hermes skills list` and confirm `covidence-full-text-retrieval` parses with no error.

- [ ] **Step 4: Commit**

```bash
git add skills/covidence-full-text-retrieval/SKILL.md
git commit -m "feat: append loop control, safety rules, logging, error recovery (incl. NotebookLM layer 4) to covidence-full-text-retrieval"
```

---

### Task 7: Author `STATE.md`

**Files:**
- Create: `skills/covidence-full-text-retrieval/STATE.md`

**Interfaces:**
- Consumes: nothing.
- Produces: the daily-cap counter file `SKILL.md`'s Loop Control section reads/writes as `processed_today`. Layer 4 adds nothing here -- the NotebookLM notebook is never persisted to a file (see Global Constraints).

- [ ] **Step 1: Write `STATE.md`**

Write `skills/covidence-full-text-retrieval/STATE.md` with this content:

```markdown
# Daily full-text retrieval counter

<!-- The agent updates this file after every processed reference. Delete the file to reset the counter. -->

date: 1970-01-01
processed_today: 0
```

- [ ] **Step 2: Verify field name consistency**

Run:
```bash
grep -n 'processed_today\|daily_cap' skills/covidence-full-text-retrieval/SKILL.md skills/covidence-full-text-retrieval/STATE.md
```
Expected: `SKILL.md`'s Loop Control / Parameters sections reference `daily_cap` and (via "the daily counter in `STATE.md`") the same `processed_today` field name used here -- no mismatched counter names between the two files.

- [ ] **Step 3: Commit**

```bash
git add skills/covidence-full-text-retrieval/STATE.md
git commit -m "feat: add STATE.md daily counter for covidence-full-text-retrieval"
```

---

### Task 8: Author `SETUP.md`

**Files:**
- Create: `skills/covidence-full-text-retrieval/SETUP.md`

**Interfaces:**
- Consumes: Tasks 2-7 (the finished `SKILL.md` and `STATE.md`).
- Produces: human-facing install, per-review setup, launch, first-run-safety, and quick-reference sections -- including the symlink-into-`~/.hermes/skills/` step, the extra `terminal`-toolset approval guidance, and (new) the optional NotebookLM login prerequisite plus a `notebooklm_topic` launch example.

- [ ] **Step 1: Write `SETUP.md`**

Write `skills/covidence-full-text-retrieval/SETUP.md` with this content:

```markdown
# Covidence Full-Text Retrieval — Setup

## One-time setup

1. Install Hermes Agent v0.18+ (same install as `covidence-screening`; skip if already done).
2. Enable BOTH the `browser` and `terminal` toolsets:
   ```bash
   hermes tools list
   ```
   Expected: both `browser` and `terminal` show as enabled. If `terminal` is missing, run `hermes setup tools` and enable it (Terminal / Shell Access).
3. Confirm `curl` and `python3` are on `$PATH` (macOS ships both by default):
   ```bash
   curl --version | head -1
   python3 --version
   ```
4. Merge the extra approval scopes into `~/.hermes/config.yaml` so the session runs unattended after onboarding, same pattern as `.hermes-config/config-patch.yaml`:
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
       - browser.uploadFile
       # terminal's exec/run action key varies by Hermes version --
       # run `hermes tools list --schema terminal` (or `hermes config show --defaults`)
       # to find the exact key in your installed version and add it here.
   ```
   Back up `~/.hermes/config.yaml` first (`cp ~/.hermes/config.yaml ~/.hermes/config.yaml.bak.$(date +%Y%m%d-%H%M%S)`). Without the terminal key added, every `curl` call this skill makes will pause for manual approval, defeating unattended operation after onboarding.
5. Symlink this skill into Hermes's skill directory (Hermes auto-discovers skills in `~/.hermes/skills/`; this repo is the source of truth):
   ```bash
   mkdir -p ~/.hermes/skills
   ln -sf "$(pwd)/skills/covidence-full-text-retrieval" ~/.hermes/skills/covidence-full-text-retrieval
   ```
   Verify:
   ```bash
   hermes skills list
   ```
   `covidence-full-text-retrieval` should appear.

## Per-review setup

1. Log into `app.covidence.org` in Chrome.
2. Open the target review and navigate to **Full text review -> Screen references**.
3. Have a real contact email ready to pass as `contact_email` -- Unpaywall requires one on every lookup call.
4. No reviewer-mode change and no criteria file needed -- this skill never casts an Include/Exclude vote.
5. **Optional -- NotebookLM last-resort search (Layer 4)**: if you want the skill to try NotebookLM's "Discover sources" web search for references Unpaywall/Semantic Scholar/arXiv all miss, log into `notebooklm.google.com` in the SAME Chrome window (the one on port 9222). No cookie export, no separate credentials -- the skill drives that tab directly. Skip this step entirely if you don't want Layer 4; the skill runs fine without it (just omit `notebooklm_topic` at launch).

## Launch a session

1. Start Chrome with remote debugging (same as `covidence-screening`):
   ```bash
   open -na "Google Chrome" --args --remote-debugging-port=9222
   ```
2. In Chrome, navigate to the review's **Full text review -> Screen references** tab. (If using Layer 4, also open a second tab logged into `notebooklm.google.com` -- the skill will find and use it.)
3. Start Hermes:
   ```bash
   hermes -t browser,terminal chat
   ```
4. In the Hermes prompt:
   ```
   /browser connect
   ```
   Then, without Layer 4:
   ```
   run the covidence-full-text-retrieval skill on my current review, contact_email=you@example.org, max_refs=100, max_time=60, dry_run=false
   ```
   Or, with the optional NotebookLM last-resort layer enabled:
   ```
   run the covidence-full-text-retrieval skill on my current review, contact_email=you@example.org, notebooklm_topic="AI multi-agent depression screening review", max_refs=100, max_time=60, dry_run=false
   ```
   Adjust `max_refs`, `max_time`, `approve_first_n`, `daily_cap`, `download_dir`, `notebooklm_max_candidates`, and `dry_run` as needed. For first-pass validation, use `dry_run=true` against the Covidence Demo review.

## First-run safety

Always do the first run as `dry_run=true` on the Covidence Demo review (or a test review), then a single-reference live run (`max_refs=1`), then an approve-first-N run (`max_refs=10, approve_first_n=5`) before going fully unattended. If using `notebooklm_topic`, do at least one dry run and one approved live run WITH it set before relying on Layer 4 unattended -- confirm in the NotebookLM UI that only the intended notebook was touched.

## Quick reference

- **Stop conditions**: `max_refs` or `max_time` hit; daily cap (in `STATE.md`) hit; queue empty; approve-first-N `stop` response; CDP drop / login expired / 3 consecutive identical ref IDs; 3 consecutive references failing all discovery layers. A NotebookLM auth problem (Layer 4 only) disables Layer 4 for the rest of the session rather than stopping the run. Full detail in `SKILL.md` under "Loop Control".
- **Audit trail**: every tick appends a JSON line to `~/.hermes/logs/covidence-full-text-retrieval-<session-id>.jsonl`; not-found notes land in the per-reference notes field in Covidence (visible in the UI); fetched PDFs are kept in `download_dir` (default `~/.hermes/downloads/covidence-full-text-retrieval`) for audit -- clean this directory periodically, it is not auto-pruned; sources NotebookLM Discover adds (Layer 4 only) accumulate in the one notebook named by `notebooklm_topic`, including ones that didn't validate as a PDF -- that notebook is a useful byproduct research artifact, not just a search cache; an end-of-session summary prints to the Hermes terminal. Full detail in `SKILL.md` under "Logging".
- **What this skill never does**: cast an Include/Exclude vote, touch `Move to screening`/`Duplicate`/bulk actions, fetch from paywall-circumvention sites, or (Layer 4 only) touch any NotebookLM notebook other than the one named by `notebooklm_topic`. Full-text review decisions stay 100% manual.
```

- [ ] **Step 2: Verify cross-references are accurate**

Run:
```bash
grep -n 'SKILL.md\|STATE.md' skills/covidence-full-text-retrieval/SETUP.md
```
Expected: every reference points to a section name that actually exists in `SKILL.md` ("Loop Control", "Logging") -- confirmed by Tasks 3-6 above.

- [ ] **Step 3: Commit**

```bash
git add skills/covidence-full-text-retrieval/SETUP.md
git commit -m "docs: add SETUP.md for covidence-full-text-retrieval (incl. optional NotebookLM layer 4 setup)"
```

---

### Task 9: Update `README.md`

**Files:**
- Modify: `README.md` (append a bullet to "Other skills in this repo")

**Interfaces:**
- Consumes: the finished skill pack from Tasks 2-8.
- Produces: discoverability -- a reader of the repo's README sees the new skill listed alongside `slack-todo-bot`, `slack-scan`, and `covidence-screening`.

- [ ] **Step 1: Read the current "Other skills in this repo" section**

Run:
```bash
grep -n "Other skills in this repo" -A 6 README.md
```
Confirm the exact three existing bullet lines and their indentation/format before appending a fourth.

- [ ] **Step 2: Append the new bullet**

Add this line immediately after the existing `covidence-screening` bullet under "## Other skills in this repo":

```markdown
- [`skills/covidence-full-text-retrieval/`](skills/covidence-full-text-retrieval/SKILL.md) -- Companion to `covidence-screening` for the next stage: for each reference in Covidence's full-text review "Screen references" list, looks up an open-access PDF via Unpaywall/Semantic Scholar/arXiv (with an optional NotebookLM Discover last-resort web search) and uploads it, or leaves a note for manual follow-up if none is found. Never casts an Include/Exclude vote -- that stage stays fully manual.
```

- [ ] **Step 3: Verify the bullet renders correctly**

Run:
```bash
grep -n "covidence-full-text-retrieval" README.md
```
Expected: one match, the new bullet line, with a valid relative link path.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: list covidence-full-text-retrieval in README"
```

---

### Task 10: End-to-end smoke validation

**Files:**
- Verify only: `skills/covidence-full-text-retrieval/SKILL.md`, `SETUP.md`, `STATE.md` (deployed via the Task 8 symlink)

**Interfaces:**
- Consumes: the complete skill pack (Tasks 2-9).
- Produces: confirmation that the skill loads, classifies the Full text review page correctly, discovers and uploads a full text for a reference that has one available via Layers 1-3, correctly notes-and-skips one that doesn't, and (separately) that Layer 4 fires, searches, and either uploads or notes correctly when Layers 1-3 miss and `notebooklm_topic` is set -- run against the Covidence Demo review (or a low-stakes real review) with `dry_run=true` first.

- [ ] **Step 1: Confirm the skill loads**

Run:
```bash
hermes skills list
```
Expected: `covidence-full-text-retrieval` appears with no parse errors.

- [ ] **Step 2: Dry-run against the Covidence Demo review, without Layer 4**

In Chrome, open the Demo review's Full text review -> Screen references tab. In Hermes:
```
run the covidence-full-text-retrieval skill on my current review, contact_email=you@example.org, max_refs=5, dry_run=true
```
Expected terminal output: for each of up to 5 references, a printed discovery result (`FOUND` with `candidate_url`+`source`, or `NOT_FOUND`) and a described action (`would upload` / `would note`), with NO actual `curl` download past the validation check, no click on `Upload full text`, and no notes dialog opened. Confirm at least one reference resolves via each of Layers 1-3 if the Demo review's references support it (a DOI-bearing reference for Unpaywall, an arXiv preprint for the arXiv layer); if the Demo review lacks variety, note which layers weren't exercised and revisit with a small real review that has both DOI and arXiv references.

- [ ] **Step 3: Fix any misclassification found in Step 2**

If the agent misclassifies the page, misreads a reference block field (e.g. picks up the wrong DOI, or the "already has full text" heuristic doesn't detect the button-label swap for that Covidence UI version), edit `skills/covidence-full-text-retrieval/SKILL.md`'s "State Classification" or "Full-Text Discovery Step" section and re-run Step 2. The skill is prose -- tuning is the work, not code. Commit any fix:
```bash
git add skills/covidence-full-text-retrieval/SKILL.md
git commit -m "fix: tune covidence-full-text-retrieval based on live dry-run observation"
```

- [ ] **Step 4: Dry-run with Layer 4 enabled, against a reference Layers 1-3 can't resolve**

Pick (or temporarily treat) a Demo-review reference with no DOI and no arXiv ID -- or one whose DOI/arXiv lookups you already confirmed miss in Step 2. Make sure you are logged into `notebooklm.google.com` in the same Chrome. In Hermes:
```
run the covidence-full-text-retrieval skill on my current review, contact_email=you@example.org, notebooklm_topic="Covidence demo review smoke test", max_refs=1, dry_run=true
```
Expected: the skill opens a second tab to NotebookLM, finds-or-creates a notebook titled exactly `Covidence demo review smoke test`, runs Discover sources with the reference's title, and (in `dry_run`) describes whichever candidate it would try to add/validate/upload instead of acting -- if it also actually clicks Add and opens the source's "view original" tab during discovery (per the design, discovery itself is not gated by `dry_run`, only the terminal upload/note action is), confirm in the NotebookLM UI that exactly one notebook with that title exists and it contains the source(s) the log says it added.

- [ ] **Step 5: Fix any Layer 4 misbehavior found in Step 4**

If notebook reuse misfires (e.g. creates a duplicate, or the title-match heuristic accepts an unrelated result), edit the "NotebookLM Notebook Reuse" or "Layer 4 -- NotebookLM Discover" subsections (Task 5) and re-run Step 4. Commit any fix:
```bash
git add skills/covidence-full-text-retrieval/SKILL.md
git commit -m "fix: tune covidence-full-text-retrieval NotebookLM layer 4 based on live dry-run observation"
```

- [ ] **Step 6: Single-reference live run with approvals**

Once both dry runs look correct, run one real reference through end to end (without Layer 4, for a reference Layers 1-3 can resolve):
```
run the covidence-full-text-retrieval skill on my current review, contact_email=you@example.org, max_refs=1, approve_first_n=1, dry_run=false
```
Expected: the agent prints the discovery result and proposed action, waits for `approve`, then (if you approve) either successfully uploads a PDF that the target block now reflects (primary button no longer reads `Upload full text`) or writes a visible note in Covidence's per-reference notes field. Confirm the outcome in the Covidence UI directly (not just the agent's log).

- [ ] **Step 7: Confirm no Include/Exclude click occurred**

In the Covidence UI, check the reference processed in Step 6: its Include/Exclude state must be unchanged (still unvoted) -- the skill must not have touched it. This is the hard acceptance check for the user's core requirement. Also confirm, in the NotebookLM UI (if Step 4 ran), that no notebook other than `Covidence demo review smoke test` was created or modified.

No commit for Steps 2, 4, 6, 7 (live verification only, no file changes) unless a fix loop (Step 3 or 5) was triggered.

---

## Self-Review

**Spec coverage:**
- Full-text discovery via API lookups -> Task 4 (Unpaywall/Semantic Scholar/arXiv layers).
- Full-text discovery via NotebookLM last-resort web search -> Task 5 (tab management, notebook reuse-by-title with no persisted state, Discover flow, title-match, add-source, extract-URL-via-view-original, validate) -- matches `docs/superpowers/specs/2026-07-25-covidence-notebooklm-fulltext-discovery-design.md` section-for-section.
- Upload found PDFs -> Task 4 Action Policy step 6, using `tab.uploadFile`, unchanged by and reused verbatim for Layer 4 hits (no new action-policy branch, per the design's explicit non-goal).
- Skip + note for manual follow-up when nothing found, including crediting NotebookLM byproduct sources -> Task 4 Action Policy step 7.
- No full-text review (Include/Exclude) decisions made by the agent -> Safety Rules (Task 6) + explicit acceptance checks (Task 10 Steps 7).
- Layer 4 is optional and additive, never a replacement, per the user's own decision during design -> Global Constraints, Task 2's `notebooklm_topic` parameter (omit = zero NotebookLM footprint), Task 4 step 5's conditional.
- Single notebook per research topic, no notebook-per-reference/per-review, no persisted notebook ID -> Task 5's NotebookLM Notebook Reuse subsection, Global Constraints.
- No cookie-export hack / no `nlm` CLI dependency -> Global Constraints, Task 5 (same CDP-attached Chrome, a second tab).

**Placeholder scan:** no `TBD`/`implement later`/"add validation" language anywhere in the task bodies above; every code block is complete, runnable content, not a description of content.

**Type/name consistency:** `current_ref_id`, `processed_ref_ids`, `uploaded_ref_ids`, `not_found_ref_ids`, `upload_failed_ref_ids`, `skipped_ref_ids`, `actions_approved_this_session`, `auto_mode`, `refs_processed`, `discovery`/`source`/`candidate_url` fields, `processed_today` (STATE.md), and the Layer 4 additions `notebook_ready`, `notebooklm_disabled_this_session`, `notebook_sources_added` are used identically across Tasks 2-10 -- verified by re-reading each section while assembling this plan. `source` now has four valid values (`unpaywall`/`semantic_scholar`/`arxiv`/`notebooklm`) plus `none`, consistent between Task 4's discovery step, Task 5's Layer 4 flow, and Task 6's Logging field description.
