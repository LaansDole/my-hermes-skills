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
