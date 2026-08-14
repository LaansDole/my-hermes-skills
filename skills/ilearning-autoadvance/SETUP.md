# iLearning Auto-Advance — Setup & Launch

## One-time setup

1. Install Hermes Agent:
   ```bash
   curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
   ```
   Open a new shell (or `source ~/.zshrc`) so `hermes` is on `$PATH`. Verify with `hermes --version` (must be >= 0.18.0).

2. Log in to Nous Portal (gives the agent a vision-capable model via the Tool Gateway — no separate API keys):
   ```bash
   hermes setup --portal
   ```

3. Enable the `browser` toolset in local CDP mode:
   ```bash
   hermes setup tools
   ```
   Pick `Browser Automation` → `Local Chromium-family CDP`. NOT Browserbase / Browser Use / Firecrawl / Camofox (those are cloud and out of scope).

4. Patch `~/.hermes/config.yaml` for unattended approvals. From the repo:
   ```bash
   cp ~/.hermes/config.yaml ~/.hermes/config.yaml.bak.$(date +%Y%m%d-%H%M%S)
   $EDITOR ~/Projects/auto-learn-for-me/.hermes-config/config-patch.yaml
   $EDITOR ~/.hermes/config.yaml
   ```
   Ensure `approvals.mode: scoped` (or `auto` as a fallback) and `browser.cloud_provider: local` are set. Validate with `hermes config show`.

5. The chrome-profiles plugin (`browser_profile` tool) must have the user's live browser registered (e.g. `brave-live` on port 9222). Verify with `browser_profile()` (no args) — the live profile must be `reachable: true`.

## Per-session launch

1. Start Brave/Chrome with remote debugging. Quit the browser fully (Cmd-Q) first — the flag only takes effect on a fresh launch:
   ```bash
   /Applications/Brave\ Browser.app/Contents/MacOS/Brave\ Browser \
     --remote-debugging-port=9222 \
     --user-data-dir="$HOME/Library/Application Support/BraveSoftware/Brave-Browser" &
   ```
   Using your normal `--user-data-dir` preserves your existing SAP SuccessFactors LMS login. (Chrome equivalent: `Google Chrome` + `~/Library/Application Support/Google/Chrome`.)

2. Verify the debug port is listening:
   ```bash
   curl -s http://127.0.0.1:9222/json/version | head -1
   ```
   Expected: JSON containing `"webSocketDebuggerUrl"`. If empty, the browser didn't start with the flag — make sure no other browser process is using that user-data-dir first.

3. In the browser, navigate to SAP SuccessFactors LMS (`hclt.lms.hr.cloud.sap`), log in via SSO/2FA, and open the course. The overview page shows a **"Launch Content"** button. Clicking it opens the SCORM player in a **NEW TAB** (URL contains `scorm2004contentplayer`). The overview tab keeps a disabled Launch button — the player is the other tab.

4. Start Hermes, switch browser tools to the live profile, and invoke the skill:
   ```bash
   hermes -t browser chat
   ```
   ```
   browser_profile(name='brave-live')   # or whatever the live profile is named
   Run the ilearning-autoadvance skill, max_modules=10.
   ```

## What the agent does

The course content plays inside an `<iframe>` as Articulate Storyline SCORM. There is no single HTML5 `<video>` — progress is driven by ~44 audio MP3 timelines (plus occasional mp4 slides) and interactive slide-object clicks.

**IMPORTANT (v3.0.0):** Hermes browser tools stay pinned to whichever tab was active when the profile connected — usually the OVERVIEW tab, not the player tab. The agent therefore drives the player tab over **raw CDP** (websocket): `curl http://localhost:9222/json/list` to find the `scorm2004contentplayer` tab, then small Python helpers for Runtime.evaluate (probe), Input.dispatchMouseEvent (clicks), and Page.captureScreenshot (vision). Each tick:

1. Runs the state probe (audio playback, slide/scene metadata, viewport-filtered clickable slide objects with stategroup click rects, instructions text, quiz inputs).
2. Classifies the state (`COURSE_OVERVIEW`, `TIMELINE_PLAYING`, `TIMELINE_PAUSED`, `INTERACTIVE_SLIDE`, `MENU_SLIDE`, `QUIZ_SLIDE`, `SLIDE_DONE`, `UNKNOWN`).
3. Acts: resume paused audio, click each interactive card/topic (waiting for its audio to finish; never clicking any card more than once), click menu cards that jump to sections, answer quizzes, or click Next/Continue (PNG `Next.png` slide-object) to advance.

It does NOT type passwords, click logout/sign-out, or navigate away from `hclt.lms.hr.cloud.sap`.

## First-run safety pattern

Before the first unattended run, do a **dry run** to validate state classification against the real DOM:

```
Run the ilearning-autoadvance skill, max_modules=1, dry_run=true.
```

Watch the agent describe each action it WOULD take. If it misclassifies (e.g. calls a paused timeline "done", or tries to click a label instead of its stategroup), edit `~/.hermes/skills/ilearning-autoadvance/SKILL.md` (State Classification / Clicking sections) and re-run. The skill is prose — tuning is the work.

Then do a **single-module live run** with approvals on (temporarily set `approvals.mode: manual` in `~/.hermes/config.yaml` and restart Hermes):

```
Run the ilearning-autoadvance skill, max_modules=1.
```

Approve each click yourself. Confirm: audio resumes, interactive cards clicked once each, quiz answered, next slide reached. If clean, flip approvals back to `scoped`/`auto` and do the full unattended run.

## Logs and troubleshooting

- Per-tick logs: `~/.hermes/logs/ilearning-autoadvance-<session-id>.jsonl`
- Resume state (per-slide clicked cards): `~/.hermes/logs/ilearning-autoadvance-resume.json`
- If the agent gets stuck on `UNKNOWN` state for > 2 ticks, check the screenshot it logged — the course may have pushed a modal not covered by the classification rules. Edit `SKILL.md` to add the new state and re-run.
- **If clicks aren't registering, the likely cause is dispatching JS `MouseEvent`s instead of trusted CDP input.** The skill's "Clicking Slide Objects" section is explicit: only `Input.dispatchMouseEvent` works on this build. Re-read it.
- **If cards get clicked repeatedly**, the cause is either (a) a stale orchestrator process from an older code version still running — `process action=list` and kill ALL old sessions first — or (b) clicked sets being cleared on a failed Next click instead of on a real slide transition. Re-read the SLIDE_DONE / Resume State sections.
- `hermes computer-use doctor` is for the computer-use toolset (not used here) — only run if you suspect platform-level issues unrelated to this skill.
