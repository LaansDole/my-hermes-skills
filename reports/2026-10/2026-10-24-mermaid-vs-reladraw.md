# Should Reladraw replace Mermaid for README diagrams?

- **Date:** 2026-10-24
- **Report type:** Evidence review
- **Keywords:** Mermaid, Reladraw, diagrams as code, GitHub markdown, SVG rendering
- **Data collected:** Reladraw README, SYNTAX.md and Show HN thread, GitHub Docs and Mermaid docs fetched 2026-10-24; npm registry metadata queried 2026-10-24; local render test run 2026-10-24.

## Abstract

**Background.** Reladraw, shown on Hacker News around 2026-09-27 [1], is a diagram language in which the author places elements relative to each other instead of leaving layout to an engine. Mermaid is the usual choice for diagrams in GitHub READMEs and docs.
**Objective.** To decide whether Reladraw should replace Mermaid for diagrams in GitHub READMEs and docs.
**Methods.** GitHub's diagram documentation [2], the Reladraw README [3], Mermaid's introduction [4] and Reladraw's syntax reference [5] were read alongside the Show HN thread [1], an editor extension [6] and an alternative raised there [7]; npm metadata was queried. One diagram was rendered locally with both CLIs, timing 3 warm runs.
**Results.** GitHub renders only four fenced diagram syntaxes (mermaid, geojson, topojson, stl) [2], so a `reladraw` block shows as plain text. Reladraw is at v0.19.0 with its syntax still changing [3]. Locally, Reladraw rendered in 0.17-0.19 s versus 0.59-0.64 s for Mermaid and produced a 1,632-byte SVG versus 197,763 bytes (measured).
**Conclusions.** Keep Mermaid for anything that must render inline in a GitHub README, issue or PR; use Reladraw only for hand-placed architecture or flow diagrams that you are willing to render to SVG and commit, or show on a Pages site.

## 1. Introduction

Diagrams in this repository's READMEs and skills site are written in Mermaid, which GitHub renders natively. Reladraw proposes a different model: declare where things go relative to each other, and the tool never moves anything [3]. Its own README frames it as filling the gap between auto-layout languages (Mermaid, Graphviz, D2) and absolute-placement tools (draw.io, Excalidraw), not as a full Mermaid replacement [3].

- **RQ1.** Can Reladraw diagrams render inline on GitHub?
- **RQ2.** How do the two tools compare in diagram coverage, layout control, error reporting and maturity?
- **RQ3.** How do they compare in practice on a small diagram?

## 2. Methods

### 2.1 Sources and search strategy

Fetched 2026-10-24: the Reladraw Show HN thread [1], GitHub Docs "Creating diagrams" [2], the Reladraw README [3], the Mermaid intro docs [4] and Reladraw SYNTAX.md [5]. The VS Code extension [6] and the TALA layout engine [7] were followed from the HN thread. npm registry metadata (versions, publish dates) was queried on 2026-10-24; no reference URL was recorded for it.

### 2.2 Evidence classification

- **Vendor-reported:** Reladraw README and SYNTAX.md [3, 5], Mermaid docs [4], GitHub Docs [2], author replies on HN [1].
- **Community report:** HN commenters [1].
- **Measured:** the local render test (Table 2).
- **Registry metadata:** npm versions and dates.

### 2.3 Experimental setup

One diagram was rendered locally with both CLIs (reladraw 0.19.0, @mermaid-js/mermaid-cli 12.0.0 / mermaid 12.x) on macOS, Node via npx; timings are 3 warm runs plus one cold first render. Diagram: a "Web app" container holding Interface above API, API -> Database labelled "queries". Times include `npx` startup. Mac model and Node version were not recorded.

### 2.4 Analysis

Descriptive comparison; ranges are min-max over the 3 warm runs.

## 3. Results

### 3.1 Feature comparison (RQ1, RQ2)

Table 1. Mermaid and Reladraw compared (vendor-reported unless marked).

| Dimension | Mermaid | Reladraw | Source |
| --- | --- | --- | --- |
| Core idea | Declare nodes/edges; layout engine decides positions | Declare where things go relative to each other; tool never moves anything | Mermaid docs [4]; Reladraw README [3] |
| Renders natively in GitHub markdown | Yes (```` ```mermaid ```` fence; Issues, PRs, wikis, Discussions, .md files) | No - must pre-render SVG and embed as image | GitHub Docs [2] |
| Diagram types | Many dedicated types: flowchart, sequence, class, state, Gantt, ER, git graph, user journey, quadrant, XY chart, use case (beta) and more | One generic language (nodes, edges, points, regions, bundles); flowchart shapes built in; no dedicated sequence/Gantt/class syntax | Mermaid intro [4]; Reladraw SYNTAX.md [5] |
| Layout control | Limited; direction, subgraphs, layout engine choice (e.g. ELK) | Full relative control: `right of`, `below`, `even with`, gaps, fractions, waypoints | SYNTAX.md [5] |
| Problem reporting | Parse errors; layout surprises are silent | Draws exactly what is written, prints one-line findings (line through box, overlapping text); `reladraw check`; contradictions are errors | Reladraw README [3]; HN author replies [1] |
| Edge routing | Automatic | No auto-routing around obstacles; edges sharing a side space themselves; manual waypoints | HN author reply [1] |
| Maturity | v12.2.0 (npm, 2026-10-13); long-running project, MIT | v0.19.0 (npm, 2026-10-23); "language is changing frequently"; 0.17.0 had large breaking renames; Apache-2.0; no PRs accepted (issues only) | npm; Reladraw README/SYNTAX.md [3, 5] |
| Web embedding | `mermaid` JS from CDN | One script, `<reladraw-diagram>` custom element | both docs [3, 4] |
| Agent tooling | Widely known to LLMs | Ships an agent skill: `npx skills add reladraw/reladraw -g` | Reladraw README [3] |
| Editor support | Many integrations (Obsidian, GitLab, Notion, VS Code) | Community VS Code extension for markdown preview (volkanunsal/relative-diagrams-vscode) [6] | HN thread [1] |

- GitHub's diagram support is limited to mermaid, geoJSON, topoJSON and ASCII STL [2], so Reladraw needs a build step (`reladraw render x.reladraw -o x.svg`) plus a committed or CI-generated SVG.
- Reladraw never silently relayouts, and conflicting placements are errors naming the clashing statements (HN author) [1].
- The author says the language "is changing frequently" [3].
- HN reception: 415 points, 119 comments (2026-10-24 snapshot) [1]. Alternatives raised in the thread: D2 with the TALA layout engine [7] (now open source), PlantUML, TikZ positioning, schemdraw. One commenter described flowcharts and architecture diagrams as cases where "position is king" [1].

### 3.2 Local render test (RQ3)

Table 2. Local render test, 2026-10-24 (measured).

| Metric | Mermaid (mmdc 12.0.0) | Reladraw 0.19.0 |
| ---: | ---: | ---: |
| Warm render time (3 runs) | 0.59-0.64 s | 0.17-0.19 s |
| Cold first render | 2.39 s | 0.66 s |
| Output SVG size | 197,763 bytes | 1,632 bytes |
| Installed size | mermaid 125 MB + @mermaid-js 48 MB | 1.1 MB, zero runtime deps |
| Source lines | 7 | 5 |

Both rendered correctly. Mermaid's result placed Interface above API by its own layout choice; Reladraw placed it because the file says `below app.ui`.

## 4. Discussion

### 4.1 Principal findings

RQ1 decides the README case: a `reladraw` block cannot render inline on GitHub [2]. RQ2: Reladraw is not a Mermaid replacement in general. It is one generic "boxes and lines with relative placement" language at v0.19.0 with syntax still changing [3], while Mermaid is a mature multi-diagram-type tool [4] with native rendering on GitHub [2]. Where Mermaid is weak, in flowcharts and architecture diagrams where position matters most [1], Reladraw is the stronger tool; where Mermaid is strong (sequence diagrams, Gantt, class/ER), Reladraw has no dedicated syntax. Reladraw is deterministic and loud, which suits agent-edited diagrams because the agent gets actionable warnings. RQ3: on one small diagram Reladraw was faster, far smaller in output and install size, and equally correct. The SVG size difference is mostly Mermaid's embedded styles/fonts (ASSUMPTION: not inspected byte-by-byte).

### 4.2 Comparison with prior work

HN commenters proposed other placement-aware options, notably D2 with TALA [7]; these were not evaluated here.

### 4.3 Practical implications

- **Stay on Mermaid** in README files (zero setup, renders everywhere).
- **Hybrid:** keep `.reladraw` sources in the repo, render SVG via a pre-commit hook or GitHub Action, embed `![diagram](docs/arch.svg)` in the README.
- **GitHub Pages only:** the `<reladraw-diagram>` element works on a self-hosted page (e.g. laansdole.github.io/my-hermes-skills); it will not work inside a GitHub-rendered README, which strips scripts (ASSUMPTION: standard GitHub markdown sanitization; not tested here).
- **If adopting Reladraw:** the stability risk is real, since diagrams written today may need edits after upgrades; pin the npm version.

## 5. Limitations

- **Single-party claims.** Feature claims about Reladraw come from its own README/SYNTAX.md and author comments on HN [1, 3, 5]; only rendering of one small diagram was verified locally.
- **Tiny benchmark.** Timing is one machine, one tiny diagram, 3 warm runs; not representative of large diagrams. Times include `npx` startup.
- **Staleness.** Reladraw is changing fast (v0.19.0 published 2026-10-23); re-check before adopting.
- **Untested assumptions.** SVG size attribution and script stripping in GitHub READMEs were not tested.

## 6. Conclusion

Mermaid should stay as the README diagram tool because GitHub renders it inline and does not render Reladraw. Reladraw is a better fit for hand-placed architecture and flow diagrams when rendering to a committed SVG or a Pages site is acceptable, with its version pinned while the language is still changing.

## References

[1] Show HN: Reladraw - A diagram language where you decide where to place things (Hacker News, ~2026-09-27): <https://news.ycombinator.com/item?id=49858513>
[2] Creating diagrams (GitHub Docs): <https://docs.github.com/en/get-started/writing-on-github/working-with-advanced-formatting/creating-diagrams>
[3] reladraw/reladraw (GitHub README, v0.19.0): <https://github.com/reladraw/reladraw>
[4] About Mermaid (Mermaid docs): <https://mermaid.js.org/intro/>
[5] reladraw SYNTAX.md (syntax reference 0.19.0): <https://github.com/reladraw/reladraw/blob/main/SYNTAX.md>
[6] relative-diagrams-vscode, render Reladraw diagrams in the VS Code Markdown preview (Volkan Unsal, GitHub): <https://github.com/volkanunsal/relative-diagrams-vscode/>
[7] TALA layout engine (D2 Documentation): <https://d2lang.com/tour/tala/>
