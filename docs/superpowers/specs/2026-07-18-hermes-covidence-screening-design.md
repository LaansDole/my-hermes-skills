# Hermes Covidence Title & Abstract Screening — Design Spec

- **Date:** 2026-07-18
- **Author:** brainstorming session (user + assistant)
- **Status:** approved, ready for implementation planning
- **Prior art:** `docs/superpowers/specs/2026-07-18-hermes-iLearning-autoadvance-design.md` (commit 0aef722). This spec is a sibling design that reuses the same Hermes + CDP + skill-pack architecture for a different web target (Covidence instead of HCL iLearning).

## 1. Goal

Use [Hermes Agent](https://hermes-agent.nousresearch.com/) (Nous Research, MIT, macOS/Windows/Linux) to autonomously screen references in a Covidence systematic review at the **title & abstract** stage. The agent votes **Yes / Maybe / No** per reference against the user's PICO criteria, runs **unattended after an approve-first-N onboarding phase**, and is bounded by `max_refs` and `max_time`.

The user has explicitly chosen:

- **Title & abstract stage only** (full-text and extraction stay manual).
- **Single-reviewer mode** (review is set to single-screener in Covidence before the agent runs).
- **Covidence metadata only** as the decision basis (no PubMed/DOI/PDF lookups).
- **Maybe + note rationale** for borderline references (one-line rationale written to the per-reference notes field).
- **Approve first N, then auto** approval policy (N=5 default; agent pauses for human confirmation on the first N votes, then flips to unattended for the rest of the session).
- **max_refs OR max_time** as the session bound (with an optional daily cap persisted across sessions).

The goal is speeding through the repetitive T&A queue; the PRISMA flow that Covidence auto-generates from the votes is the output the user cares about.

## 2. Background — Covidence & Hermes Capabilities (researched)

### Covidence

- Web app at `app.covidence.org`; reviewer logs in via institutional SSO.
- **Title & abstract screening**: for each reference, vote **Yes / Maybe / No**. Covidence auto-advances to the next reference after each vote. Each reference shows title, abstract, authors, journal, MeSH keywords (with keyword highlighting). Optional per-reference notes field.
- **Single vs dual mode**: a new review defaults to dual-screener (two blinded votes to advance). The user **must switch the review to single-reviewer mode** before running the agent (Settings → Switch to single reviewer). In single mode, one vote advances the reference.
- **Sorting**: "Most relevant" (active-learning ML ranker), Author, Title, Most recent. Page size 25/50/100.
- **PRISMA flow** auto-tracked from votes; no manual bookkeeping.
- Docs: [`support.covidence.org/help/screening-by-title-and-abstract`](https://support.covidence.org/help/screening-by-title-and-abstract)

### Hermes

Hermes ships two automation paths. This design uses the first (same as the iLearning spec).

#### Browser toolset (used)

- Drives a real Chromium-family browser via the accessibility tree (text snapshots with `@e1`, `@e2` ref IDs for clicking).
- Modes: Browserbase / Browser Use / Firecrawl (cloud), Camofox / **local CDP** / local `agent-browser` (local).
- Vision analysis available: `tab.screenshot()` + AI for stuck-state diagnosis.
- No OS-level screen permissions needed on macOS.
- Docs: [`browser.md`](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/browser.md)

#### Computer Use toolset (not used; fallback)

- Drives the actual desktop via `cua-driver`. Clicks at screen coordinates in the background.
- Requires macOS Accessibility + Screen Recording permissions.
- Overkill for a pure web app reachable via CDP.
- Docs: [`computer-use.md`](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/computer-use.md)

## 3. Architecture

```
[User's Chrome, logged into Covidence (app.covidence.org)]
        |  CDP via --remote-debugging-port=9222
        |  Hermes attaches with /browser connect
        v
[Hermes Agent runtime]  <-- ~/.hermes/skills/covidence-screening/SKILL.md
        |                <-- ~/.hermes/skills/covidence-screening/CRITERIA.md
        |                <-- ~/.hermes/skills/covidence-screening/STATE.md (daily counter)
        |
        |  vision-capable model (Claude / GPT / Gemini via Nous Portal)
        v
[Screen loop: observe -> read reference -> classify vs criteria -> vote -> advance -> repeat]
```

### Components

1. **Hermes Agent runtime** (v0.18+). Invoked with `hermes -t browser chat`. Configured via `~/.hermes/config.yaml` + `~/.hermes/.env`. Unchanged from iLearning setup.
2. **Chrome with remote debugging** — user starts Chrome with `--remote-debugging-port=9222`, logs into Covidence normally (institutional SSO, 2FA, whatever). Hermes attaches via `/browser connect`. **No credentials in the agent, no auth flow to automate.** Cookies and session state live in the user's real Chrome profile.
3. **`covidence-screening` skill pack** at `~/.hermes/skills/covidence-screening/`:
   - `SKILL.md` — the screen-loop instructions, state machine, decision-step prompt, action policy, approve-first-N onboarding, safety rules, logging format.
   - `CRITERIA.md` — the PICO + inclusion/exclusion bullets. User edits this file between runs. Loaded fresh each session.
   - `SETUP.md` — install and launch steps.
   - `STATE.md` — persisted daily counter (refs screened today) for the daily-cap backstop. Auto-created on first run; user can reset by deleting.
   - No code. Pure prose the agent loads when the skill is invoked.
4. **Vision-capable model** — via Nous Portal subscription (`hermes setup --portal`) or any OpenAI-compatible endpoint. Used only when the a11y tree is ambiguous: vote buttons rendered as icon-only, notes field behind a shadow-DOM popup, queue-empty banner. Never for the decision itself — the decision is text reasoning over title+abstract, which the model does from the tree snapshot.
5. **Approval config** — `~/.hermes/config.yaml` keeps `approvals.mode` default; the **skill prose** implements approve-first-N by having the agent pause and ask for confirmation on the first N votes, then set an in-skill flag (`auto_mode=true`) to skip confirmation for the rest of the session. Keeps the global config untouched (so iLearning runs stay unaffected).

### Reused from iLearning spec

- CDP attach pattern, no-credentials-in-agent rule.
- Bounded session via `max_*` params.
- Screenshot+vision fallback for ambiguous UI.
- Hermes built-in destructive-action blocklists remain active.

### New vs iLearning

- `CRITERIA.md` as a loaded file (iLearning had no criteria concept).
- `STATE.md` for daily cap (iLearning's `max_modules` was per-session only).
- Approve-first-N implemented in-skill, not via global config (iLearning was fully unattended from tick 0).
- Maybe + note rationale (iLearning had no "write a note alongside the action" step).

## 4. Screen-Loop State Machine

Each tick: snapshot the a11y tree, classify the screen state, dispatch the matching action, sleep, repeat.

```
                      +--------------------+
                      |   TICK (every ~5s) |
                      +--------------------+
                               |
            +------------------+------------------+
            |                  |                  |
            v                  v                  v
   [REVIEW SUMMARY PAGE]  [T&A SCREENING]   [UNKNOWN/ELSEWHERE]
            |                  |                  |
            | click "Continue" | read reference   | screenshot +
            | under T&A        | via tree        | vision to classify
            |                  |                  | (fallback)
            |                  v                  |
            |          [CLASSIFY vs CRITERIA]     |
            |                  |                  |
            |       +----------+----------+      |
            |       |          |          |      |
            |       v          v          v      |
            |   [INCLUDE]  [MAYBE]  [EXCLUDE]     |
            |       |    + note     |            |
            |       |    rationale  |            |
            |       v          |    |            |
            |   [approve-first-N?]               |
            |       |          |    |            |
            |       v          v    v            |
            |   click Yes / Maybe / No button (@eN)
            |                  |
            |                  v
            |   Covidence auto-advances to next ref
            |
            +--------+---------+------------------+
                     |
                     v
            [QUEUE EMPTY / "No more references"?]
                     |
            yes ----> STOP, log summary
            no  ----> [max_refs OR max_time hit?]
                     |
              yes --> STOP, log summary
              no  --> back to TICK
```

### State classification

Three signals, in order of preference:

1. **URL + page landmark** (primary, deterministic) — `tab.evaluate` checks `window.location.pathname` against known Covidence routes (Review Summary vs T&A screening). Cheap and authoritative.
2. **Accessibility tree scan** (`tab.observe()`) — look for the three vote buttons (`Yes` / `Maybe` / `No`), the reference metadata block (title, abstract, authors, journal, MeSH tags), the notes field, and the "No more references" / queue-empty banner.
3. **Screenshot + vision** (fallback only) — invoked when the tree is ambiguous: icon-only vote buttons, shadow-DOM notes popup, an unexpected modal. The vision pass describes what is on screen and returns a ref or coordinate.

### Decision step (the `[CLASSIFY vs CRITERIA]` box)

This is pure text reasoning, not a UI action:

1. Read reference metadata from the tree: title, abstract, authors, journal, MeSH keywords (with Covidence's keyword highlighting if exposed).
2. Load `CRITERIA.md` + apply any inline overrides from the invocation (e.g. "also exclude studies before 2010").
3. Reason per criterion: which PICO elements does this reference satisfy / violate / leave unclear?
4. Decide:
   - **Include (Yes)** — meets all inclusion criteria, violates no exclusion criterion.
   - **Exclude (No)** — violates a clear exclusion criterion (wrong population, wrong study design, not English, etc.).
   - **Maybe** — borderline: meets some criteria but the title/abstract leaves a PICO element ambiguous (e.g. population unclear, study type not stated).
5. If Maybe: compose a one-line rationale citing the specific ambiguity (e.g. "Population unclear — abstract says 'adults' but doesn't specify whether surgical patients").

The model does this reasoning — "attempt seriously" per the user's intent. No external lookups (PubMed/DOI/PDF), per the decision basis chosen.

### Action policy

- **On Review Summary page** → find "Continue" under Title & Abstract Screening, click it. Lands on the T&A screen.
- **On T&A screen with a reference loaded** → run the decision step, then:
  - If Maybe: type the rationale into the notes field first (find the notes textarea `@eN`, `tab.fill`), then click the Maybe button.
  - If Yes/No: click the Yes or No button directly.
- **Approve-first-N (onboarding)**: for the first N votes (default N=5), before clicking the vote button, the agent **pauses and prints its decision + rationale to the terminal** and waits for user confirmation. User responses: "approve" = cast this vote as decided and advance the onboarding counter; "skip" = leave this reference unvoted, advance to the next reference, onboarding counter does **not** advance; "stop" = end session immediately. After N "approve" responses, set `auto_mode=true` for the rest of the session (no further pauses).
- **Queue empty / "No more references"** detected → stop, log summary.
- **Unknown state** for > 2 consecutive ticks → screenshot, log, keep polling (no clicks) until a known state reappears. Do **not** click blindly.

### Loop control

- Tick cadence: 5 s between actions when idle; immediate next-tick after an action (so the page has time to react to a vote before re-reading).
- **Bounded session**: `max_refs` (default 200) OR `max_time` (default 90 min), whichever first. Plus optional daily cap persisted to `STATE.md` (default 500/day; 0 = disabled).
- **Idempotency guards** to prevent double-votes:
  - Track the current reference's stable ID (Covidence exposes a reference ID in the tree or URL). Never vote twice on the same ID.
  - Never click a vote button if a vote-confirmation banner is already present.
- **Infinite-loop guard**: track the last 3 reference IDs seen; if all three are identical after actions, stop and surface to the user.
- **Re-vote guard**: Covidence allows re-opening a voted reference in single mode to change the vote. The agent must **not** re-open already-voted references — only operate on the "Awaiting my vote" queue. Detected by the presence of a vote-confirmation banner vs. fresh vote buttons.

### Safety guardrails (on top of Hermes defaults)

- Never click anything labeled logout / sign-out.
- Never click into Full Text, Data Extraction, Risk of Bias, or Settings — strict allowlist of T&A screen + Review Summary page. If the page navigates elsewhere inside covidence.org, stop and log.
- If the page navigates outside the `covidence.org` domain, stop and log.
- Never type into password fields (Hermes hard-blocks this anyway).
- Never modify the review's inclusion/exclusion criteria, team members, or settings — agent is read-only on everything except vote buttons and the per-reference notes field.
- Hermes's built-in destructive-action blocklists remain active.

## 5. Error Handling & Recovery

| Failure | Detection | Recovery |
|---|---|---|
| CDP connection dropped (Chrome closed/crashed) | `tab.observe()` returns connection error | Stop, log, surface to user. Cannot auto-recover (user must restart Chrome). |
| Session/login expired | Page navigates to institutional SSO login URL, or vote buttons missing for > 30 s | Stop loop, log URL, surface to user. No auto-relogin (credentials out of scope). |
| Vote landed wrong / no state change | Reference ID unchanged 2 ticks after a vote click | Re-screenshot, re-classify, retry once. If still stuck, log and skip to next tick (don't spam clicks). |
| Maybe notes field write failed | Notes textarea `@eN` not found, or `tab.fill` returns error | Fall back to screenshot+vision to locate the notes field. If still not found after 1 retry, **skip the Maybe vote entirely** — do not vote without the rationale. Log the reference ID; user can review manually. |
| Queue-empty banner missing but no reference loads | "No more references" not detected, but no title/abstract in tree for > 3 ticks | Screenshot + vision to classify. If genuinely empty, stop with summary. If a modal/error overlay is blocking, log and stop rather than clicking through it. |
| Page JS error / blank render | Screenshot returns empty canvas or error overlay | Wait 2 ticks; if persists, log and stop. Do not attempt to advance — user reviews. |
| Model API failure / rate limit | Model call times out or 429 | Backoff 10 s → 30 s → 60 s; after 3 failures, stop and surface to user. |
| Infinite loop (same reference ID seen 3×) | `last_3_ref_ids` identical after actions | Stop, log, surface to user. |
| Daily cap hit | `STATE.md` counter >= daily cap | Stop, log "daily cap reached (N/N)", surface to user. Does not count toward `max_refs` for the next session. |
| Approve-first-N: user says "skip" | User response during onboarding | Skip the vote for this reference (leave it unvoted), advance, continue onboarding with the next reference. Do not auto-vote. |
| Approve-first-N: user says "stop" | User response during onboarding | End session immediately, log summary including which references were skipped. |

### Logging

Every tick writes a structured line to `~/.hermes/logs/covidence-screening-<session-id>.jsonl`:

```json
{"ts":"...","ref_id":"<covidence-ref-id>","title":"<short>","state":"on-reference","decision":"maybe","rationale":"Population unclear — abstract says 'adults' but not whether surgical","action":"vote Maybe + note","ok":true}
```

End-of-session summary printed to the terminal: refs screened, votes cast (Yes/Maybe/No counts), Maybe rationales list, time elapsed, any stuck points, daily-cap remaining.

## 6. Testing Strategy

Skill is prose, not application code — verification is end-to-end behavioral, not unit tests. Same shape as the iLearning spec.

1. **Dry-run mode** in the skill: `--dry-run` flag → agent observes each reference, reasons through the decision step, and *describes* the vote it *would* cast (with rationale) without clicking. Run against a real Covidence review (or the Covidence Demo review) to validate state classification and the CRITERIA.md reasoning on actual DOM. First-pass correctness check.
2. **Single-reference live run**: `max_refs=1`, approve-first-N active for this reference. Watch the agent read the metadata, reason, and cast one vote. Confirm: correct reference read, decision matches expectation, vote lands, Covidence advances. Smoke test.
3. **Approve-first-N live run**: `max_refs=10`, N=5. Confirm the onboarding loop: agent pauses, prints decision + rationale, waits for confirmation; after 5 approvals, flips to `auto_mode=true` and runs the remaining 5 unattended. Verify the auto-mode transition lands.
4. **Full unattended run on a real review**: `max_refs=20`, N=0 (auto from start), `max_time=15`. Observe the log file. Success = log shows clean voting through 20 references with no double-votes, no re-opens of already-voted refs, no navigation outside T&A + Review Summary.
5. **Maybe-rationale check**: run on a review where you've seeded borderline references in CRITERIA.md. Confirm every Maybe vote has a non-empty rationale in the notes field, visible in the Covidence UI afterward.
6. **Stop-condition regression**: force each stop — queue empty, `max_refs` hit, `max_time` hit, daily cap hit, CDP drop. Confirm each produces the right log summary and no spurious clicks after stop.
7. **Regression check after Covidence UI changes**: if a run misbehaves, the `--dry-run` mode on the demo review is the diagnostic — the skill prose gets updated, no code rebuild.

## 7. Deliverables

1. `~/.hermes/skills/covidence-screening/SKILL.md` — the screen-loop instructions, state machine, decision-step prompt, action policy, approve-first-N onboarding, safety rules, logging format.
2. `~/.hermes/skills/covidence-screening/CRITERIA.md` — template with PICO + inclusion/exclusion bullets for the user to fill in. Ships empty; user edits before first run.
3. `~/.hermes/skills/covidence-screening/STATE.md` — daily-cap counter file. Auto-created on first run; user can reset by deleting.
4. `~/.hermes/skills/covidence-screening/SETUP.md` — install steps: Chrome `--remote-debugging-port=9222`, `/browser connect`, Nous Portal model, how to edit CRITERIA.md, how to set the review to single-screener mode in Covidence, how to launch with `max_refs` / `max_time` / `--dry-run`.
5. No `~/.hermes/config.yaml` patch required — approve-first-N is implemented in-skill, leaving the global config (and iLearning runs) untouched.
6. A short `README.md` at `~/Projects/auto-learn-for-me/covidence-screening.md` documenting how to launch a session: `hermes -t browser chat` then "run the covidence-screening skill on my current review, max_refs=200, max_time=90, dry_run=false".

## 8. Non-Goals (explicit)

- Handling Covidence institutional SSO login (out of scope — user stays logged in via their real Chrome).
- Full-text screening, data extraction, risk-of-bias assessment (agent cannot navigate there).
- Dual-reviewer mode (review must be set to single-screener before running; agent only casts the deciding vote).
- External lookups (PubMed, DOI, publisher PDFs) for the decision — Covidence metadata only.
- Anti-detection / stealth (if Covidence detects automation, that's a policy problem for the user, not a design problem — no stealth added).
- Multi-review parallelism (one review at a time).
- Tracking screening progress across sessions (Covidence itself tracks votes; we don't duplicate).

## 9. Risk Callouts

- **Covidence T&A DOM may not expose vote buttons as standard form controls** (could be custom React components or shadow DOM). Mitigation: screenshot+vision fallback is in the skill from day one.
- **Reference ID may not be trivially extractable** from the tree or URL. Mitigation: the idempotency guard falls back to hashing the title+first-author+year as a synthetic ID; if that collides, the infinite-loop guard (3 identical IDs) still catches it.
- **"Attempt decisions seriously" depends on model quality.** The skill prompts the model to reason per PICO criterion; if the model hallucinates inclusion/exclusion, the PRISMA flow is wrong. Acceptable per the stated goal (speed through the queue; user reviews the Maybe list and can re-open any vote in single mode).
- **Approve-first-N does not guarantee later correctness.** It validates the agent's reasoning on N references; once `auto_mode=true`, the agent could drift. Mitigation: log every decision + rationale to the jsonl; the Maybe queue and the log are the user's audit trail.
- **Fully unattended browser automation can misbehave.** Bounded by `max_refs`, `max_time`, daily cap, double-vote guards, the re-vote guard, and the "stop if same ref ID 3×" rule. First runs should follow the dry-run → single-ref → approve-first-N → full-unattended pattern from Section 6.

## 10. Next Step

Invoke the `writing-plans` skill to produce a step-by-step implementation plan from this spec.