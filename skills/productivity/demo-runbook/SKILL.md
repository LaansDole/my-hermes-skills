---
name: demo-runbook
description: "Use when asked for a runbook demo. Real runs, video, Pages."
version: 0.1.0
author: Do Le Long An (LaansDole), Hermes Agent
license: MIT
platforms: [macos, linux]
metadata:
  hermes:
    tags: [demo, runbook, walkthrough, screencast, video, captions, github-pages, cdp, headless-chrome]
    related_skills: []
---

# Demo Runbook Skill

Turns a working app feature into a demo package that a stranger can follow and watch:
a markdown runbook with real-run screenshots, ONE continuous captioned video of the runbook journey,
a `demo.html` page (video plus clickable runbook steps), and a GitHub Pages deploy of that page.
Everything shown comes from real runs; nothing is staged, mocked or forced. Proven on the
DynaClinic 3D demo (`templates/captions.example.json` and `templates/page.example.json` are that demo).

## When to Use

- "give me a runbook", "runbook demo", "record the whole workflow", "capture it in the UI", "deploy the demo to GitHub Pages".
- Re-recording after UI or model changes (the package must be regenerated, not patched).
- Don't use for: unit-level docs, slide decks (use a slides skill), or demos where the user wants scripted/mock output.

## Prerequisites

- Google Chrome (real Chrome renders WebGL/WebGPU; some automation browsers capture a blank canvas), `ffmpeg` with libx264, Python 3 with `websocket-client` and `Pillow`.
- `gh` authenticated with push access, for the Pages deploy.
- The app's servers runnable locally; the model/provider env vars present (names only in docs, never values).
- Scripts in this skill: `scripts/cdp.py` (nav/eval/shot/click/type/enter), `scripts/record_screencast.py`, `scripts/caption_video.py`, `scripts/build_demo_page.py`, `scripts/shots_widths.py`. Templates: `templates/record-journey.sh`, `templates/captions.example.json`, `templates/page.example.json`, `templates/demo.html`, `templates/pages.yml`. Structure: `references/runbook-structure.md`.

## Procedure

1. **Freeze the code first.** Finish and verify every code change (and stop any coding agent that runs its own servers on the same ports) before capturing. Done when: tests green, tree clean, no other process on the capture ports.
2. **Pick inputs per path.** For every route the demo must show (cheap path, normal path, escalation path), take an existing case known to take it; if none does, write a clearly labelled demo input and PRE-FLIGHT it headless through the same entry point (SDK/CLI). Never lower thresholds or script outputs to force a path. Done when: each scenario has an input file and a pre-flight result.
3. **Start servers and a sandbox browser.** Servers in the background with health checks; restart any backend started without auto-reload after code changes. Chrome: `"<chrome>" --headless=new --remote-debugging-port=9333 --user-data-dir=<fresh dir> --no-first-run --window-size=1600,1000 about:blank`. Done when: health checks return 200 and a first `cdp.py shot` is not blank.
4. **Write the runbook** at `docs/<feature>/runbook/README.md` following `references/runbook-structure.md`, with stills captured per scenario (`cdp.py shot` during a run). Done when: every number quoted is traceable to a run output file.
5. **Record the journey.** Copy `templates/record-journey.sh`, fill the steps in runbook order (one `log` line per runbook step; sleeps sized for a viewer to read), run it once on a fresh profile. Done when: `frames/times.txt` exists, `steps.log` lists every step, the backend shows exactly one run per scenario.
6. **Write captions.** Copy `templates/captions.example.json`. One caption per runbook step and per meaningful backend event: `at` = wall time from `steps.log` or the backend log (node entry, route, result), `label` = runbook step id, `line1`/`line2` = what is on screen, quoting the run's own numbers; `chapter` starts a chapter; `list` = short label for the page's step list. Check every quoted number against the run's output files. Done when: no caption states a value you have not seen in an output file.
7. **Render and frame-check.** `terminal(command="python3 scripts/caption_video.py <frames> captions.json <out>")`, then extract a frame at each caption's video time (`ffmpeg -ss`) and look at them (`vision_analyze`). Auto-opening result modals often appear BEFORE the scripted click; move those captions to the real appearance time. Done when: sampled frames match their captions.
8. **Build the page.** Copy `templates/page.example.json`, fill title/subtitle/evidence table/run commands (repo-relative, no machine-local paths, link `.md` files by GitHub blob URL), then `python3 scripts/build_demo_page.py page.json <out> docs/<feature>/runbook/demo.html`, and copy the MP4 next to it. Check layout with `scripts/shots_widths.py` at 1871, 1440, 1280 and 390 px, and test seeking over `file://`. Done when: no early line breaks or overflow, and a step click seeks to its time and highlights it.
9. **Deploy.** Copy `templates/pages.yml` to `.github/workflows/pages.yml` (set `DEMO_DIR` and branches). Enable Pages for Actions with `gh api -X POST repos/<o>/<r>/pages -f build_type=workflow`; if deploying from a non-default branch, add it: `gh api -X POST repos/<o>/<r>/environments/github-pages/deployment-branch-policies -f name=<branch> -f type=branch`. Push, then watch the run with `gh run watch <id> -R <o>/<r>`. Done when: the run succeeds, the live URL returns 200 with the page title, the MP4 returns `accept-ranges: bytes`, and a chapter click seeks in real Chrome.
10. **Report.** Live URL, what the video shows per scenario, the variance table for model-driven paths, and what is not fixed. Done when: the user can follow the link and the runbook alone.

## Pitfalls

- **Real runs only, and say how often.** When a model-driven path (an escalation, a switch) does not fire on a re-run, do not retry until it does. Explain why from the run outputs, keep earlier real captures with their commit, and publish the rate over all runs.
- **Stale browser state.** Apps that persist config in localStorage keep old values (an old default model) in the user's browser forever; a fresh capture profile will not reproduce it. Reproduce by seeding the old stored shape, and fix with a store version/migration plus a resync from the backend.
- **Timing.** Switch log panels to their live view BEFORE starting a run; completion modals open by themselves and cover the screen afterwards. Insert text once, screenshot, then send Enter separately (insert-plus-Enter helpers duplicate input when called twice).
- **Moving targets.** Under Vite dev, page code can import the app's live store modules (`await import("/<base>/src/.../store.ts")`) to select or reset; better still, add a real UI entry button and use it.
- **Approval prompts.** A one-shot `execute_code` screenshot loop can sit on an approval prompt the user never sees; run capture loops as shell scripts through `terminal`.
- **ffmpeg quirks.** Some builds lack `drawtext`/`subtitles`; `caption_video.py` draws with Pillow instead. Concat lists need absolute paths. Cap idle gaps (2.5 s) and say so on the page.
- **Testing the page.** Python's `http.server` has no Range support, so video seeking fails there; test over `file://` or the live site.
- **Publishing.** Pages serves `.md` as raw text: link the runbook by GitHub blob URL. Remove `max-width` caps on header text (early line breaks on wide screens). `gh run list` in a fork defaults to the upstream repo: pass `-R owner/repo`.

## Verification

- [ ] Runbook: every scenario has real screenshots, quoted live outputs, and a variance row if its path is model-driven
- [ ] Video: one continuous take, captions checked against sampled frames, edit rule stated
- [ ] Page: steps generated from `steps.json`, no unfilled placeholders, clean at 1871/1440/1280/390 px, seek works over `file://`
- [ ] No machine-local paths, secrets or env values in anything published
- [ ] Pages run green, live URL 200 with the title, MP4 `accept-ranges: bytes`, chapter seek works live
