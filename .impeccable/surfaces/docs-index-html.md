---
version: 1
slug: "docs-index-html"
primary_target: "docs/index.html"
related_targets: ["docs/reports.html","docs/daily-news.html"]
---

## Scope

All generated pages of the my-hermes-skills site: skills catalog (docs/index.html), reports catalog (docs/reports.html), compatibility redirect (docs/daily-news.html), report reader pages (docs/reports/YYYY-MM/<slug>.html). Mode: Read. Built code-led in scripts/generate_docs.py.

## Audience and job

The owner reviewing changes after each push; Hermes users finding a skill, understanding it, and opening its SKILL.md or source; readers of long-form reports.

## Direction contract

THESIS: The catalog is a printed reference wall chart: every skill is a numbered element cell with a two-letter symbol, grouped into colour-blocked families, keyed to a handbook entry. Refuses the GitHub-dark card grid with emoji section headers.

OWN-WORLD: Chart-paper ground (light) / carbon-ink ground (dark), near-black ink, flat process-colour family blocks (amber Research, vermilion Productivity, cobalt Coding Agents, violet Design, green Slack, warm grey Unfiled). Heavy grotesk for symbols, masthead and labels; reading serif for running text; mono only for paths and commands. 3px ink rules, square corners, no shadows, no rounded cards.

STORY: The reader sees the whole toolkit at once as one chart, reads the key, opens a cell's handbook entry for description, tags, version and links, and finds reports as a dated table of data. Raises: ruled foot band (exhibition); A-Z index keyed to cell numbers (star atlas); one baseline unit (cracktro); family is mark plus word, never hue alone (cutting bench); colour only in the frame, report column achromatic (cloud edge); small-caps dates and versions (provenance).

FIRST VIEWPORT: Masthead with eyebrow line and the name, nav (Chart, Entries, Index, Reports, GitHub, theme). Below: the chart of all cells in family blocks filling the width at left, the key with counts and a two-line how-to-read plus install line at right. A ruled foot band closes the page.

FORM: Reference wall chart, position 7 of the ordered list. seed:b12cd4f889c5acfa

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

## Constraints

Light/dark toggle (follows OS until overridden, persisted). Full-width text: no narrow 65-75ch measure (owner preference). Every skill one click from source. Routes may change if needed, but keep existing URLs working.
