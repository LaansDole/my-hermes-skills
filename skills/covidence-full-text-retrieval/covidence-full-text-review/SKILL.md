---
name: covidence-full-text-review
description: "Review full-text papers in a Covidence systematic review. Mode 1 (websearch_queue): walks the Covidence queue, web-searches each title, opens the first result in the papers-access browser profile, reads the full text, and reports verdicts in chat (no Covidence writes). Mode 2 (secondary_reviewer): receives a URL from the user, reads the paper, returns a structured Include/Exclude verdict with rationale, and optionally casts the vote in Covidence when a ref_id is supplied."
version: 2.0.0
metadata:
  hermes:
    tags: [covidence, systematic-review, full-text, review, browser-automation]
    requires_toolsets: [browser, terminal]
---

# Covidence Full-Text Review

This skill operates in two modes set via the `mode` parameter:

- **Mode 1 (`websearch_queue`)**: the user is logged into a browser profile with institutional/papers access (e.g. Brave `research` profile). The agent walks the Covidence Screen references queue, and for each unreviewed title: web-searches the title, opens the FIRST result in a new tab of the papers-access profile, reads the full text via the tab (session cookies apply, so paywalled-but-subscribed content unlocks), and reports an Include/Exclude verdict in chat. References whose first result has no accessible full text are SKIPPED (no vote). NO Covidence writes are made — the user casts votes themselves based on the verdicts.
- **Mode 2 (`secondary_reviewer`)**: the user supplies a `url` (paper URL, DOI landing page, or arXiv link). The agent downloads and reads the paper, applies criteria, and returns a structured verdict. If `ref_id` is also provided, the agent additionally casts the vote in Covidence and writes the rationale to the notes field.

> NOTE: there is deliberately NO fully-unattended queue mode. Full-text screening always involves a human reviewer casting the votes (Mode 2 with a ref_id, or the user manually after Mode 1 verdicts). Unattended full-text review is not good research practice — borderline decisions need human judgment.

## Parameters

- `mode` (str, REQUIRED): `"secondary_reviewer"` or `"websearch_queue"`. REFUSE TO RUN if absent.
- `url` (str, Mode 2 only, REQUIRED when mode=secondary_reviewer): the paper URL to review. May be a direct PDF URL, DOI link, arXiv abstract, PubMed page, or any URL from which the agent can reach the full text.
- `ref_id` (str, optional, Mode 2 only): Covidence Ref ID (the numeric `Ref ID:` value on the reference block, e.g. `"4060"`). When provided alongside `url`, the agent also casts the Include/Exclude vote in Covidence and writes the rationale note. When omitted in Mode 2, the agent returns a recommendation only (no Covidence write).
- `profile_port` (int, default 9254, Mode 1 only): CDP port of the papers-access browser profile (Brave `research` profile). The agent must NOT touch port 9222 — that is the user's personal-work profile.
- `profile_name` (str, default `"research"`, Mode 1 only): name passed to `browser_profile` to attach the browser tools to the papers-access profile.
- `review_id` (str, default `"773228"`): the Covidence review ID. Used to construct the full-text review URL. Override only when running on a different review.
- `criteria_file` (str, default `"CRITERIA.md"`): path to the eligibility criteria file, relative to this skill directory. Must exist and be filled in before running. The agent refuses to run if it still contains the placeholder text.
- `max_time` (int, default 60): wall-clock cap in minutes.
- `dry_run` (bool, default false): when true, reason through the decision and describe the vote + rationale WITHOUT clicking any button or writing to the notes field.
- `rationale_in_notes` (bool, default true): when true, write the Include/Exclude rationale to the per-reference notes field in Covidence before casting the vote (Mode 2 with ref_id only; Mode 1 never writes to Covidence).
- `pdf_max_chars` (int, default 20000): maximum characters of extracted PDF text to load into context.

## User Preferences

This user runs Mode 1 (websearch_queue) with:

- Verdicts reported IN CHAT ONLY — NO Covidence writes of any kind (no vote, no note). The user casts votes themselves.
- Tab policy: CLOSE each paper tab after reading it (user explicitly approved closing tabs).
- Verdict format: one compact block per paper (see Mode 1 workflow) — user praised this exact format as "comprehensive and concise". Do NOT switch to the pbcopy/Word format in Mode 1. EVERY verdict block includes a `Full text: <URL>` line with the link the paper was read from — the user pastes it into Covidence when attaching the full text.
- Papers-access profile: Brave `research` (port 9254, profile_directory "Profile 3"). Never touch port 9222 (user's personal-work profile).
- If the first search result is not actually the paper (search noise) but a later result IS the paper with a DOI visible in the Covidence block, use the DOI-derived URL instead of reviewing the wrong hit.

This user runs Mode 2 (secondary_reviewer) with:

- `rationale_in_notes=true` — write rationale to the note field when casting a vote
- Verdicts delivered via pbcopy (Word-friendly plain text) when no ref_id is given — see Mode 2 workflow

Set these on every invocation unless the user explicitly overrides.

## Prerequisites

### All modes
- `CRITERIA.md` in this skill directory is filled in with the review's eligibility criteria. If it still contains the placeholder text, REFUSE TO RUN and tell the user to edit it first.
- `curl` and `python3` are on `$PATH`.
- `pdftotext` or PyMuPDF (`fitz`) available for PDF text extraction — check on first use. If neither is present, fall back to `browser_navigate` text extraction (see PDF Extraction Step).

### Mode 2 (secondary_reviewer) additional prerequisites
- No Covidence browser session is required unless `ref_id` is provided (vote-casting step needs a browser attached to Covidence, logged in on the **Full text review -> Screen references** tab of the target review).
- The `url` parameter must be reachable by `curl`. For paywalled content, supply a direct OA PDF URL (e.g. arXiv, PMC, Unpaywall result).

### Mode 1 (websearch_queue) additional prerequisites
- A Brave instance is running with `--remote-debugging-port=<profile_port>` (default 9254) AND `--profile-directory="Profile 3"` (the Research profile — the user's papers-access login). Verify with `ps aux | grep -i brave | grep -oE -- "--profile-directory=[^ ]+"` before starting; if the running instance has NO profile flag it is the Default profile — STOP and relaunch as Research (see cdp-browser-profiles skill for the quit/relaunch procedure).
- The user is logged into Covidence at `app.covidence.org` in that profile, on the **Full text review -> Screen references** tab.
- `browser_profile(name='research')` attaches the browser tools to port 9254. The CDP helper script `scripts/cdp_paper_extract.py` in this skill dir hardcodes port 9254 — edit the `CDP` constant if the profile port differs.
- `python3` with the `websockets` package (`pip install websockets` if missing).
- The user's personal-work profile runs on port 9222 — NEVER attach to it, never close its tabs, never navigate it.

## Browser Window Management

Run this whenever Brave appears windowless, `browser_snapshot` returns empty, or CDP reports the wrong URL:

1. `computer_use(action='list_apps')` — check for `com.brave.Browser` running but `windows=[]`.
2. If windowless: `osascript -e 'tell application "Brave Browser" to make new window'`
3. `computer_use(action='focus_app', app='com.brave.Browser', raise_window=true)`
4. `computer_use(action='capture', app='com.brave.Browser', mode='vision')` — confirm visible.
5. `browser_navigate(url='https://app.covidence.org/reviews/<review_id>/full_text_reviews/screen_references')` — always explicit after restoring window.

## Mode 1: Web-Search Queue Review (websearch_queue)

Mode 1 is the primary workflow: the user is logged into a browser profile with institutional/papers access, and the agent walks the Covidence Screen references queue WITHOUT uploaded full texts. For each unreviewed reference: web-search the title, open the first result in the papers-access profile (Research, port 9254), read the full text through the tab (session cookies unlock subscribed content), and report the verdict in chat. **No Covidence writes.**

### Workflow (single pass down the queue)

1. **Extract the queue** from the Covidence Screen references tab via `browser_console`:
   ```js
   (() => {
     const blocks = Array.from(document.querySelectorAll('h3')).map(h => {
       let el = h;
       let num = null;
       for (let i=0;i<6;i++){ el=el.parentElement; if(!el) break; const lbl = el.querySelector('label input[type=checkbox]'); if(lbl){ const lab = lbl.closest('label'); if(lab) num = lab.textContent.trim().match(/Study #(\d+)/)?.[1] || null; break; } }
       return {num, title: h.textContent.trim()};
     }).filter(b => b.title);
     return {count: blocks.length, blocks};
   })()
   ```
   Filter out non-reference blocks (e.g. "Feedback & Support"). Keep the title list; note any DOI visible in each block.

2. **For each title** (in queue order), until the user says stop or the queue is exhausted:
   a. **Web search** the title (quoted exact title first; if empty/rate-limited, retry without quotes or after a pause).
   b. **Pick the URL**: take the FIRST result. If the first result is clearly not the paper (search noise — e.g. an unrelated arXiv paper), but a later result matches the title AND the Covidence block shows a DOI, use the DOI-derived URL (`https://link.springer.com/chapter/<doi>`, `https://dl.acm.org/doi/<doi>`, etc.) instead. NEVER review a wrong paper.
   c. **Open + extract via CDP script** (SILENT: downloads via the profile's session cookies with curl — no tab is created, the window is never raised, cursor focus never moves; falls back to a non-activated background tab only when a page needs JS rendering):
      ```bash
      python3 <skill_dir>/scripts/cdp_paper_extract.py "<url>" ~/.hermes/downloads/covidence-full-text-review/ref<N>
      ```
      Inspect the JSON: `mode` (`cookie` = silent curl, `background_tab` = non-activated tab), `is_pdf`, `len`, `digest`, `error`.
   d. **Full-text check**: if `error` is set, or `len` is tiny (< ~5K chars for an HTML page) and the digest shows paywall markers ("preview of subscription content", "log in via an institution", "Buy Chapter", "Request PDF" without content), the full text is NOT accessible → **SKIP** (log `no_full_text`, move on). If the digest shows real content (abstract + sections, or "Access provided by <institution>"), proceed to read.
   e. **Read the full text**: read the saved `<prefix>.txt` file (or digest). Prioritize abstract + architecture/methods sections. Search the text for LLM/agent keywords when deciding.
   f. **Apply the Decision Step** (same criteria as Mode 2: PCC from `CRITERIA.md`).
   g. **Report the verdict in chat** using the user's preferred format (see below) — ALWAYS include the `Full text: <URL>` line (the URL the paper was read from). Log to JSONL + Mnemosyne (see Verdict Persistence).

3. **Stop** when: user says stop, queue exhausted, or a daily cap the user set is hit. Report a batch summary (Include/Exclude/Skip counts) when pausing.

### Verdict format (Mode 1 — the user's preferred compact block)

Print one block per paper in chat, exactly in this shape (user praised it as "comprehensive and concise"):

```
#<N> — "<Title>" (Author Year, Venue/Publisher)
Verdict: <INCLUDE|EXCLUDE|SKIP> — <2-4 sentence rationale naming the agents/architecture and the decisive criterion; for EXCLUDE state which exclusion criterion and map to the dropdown reason (e.g. "Wrong intervention"); for SKIP state why full text was unreachable>. Confidence: <HIGH/MEDIUM/LOW> (<one-line note if MEDIUM/LOW>).
Full text: <URL>
```

**ALWAYS include the `Full text:` line** with the actual URL the paper was read from (the web-search result / DOI-derived URL that yielded the full text). This is the user's key workflow aid: they paste that link into Covidence to attach the full text when casting their vote. Include it for INCLUDE and EXCLUDE verdicts; for SKIP, still include the attempted URL (so the user knows what was tried) — e.g. `Full text: <URL> (paywalled/unreachable)`.

Do NOT use the pbcopy/Word format in Mode 1 — the user reads these in chat and casts votes in Covidence themselves.

### Mode 1 pitfalls

- **Wrong profile**: the running Brave must be Research (`--profile-directory="Profile 3"`). A windowless/default-profile instance gives empty snapshots or paywalled pages. Verify via `ps` before starting; relaunch via the cdp-browser-profiles skill if wrong (quit first — confirm with user if they have other windows).
- **Search rate limits**: web_search may return HTTP 429 when batched; space searches out or retry after a few seconds.
- **Search noise**: first result unrelated to the paper → use the DOI from the Covidence block (Springer/ACM DOI-derived URL) or the next matching result.
- **PDFs in browser**: Chrome/Brave's PDF viewer exposes no `innerText`; the script downloads PDF bytes via cookie mode (curl with the profile's session cookies) or, when the site blocks curl (e.g. ACM Cloudflare), via a non-activated background tab whose in-page `fetch()` carries session cookies. `pdftotext` runs on the bytes. If both paths fail, SKIP.
- **ACM DL**: `dl.acm.org/doi/<doi>` HTML often returns ~20 chars (bot protection) — use `dl.acm.org/doi/pdf/<doi>` instead.
- **Springer paywall**: even with institutional access some chapters show "preview of subscription content" (institution doesn't subscribe to that volume) → SKIP. When "Access provided by <institution>" appears, full text is available.
- **ResearchGate**: the publication page may embed only the first section of the paper; treat a page that shows abstract + intro but then "Citations (6) / Recommended publications" as PARTIAL — check the extracted text length; if the key methods sections are missing, either fetch the PDF via the page's "Download full-text PDF" link or SKIP with a note.
- **Duplicates in queue**: Covidence may list the same paper twice (title repeats) — review once, report both with the same verdict.
- **Tab hygiene**: the script never creates a visible tab (cookie mode) or creates a non-activated background tab that it closes automatically. The user's Covidence tab and port-9222 tabs are never touched, closed, or navigated.

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

## Shared Steps: PDF Extraction and Decision

These two steps are used by both Mode 1 and Mode 2. There is NO fully-automated queue loop in this skill — every verdict is produced here and then either reported to the user (Mode 1) or voted by the agent on explicit request (Mode 2 with ref_id).

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

   d. **Failure**: all three paths empty — log "text_extraction_failed", report to user (Mode 2) or SKIP the reference (Mode 1).

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

## Covidence Interface Notes

- Full text review Screen references URL:
  `https://app.covidence.org/reviews/<review_id>/full_text_reviews/screen_references`
- Reference block DOM layout mirrors `covidence-full-text-retrieval` except the primary action area shows `Include` / `Exclude` (not `Upload full text`), with an additional `Full text` / `Manage full text` link once a full text is attached. Relevant when reading the queue in Mode 1 or casting a vote in Mode 2 (ref_id).
- DOM-depth quirk (same as retrieval skill): `Include`/`Exclude` buttons sit ~2 `parentElement` hops above the header `<p>`; the `Note`/`History` footer links sit ~3 hops up. Climb iteratively rather than assuming a fixed depth.
- Covidence re-renders the list often. Prefer `browser_console` block-locator patterns over `@eN` refs.
- This skill reads ONLY the `Screen references` tab. The `Resolve conflicts` tab is out of scope even if there are conflicting votes.

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

Hard rules for ALL modes (1 and 2):

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

## Verdict Persistence (Mnemosyne + JSONL)

Every decision MUST be persisted to BOTH places so the user can later ask "what were your verdicts on all papers?":

1. **Mnemosyne** (primary, queryable): after composing the decision, call `mnemosyne_remember` (scope=`global`, source=`covidence_ft_review`, importance=0.65, extract_entities=true, veracity=`tool`) with:
   - content: `FT verdict (Covidence review <review_id>, LLM multi-agent in healthcare): '<title>' (<url>) => INCLUDE/EXCLUDE. <rationale condensed to 1-3 sentences>.` — if the verdict overturns an earlier one, append `(Earlier verdict <date> was <old decision>; overturned by <criteria_version>.)`
   - metadata dict: `{"review_id": "<id>", "url": "<ft_url>", "decision": "include|exclude", "confidence": "HIGH|MEDIUM|LOW", "criteria_version": "<version>", "verdict_date": "<ISO date>"}`
   - Do NOT re-store a duplicate for the same URL+decision+verdict_date; idempotency check via `mnemosyne_recall(query="FT verdict <title>")` first if unsure.
2. **JSONL log** (raw audit trail): write a JSON line to `~/.hermes/logs/covidence-full-text-review-<session-id>.jsonl` for every decision:

Mode 2 (ref_id may be null):
```json
{"ts":"2026-08-02T12:40:00Z","ref_id":null,"url":"https://arxiv.org/pdf/2506.06574","title":"<title>","mode":"secondary_reviewer","decision":"exclude","rationale":"<rationale>","confidence":"HIGH","note_written":false,"vote_cast":false,"ok":true}
```

Mode 1 (no Covidence writes; skips are logged too, with the skip reason):
```json
{"ts":"2026-08-15T09:05:00Z","ref_id":null,"title":"<title>","mode":"websearch_queue","ft_url":"<first-result-or-DOI-url>","text_extracted_chars":12822,"decision":"exclude","rationale":"<2-4 sentences>","confidence":"MEDIUM","note_written":false,"vote_cast":false,"ok":true}
{"ts":"2026-08-15T09:10:00Z","ref_id":null,"title":"<title>","mode":"websearch_queue","ft_url":"<url>","text_extracted_chars":0,"decision":"skip","skip_reason":"no_full_text|paywalled|download_failed|text_extraction_failed","note_written":false,"vote_cast":false,"ok":true}
```

Session summary (at loop end): refs reviewed, Include/Exclude/Skip counts, skipped counts by reason, confidence distribution, time elapsed, log file path.

## Error Recovery

| Failure | Detection | Recovery |
|---|---|---|
| CDP connection dropped | `browser_snapshot` returns connection error | Stop, log, surface to user. |
| CDP session lost mid-action | `browser_console` returns "Session with given id not found." | Reconnect with `browser_profile(name='research')`, verify `location.href`, resume. |
| PDF download failed or < 1024 bytes | `curl` non-zero exit or file too small | Log "download_failed", skip reference. |
| All text extraction methods fail | pdftotext + PyMuPDF + browser all return empty | Log "text_extraction_failed", report to user (Mode 2) or SKIP the reference (Mode 1). |
| Login/session expired (Covidence) | Page navigates to SSO login URL, or no blocks render > 30 s | Stop, log URL, surface to user. No auto-relogin. |
| `browser_navigate` false-timeout | Returns "Operation timed out" despite navigation completing | Check `location.href` via `browser_console` — if URL matches target, proceed. |
| Wrong Brave profile (Mode 1) | `ps aux | grep brave` shows no `--profile-directory="Profile 3"`, or Springer pages show paywall despite expected access | Stop. Relaunch Brave with `--remote-debugging-port=9254 --profile-directory="Profile 3"` per cdp-browser-profiles skill (quit first, confirm with user). Re-attach via `browser_profile(name='research')`. |
| Search rate-limited (Mode 1) | web_search returns HTTP 429 | Wait a few seconds, retry; if persistent, switch to DOI-derived URL from the Covidence block. |
| CDP script connect refused (Mode 1) | `cdp_paper_extract.py` errors `Connect call failed` | Confirm the papers-access profile is running on the port in the script's `CDP` constant (default 9254); fix the constant if the port changed. |
| Paywalled first result (Mode 1) | digest shows "preview of subscription content" / "Buy Chapter" / tiny `len` | Try DOI-derived URL if the Covidence block has a DOI; otherwise log `skip_reason=paywalled` and move on. |
