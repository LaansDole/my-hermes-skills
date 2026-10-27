# my-hermes-skills

[![GitHub Pages](https://img.shields.io/badge/docs-GitHub%20Pages-blue?style=flat-square&logo=github)](https://laansdole.github.io/my-hermes-skills/)

Personal collection of [Hermes Agent](https://hermes-agent.nousresearch.com/) (Nous Research, MIT) skills, plugins, and bots. Each one is self-contained -- own README/SKILL.md, own setup, own scope. This file is just the index.

**Documentation site:** https://laansdole.github.io/my-hermes-skills/ — auto-generated from the `skills/**/SKILL.md` frontmatter by `scripts/generate_docs.py` on every push (via the GitHub Pages workflow). Delete or add a skill folder and the site updates itself; no manual HTML edits needed.

## Skills

Hermes auto-discovers skills from `~/.hermes/skills/`; this repo is the source of truth (symlink or copy each one in, per its own README.md).

- [`skills/covidence-screening/`](skills/covidence-screening/SKILL.md) -- Autonomously screens Covidence systematic-review references at the title & abstract stage, voting Yes/Maybe/No against your PICO criteria. Uses CDP to attach to your logged-in Chrome.
- [`skills/sci-hub-access/`](skills/sci-hub-access/SKILL.md) -- Retrieves paywalled paper full text via Sci-Hub mirrors (live-mirror discovery, Turnstile browser gate, direct CDN PDF fetch from `sci.bban.top`) and joins/uses Sci-Net (`sci-net.xyz`) for post-2022 papers: invite-code API, activation with `t.d` SCI tokens, registration. Unpaywall check first; the wallet transaction is always left to the user. Works from the isolated `work` browser profile (never the daily Brave).
- [`skills/covidence-full-text-retrieval/`](skills/covidence-full-text-retrieval/SKILL.md) -- Companion to `covidence-screening` for the next stage: for each reference in Covidence's full-text review "Screen references" list, looks up an open-access PDF via Unpaywall/Semantic Scholar/arXiv (with an optional NotebookLM Discover last-resort web search) and uploads it, or leaves a note for manual follow-up if none is found. Never casts an Include/Exclude vote -- that stage stays fully manual. Design/plan docs: `docs/superpowers/specs/2026-07-25-covidence-notebooklm-fulltext-discovery-design.md`, `docs/superpowers/plans/2026-07-25-covidence-full-text-retrieval.md`.
- [`skills/slack/slack-scan/`](skills/slack/slack-scan/SKILL.md) -- On-demand Slack summary: ask Hermes directly in any chat to summarize today's activity -- every channel/DM it's in, or one named channel -- no cron job required. Calls the Slack Web API via `curl` + `SLACK_BOT_TOKEN`.
- [`skills/slack/slack-mention-watch/`](skills/slack/slack-mention-watch/SKILL.md) -- Read-only Slack @mention watcher for any Hermes Slack gateway: ask "who pinged me?" (runs `watch_mentions.py --recent 24`), type `/pings` (a `quick_commands` exec, no LLM), or run it as an `every 5m` `--no-agent` cron job that DMs you each NEW mention and stays silent otherwise. Watches the owner of a `search:read` user token (covers every channel/DM you can see); falls back to bot-member channel history. GET-only 7-method allowlist; ignores its own alert DMs. Stdlib-only, unit-tested.
- [`skills/oh-my-pi/`](skills/oh-my-pi/SKILL.md) -- Troubleshoot/operate the Oh-My-Pi (omp) coding agent: `hub` coordination, task agents & model routing, two-tier review, OAuth fallback diagnosis, extension/plugin mechanics, and user-authored task agents (the `tldr` and `pr` roles). Reference + RPC smoke script included.
- [`skills/productivity/hermes-deepseek-cache/`](skills/productivity/hermes-deepseek-cache/SKILL.md) -- Hermes Agent's native DeepSeek prefix-cache feature (ported from ruanbw/pi-deepseek-cache): cache-hit telemetry, `/cache-stats` `/cache-graph` `/cache-reset`, prefix-break diagnostics, stable tool ordering, cache-friendly compaction. Active only for DeepSeek-family models, gated by `deepseek_cache.enabled` (default on).
- [`skills/superpowers/`](skills/superpowers/superpowers-using-superpowers/SKILL.md) -- `superpowers-using-superpowers` from the [obra/superpowers](https://github.com/obra/superpowers) methodology converted to Hermes tool calls (derivative of [Labhund/hermes-superpowers](https://github.com/Labhund/hermes-superpowers)): establishes how to find and load skills before responding. Symlinked at `~/.hermes/skills/superpowers`; prefixed `superpowers-` so it never collides with native Hermes skills.
- [`skills/productivity/i-have-adhd/`](skills/productivity/i-have-adhd/SKILL.md) -- Output-shaping skill for a reader with ADHD: lead with the next action, number multi-step work, restate state across turns, suppress tangents, give specific time estimates, make wins visible. Vendored from [`ayghri/i-have-adhd`](https://github.com/ayghri/i-have-adhd) (MIT); symlinked at `~/.hermes/skills/productivity/i-have-adhd`. Activate by asking "use i-have-adhd mode"; turn off with "stop adhd mode".
- [`skills/productivity/tldr/`](skills/productivity/tldr/SKILL.md) -- Triggered by "tldr" / "TL;DR" / "what changed": a one-line TL;DR, then a column-aligned (space-padded) `| Aspect | BEFORE | AFTER |` table with concrete facts per row, then open items. Terminal-friendly plain text; ~40-line cap. Symlinked at `~/.hermes/skills/productivity/tldr`.
- [`skills/productivity/camofox-browser/`](skills/productivity/camofox-browser/SKILL.md) -- Routes Hermes' browser tools through a local [Camofox](https://github.com/jo-inc/camofox-browser) server ([Camoufox](https://github.com/daijro/camoufox) anti-fingerprint Firefox) to get past Cloudflare/bot walls and keep site logins across sessions. Ships `install.sh` (server, `~/.camofox`, launchd job, Hermes config), a `camofox` helper (`status` / `start` / `login` / `headless`) for sign-in-once-then-headless logins, and the agent procedure for restarting the server. Symlinked at `~/.hermes/skills/productivity/camofox-browser`.
- [`skills/productivity/multi-repo-pr-review-merge-round/`](skills/productivity/multi-repo-pr-review-merge-round/SKILL.md) -- Spends a metered omp model budget (e.g. Command Code) before it expires. Hermes coordinates and `omp -p` agents do the work: they review, fix and push the user's open PRs across repos, then finish leftover worktrees. Hermes checks each result itself, merges stacked PRs in order, stops everything when the usage window runs out, resumes from continuation briefs after the reset, and refills the queue with worktree, post-merge and coverage audits until the month ends. Ships `inventory.sh` (PRs on origin, not the fork's upstream, plus worktree state), `lane.sh` (serial job lane with 429/usage-limit detection), a zsh `watchdog.sh`, `last-texts.py` (progress from omp transcripts) and a review-brief template. Symlinked at `~/.hermes/skills/productivity/multi-repo-pr-review-merge-round`.
- [`skills/productivity/demo-runbook/`](skills/productivity/demo-runbook/SKILL.md) -- Turns a working feature into a demo package from REAL runs: a markdown runbook with live screenshots, one continuous captioned screencast of the runbook journey (CDP screencast, captions keyed to the run's own timestamps and outputs, idle gaps capped), a `demo.html` page with clickable runbook steps, and a GitHub Pages deploy of that page. Ships `record_screencast.py`, `caption_video.py` (Pillow captions, ffmpeg concat with real frame durations), `build_demo_page.py`, `shots_widths.py` (line-break check), `cdp.py`, a journey-recorder template and a Pages workflow template; the worked example is the DynaClinic 3D demo ([live](https://laansdole.github.io/multi-agent-simulation/)). Unit-tested. Symlinked at `~/.hermes/skills/productivity/demo-runbook`.

## Plugins

Hermes loads plugins from `~/.hermes/plugins/`; symlink each one in and run `hermes plugins enable <name>` (see its README.md).

- [`plugins/camofox-web/`](plugins/camofox-web/README.md) -- Hermes `web_search` + `web_extract` provider backed by the local Camofox server (see `skills/productivity/camofox-browser/`): Camoufox opens DuckDuckGo (Bing fallback) and decodes redirect links to real URLs (Camofox is a browser, not a search index, so it searches by loading an engine's results page; no external API); extract renders each page, waits out Cloudflare interstitials and returns the main text. Replaces SearXNG. Enable: `ln -s` into `~/.hermes/plugins/`, `hermes plugins enable camofox-web`, `hermes config set web.backend camofox`.
- [`plugins/refusal-fallback-alert/`](plugins/refusal-fallback-alert/README.md) -- Logs (`~/.hermes/logs/refusal-fallback.log`) and macOS-notifies whenever an Anthropic safety classifier blocks a turn (`Refusal (cyber)` etc.) in the main agent or any subagent. Observe-only `api_request_error` hook; pair with `fallback_providers: claude-opus-4-8` + `reasoning_overrides: xhigh` so Hermes retries the refused turn on Opus 4.8.

## Bots

- [`slack-todo-bot/`](slack-todo-bot/README.md) -- Hermes gateway bot (Slack Socket Mode) that answers "summarize today's Slack" on demand and can layer on optional hourly Slack/Jira/GitHub cron scans + a 9 AM digest to your private Slack DM. No public URL needed.

## Shared config

`.hermes-config/config-patch.yaml` -- example `approvals`/`browser` block for `~/.hermes/config.yaml` that auto-approves the browser tool calls a CDP-driven skill needs for unattended operation, plus pinning `browser.cloud_provider: local` (no cloud CDP provider). Referenced as a starting pattern by the browser-automation skills above; copy the relevant keys in, don't apply it wholesale if you don't want every browser call auto-approved.

## Companion repo

- [`LaansDole/omp-preset`](https://github.com/LaansDole/omp-preset) -- Portable Oh-My-Pi (omp) harness. Not a fork and not a Hermes skill -- it's the source-of-truth dotfiles for the `oh-my-pi` skill's subject: `config.yml`, custom task agents (`reviewer`, `reviewer-deep`, `tldr`, `pr`), `WATCHDOG.md`, a plugin install manifest, the `writing-pr-descriptions` skill, and a sandbox-verified `bootstrap.sh`. Clone it and run `./bootstrap.sh` to reproduce this agent harness on a new machine.

## Repository layout

```
.
|-- README.md                 # this file
|-- LICENSE
|-- .hermes-config/
|   `-- config-patch.yaml     # example approvals + browser config patch
|-- skills/
|   |-- covidence-screening/
|   |-- covidence-full-text-retrieval/
|   |   `-- covidence-full-text-review/
|   |-- productivity/
|   |   |-- camofox-browser/      # Camoufox stealth browser server + logins
|   |   |-- demo-runbook/         # real-run runbook + captioned video + Pages demo
|   |   |-- i-have-adhd/          # vendored from ayghri/i-have-adhd (MIT)
|   |   `-- tldr/                 # TL;DR + aligned before/after table
|   |-- slack/
|   |   |-- slack-scan/
|   |   `-- slack-mention-watch/  # cron @mention watcher (read-only)
|   |-- oh-my-pi/
|   `-- superpowers/
|       `-- superpowers-using-superpowers/
|-- plugins/
|   |-- camofox-web/              # web_search/web_extract via Camofox
|   `-- refusal-fallback-alert/   # Hermes plugin: alert on classifier refusals
|-- scripts/
|   |-- generate_docs.py       # builds docs/ (site, reports pages) + skills.json
|   `-- verify_docs.py
|-- reports/
|   `-- YYYY-MM/YYYY-MM-DD-<slug>.md  # report sources (writing-reports skill)
|-- benchmarks/
|   `-- <name>/               # reproducible harnesses + raw data behind reports
|-- slack-todo-bot/
|-- tests/
|-- skills.json               # skill manifest (CI-refreshed)
|-- docs/                     # GitHub Pages site
|   |-- index.html, reports.html, daily-news.html
|   `-- reports/              # generated from reports/, gitignored, built in CI
`-- .github/
    `-- workflows/
        |-- pages.yml         # regenerates + deploys docs/ on push
        `-- sync-manifest.yml # refreshes skills.json
```

## License

This repo's own contents (skill/plugin prose, design docs, config patch) are MIT-licensed -- see `LICENSE`. Hermes Agent itself is MIT-licensed by Nous Research.
