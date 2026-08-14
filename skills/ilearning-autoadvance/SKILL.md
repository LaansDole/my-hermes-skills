---
name: ilearning-autoadvance
description: Autonomously advance HCL iLearning / SAP SuccessFactors compliance courses (Articulate Storyline SCORM, Ethena GoEthena, or direct-HTML SVG players) via raw CDP on port 9222. Resumes paused audio, clicks interactive slide topics/cards, answers quizzes, navigates to the next slide.
version: 5.0.0
trigger:
  - iLearning
  - auto-advance
  - course
  - continue video
  - next module
  - iSuccess
  - Ethena
  - GoEthena
  - AppSec
---

# iLearning Auto-Advance

Autonomously progress through HCL iLearning / SAP SuccessFactors compliance courses. These run on `hclt.lms.hr.cloud.sap` in one of THREE player formats (see Course Format Registry). All formats share the same core rule set below.

## THE USER'S CARDINAL RULES (follow exactly)

1. > "Unless it is a quiz, you only need to find clickable items when the slide mentions 'Click...' itself. Otherwise it is just a normal slide you can 'Next'. Always try 'Next' first."
2. > "You should always prioritize the 'Next' button on top of anything." — NEXT (or Continue) enabled → click it BEFORE considering any other clickable element on the slide.
3. > "Stop sleeping when Next button cannot be clicked for 10s" — if NEXT stays disabled/unclickable for ~10s, hand off (STUCK) instead of polling forever. Long narrations auto-play and usually resolve it, but a mid-paused narration will NOT — hand off so the agent can resume it or surface to the user.

Decision tree (all formats):
1. **Quiz?** (radio/checkbox inputs present, or title contains Quiz/Question/Assessment) → answer it.
2. **NEXT/Continue enabled?** → click it. Always first.
3. **Slide text mentions "Click..."?** → click each target once, wait for audio between clicks.
4. **NEXT exists but disabled** → wait up to 10s, then hand off.
5. Otherwise → screenshot + vision, hand off UNKNOWN.

## Second Brain Optimisation (Mnemosyne)

This skill pairs with the local-first Mnemosyne memory (the user's second brain) to make repeat courses progressively faster:

- **Persist quiz slide layouts to memory.** After confirming a course's quiz format (option-row Y coordinates per option count, SUBMIT/Continue/Try Again positions), save it via `mnemosyne_remember(..., importance=0.7, scope='session')` — e.g. the Format C layout (2-opt y≈382/442; 3-opt y≈386/446/506; 4-opt y≈360/421/481/541; SUBMIT (1383,802); popup ≈(756,531)). Subsequent questions on the same course can then be answered WITHOUT re-screenshotting: read the question via a quick screenshot, click the option at the memorized row, submit, continue.
- **Recall before re-probing.** When resuming a course, run `mnemosyne_recall(query="<course> quiz format")` first — the stored layout eliminates per-question rect discovery.
- **Store per-format facts, not per-question trivia.** Only durable layout/flow facts belong in memory; per-question answers are one-off and belong in the session transcript (session_search).
- **Memory is the shortcut, the skill is the method.** The skill's probes/orchestrators handle the *how*; Mnemosyne's stored layouts skip the *where* on the next run.

## Course Format Registry (proven 2026-08-13)

### Format A — Storyline SCORM in iframe (e.g. "Information Security", "COBEC" Storyline courses)
- Player tab URL contains `scorm2004contentplayer`; course content is in ONE `<iframe>` (fills viewport 1920x1027 → 1:1 coordinates).
- Slide objects: `<div class="slide-object">` with `data-model-id`; real click targets are ancestor `.slide-object-stategroup`s (use `clickRect`/`clickMid` from probe).
- Nav: `Next.png`/`Backbtn.png` PNG slide-objects, embedded nav at y≈718 or global chrome y≈915. Read rects, never hardcode.
- JS-dispatched mouse events DO NOT register — only trusted CDP `Input.dispatchMouseEvent` works.
- Quiz: option radios `id="acc-<modelId>"` (labels useless, usually "Rectangle 3") → screenshot + vision to read; submit `submit0001.png` appears after selection; feedback popup green `next0001.png` ≈(750,612)/(750,635).
- Driver: `ilearn_orchestrator.py` + `ilearn_probe.js`. Orchestrator states: QUIZ / STUCK / STOP / UNKNOWN / DONE / CLICK_REPEAT.

### Format B — Ethena / GoEthena course (e.g. "Anti-Money Laundering Basics", "Export Controls")
- Player tab URL contains `scorm2004contentplayer`; inside it a NESTED cross-origin iframe `https://app.goethena.com/learning/assignments/...` (chain: hclt page → `icontent.do?url=...` iframe → goethena iframe).
- **The GoEthena iframe is its OWN CDP target with `"type": "iframe"`** — the standard helpers match `type == "page"` only. Use the iframe-capable variants:
  ```bash
  sed 's/t.get("type") == "page" and match in t.get("url", "")/t.get("type") in ("page", "iframe") and match in t.get("url", "")/' cdp_eval.py > /tmp/cdp_eval_if.py
  sed 's/t.get("type") == "page" and match in t.get("url", "")/t.get("type") in ("page", "iframe") and match in t.get("url", "")/' cdp_click.py > /tmp/cdp_click_if.py
  ```
  Target match: `goethena.com/learning/assignments`. Coordinates are the iframe's own viewport space.
- Player: simple content slides with a blue `Continue` button. **On long slides the Continue sits BELOW THE FOLD** — scroll the slide container (`.Slide_container__Zpm4v`) to bottom first, then click. Scroll via JS on the iframe target (`e.scrollTop = e.scrollHeight` on scrollable containers).
- Quiz: per-section assessments (3 Qs, 2 Qs, 1 Q...) with radio inputs + `Submit Answer` button. Feedback popup: correct → `Continue`; incorrect → `View Answer` (shows correct option green) then NEXT/Continue. Optional feedback survey at the end (Likert 1-5 + tag chips) — submit to finish.
- Some courses end with a policy-attestation CHECKBOX section — **user does that manually; stop when reached** (ask first if unclear).
- Driver: `goe_orchestrator.py` (probe → scroll if needed → click Continue; hands off on QUIZ).

### Format C — Direct-HTML SVG slide deck (e.g. "Application Security Foundation Certification" / Appsec_may12)
- Course opens at a plain URL like `.../icontent_e/CUSTOM_fra/hcl/self-managed/LSS/Appsec_may12/index_lms.html` — NO iframe, slides are inline SVG in the page DOM. Target match: `index_lms.html`.
- Player bar bottom-right: `PREV` (1260,786) / `NEXT` (1345,786) real `<button class="cs-button btn">`. **Disabled state is the CSS class `cs-disabled`, NOT the HTML `disabled` attribute** — always check `className.includes('cs-disabled')`.
- Per-slide `<audio>` elements (do not reliably auto-play; NEXT stays cs-disabled until narration completes — WAIT_NEXT handles this; if audio is mid-paused, clicking the Play button (82,786) resumes it).
- Slide number in footer: `<n> Copyright © 2024` on one line (nbsp-separated) → regex `/(\d+)\s*(?:\u00a0|\s)*Copyright/i`.
- Quiz: "Question X of 25" top-right, interleaved with content slides (NOT one block at the end). Purple banner question; radios left-aligned x≈130-147, w≈796-901, h=63; rows depend on count:
  - 2 options: y≈382/442
  - 3 options: y≈386/446/506
  - 4 options: y≈360/421/481/541 (or 352/447/542/602 when options are tall)
  - option centers ≈ (537, row+20)
- `SUBMIT` at (1383,802), cs-disabled until an option is selected.
- Feedback popup (center): correct → `Continue` ≈(756,531); incorrect → `Try Again` ≈(756,531) (retry SAME question; the "View Answer" pattern is Format B only). Sometimes incorrect just shows the green-highlighted correct answer + NEXT.
- Hyperlink `<a>` elements are NOT course interactions — exclude from clickable detection.
- Driver: `appsec_orchestrator.py` + `appsec_probe.js`-style probes (in skill scripts/). States: QUIZ / STUCK / DONE / UNKNOWN / INTERACTIVE. **NEXT-first priority and 10s WAIT_NEXT timeout are baked in.**

## Parameters

- `max_modules` (int, default 50): hard cap on the number of slides/modules to advance through before stopping.
- `dry_run` (bool, default false): when true, observe and *describe* the action you would take, but do NOT call any click/type/fill tool.
- `tick_seconds` (int, default 5): idle polling interval. After an action, poll again immediately (the page needs time to react).

## Prerequisites

- Brave (or Chrome) running with `--remote-debugging-port=9222` (profile `brave-live` — switch to it with `browser_profile(name='brave-live')`).
- User logged into SAP SuccessFactors LMS (`hclt.lms.hr.cloud.sap`).
- Course open: overview page shows a **"Launch Content"** UI5 button (Formats A/B) or the direct content URL (Format C). Clicking Launch opens the SCORM player in a NEW TAB; the overview tab keeps a disabled Launch button.

### CRITICAL: drive the player over raw CDP, not browser_console

Hermes browser tools stay pinned to the tab active when the profile connected — usually the OVERVIEW tab, not the player tab. Use raw CDP over websocket:

```bash
curl -s http://localhost:9222/json/list | python3 -c "
import json,sys
for t in json.load(sys.stdin):
    if t.get('type')=='page' and 'scorm2004contentplayer' in t.get('url',''):
        print(t['id'], t['webSocketDebuggerUrl'])"
# Format B: also list iframe targets
#   if t.get('type')=='iframe' and 'goethena' in t.get('url',''): ...
```

## CDP Helper Scripts

In `scripts/` (copy to /tmp when working):

- `cdp_eval.py` / `cdp_click.py` / `cdp_shot.py` — page-target helpers (Formats A/C).
- `ilearn_probe.js` / `ilearn_orchestrator.py` — Format A.
- `goe_orchestrator.py` — Format B (iframe-target; also make cdp_eval_if/cdp_click_if via sed, see Registry).
- `appsec_orchestrator.py` / `appsec_probe.js` — Format C (page-target, direct DOM).
- `quiz_rects.js` — map quiz radio ids to real `.slide-object` click rects (Format A).

Run with `/usr/bin/python3` (bare `python3` in background shells lacks `websockets`):
```bash
cd /Users/laansdole/.hermes/skills/ilearning-autoadvance/scripts
/usr/bin/python3 cdp_eval.py "<target-match>" ilearn_probe.js
/usr/bin/python3 cdp_click.py "<target-match>" X Y
/usr/bin/python3 cdp_shot.py "<target-match>" /tmp/shot.png
```

## Watch Loop

Repeat until a stop condition (see Loop Control) fires:

1. **Observe** — one probe call (`cdp_eval.py` + the format's probe JS).
2. **Classify** into: `COURSE_OVERVIEW`, `TIMELINE_PLAYING`, `TIMELINE_PAUSED`, `INTERACTIVE_SLIDE`, `QUIZ_SLIDE`, `SLIDE_DONE`, `UNKNOWN` (Formats A/C); Format B uses its own probe (Continue button presence).
3. **Act** per the action policy below.
4. **Sleep** `tick_seconds` if no action was taken; otherwise repeat immediately.

## Action Policy

### `COURSE_OVERVIEW`
1. Click "Launch Content" (opens player in a NEW tab; native `.click()` works).
2. Re-enumerate tabs; re-target helpers on the player tab (or the goethena iframe target for Format B).
3. Re-probe.

### `TIMELINE_PLAYING`
No action. Sleep, re-probe. Narrations can be 100s+.

### `TIMELINE_PAUSED`
Find Play/Resume and click via CDP. If none, re-classify (may be SLIDE_DONE). In Format C the Play button is at ≈(82,786).

### `INTERACTIVE_SLIDE`
1. Targets = clickables minus (instruction banner, slide title, header band `y < 100`, background stategroups, nav, hyperlinks).
2. For each target not in the clicked set (key = PHYSICAL rect `"x,y,w,h"`): click its center; **hard guard: any key >1 click → STOP (CLICK_REPEAT)**; wait for audio between clicks.
3. All clicked → fall through to SLIDE_DONE.
4. Persist per-slideId clicked sets to `~/.hermes/logs/ilearning-autoadvance-resume.json`.

### `QUIZ_SLIDE`
1. Screenshot + vision to read the question and options (DOM labels are usually useless).
2. Reason the correct answer from course content; common patterns: "All the above" when all options are valid; "NOT true"/"NOT a good practice" picks the single bad option; scenario questions pick the policy-compliant action.
3. Map radios to click targets per format (Format A: `acc-<modelId>` → slide-object rect; Format B: walk up to the clickable container; Format C: use the memorized row layout, or re-probe rects).
4. Click option center, then Submit/SUBMIT (Format A `submit0001.png` ≈(741,693); Format B `Submit Answer`; Format C (1383,802)). Submit appears only after selection.
5. Feedback popup: Continue ≈(750,612)/(756,531) to proceed; Try Again ≈(756,531) to retry an incorrect answer (Format C); View Answer (Format B) shows the correct option.
6. Never submit twice for the same question (track submitted keys).
7. Assessments can be interleaved with content (Format C: "Question X of 25" spread through the deck) — after the last question the course returns to content slides; restart the orchestrator.

### `SLIDE_DONE`
1. Find Next/Continue (PNG `Next.png` in clickables, or button with text NEXT/Continue).
2. Click center via CDP. Record `last_slide_id` BEFORE the click.
3. **Transitions can take >10s.** Wait 4s between clicks; clear per-slide clicked sets ONLY on real slideId/page change (TRANSITION).
4. If unchanged after 10 next-clicks → screenshot + vision, one alternative affordance, else hand off (STUCK).
5. Some slides' embedded nav acts as play/resume — if playing goes 1 after a next-click, wait for audio, click Next again.
6. Increment `modules_advanced`; stop at `max_modules`.

## Clicking Slide Objects (CRITICAL)

**JS-dispatched `MouseEvent`s DO NOT register in this Storyline build (Format A).** Only trusted CDP `Input.dispatchMouseEvent` works:

```python
await send("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y, "button": "left", "buttons": 1, "clickCount": 1})
await send("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y, "button": "left", "buttons": 0, "clickCount": 1})
```

**Click identity = PHYSICAL LOCATION** (`f"{x},{y},{w},{h}"`), never modelId/acc-text — duplicate DOM layers of one card share one rect; id-keyed tracking causes same-card double-clicks.

Pitfalls:
- Click the stategroup, not the label (Format A).
- Skip background stategroups whose clickRect covers >50% of the slide.
- Offscreen decoys at x≥1920 (Format A probe filters them).
- **cs-disabled class = disabled** (Format C) — check `className.includes('cs-disabled')`, not just the attribute.
- Zero-size SVG buttons → click parent `.slide-object` rect; else screenshot + vision.
- Popup overlay freeze (z=9999 full-slide container at popup position) → surface to user for reload.

## Screenshot & Vision

`cdp_shot.py "<target>" /tmp/shot.png`, then `vision_analyze` (ask for: question text verbatim, all options verbatim, instruction text, submit button, popup, button colors/positions). Use on every QUIZ_SLIDE, on UNKNOWN > 2 ticks, and after stuck Next.

## Resume State

Persist per-slide click history per slideId to `~/.hermes/logs/ilearning-autoadvance-resume.json`. Seed clicked sets on startup; save after every card click. Delete a slideId's entry if it was recorded from a buggy run.

## Orchestrator Patterns

- **Format A**: `ilearn_orchestrator.py` — `MATCH="scorm2004contentplayer"`, TICK=5, STUCK_AFTER=10 (transitions slow), NO MENU_SLIDE (instructions-only trigger), `is_background()`, physical-rect dedupe, CLICK_REPEAT guard, per-slideId resume.
- **Format B**: `goe_orchestrator.py` — iframe target; scroll-to-bottom then click Continue; QUIZ handoff on inputs.
- **Format C**: `appsec_orchestrator.py` — NEXT-first priority; WAIT_NEXT with 10s timeout (hand off STUCK after 2×5s ticks); cs-disabled check; hyperlink exclusion; QUIZ handoff on inputs.

```bash
cd /Users/laansdole/.hermes/skills/ilearning-autoadvance/scripts
/usr/bin/python3 <format>_orchestrator.py 50 <runid>
# background with notify_on_complete: true
```

**ALWAYS kill all previously-started orchestrator background sessions before starting a new one** — stale processes from older code keep clicking and corrupt state.

## Loop Control

Stop when any of:
- `modules_advanced >= max_modules`.
- No Next affordance for 60s (12 ticks) after SLIDE_DONE.
- `last_3_slide_ids` identical AND last action was a Next click (infinite loop).
- Page navigates outside `hclt.lms.hr.cloud.sap` (or to a report/thanks page = course finished).
- CDP connection dropped.
- `unknown_streak > 6`.
- Session/login expired.
- Any card's `click_counts` > 1 (CLICK_REPEAT).
- **NEXT disabled for 10s+ (WAIT_NEXT timeout → STUCK handoff).**
- **User-stopped boundary: policy-attestation checkbox section (user completes manually).**

## Safety Rules

- Never type into any `type="password"` field.
- Never click anything whose accessible name contains: logout, sign out, sign-out, signout, log off.
- If `location.hostname` is not `hclt.lms.hr.cloud.sap` (or `app.goethena.com` inside the nested iframe), stop and surface.
- Do NOT navigate away with `browser_navigate`; interact within the current tab only.
- Do NOT close tabs or the browser.

## Logging

JSONL per run in `~/.hermes/logs/ilearning-autoadvance-<runid>.jsonl` with `ts`, `state`, `slide`/`heading`, `action`, `page`, `audio_playing`/`audioPlayingCount`, `ok`. Include per-card counts in click lines (user reviews these to verify no double-clicks). Print a summary at loop end.

## Error Recovery

| Failure | Detection | Recovery |
|---|---|---|
| CDP connection dropped | Runtime.evaluate error | Stop, log, surface. |
| Session/login expired | SSO redirect / iframe missing >30s | Stop, surface. No auto-relogin. |
| Click didn't register | slideId unchanged after click | Re-probe; click stategroup center; verify in-viewport; screenshot+vision. Transitions can take >10s. |
| Card re-clicked | `click_counts[key] > 1` | HARD STOP (CLICK_REPEAT) — fix dedupe/state bug before resuming. |
| Clicked sets cleared wrongly | sets reset on failed Next | Only clear on real slideId change (TRANSITION). |
| Quiz submit disabled | `disabled`/`aria-disabled`/`cs-disabled` | Re-scan for unanswered questions, answer, retry. |
| Quiz option labels useless | labels "Rectangle 3" (Format A) | Screenshot + vision; radio id → modelId → rect. |
| NEXT disabled long | cs-disabled / no click effect for 10s | Hand off STUCK; agent resumes audio (Play button) or surfaces. |
| Feedback popup Next unreachable | elementFromPoint hits z=9999 overlay | Player frozen — surface to user for reload. |
| Format C quiz wrong answer | popup says Incorrect + Try Again | Click Try Again (756,531), select the other option, resubmit. |
| Next click starts narration | playing goes 1 after next-click | Wait for audio, click Next again. |
| Stale orchestrator process | duplicate clicks in log | process list + kill ALL, restart current code. |
| Infinite loop | same slide_id 3+ actions | Stop, log, surface. |

## Key Lessons Learned

### 2026-07-19 session (Format A basics)
1. Probe, classify, act, repeat — ONE probe per tick. Don't over-investigate Storyline internals.
2. `acc-shadow-el`/`#acc-<modelId>` are accessibility mirrors — clicking them does nothing. Click the real `.slide-object`.
3. Audio playback is the progress indicator; `playing > 0` = timeline advancing.
4. Interactive slides require clicking each topic and waiting for its audio before Next enables.
5. Next is often a zero-size SVG inside a `.slide-object` div — click the parent.

### 2026-08-13 session (v3.0.0 — Format A hard truths)
6. **JS-dispatched mouse events DO NOT register** — only trusted CDP Input.dispatchMouseEvent.
7. **Drive the player tab over raw CDP** — Hermes browser tools stay pinned to the overview tab.
8. Nav buttons are PNG slide-objects; embedded nav at y≈718 vs global chrome y≈915.
9. Interactive targets are stategroups (click the ancestor, not the label).
10. Duplicate DOM layers + offscreen decoys at x≥1920 — filter to viewport, dedupe by physical rect.
11. **Never re-click a card** — log counts, hard-stop on >1 (user requirement).
12. Clear clicked sets only on real slide transitions.
13. Narrations can be 110s+ — TIMELINE_PLAYING is often just a long wait.
14. Video slides play separately from audio MP3s.
15. **Kill all stale orchestrator background sessions before restarting.**

### 2026-08-13 full-course completion (v4.0.0 — user's rules)
16. **Interactive targets exist ONLY when slide text says "Click..." — otherwise just Next.** No pointer-cursor fallback, no menu heuristics.
17. **Click-tracking key = physical rect (x,y,w,h)**, never modelId/acc-text.
18. Filter background stategroups (>50% slide); keep static-named elements ("Oval 2") with a stategroup clickRect — they ARE targets.
19. Quiz flow (used ~12x): screenshot+vision; radio id → slide-object rect; submit appears after selection; popup next ≈(750,612); never submit twice.
20. Final Assessment = 10 questions, 80% pass, separate scene; then Results → Thank You → certificate.
21. **Transitions can take >10s** — STUCK patience ~10 next-clicks with 4s spacing.
22. Embedded nav at y≈718 can act as play/resume — wait for audio, click Next again.
23. Popup overlay freeze (z=9999) → surface to user for reload.

### 2026-08-13 Ethena + AppSec courses (v5.0.0 — new formats)
24. **Format B (Ethena/GoEthena)**: nested cross-origin iframe = its own `"type":"iframe"` CDP target — use iframe-capable helpers (sed-variant of cdp_eval/click). Scroll the slide container, then click Continue. Per-section assessments with Submit Answer; incorrect → View Answer; ends with optional feedback survey. Some courses end with a policy-attestation checkbox the USER completes.
25. **Format C (direct-HTML SVG, AppSec)**: no iframe; NEXT/PREV real buttons at bottom-right; **disabled = `cs-disabled` CSS class** (not the attribute); audio must finish before NEXT enables; slide number `<n> Copyright` in footer. 25-question assessment INTERLEAVED with content slides ("Question X of 25").
26. **NEXT-first priority (user rule)**: enabled NEXT beats any clickable item — always click NEXT first.
27. **10s wait cap (user rule)**: NEXT disabled → wait ~10s, then STUCK handoff — never sleep forever. Long narrations resolve themselves; mid-paused narrations need the agent (resume Play) or the user.
28. **Quiz layout memory (Format C)**: 2-opt y≈382/442; 3-opt y≈386/446/506; 4-opt y≈360/421/481/541 (x≈130-147, centers ≈(537, row+20)); SUBMIT (1383,802); Continue/Try Again (756,531). Wrong answers → Try Again to retry.
29. Course completion signal: player reaches "Thank you"/"Completed" screen, or the LMS portal tab shows `courseCompleted=true` / a certificate-report page — stop the orchestrator there.
