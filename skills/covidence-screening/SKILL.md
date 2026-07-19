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
- `tick_seconds` (int, default 5): idle polling interval between ticks when no action was taken. After an action, poll again immediately (the page needs time to react).

## Prerequisites

- A Chrome instance is running with `--remote-debugging-port=9222`.
- The user has logged into Covidence at `app.covidence.org` in that Chrome and is on the **Title and Abstract Screening** page of the target review (the scrollable list of references, NOT the Review Summary dashboard).
- The target review is set to **single-reviewer mode** (Settings → Switch to single reviewer). In dual mode the agent's vote alone will not advance references; do not run in dual mode.
- `CRITERIA.md` in this skill directory has been filled in by the user with the PICO + inclusion/exclusion bullets. If it still contains the template placeholder text, REFUSE TO RUN and tell the user to edit it first.
- Hermes is attached to that Chrome via `/browser connect` (run this once per Hermes session before invoking the skill).

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

2. **Classify** the screen into one of: `REVIEW_SUMMARY`, `TA_SCREENING`, `UNKNOWN`.
3. **Act** per the action policy below.
4. **Sleep** `tick_seconds` if no action was taken this tick; otherwise immediately repeat from step 1 (so the page has time to react to a vote before re-reading).

## State Classification

Three signals, in order of preference:

1. **URL + page landmark** (primary, deterministic) -- the `tab.evaluate` snippet above returns `hostname` and `pathname`. Classify:
   - `REVIEW_SUMMARY`: hostname is `app.covidence.org` AND the page shows the "Review Summary" heading with a "Title and Abstract Screening" section (the dashboard for the review, not the screening list).
   - `TA_SCREENING`: hostname is `app.covidence.org` AND the accessibility tree contains at least one reference block matching the structure below (a heading like `#69 - Bazargani 2025`, an abstract paragraph, a `Ref ID:` line, and inline `Yes` / `Maybe` / `No` buttons). The page heading reads `< Title and abstract screening` with counts (`Screen references N`, `Resolve conflicts N`, `Awaiting other reviewer N`, `Irrelevant references N`).
   - If hostname is not `app.covidence.org`, classify as `UNKNOWN` and apply the off-domain safety rule.

2. **Accessibility tree scan** (`tab.observe()`) -- the T&A screening page is a **single scrollable list of reference blocks** (NOT one reference per screen). Each reference block contains, in order:
   - A header line like `#69 - Bazargani 2025` (Covidence's own ref number + first author + year).
   - **Inline vote buttons** `Yes`, `Maybe`, `No` positioned to the right of / inline with the header. Each ref block has its OWN set of three buttons.
   - The article **title** (large text).
   - The **authors** line (e.g. `Bazargani, J. S.; Sadeghi-Niaraki, A.; ...`).
   - The **journal + year** line (e.g. `IEEE Access 2025;13():131789-131802`).
   - The **DOI + Ref ID** line: `DOI: 10.1109/...  ↗  Ref ID: 4060`. The `Ref ID:` value is this reference's stable identifier -- use it as `current_ref_id` directly. Do NOT derive from URL.
   - The **abstract** paragraph.
   - A per-reference footer with `Note`, `History`, `Duplicate` links. `Note` opens a notes dialog -- it is NOT an inline textarea.
   - Look across the whole visible list, not just the top of the page. Multiple ref blocks are on screen at once; the agent must walk them top-to-bottom.
   - Also note the top toolbar: `Sort: Most relevant`, `Filter`, `Show criteria`, `More options`. Do not click these.
   - A reference block is **already voted** when its vote area shows a voted-state marker (e.g. the chosen vote appears as a chip/badge next to the ref number, or the three buttons are replaced by a single "voted: X" indicator). Treat any block without fresh Yes/Maybe/No buttons as already voted; skip it.

3. **Screenshot + vision** (fallback only) -- invoked when the tree is ambiguous:
   - Icon-only vote buttons (no accessible name).
   - Shadow-DOM notes dialog not exposed in the tree.
   - An unexpected modal or overlay.
   The vision pass describes what is on screen and returns a ref or coordinate. Never use vision for the decision itself -- the decision is text reasoning over title+abstract.

### `UNKNOWN` handling

Increment an `unknown_streak` counter. If `unknown_streak > 2`: take a screenshot via `tab.screenshot()`, describe what you see, log the observation, and keep polling (NO clicks) until a known state reappears or a stop condition fires. Do **not** click blindly.

## Decision Step

This is pure text reasoning, not a UI action. Run it once per unvoted reference block, top-to-bottom.

1. Read the reference's metadata from its block in the accessibility tree: title, abstract, authors, journal + year, DOI, and `Ref ID:`. (MeSH keyword highlighting, if exposed, is a bonus signal; do not require it.)
2. Load `CRITERIA.md` from this skill directory (`~/.hermes/skills/covidence-screening/CRITERIA.md`) into context. Apply any inline overrides from the user's invocation (e.g. "also exclude studies published before 2010").
3. Reason per criterion: which PICO elements does this reference satisfy / violate / leave unclear? Show the reasoning briefly in the log.
4. Decide:
   - **Include (Yes)** -- meets all inclusion criteria, violates no exclusion criterion.
   - **Exclude (No)** -- violates a clear exclusion criterion (wrong population, wrong study design, not in the specified language, etc.).
   - **Maybe** -- borderline: meets some criteria but the title/abstract leaves a PICO element ambiguous (e.g. population unclear, study type not stated).
5. If Maybe: compose a one-line rationale citing the specific ambiguity (e.g. "Population unclear -- abstract says 'adults' but doesn't specify whether surgical patients"). This rationale will be written to the per-reference notes dialog before the vote is cast.

The model does this reasoning -- "attempt seriously" per the user's intent. No external lookups (PubMed, DOI, publisher PDFs). Covidence metadata only.

## Action Policy

### `REVIEW_SUMMARY`

1. Find the "Continue" button under the "Title and Abstract Screening" section in the accessibility tree.
2. If found, click it via its `@eN` ref. This lands the tab on the T&A screening list.
3. If `dry_run` is true, describe the navigation intent and do NOT click (dry-run mode only screens references, not navigation). Otherwise click.

### `TA_SCREENING` -- walk the list top-to-bottom

The T&A screening page is a scrollable list of reference blocks, many visible at once. The agent walks them top-to-bottom, voting on the first unvoted block it finds, then re-observing and continuing.

1. **Scan the visible reference blocks** top-to-bottom. For each block, determine:
   - Its `Ref ID:` value -> `current_ref_id`.
   - Whether it is already voted (no fresh Yes/Maybe/No buttons, or a voted-state marker present).
2. **Find the first unvoted block** on the visible portion of the list. That is this tick's target. If all visible blocks are already voted, scroll down (`tab.evaluate(() => window.scrollBy(0, window.innerHeight * 0.8))`) to reveal more, and re-observe. If scrolling produces no new unvoted blocks after 2 attempts, the queue is empty -- see "Queue empty" below.
3. For the target block: run the **Decision Step**. Get a decision: Yes, Maybe, or No (Maybe comes with a one-line rationale).
4. **Idempotency guard**: if `current_ref_id` is already in the `voted_ref_ids` set, skip this block (do NOT vote again). Continue scanning down the list. (This guards against double-clicks and re-observation of a block that was voted earlier this tick.)
5. **Approve-first-N onboarding**: if `votes_approved_this_session < approve_first_n` AND `auto_mode` is false:
   - Print to the terminal: the `current_ref_id`, the ref header (`#69 - Bazargani 2025`), the title (short), the decision (Yes/Maybe/No), and the rationale (if Maybe).
   - Wait for user input. Accept three responses only:
     - `approve` -- cast this vote as decided. Increment `votes_approved_this_session`. If `votes_approved_this_session == approve_first_n`, set `auto_mode = true` and announce "Onboarding complete, switching to unattended mode."
     - `skip` -- leave this reference unvoted. Do NOT increment `votes_approved_this_session`. Add `current_ref_id` to a `skipped_ref_ids` set (so we don't re-target it next tick) and continue scanning down the list for the next unvoted block. Log the skip. Do NOT auto-vote.
     - `stop` -- end the session immediately. Log summary including which references were skipped.
6. **Cast the vote** (or describe it if `dry_run`):
   - If **Maybe**: first write the rationale to the notes dialog. Find the `Note` link in the target block via `tab.observe()` (its `@eN` ref). Click it to open the notes dialog. Find the textarea inside the dialog via `tab.observe()`, type the rationale with `tab.fill`, then click the dialog's save/submit button. If the dialog or textarea is not exposed in the tree, fall back to screenshot+vision to locate it. If still not found after 1 retry, SKIP this Maybe vote entirely -- do NOT vote without the rationale. Log the reference ID and "notes dialog unavailable, skipped" so the user can review manually.
   - Then click the target block's vote button (`Yes`, `Maybe`, or `No`) via its `@eN` ref. The vote button is inline with this ref's header -- make sure you click the button belonging to THIS block, not the one above or below. If the vote button is icon-only or missing from the tree, fall back to screenshot+vision to locate it.
   - In `dry_run`: print the vote + rationale instead of clicking, filling, or opening the notes dialog.
7. After the vote click, **do NOT wait for auto-advance** -- Covidence's T&A list does not auto-advance. The block you just voted now shows a voted-state marker; the next unvoted block is the next one down (already on screen, or one scroll-down away). Add `current_ref_id` to `voted_ref_ids`. Increment `refs_screened` and the daily counter in `STATE.md`.
8. Poll the next tick immediately (no sleep) so the page has time to register the vote before re-reading.

### `TA_SCREENING` -- queue empty

The T&A list does NOT show a "No more references" banner. Instead, the queue is empty when:
- Scrolling reveals no new unvoted reference blocks after 2 scroll attempts, AND
- The top-bar counts confirm (e.g. `Screen references 0` remaining, or the count matches `refs_screened` this session).

When both hold, stop the loop, log "queue empty", print summary. If the top-bar count shows unvoted refs remain but none render (likely a UI bug or filtered-out view), log and STOP -- do not click blindly.

### `UNKNOWN`

Increment `unknown_streak`. Screenshot + vision to classify. If genuinely a transient page transition (Covidence loading), wait one tick and re-observe. If a modal/error overlay is blocking, log and STOP -- do not click through modals.

## Loop Control

Track these counters across the session:
- `refs_screened` (int, starts 0): references voted on this session.
- `current_ref_id` (string or null): `Ref ID:` of the reference currently being voted on.
- `voted_ref_ids` (set): `Ref ID:` values voted this session (idempotency guard).
- `skipped_ref_ids` (set): `Ref ID:` values skipped during onboarding (so they aren't re-targeted next tick).
- `last_3_ref_ids` (list of last 3 `current_ref_id` values, infinite-loop guard).
- `votes_approved_this_session` (int, starts 0): approvals received in onboarding.
- `auto_mode` (bool, starts false): whether onboarding is complete.
- `session_start_ts` (ISO timestamp): for `max_time` enforcement.
- `unknown_streak` (int, starts 0): consecutive UNKNOWN classifications; screenshot threshold for the UNKNOWN handling rule.

Stop the loop when any of:
- `refs_screened >= max_refs`.
- `now - session_start_ts >= max_time * 60` seconds.
- Daily cap: read `STATE.md`; if today's counter >= `daily_cap` (and `daily_cap != 0`), stop with "daily cap reached (N/N)".
- Queue empty (per the queue-empty rule above).
- `last_3_ref_ids` are all identical AND the last action was a vote click (infinite-loop guard -- means we keep targeting the same block without the vote landing).
- Unrecoverable error: CDP connection dropped, page navigates outside `covidence.org`, vote buttons missing for > 30 s, model API failure after 3 backoffs.
- Approve-first-N: user responded `stop`.

### Re-vote guard

Covidence allows re-opening a voted reference in single mode to change the vote. This agent MUST NOT re-open already-voted references. A reference block is "already voted" when its inline Yes/Maybe/No buttons are gone (or replaced by a voted-state chip/badge). Do NOT click a voted block's "change vote" affordance. If the first unvoted block search finds only voted blocks, treat per the queue-empty rule (scroll for more, else stop).

## Safety Rules

Hard rules the agent MUST follow:
- Never type into any field of `type="password"` (Hermes hard-blocks this anyway).
- Never click any element whose accessible name contains: logout, sign out, sign-out, signout, log off.
- Never click into Full Text, Data Extraction, Risk of Bias, or Settings -- strict allowlist of T&A screening list + Review Summary page. If the page navigates elsewhere inside covidence.org, stop and log.
- Never click the top-toolbar buttons (`Sort`, `Filter`, `Show criteria`, `More options`) -- the agent does not re-sort or re-filter the list. It walks the list in whatever order Covidence presents.
- If the page URL navigates outside the `covidence.org` domain (check via `tab.evaluate(() => location.hostname)`), stop the loop immediately and log.
- Never modify the review's inclusion/exclusion criteria, team members, or settings -- the agent is read-only on everything except vote buttons and the per-reference notes dialog.
- Hermes's built-in destructive-action blocklists (recursive force-delete, piped-shell installers, fork bombs, lock-screen combos) remain active and are NOT overridden by this skill.

## Logging

Every tick, write a JSON line to `~/.hermes/logs/covidence-screening-<session-id>.jsonl` (create the logs dir if missing). The `<session-id>` is the ISO timestamp at session start.

```json
{"ts":"2026-07-18T12:34:56Z","ref_id":"4060","ref_header":"#69 - Bazargani 2025","title":"<short title>","state":"TA_SCREENING","decision":"maybe","rationale":"Population unclear -- abstract says 'adults' but not whether surgical","action":"vote Maybe + note","ok":true}
```

Fields: `ts` (ISO), `ref_id` (the `Ref ID:` value), `ref_header` (the `#69 - ...` line), `title` (truncated), `state` (REVIEW_SUMMARY/TA_SCREENING/UNKNOWN), `decision` (yes/maybe/no/skip), `rationale` (only for maybe), `action` (what was clicked or "dry-run describe"), `ok` (bool).

At loop end, print a summary to the terminal: refs screened, votes cast (Yes/Maybe/No counts), Maybe rationales list, time elapsed, any stuck points, daily-cap remaining.

## Error Recovery

| Failure | Detection | Recovery |
|---|---|---|
| CDP connection dropped | `tab.observe()` returns connection error | Stop, log, surface to user. Cannot auto-recover (user must restart Chrome). |
| Session/login expired | Page navigates to institutional SSO login URL, or no reference blocks render for > 30 s | Stop loop, log URL, surface to user. No auto-relogin (credentials out of scope). |
| Vote landed wrong / block still shows unvoted | The target block still shows fresh Yes/Maybe/No buttons 2 ticks after the vote click | Re-screenshot, re-classify, retry the vote click once with a different ref (the correct button for THIS block). If still stuck, log, add `current_ref_id` to `skipped_ref_ids`, and continue scanning down. |
| Maybe notes dialog write failed | `Note` link `@eN` not found, dialog didn't open, or `tab.fill` returns error | Screenshot+vision to locate the Note link / dialog. If still not found after 1 retry, SKIP the Maybe vote entirely -- do NOT vote without the rationale. Log the reference ID; user reviews manually. |
| Queue-empty detection false negative | Top-bar counts show unvoted refs remain but scrolling yields no unvoted blocks after 2 attempts | Screenshot + vision to classify. If genuinely empty (list shows all-voted state), stop with summary. If a modal/error overlay is blocking, log and STOP rather than clicking through it. |
| Page JS error / blank render | Screenshot returns empty canvas or error overlay | Wait 2 ticks; if persists, log and STOP. Do not attempt to advance. |
| Model API failure / rate limit | Model call times out or 429 | Backoff 10 s -> 30 s -> 60 s; after 3 failures, stop and surface to user. |
| Infinite loop (same `current_ref_id` targeted 3× without landing) | `last_3_ref_ids` identical after vote actions | Stop, log, surface to user. |
| Daily cap hit | `STATE.md` counter >= `daily_cap` (and `daily_cap != 0`) | Stop, log "daily cap reached (N/N)", surface to user. Does not count toward `max_refs` for the next session. |
| Approve-first-N: user says `skip` | User response during onboarding | Leave reference unvoted, add `current_ref_id` to `skipped_ref_ids`, continue scanning down for the next unvoted block. Do NOT auto-vote. Onboarding counter does NOT advance. |
| Approve-first-N: user says `stop` | User response during onboarding | End session immediately. Log summary including which references were skipped. |
