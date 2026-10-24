# Mermaid vs Reladraw for README diagrams

- **Date:** 2026-10-24
- **Scope:** Whether Reladraw (Show HN, ~2026-09-27) should replace Mermaid for diagrams in GitHub READMEs and docs.
- **Method:** Reladraw README, SYNTAX.md and Show HN thread; GitHub Docs "Creating diagrams"; Mermaid intro docs - all fetched 2026-10-24. npm registry metadata queried 2026-10-24. One diagram rendered locally with both CLIs (reladraw 0.19.0, @mermaid-js/mermaid-cli 12.0.0 / mermaid 12.x) on macOS, Node via npx; timings are 3 warm runs (measured).

---

## Verdict

Keep Mermaid for anything that must render inline in a GitHub README, issue or PR; use Reladraw only for hand-placed architecture or flow diagrams that you are willing to render to SVG and commit (or show on a Pages site). GitHub renders only four fenced diagram syntaxes (mermaid, geojson, topojson, stl), so a `reladraw` code block shows as plain text. Reladraw is not a Mermaid replacement in general: it is one generic "boxes and lines with relative placement" language at v0.19.0 with syntax still changing, while Mermaid is a mature multi-diagram-type tool with native rendering on GitHub.

---

## Comparison

| Dimension | Mermaid | Reladraw | Source |
| --- | --- | --- | --- |
| Core idea | Declare nodes/edges; layout engine decides positions | Declare where things go relative to each other; tool never moves anything | Mermaid docs; Reladraw README |
| Renders natively in GitHub markdown | Yes (```` ```mermaid ```` fence; Issues, PRs, wikis, Discussions, .md files) | No - must pre-render SVG and embed as image | GitHub Docs |
| Diagram types | Many dedicated types: flowchart, sequence, class, state, Gantt, ER, git graph, user journey, quadrant, XY chart, use case (beta) and more | One generic language (nodes, edges, points, regions, bundles); flowchart shapes built in; no dedicated sequence/Gantt/class syntax | Mermaid intro; Reladraw SYNTAX.md |
| Layout control | Limited; direction, subgraphs, layout engine choice (e.g. ELK) | Full relative control: `right of`, `below`, `even with`, gaps, fractions, waypoints | SYNTAX.md |
| Problem reporting | Parse errors; layout surprises are silent | Draws exactly what is written, prints one-line findings (line through box, overlapping text); `reladraw check`; contradictions are errors | Reladraw README; HN author replies |
| Edge routing | Automatic | No auto-routing around obstacles; edges sharing a side space themselves; manual waypoints | HN author reply |
| Maturity | v12.2.0 (npm, 2026-10-13); long-running project, MIT | v0.19.0 (npm, 2026-10-23); "language is changing frequently"; 0.17.0 had large breaking renames; Apache-2.0; no PRs accepted (issues only) | npm; Reladraw README/SYNTAX.md |
| Web embedding | `mermaid` JS from CDN | One script, `<reladraw-diagram>` custom element | both docs |
| Agent tooling | Widely known to LLMs | Ships an agent skill: `npx skills add reladraw/reladraw -g` | Reladraw README |
| Editor support | Many integrations (Obsidian, GitLab, Notion, VS Code) | Community VS Code extension for markdown preview (volkanunsal/relative-diagrams-vscode) | HN thread |

### Local render test (measured, 2026-10-24)

Same diagram in both: a "Web app" container holding Interface above API, API -> Database labelled "queries".

| Metric | Mermaid (mmdc 12.0.0) | Reladraw 0.19.0 |
| ---: | ---: | ---: |
| Warm render time (3 runs) | 0.59-0.64 s | 0.17-0.19 s |
| Cold first render | 2.39 s | 0.66 s |
| Output SVG size | 197,763 bytes | 1,632 bytes |
| Installed size | mermaid 125 MB + @mermaid-js 48 MB | 1.1 MB, zero runtime deps |
| Source lines | 7 | 5 |

Both rendered correctly. Mermaid's result placed Interface above API by its own layout choice; Reladraw placed it because the file says `below app.ui`. SVG size difference is mostly Mermaid's embedded styles/fonts (ASSUMPTION: not inspected byte-by-byte). Times include `npx` startup.

---

## Findings

1. The README use case decides it: GitHub's diagram support is limited to mermaid, geoJSON, topoJSON and ASCII STL (GitHub Docs), so Reladraw needs a build step (`reladraw render x.reladraw -o x.svg`) plus a committed or CI-generated SVG.
2. Reladraw's own README frames it as filling the gap between auto-layout languages (Mermaid, Graphviz, D2) and absolute-placement tools (draw.io, Excalidraw), not as a full Mermaid replacement.
3. Where Mermaid is weak - flowcharts and architecture diagrams where "position is king" (HN commenter) - Reladraw is the stronger tool. Where Mermaid is strong - sequence diagrams, Gantt, class/ER - Reladraw has no dedicated syntax.
4. Reladraw is deterministic and loud: it never silently relayouts, and conflicting placements are errors naming the clashing statements (HN author). That suits agent-edited diagrams, since the agent gets actionable warnings.
5. Stability risk is real: the author says the language "is changing frequently"; diagrams written today may need edits after upgrades. Pin the npm version if you adopt it.
6. HN reception: 415 points, 119 comments (2026-10-24 snapshot). Alternatives raised in the thread: D2 with the TALA layout engine (now open source), PlantUML, TikZ positioning, schemdraw.

### Practical options for the README / skills site

- **Stay on Mermaid** in README files (zero setup, renders everywhere).
- **Hybrid:** keep `.reladraw` sources in the repo, render SVG via a pre-commit hook or GitHub Action, embed `![diagram](docs/arch.svg)` in the README.
- **GitHub Pages only:** the `<reladraw-diagram>` element works on a self-hosted page (e.g. laansdole.github.io/my-hermes-skills); it will not work inside a GitHub-rendered README, which strips scripts (ASSUMPTION: standard GitHub markdown sanitization; not tested here).

---

## Caveats

- Feature claims about Reladraw come from its own README/SYNTAX.md and author comments on HN (single-party source); only rendering of one small diagram was verified locally.
- Timing is one machine, one tiny diagram; not representative of large diagrams.
- Reladraw is changing fast (v0.19.0 published 2026-10-23); re-check before adopting.

---

## References

- reladraw/reladraw (GitHub README, v0.19.0): <https://github.com/reladraw/reladraw>
- reladraw SYNTAX.md (syntax reference 0.19.0): <https://github.com/reladraw/reladraw/blob/main/SYNTAX.md>
- Show HN: Reladraw - A diagram language where you decide where to place things (Hacker News, ~2026-09-27): <https://news.ycombinator.com/item?id=49858513>
- Creating diagrams (GitHub Docs): <https://docs.github.com/en/get-started/writing-on-github/working-with-advanced-formatting/creating-diagrams>
- About Mermaid (Mermaid docs): <https://mermaid.js.org/intro/>
- relative-diagrams-vscode (community VS Code extension): [unfetched - <https://github.com/volkanunsal/relative-diagrams-vscode/>]
- D2 TALA layout engine: [unfetched - <https://d2lang.com/tour/tala/>]
