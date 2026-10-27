# Runbook structure (docs/<feature>/runbook/README.md)

Opening paragraph: what the runbook replays, that every screenshot and the video are real runs (date, commit, model), a link to the live demo page and the local `demo.html`, how the video was edited (idle gaps capped at N s, nothing else cut), and time estimates (start-up, per scenario).

1. **Prerequisites (once)**: installs; required env vars by NAME only (never values); which provider/model the demo uses and how the UI shows it; ports and why a non-default port is used.
2. **Start the servers**: exact commands per terminal, plus a health check (`curl` an endpoint, a UI status label).
3. **Load the app/workflow**: numbered clicks, including any required reload; how to close every overlay; a ROLE MAPPING table: on-screen element -> code node/type -> spec/proposal role.
4. **Run a case**: generic numbered steps using the app's own entry button (not clicking moving targets), and where to see the route taken (activity log etc.).
5. **One section per scenario**: input id and where it lives (eval set vs labelled demo set), screenshots in run order, then "What to look for" bullets quoting the live outputs (route, scores, thresholds, final answer, timing) and tying each to the spec element it demonstrates.
6. **Variance table for model-driven paths**: every real run of a scenario whose path is not deterministic (run, route, key numbers, outcome), and a one-line rate ("switched in 4 of 8 runs"). Never only the successful run.
7. **Coverage table**: spec element | visible in UI (yes / route only / stub / no) | where to see it. Be explicit about stubs and what only shows in logs or output files.
8. **Stop**: commands for foreground and background servers, and a check that the ports are free.
9. **Troubleshooting table**: symptom | fix, from problems actually hit while capturing (stale browser state, old backend code, overlays, blank WebGL capture).
10. **Findings (not fixed)**: defects the capture revealed, phrased as observations; mark causes as not investigated unless verified.

Style: no emojis; plain claims; every number traceable to a captured run; screenshots named `NN-<scenario>-<stage>.png` in run order; no machine-local absolute paths in anything published.
