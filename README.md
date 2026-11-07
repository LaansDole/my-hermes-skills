# my-hermes-skills

[![GitHub Pages](https://img.shields.io/badge/docs-GitHub%20Pages-blue?style=flat-square&logo=github)](https://laansdole.github.io/my-hermes-skills/)

[Hermes Agent](https://hermes-agent.nousresearch.com/) skills, plugins and bots I use day to day, plus the research reports behind them.

**Browse the catalog: https://laansdole.github.io/my-hermes-skills/** - every skill with its full description, version, tags and links, and the [reports](https://laansdole.github.io/my-hermes-skills/reports.html). The site is generated from `skills/**/SKILL.md` and `reports/**/*.md` on every push; never edit `docs/` by hand.

## Install

1. Clone this repo, then symlink (or copy) a skill folder into `~/.hermes/skills/`, e.g. `ln -s "$PWD/skills/productivity/tldr" ~/.hermes/skills/productivity/tldr`.
2. Follow the skill's own `README.md` for env vars, browser profiles or criteria files.
3. Start a new Hermes session; skills are auto-discovered.

Browser-automation skills may need the auto-approvals in [`.hermes-config/config-patch.yaml`](.hermes-config/config-patch.yaml); merge only the keys you want.

## Skills

| Section | Skills |
|---|---|
| Research | [covidence-screening](skills/covidence-screening/SKILL.md), [covidence-full-text-retrieval](skills/covidence-full-text-retrieval/SKILL.md) + [covidence-full-text-review](skills/covidence-full-text-retrieval/covidence-full-text-review/SKILL.md), [sci-hub-access](skills/sci-hub-access/SKILL.md) |
| Productivity | [auditing-worktrees](skills/productivity/auditing-worktrees/SKILL.md), [camofox-browser](skills/productivity/camofox-browser/SKILL.md), [demo-runbook](skills/productivity/demo-runbook/SKILL.md), [hermes-deepseek-cache](skills/productivity/hermes-deepseek-cache/SKILL.md), [i-have-adhd](skills/productivity/i-have-adhd/SKILL.md), [memory-ui](skills/productivity/memory-ui/SKILL.md), [multi-repo-pr-review-merge-round](skills/productivity/multi-repo-pr-review-merge-round/SKILL.md), [oh-my-ghostty](skills/productivity/oh-my-ghostty/SKILL.md), [tldr](skills/productivity/tldr/SKILL.md), [writing-reports](skills/productivity/writing-reports/SKILL.md) |
| Coding Agents | [oh-my-pi](skills/oh-my-pi/SKILL.md) |
| Design | [impeccable](skills/creative/impeccable/README.md) |
| Slack | [slack-mention-watch](skills/slack/slack-mention-watch/SKILL.md), [slack-scan](skills/slack/slack-scan/SKILL.md) |
| Other | [ilearning-autoadvance](skills/ilearning-autoadvance/SKILL.md), [superpowers-using-superpowers](skills/superpowers/superpowers-using-superpowers/SKILL.md) |

Vendored third-party skills keep their upstream license: [impeccable](skills/creative/impeccable/README.md) (pbakaus/impeccable, Apache 2.0), [i-have-adhd](skills/productivity/i-have-adhd/SKILL.md) (ayghri/i-have-adhd, MIT), and superpowers (derived from obra/superpowers via Labhund/hermes-superpowers).

### Changelogs and releases

Each versioned skill keeps a `CHANGELOG.md` next to its `SKILL.md`. When you change a skill, bump `version:` in its frontmatter and add a matching `## [x.y.z] - YYYY-MM-DD` section. On push to `main`, [`release.yml`](.github/workflows/release.yml) runs `scripts/release_notes.py`, collects the sections for every bumped skill and publishes one GitHub Release (`skills-YYYY-MM-DD`, `.2`, `.3` … for later pushes that day). A bump without a matching section fails the workflow; check locally with `python3 scripts/release_notes.py origin/main`. Every dated section across all skills is also listed, newest first, on the site's [Changelog](https://laansdole.github.io/my-hermes-skills/changelog.html) page.

Publishing a Release by hand (GitHub UI or `gh release create`) also runs [`pages.yml`](.github/workflows/pages.yml). It checks every skill bumped since the previous tag for a changelog section and fails if one is missing. If you left the Release body empty, it fills it with those sections. Then it redeploys the site from `main`, including the Changelog page. Releases that `release.yml` creates don't trigger it, because GitHub never starts workflows from `GITHUB_TOKEN` actions. Nothing writes `CHANGELOG.md`: you edit it.

## Plugins

Symlink into `~/.hermes/plugins/`, then `hermes plugins enable <name>`.

- [camofox-web](plugins/camofox-web/README.md) - `web_search` / `web_extract` through the local Camofox browser (pairs with `camofox-browser`).
- [refusal-fallback-alert](plugins/refusal-fallback-alert/README.md) - logs and notifies when a safety classifier blocks a turn.

## Bots

- [slack-todo-bot](slack-todo-bot/README.md) - Slack Socket Mode gateway bot: on-demand "summarize today's Slack", optional cron scans and a morning digest.

## Companion repo

- [LaansDole/omp-preset](https://github.com/LaansDole/omp-preset) - portable Oh-My-Pi harness (config, task agents, bootstrap) behind the `oh-my-pi` skill.

## Repository layout

```
skills/<section>/<skill>/   SKILL.md + README.md + scripts per skill
plugins/  slack-todo-bot/   Hermes plugins and the Slack bot
reports/YYYY-MM/*.md        report sources (writing-reports skill)
benchmarks/                 harnesses and raw data behind reports
scripts/generate_docs.py    builds docs/ and skills.json; verify_docs.py checks it
docs/                       GitHub Pages output (docs/reports/ built in CI)
PRODUCT.md, DESIGN.md       site product context and design system (Impeccable)
tests/                      unit tests
```

## License

MIT for this repo's own contents (see [LICENSE](LICENSE)); vendored skills keep their upstream licenses.
