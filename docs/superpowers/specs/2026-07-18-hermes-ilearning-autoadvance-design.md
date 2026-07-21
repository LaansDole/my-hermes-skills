# Hermes iLearning Auto-Advance — Design Spec

- **Date:** 2026-07-18
- **Author:** brainstorming session (user + assistant)
- **Status:** approved, ready for implementation planning

## 1. Goal

Use [Hermes Agent](https://hermes-agent.nousresearch.com/) (Nous Research, MIT, macOS/Windows/Linux) to autonomously watch and advance through HCL iLearning Success online courses in the user's web browser. The agent must:

- Resume paused videos.
- Answer in-video quizzes seriously (reason about the question, pick the best option).
- Navigate to the next module when a video ends.
- Run **fully unattended** — no per-click approval.

The user has explicitly chosen "fully unattended" operation and "attempt quizzes seriously." The goal is advancing the video, not earning a credential.

## 2. Background — Hermes Capabilities (researched)

Hermes ships two distinct automation paths. This design uses the first.

### Browser toolset (used)

- Drives a real Chromium-family browser via the accessibility tree (text snapshots with `@e1`, `@e2` ref IDs for clicking).
- Modes: Browserbase / Browser Use / Firecrawl (cloud), Camofox / **local CDP** / local `agent-browser` (local).
- Vision analysis available: `tab.screenshot()` + AI for stuck-state diagnosis.
- No OS-level screen permissions needed on macOS.
- Docs: [`browser.md`](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/browser.md)

### Computer Use toolset (not used; fallback)

- Drives the actual desktop via `cua-driver`. Clicks at screen coordinates in the background (real cursor doesn't move).
- Requires macOS Accessibility + Screen Recording permissions.
- Overkill for a pure web app reachable via CDP.
- Docs: [`computer-use.md`](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/computer-use.md)

## 3. Architecture

```
[User's Chrome, logged into HCL iLearning]
        |  CDP via --remote-debugging-port=9222
        |  Hermes attaches with /browser connect
        v
[Hermes Agent runtime]  <-- ~/.hermes/skills/ilearning-autoadvance/SKILL.md
        |
        |  vision-capable model (Claude / GPT / Gemini via Nous Portal)
        v
[Watch loop: observe -> classify state -> act -> sleep -> repeat]
```

### Components

1. **Hermes Agent runtime** (v0.18+). Invoked with `hermes -t browser chat`. Configured via `~/.hermes/config.yaml` + `~/.hermes/.env`.
2. **Chrome with remote debugging** — user starts Chrome with `--remote-debugging-port=9222`, logs into HCL iLearning normally (corporate SSO, 2FA, whatever). Hermes attaches via `/browser connect`. **No credentials in the agent, no auth flow to automate.** Cookies and session state live in the user's real Chrome profile.
3. **`ilearning-autoadvance` skill pack** at `~/.hermes/skills/ilearning-autoadvance/`:
   - `SKILL.md` — the watch-loop instructions, state machine, action policy, safety rules, logging format.
   - `SETUP.md` — install and launch steps.
   - No code. Pure prose the agent loads when the skill is invoked.
4. **Vision-capable model** — via Nous Portal subscription (`hermes setup --portal`) or any OpenAI-compatible endpoint. Used only when the accessibility tree is ambiguous (stuck-state diagnosis, icon-only buttons, quiz options rendered as images).
5. **Approval config** — `~/.hermes/config.yaml` sets `approvals.mode` so that `browser.click` and `browser.type` do **not** require confirmation. The user explicitly accepts unattended operation.

## 4. Watch-Loop State Machine

Each tick (every ~5 s when idle; immediately after an action): snapshot the accessibility tree, classify the player state, dispatch the matching action, sleep, repeat.

```
                      +--------------------+
                      |  TICK (every ~5s)  |
                      +--------------------+
                               |
            +------------------+------------------+
            |                  |                  |
            v                  v                  v
     [VIDEO PLAYING]    [VIDEO PAUSED]    [QUIZ POPUP]
            |                  |                  |
            | no action,       | find resume     | read Q + options
            | sleep            | button @eN,      | via tree + screenshot
            |                  | click it         | reason, pick answer
            |                  |                  | click option, submit
            |                  |                  |
            +--------+---------+------------------+
                     |
                     v
            [VIDEO ENDED / END-OF-MODULE]
                     |
                     | find "Next" / "Mark complete" / "Next module"
                     | via tree
                     | click it
                     |
                     v
            [NEW LESSON LOADED] -> back to TICK
```

### State classification

Three signals, in order of preference:

1. **`<video>` element state** (primary, deterministic) — query `paused`, `ended`, `currentTime`, `duration` via `tab.evaluate`. Cheap and authoritative.
2. **Accessibility tree scan** (`tab.observe()`) — look for known button labels: resume / continue / next / replay / mark-complete / submit. Look for quiz form structures (radio buttons, checkboxes, text inputs inside a labeled question block).
3. **Screenshot + vision** (fallback only) — invoked when the tree is ambiguous: icon-only `<button>`, shadow-DOM popups, quiz options rendered as images. The vision pass describes what is on screen and returns a ref or coordinate.

### Action policy (all unattended)

- **Paused + resume button visible** → click it.
- **Quiz popup** → read question, read each option, reason about the correct answer (the model does this — "attempt seriously"), click the chosen option's `@eN` ref, click submit. If submit is disabled until all questions answered, repeat for each unanswered question.
- **Video ended** → click "Next" / "Mark complete" (whichever the tree exposes). If neither appears within 10 s, screenshot + vision to find the affordance.
- **Unknown state** for > 2 consecutive ticks → screenshot, log, keep polling (no clicks) until a known state reappears or `max_modules` is reached. Do **not** click blindly.

### Loop control

- Tick cadence: 5 s between actions when idle; immediate next-tick after an action (so the page has time to react).
- **Bounded session** via `max_modules` parameter (default 50, configurable). Stops when:
  - (a) no "Next" affordance for 60 s after a video ends, or
  - (b) module count reached, or
  - (c) an unrecoverable error (login expired, page 404, model API failure exhausted).
- **Idempotency guards** to prevent double-advances:
  - Never click "submit" twice in the same quiz.
  - Never click "Next" if the URL has not changed since the last "Next" click.
- **Infinite-loop guard**: track the last 3 URLs; if all three are identical after actions, stop and surface to the user.

### Safety guardrails (on top of Hermes defaults)

- Never type into password fields (Hermes hard-blocks this anyway).
- Never click anything labeled logout / sign-out / sign-out.
- If the page navigates outside the HCL iLearning domain, stop and log.
- Hermes's built-in destructive-action blocklists (`sudo rm -rf`, `curl | bash`, fork bombs, lock-screen combos) remain active.

## 5. Error Handling & Recovery

| Failure | Detection | Recovery |
|---|---|---|
| CDP connection dropped (Chrome closed/crashed) | `tab.observe()` returns connection error | Stop, log, surface to user. Cannot auto-recover (user must restart Chrome). |
| Session/login expired | Page navigates to SSO login URL, or `<video>` element missing for > 30 s | Stop loop, log URL, surface to user. No auto-relogin (credentials out of scope). |
| Click landed wrong / no state change | URL + `video.currentTime` unchanged 2 ticks after a click | Re-screenshot, re-classify, retry once with a different ref/coordinate. If still stuck, log and skip to next tick rather than spam clicks. |
| Quiz submit disabled | Submit button has `disabled` / `aria-disabled` | Do not attempt submit; re-scan for unanswered questions, answer them, then submit. |
| Page JS error / blank render | Screenshot returns empty canvas or error overlay | Wait 2 ticks; if persists, log and advance to next module if possible, else stop. |
| Model API failure / rate limit | Model call times out or 429 | Backoff 10 s → 30 s → 60 s; after 3 failures, stop and surface to user. |
| Infinite loop (same module replayed 3×) | `last_3_urls` identical after actions | Stop, log, surface to user. |

### Logging

Every tick writes a structured line to `~/.hermes/logs/ilearning-autoadvance-<session-id>.jsonl`:

```json
{"ts":"...","module":"<title>","state":"paused","action":"click @e14","video_pos":"123.4/456.7","ok":true}
```

End-of-session summary printed to the terminal: modules completed, quizzes attempted (right/wrong if gradable), time elapsed, any stuck points.

## 6. Testing Strategy

This is a skill (prose), not application code — verification is end-to-end behavioral, not unit tests.

1. **Dry-run mode** in the skill: `max_modules=1`, `--dry-run` flag → agent observes and *describes* the action it *would* take without clicking. Run against a real HCL iLearning course to validate state classification on the actual DOM. First-pass correctness check.
2. **Single-module live run**: `max_modules=1`, approvals back on for the first run. Watch the agent complete one module. Confirm: video resumes, quiz answered, next-module clicked. Smoke test.
3. **Full unattended run on a real course**: `max_modules=10`, approvals off. Observe the log file. Success = log shows clean advancement through 10 modules with no stuck loops, no double-clicks, no logout.
4. **Regression check after HCL UI changes**: if a run misbehaves, the `--dry-run` mode on a fresh course is the diagnostic — the skill prose gets updated, no code rebuild.

## 7. Deliverables

1. `~/.hermes/skills/ilearning-autoadvance/SKILL.md` — the watch-loop instructions, state machine, action policy, safety rules, logging format.
2. `~/.hermes/skills/ilearning-autoadvance/SETUP.md` — install steps: Chrome `--remote-debugging-port=9222`, `/browser connect`, approvals config, Nous Portal model.
3. `~/.hermes/config.yaml` patch — `approvals.mode` scoped so browser click/type don't require confirmation; `browser.cloud_provider` left unset (local CDP only).
4. A short `README.md` at `~/Projects/auto-learn-for-me/` documenting how to launch a session: `hermes -t browser chat` then "run the ilearning-autoadvance skill on my current tab, max_modules=10".

## 8. Non-Goals (explicit)

- Handling HCL SSO login (out of scope — user stays logged in via their real Chrome).
- Anti-detection / stealth (if HCL detects automation, that's a policy problem for the user, not a design problem — no stealth added).
- Multi-course parallelism (one course at a time).
- Tracking learning progress across sessions (HCL itself tracks completion; we don't duplicate).

## 9. Risk Callouts

- **HCL iLearning DOM may not expose quiz options as standard form controls** (could be in shadow DOM or a custom framework). Mitigation: screenshot+vision fallback is in the skill from day one.
- **"Attempt quizzes seriously" depends on model quality.** The skill prompts the model to reason about each option; if the model hallucinates, the user scores wrong. Acceptable per the stated goal (advance the video, not credential hunting).
- **Fully unattended browser automation can misbehave.** Bounded by `max_modules`, double-click guards, and the "stop if URL unchanged" rule. First runs should follow the dry-run + single-module live pattern from Section 6.

## 10. Next Step

Invoke the `writing-plans` skill to produce a step-by-step implementation plan from this spec.