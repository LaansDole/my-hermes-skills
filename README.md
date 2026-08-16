# my-hermes-skills

[![GitHub Pages](https://img.shields.io/badge/docs-GitHub%20Pages-blue?style=flat-square&logo=github)](https://laansdole.github.io/my-hermes-skills/)

Personal collection of [Hermes Agent](https://hermes-agent.nousresearch.com/) (Nous Research, MIT) skills, plugins, and bots. Each one is self-contained -- own README/SKILL.md, own setup, own scope. This file is just the index.

**Documentation site:** https://laansdole.github.io/my-hermes-skills/ — auto-generated from the `skills/**/SKILL.md` frontmatter by `scripts/generate_docs.py` on every push (via the GitHub Pages workflow). Delete or add a skill folder and the site updates itself; no manual HTML edits needed.

## Skills

Hermes auto-discovers skills from `~/.hermes/skills/`; this repo is the source of truth (symlink or copy each one in, per its own README.md).

- [`skills/covidence-screening/`](skills/covidence-screening/SKILL.md) -- Autonomously screens Covidence systematic-review references at the title & abstract stage, voting Yes/Maybe/No against your PICO criteria. Uses CDP to attach to your logged-in Chrome.
- [`skills/covidence-full-text-retrieval/`](skills/covidence-full-text-retrieval/SKILL.md) -- Companion to `covidence-screening` for the next stage: for each reference in Covidence's full-text review "Screen references" list, looks up an open-access PDF via Unpaywall/Semantic Scholar/arXiv (with an optional NotebookLM Discover last-resort web search) and uploads it, or leaves a note for manual follow-up if none is found. Never casts an Include/Exclude vote -- that stage stays fully manual. Design/plan docs: `docs/superpowers/specs/2026-07-25-covidence-notebooklm-fulltext-discovery-design.md`, `docs/superpowers/plans/2026-07-25-covidence-full-text-retrieval.md`.
- [`skills/slack-scan/`](skills/slack-scan/SKILL.md) -- On-demand Slack summary: ask Hermes directly in any chat to summarize today's activity -- every channel/DM it's in, or one named channel -- no cron job required. Calls the Slack Web API via `curl` + `SLACK_BOT_TOKEN`.
- [`skills/superpowers/`](skills/superpowers/superpowers-using-superpowers/SKILL.md) -- The [obra/superpowers](https://github.com/obra/superpowers) methodology converted to Hermes tool calls (derivative of [Labhund/hermes-superpowers](https://github.com/Labhund/hermes-superpowers)): 15 skills covering brainstorming, writing/executing plans, subagent-driven development, TDD, systematic debugging, code review, git worktrees, and verification-before-completion. Symlinked at `~/.hermes/skills/superpowers`; each skill is prefixed `superpowers-` so it never collides with native Hermes skills.
- [`skills/productivity/i-have-adhd/`](skills/productivity/i-have-adhd/SKILL.md) -- Output-shaping skill for a reader with ADHD: lead with the next action, number multi-step work, restate state across turns, suppress tangents, give specific time estimates, make wins visible. Vendored from [`ayghri/i-have-adhd`](https://github.com/ayghri/i-have-adhd) (MIT); symlinked at `~/.hermes/skills/productivity/i-have-adhd`. Activate by asking "use i-have-adhd mode"; turn off with "stop adhd mode".

## Bots

- [`slack-todo-bot/`](slack-todo-bot/README.md) -- Hermes gateway bot (Slack Socket Mode) that answers "summarize today's Slack" on demand and can layer on optional hourly Slack/Jira/GitHub cron scans + a 9 AM digest to your private Slack DM. No public URL needed.

## Plugins

Hermes auto-discovers plugins installed into `~/.hermes/plugins/` via `hermes plugins install <owner>/<repo>[/subdir]`.

- [`plugins/chrome-profiles/`](plugins/chrome-profiles/README.md) -- Switches the agent's browser tools between multiple Chrome, Brave, or Edge instances via CDP. Each profile needs its own dedicated `data_dir` -- it launches a browser process, it does not select a named profile out of an already-running shared browser. Install: `hermes plugins install LaansDole/my-hermes-skills/plugins/chrome-profiles`.

## Shared config

`.hermes-config/config-patch.yaml` -- example `approvals`/`browser` block for `~/.hermes/config.yaml` that auto-approves the browser tool calls a CDP-driven skill needs for unattended operation, plus pinning `browser.cloud_provider: local` (no cloud CDP provider). Referenced as a starting pattern by the browser-automation skills above; copy the relevant keys in, don't apply it wholesale if you don't want every browser call auto-approved.

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
|   |   |-- i-have-adhd/          # vendored from ayghri/i-have-adhd (MIT)
|   |   |-- pbcopy-word-delivery/
|   |   `-- session-handoff/
|   |-- slack-scan/
|   `-- superpowers/            # 15 skills, each in superpowers-<name>/
|       |-- superpowers-brainstorming/
|       |-- superpowers-writing-plans/
|       `-- ...
|-- scripts/
|   `-- generate_docs.py       # builds docs/index.html from skills/** frontmatter
|-- plugins/
|   `-- chrome-profiles/
|-- slack-todo-bot/
|-- docs/
|   `-- index.html            # GitHub Pages documentation site
`-- .github/
    `-- workflows/
        `-- pages.yml         # auto-deploys docs/ to GitHub Pages on push
```

## License

This repo's own contents (skill/plugin prose, design docs, config patch) are MIT-licensed -- see `LICENSE`. Hermes Agent itself is MIT-licensed by Nous Research.
