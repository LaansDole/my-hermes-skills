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
