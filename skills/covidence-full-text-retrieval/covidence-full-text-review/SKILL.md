---
name: covidence-full-text-review
description: "Review full-text papers in a Covidence systematic review. Mode 1 (unattended): processes the queue of references with uploaded full texts and casts Include/Exclude votes autonomously. Mode 2 (secondary_reviewer): receives a URL from the user, reads the paper, returns a structured Include/Exclude verdict with rationale, and optionally casts the vote in Covidence when a ref_id is supplied."
version: 1.0.0
metadata:
  hermes:
    tags: [covidence, systematic-review, full-text, review, browser-automation]
    requires_toolsets: [browser, terminal]
---

# Covidence Full-Text Review

This skill operates in two modes set via the `mode` parameter:

- **Mode 1 (`unattended`)**: scans the Covidence Full text review -> Screen references queue, accesses each reference's uploaded full text, reads the PDF, applies eligibility criteria, and casts Include/Exclude votes with rationale notes — all autonomously after an optional onboarding phase.
- **Mode 2 (`secondary_reviewer`)**: the user supplies a `url` (paper URL, DOI landing page, or arXiv link). The agent downloads and reads the paper, applies criteria, and returns a structured verdict. If `ref_id` is also provided, the agent additionally casts the vote in Covidence and writes the rationale to the notes field.

## Parameters

- `mode` (str, REQUIRED): `"unattended"` or `"secondary_reviewer"`. REFUSE TO RUN if absent.
- `url` (str, Mode 2 only, REQUIRED when mode=secondary_reviewer): the paper URL to review. May be a direct PDF URL, DOI link, arXiv abstract, PubMed page, or any URL from which the agent can reach the full text.
- `ref_id` (str, optional, Mode 2 only): Covidence Ref ID (the numeric `Ref ID:` value on the reference block, e.g. `"4060"`). When provided alongside `url`, the agent also casts the Include/Exclude vote in Covidence and writes the rationale note. When omitted in Mode 2, the agent returns a recommendation only (no Covidence write).
- `review_id` (str, default `"773228"`): the Covidence review ID. Used to construct the full-text review URL. Override only when running on a different review.
- `criteria_file` (str, default `"CRITERIA.md"`): path to the eligibility criteria file, relative to this skill directory. Must exist and be filled in before running. The agent refuses to run if it still contains the placeholder text.
- `max_refs` (int, default 20, Mode 1 only): hard cap on references reviewed per session.
- `max_time` (int, default 60): wall-clock cap in minutes.
- `daily_cap` (int, default 100, Mode 1 only): hard cap on references reviewed across sessions in a single UTC day. `0` disables. Persisted in `STATE.md`.
- `approve_first_n` (int, default 3, Mode 1 only): number of Include/Exclude votes at the start for which the agent pauses for user confirmation before casting. After N approvals, `auto_mode=true` and the agent acts unattended.
- `dry_run` (bool, default false): when true, reason through the decision and describe the vote + rationale WITHOUT clicking any button or writing to the notes field.
- `rationale_in_notes` (bool, default true): when true, write the Include/Exclude rationale to the per-reference notes field in Covidence before casting the vote.
- `pdf_max_chars` (int, default 20000): maximum characters of extracted PDF text to load into context.
- `tick_seconds` (int, default 5, Mode 1 only): idle polling interval between ticks when no action was taken.

## User Preferences

This user runs Mode 1 fully unattended with:

- `approve_first_n=0` — skip onboarding, enter auto_mode immediately
- `rationale_in_notes=true` — always write rationale (Include or Exclude reason) to the note field
- No manual confirmation for any action

Set these on every Mode 1 invocation unless the user explicitly overrides.

## Prerequisites

### Both modes
- `CRITERIA.md` in this skill directory is filled in with the review's eligibility criteria. If it still contains the placeholder text, REFUSE TO RUN and tell the user to edit it first.
- `curl` and `python3` are on `$PATH`.
- `pdftotext` or PyMuPDF (`fitz`) available for PDF text extraction — check on first use. If neither is present, fall back to `browser_navigate` text extraction (see PDF Extraction Step).

### Mode 1 (unattended) additional prerequisites
- A Chrome/Brave instance is running with `--remote-debugging-port=9222`.
- The user is logged into Covidence at `app.covidence.org` in that browser and is on the **Full text review -> Screen references** tab of the target review.
- Hermes is attached to that browser via `/browser connect`.
- Run `covidence-full-text-retrieval` first to populate the queue with uploaded full texts if needed.

### Mode 2 (secondary_reviewer) additional prerequisites
- No Covidence browser session is required unless `ref_id` is provided (vote-casting step needs the same browser prerequisites as Mode 1).
- The `url` parameter must be reachable by `curl`. For paywalled content, supply a direct OA PDF URL (e.g. arXiv, PMC, Unpaywall result).

## Browser Window Management

Run this whenever Brave appears windowless, `browser_snapshot` returns empty, or CDP reports the wrong URL:

1. `computer_use(action='list_apps')` — check for `com.brave.Browser` running but `windows=[]`.
2. If windowless: `osascript -e 'tell application "Brave Browser" to make new window'`
3. `computer_use(action='focus_app', app='com.brave.Browser', raise_window=true)`
4. `computer_use(action='capture', app='com.brave.Browser', mode='vision')` — confirm visible.
5. `browser_navigate(url='https://app.covidence.org/reviews/<review_id>/full_text_reviews/screen_references')` — always explicit after restoring window.

## Mode 2: Secondary Reviewer Workflow

Mode 2 is a single-pass workflow (no loop):

1. **Resolve the URL to a PDF**:
   - If the `url` parameter already looks like a direct PDF (ends in `.pdf`, or Content-Type is `application/pdf`), use it directly.
   - If it is a DOI link (`doi.org/...` or `dx.doi.org/...`), try Unpaywall for a `url_for_pdf`:
     ```bash
     DOI=$(python3 -c "import sys,re; m=re.search(r'10\.\d{4,}/\S+', sys.argv[1]); print(m.group() if m else '')" "$url")
     curl -s --max-time 20 "https://api.unpaywall.org/v2/${DOI}?email=dolelongan@gmail.com" \
       | python3 -c "import json,sys; d=json.load(sys.stdin); loc=d.get('best_oa_location') or {}; print(loc.get('url_for_pdf') or loc.get('url') or '')"
     ```
   - If it is an arXiv abstract URL (`arxiv.org/abs/...`), construct the PDF URL: `https://arxiv.org/pdf/<ID>`.
   - If it is a PubMed or PMC URL, try Semantic Scholar with the PMID/PMCID to get `openAccessPdf`.
   - If still no PDF URL: attempt `browser_navigate` to the URL and extract visible text (browser fallback — see PDF Extraction Step).
   - If no text can be extracted: stop and report "Could not retrieve full text from <url>. Please supply a direct OA PDF URL."

2. **Extract text** (see PDF Extraction Step).

3. **Apply criteria** (see Decision Step). Decision is `Include` or `Exclude` with a rationale.

4. **Deliver verdict via pbcopy** (so the user can Cmd+V into Word without Warp soft-wrap artifacts). Do NOT print the verdict body to the terminal — pipe it to clipboard only, then print a one-line summary confirming the decision.

   Plain text rules: no markdown symbols, ALL CAPS section headers, single blank line between sections, no hard line breaks mid-sentence.

   Use the heredoc pattern (handles single quotes safely):

   ```bash
   cat > /tmp/hermes_verdict.txt << 'EOF'
   === Full-Text Review Verdict ===
   Title:    <extracted title or URL>
   Decision: INCLUDE / EXCLUDE
   Criteria applied: PCC (Population / Concept / Context)
   Key findings from full text:
     - Population: <what the paper studies>
     - Concept: <multi-agent / LLM framework described>
     - Context: <healthcare setting / deployment context>
   Rationale: <2-4 sentences citing specific text>
   Confidence: HIGH / MEDIUM / LOW
   Confidence note: <if MEDIUM or LOW, explain ambiguity>
   EOF
   pbcopy < /tmp/hermes_verdict.txt && echo "Verdict copied to clipboard - Cmd+V into Word." && rm /tmp/hermes_verdict.txt
   ```

   After running: print one line to terminal e.g. "Decision: INCLUDE (HIGH confidence) - copied to clipboard."

5. **Cast vote in Covidence** (only if `ref_id` is provided):
   - Navigate to `https://app.covidence.org/reviews/<review_id>/full_text_reviews/screen_references`.
   - Find the reference block by `ref_id`, write rationale to notes if `rationale_in_notes=true`, click Include/Exclude.
   - Confirm vote landed. Log to JSONL.

## Mode 1: Unattended Review Loop

### Screen Loop

Repeat until a stop condition fires:

1. **Observe** — `browser_snapshot(full=false)` + evaluate:
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

2. **Classify** screen: `FULL_TEXT_REVIEW` or `UNKNOWN`.

3. **Act** per the action policy below.

4. **Sleep** `tick_seconds` if no action; otherwise re-observe immediately.

### State Classification

- `FULL_TEXT_REVIEW`: hostname is `app.covidence.org` AND the page heading is `Full text review` with `Screen references N` tab active, and reference blocks are visible in the accessibility tree. Each reference block contains a `#N - Author YYYY` header, title, authors, journal/year, DOI line, primary action area (Include + Exclude buttons for unreviewed refs), and a `Note` / `History` / `Duplicate` footer.
  - **Unreviewed**: primary action area shows both `Include` and `Exclude` buttons.
  - **Reviewed**: `Include` / `Exclude` buttons replaced by a voted-state marker (chip, badge, or buttons gone). Skip these.
  - **Full text uploaded**: a `Full text` or `Manage full text` button/link is present in the block. References without uploaded full text are skipped (cannot review without reading the paper).
- `UNKNOWN`: anything else. Apply UNKNOWN handling.

### Full Text URL Harvesting (per reference)

Before the Decision Step, obtain the full text URL from Covidence:

1. Locate the URL via `browser_console` by climbing from the reference header paragraph:
   ```js
   (() => {
     const hdr = Array.from(document.querySelectorAll('p')).find(
       p => p.textContent.trim().startsWith('#<ref_id> -')
     );
     if (!hdr) return {error: 'header not found'};
     let el = hdr;
     for (let i = 0; i < 5; i++) {
       el = el.parentElement;
       if (!el) break;
       for (const a of el.querySelectorAll('a[href]')) {
         const href = a.href || '';
         if (href && !href.includes('covidence.org') && href !== '#') {
           return {url: href};
         }
       }
     }
     return {url: null};
   })()
   ```
2. If `url` returned: use it.
3. If null: click the `Full text` / `Manage full text` button to open the modal, read the URL from the modal's link display, then close the modal (Escape or Cancel).
4. If still no URL: log "no_full_text_url", add to `skipped_no_ft_ref_ids`, skip. Do NOT vote.

### PDF Extraction Step

Given a `candidate_url`:

1. **Download**:
   ```bash
   mkdir -p ~/.hermes/downloads/covidence-full-text-review
   curl -sL --max-time 60 -o ~/.hermes/downloads/covidence-full-text-review/<ref_id>.pdf "$candidate_url"
   ```
   Verify file > 1024 bytes. If not: log "download_failed", skip.

2. **Extract text** (try in order):

   a. **pdftotext**:
      ```bash
      pdftotext ~/.hermes/downloads/covidence-full-text-review/<ref_id>.pdf - 2>/dev/null | head -c <pdf_max_chars>
      ```
      Exit 0 and non-empty: use this text.

   b. **PyMuPDF** (if pdftotext unavailable):
      ```bash
      python3 -c "
      import fitz, sys
      doc = fitz.open(sys.argv[1])
      text = ''.join(p.get_text() for p in doc)
      print(text[:<pdf_max_chars>])
      " ~/.hermes/downloads/covidence-full-text-review/<ref_id>.pdf 2>/dev/null
      ```
      Non-empty: use this text.

   c. **Browser fallback** (HTML pages, or when a and b both fail):
      ```
      browser_navigate(url=candidate_url)
      browser_snapshot(full=true)
      ```
      Extract all visible text from snapshot, truncate to `pdf_max_chars`.

   d. **Failure**: all three paths empty — log "text_extraction_failed", skip reference (Mode 1) or report to user (Mode 2).

3. **Prioritize sections**: scan extracted text for section headers matching `(?i)^(abstract|introduction|background|methods?|participants?|study design|discussion|conclusion)` and surface a window of ~1500 chars after each. Prepend these excerpts to ensure the Decision Step sees the most diagnostic content first.

### Decision Step

Pure text reasoning — no UI actions, no additional web lookups.

1. Load `CRITERIA.md` from this skill's directory into context.

2. Extract key information from the paper text:
   - **Population**: who are the subjects/users? (patients, clinicians, HCWs, simulated agents, etc.)
   - **Concept**: what multi-agent / LLM framework is described? How many distinct agents? What roles (coordinator, critic, specialist, debater, voter, etc.)? Is this a genuine multi-agent pipeline with distinct LLM agents collaborating, or a single LLM with tool-calling (ReAct-style), prompt chaining, or a simple API wrapper?
   - **Context**: what is the deployment/application domain? (clinical diagnosis, CDSSs, medical education simulation, telehealth, public health modeling, healthcare administration, etc.)
   - **Study type**: empirical study, system design, benchmark evaluation, survey, or review?

3. Apply each criterion from `CRITERIA.md`. For each: MEETS / VIOLATES / UNCLEAR.

4. **Decide**:
   - **Include**: ALL inclusion criteria met AND no exclusion criterion violated.
   - **Exclude**: ANY exclusion criterion clearly violated. Name the first (most decisive) violation.
   - There is NO "Maybe" at full-text review stage. If a criterion remains genuinely ambiguous after reading the full text, default to **Exclude** with note: "Insufficient information in full text to confirm <criterion> — criterion not resolved at FT stage."

5. **Compose rationale** (2-4 sentences):
   - Include: state which population, multi-agent framework, and healthcare context were confirmed.
   - Exclude: state which criterion was violated and cite a specific phrase or finding from the paper.

6. **Confidence**:
   - HIGH: clear, unambiguous decision.
   - MEDIUM: one criterion required inference (agents implied but not explicitly named, or healthcare context is peripheral).
   - LOW: extraction was partial; decision is best-effort only.

### Action Policy (Mode 1)

Walk the Screen references list top-to-bottom. For each unreviewed reference with uploaded full text:

1. Confirm `Include` and `Exclude` buttons present (unreviewed block).
2. Run Full Text URL Harvesting. If no URL: skip with "no_full_text_url" log.
3. Run PDF Extraction Step. If fails: skip with "text_extraction_failed" log.
4. Run Decision Step. Obtain `Include` or `Exclude` + rationale + confidence.
5. Idempotency guard: if `current_ref_id` in `processed_ref_ids`, skip.
6. Approve-first-N onboarding (if applicable): print ref_id, header, title, decision, rationale, confidence. Wait for `approve` / `skip` / `stop`.
7. Write rationale note (if `rationale_in_notes=true` and not `dry_run`):
   - Compose: `"[FT Review] Decision: <INCLUDE/EXCLUDE>. Rationale: <2-4 sentences>. Confidence: <HIGH/MEDIUM/LOW>. Reviewed by Hermes on <ISO date>."`
   - Click the `Note` link in the target block via `browser_console` (DOM-depth: Note sits one `parentElement` hop further up than Include/Exclude buttons).
   - Fill textarea using native-setter + input-event pattern (React-controlled input):
     ```js
     const ta = document.querySelector('dialog textarea, [role="dialog"] textarea');
     const nativeSet = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
     nativeSet.call(ta, '<note_text>');
     ta.dispatchEvent(new Event('input', {bubbles: true}));
     ```
   - Click `Add note` / save. Confirm note count increments.
   - Fallback: `browser_vision` to locate dialog if inaccessible. If still fails after 1 retry: log "notes_dialog_unavailable", skip note, proceed to vote.
8. Cast vote (or describe if `dry_run`):
   - Locate `Include` or `Exclude` button via `browser_console` (climb from header paragraph, up to 4 `parentElement` hops).
   - Re-observe within 3 ticks: confirm voted-state (buttons gone). If not confirmed: screenshot+vision once. If still unconfirmed: log "vote_not_confirmed", add to `vote_failed_ref_ids`, do NOT retry.
9. Add `current_ref_id` to `processed_ref_ids`. Update `STATE.md` daily counter. Increment `refs_reviewed`.
10. Poll next tick immediately.

### UNKNOWN Handling

Increment `unknown_streak`. Screenshot+vision. If transient (Covidence loading): wait one tick. If user navigated to a different tab (Resolve conflicts, Awaiting other reviewer, Excluded references): log and STOP — do not navigate back.

### Loop Control (Mode 1)

Track:
- `refs_reviewed` (int, starts 0)
- `processed_ref_ids` (set)
- `included_ref_ids` (set), `excluded_ref_ids` (set)
- `vote_failed_ref_ids` (set)
- `skipped_no_ft_ref_ids` (set)
- `skipped_extraction_failed_ref_ids` (set)
- `skipped_ref_ids` (set, onboarding skips)
- `last_3_ref_ids` (list, infinite-loop guard)
- `session_start_ts` (ISO timestamp)
- `unknown_streak` (int)
- `auto_mode` (bool, starts false)
- `actions_approved_this_session` (int, starts 0)

Stop when:
- `refs_reviewed >= max_refs`
- Wall clock >= `max_time * 60` seconds
- Daily cap: `STATE.md` counter >= `daily_cap` (and `daily_cap != 0`)
- Queue empty (see Queue-Empty Detection)
- `last_3_ref_ids` all identical AND last action was a vote or skip attempt
- Unrecoverable error (CDP dropped, page exits `covidence.org`, vote buttons missing > 60 s)
- Approve-first-N: user responded `stop`

### Queue-Empty Detection (Mode 1)

Queue is empty when scrolling reveals no unreviewed reference blocks (with `Include` + `Exclude` buttons AND uploaded full text) after 2 scroll attempts AND the `Screen references N` count confirms 0 remaining. If count shows remaining refs but none render: screenshot+vision. If genuinely empty: stop. If blocked by modal/overlay: log and STOP.

## Covidence Interface Notes

- Full text review Screen references URL:
  `https://app.covidence.org/reviews/<review_id>/full_text_reviews/screen_references`
- Reference block DOM layout mirrors `covidence-full-text-retrieval` except the primary action area shows `Include` / `Exclude` (not `Upload full text`), with an additional `Full text` / `Manage full text` link once a full text is attached.
- DOM-depth quirk (same as retrieval skill): `Include`/`Exclude` buttons sit ~2 `parentElement` hops above the header `<p>`; the `Note`/`History` footer links sit ~3 hops up. Climb iteratively rather than assuming a fixed depth.
- Covidence re-renders the list often. Prefer `browser_console` block-locator patterns over `@eN` refs.
- This skill operates ONLY on the `Screen references` tab. Any other tab -> classify as UNKNOWN.
- The `Resolve conflicts` tab is out of scope even if there are conflicting votes.

## Covidence Exclusion Reasons (review #773228, exact dropdown)

When casting an Exclude vote in Covidence, select the FIRST applicable reason:

- Adult population
- Paediatric population
- Wrong comparator
- Wrong dose
- Wrong indication
- Wrong intervention  <- wrong Concept (non-LLM-driven, single-agent, pre-LLM ABM, ReAct tool-chaining)
- Wrong outcomes
- Wrong patient population  <- wrong Population (non-HC domain, veterinary, HC-as-benchmark-only)
- Wrong route of administration
- Wrong setting  <- wrong Context (non-HC setting, bench biomedicine, superficial demo)
- Wrong study design

PCC-to-dropdown quick map:
- Wrong Concept  -> Wrong intervention
- Wrong Population -> Wrong patient population
- Wrong Context  -> Wrong setting

## Safety Rules

Hard rules for BOTH modes:

- NEVER cast Include/Exclude without first reading and processing the full text.
- Never vote based solely on the Covidence reference block's title/abstract.
- Never click `Move to screening`, `Duplicate`, `Bulk upload missing full texts`, `Sort`, `Filter`, `Show criteria`, `More options`, or the `All` select-all checkbox.
- Never navigate to `Resolve conflicts`, `Awaiting other reviewer`, `Excluded references`, Data Extraction, Risk of Bias, or Settings.
- Never modify the review's criteria, team members, or settings.
- Never re-vote on an already-reviewed reference (voted-state marker present).
- Never type into any field of `type="password"`.
- Never click any element whose accessible name contains: logout, sign out, sign-out, signout, log off.
- If the page navigates outside `covidence.org` (Tab A), stop immediately and log.
- Never fetch from domains containing `sci-hub`, `libgen`, `annas-archive`, or `z-lib`.
- Hermes's built-in destructive-action blocklists remain active and are NOT overridden.

## Logging

Write a JSON line to `~/.hermes/logs/covidence-full-text-review-<session-id>.jsonl` for every decision:

```json
{"ts":"2026-08-02T12:34:56Z","ref_id":"82","ref_header":"#82 - Agarwal 2026","title":"<short title>","mode":"unattended","ft_url":"https://arxiv.org/pdf/2506.06574","text_extracted_chars":14500,"decision":"include","rationale":"<2-4 sentences>","confidence":"HIGH","note_written":true,"vote_cast":true,"ok":true}
```

Mode 2 (ref_id may be null):
```json
{"ts":"2026-08-02T12:40:00Z","ref_id":null,"url":"https://arxiv.org/pdf/2506.06574","title":"<title>","mode":"secondary_reviewer","decision":"exclude","rationale":"<rationale>","confidence":"HIGH","note_written":false,"vote_cast":false,"ok":true}
```

Session summary (at loop end): refs reviewed, Include/Exclude counts, skipped counts by category, vote failures, confidence distribution, time elapsed, daily cap remaining, log file path.

## Error Recovery

| Failure | Detection | Recovery |
|---|---|---|
| CDP connection dropped | `browser_snapshot` returns connection error | Stop, log, surface to user. |
| CDP session lost mid-action | `browser_console` returns "Session with given id not found." | Reconnect with `browser_profile(name='brave-live')`, verify `location.href`, resume. |
| PDF download failed or < 1024 bytes | `curl` non-zero exit or file too small | Log "download_failed", skip reference. |
| All text extraction methods fail | pdftotext + PyMuPDF + browser all return empty | Log "text_extraction_failed", skip (Mode 1) or report to user (Mode 2). |
| Notes dialog inaccessible | Dialog does not open or textarea not found | Log, skip note, proceed to vote (rationale still in JSONL). |
| Vote not confirmed after 3 ticks | Include/Exclude buttons still present after click | Screenshot+vision fallback once. If still unconfirmed: log "vote_not_confirmed", add to vote_failed_ref_ids, do NOT retry. |
| Login/session expired (Covidence) | Page navigates to SSO login URL, or no blocks render > 30 s | Stop loop, log URL, surface to user. No auto-relogin. |
| Full text URL not in DOM | `browser_console` URL extraction returns null | Open Manage full text modal, read URL, close. If still null: skip with "no_full_text_url". |
| Filters accidentally activated | Page shows "N studies found" + "Reset filters" button | Click Reset filters before continuing. |
| Infinite loop | `last_3_ref_ids` all identical after vote attempts | Stop, log, surface to user. |
| Daily cap hit | STATE.md counter >= daily_cap | Stop, log "daily cap reached (N/N)". |
| `browser_navigate` false-timeout | Returns "Operation timed out" despite navigation completing | Check `location.href` via `browser_console` — if URL matches target, proceed. |
