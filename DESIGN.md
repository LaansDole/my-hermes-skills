---
name: my-hermes-skills
description: A public Hermes Agent toolkit printed as a reference wall chart, with a ledger of dated research reports.
colors:
  chart-paper: "#f6f4ee"
  carbon-ground: "#141416"
  press-ink: "#17171b"
  bone-ink: "#ece9e0"
  pencil-grey: "#5d5a52"
  ash-grey: "#9a968b"
  paper-hairline: "#cfcabd"
  carbon-hairline: "#38373a"
  paper-tint: "#ebe7dc"
  carbon-tint: "#1e1e21"
  research-amber: "#e8a33a"
  productivity-vermilion: "#e2643f"
  coding-cobalt: "#3a63b8"
  design-violet: "#7a52b3"
  slack-green: "#4f9e63"
  unfiled-stone: "#d8d4c8"
  unfiled-stone-dark: "#8f8a7e"
  fill-white: "#ffffff"
typography:
  display:
    fontFamily: "Archivo, Helvetica Neue, Arial, sans-serif"
    fontSize: "88px"
    fontWeight: 900
    lineHeight: "88px"
    letterSpacing: "-0.035em"
  symbol:
    fontFamily: "Archivo, Helvetica Neue, Arial, sans-serif"
    fontSize: "48px"
    fontWeight: 900
    lineHeight: 1
    letterSpacing: "-0.02em"
  headline:
    fontFamily: "Archivo, Helvetica Neue, Arial, sans-serif"
    fontSize: "40px"
    fontWeight: 800
    lineHeight: "44px"
    letterSpacing: "-0.02em"
  title:
    fontFamily: "Archivo, Helvetica Neue, Arial, sans-serif"
    fontSize: "20px"
    fontWeight: 800
    lineHeight: "24px"
  headline-reader-mobile:
    fontFamily: "Archivo, Helvetica Neue, Arial, sans-serif"
    fontSize: "24px"
    fontWeight: 800
    lineHeight: "28px"
  body:
    fontFamily: "Source Serif 4, Georgia, serif"
    fontSize: "17px"
    fontWeight: 400
    lineHeight: "28px"
  body-reader:
    fontFamily: "Source Serif 4, Georgia, serif"
    fontSize: "18px"
    fontWeight: 400
    lineHeight: "32px"
  label:
    fontFamily: "Archivo, Helvetica Neue, Arial, sans-serif"
    fontSize: "13px"
    fontWeight: 800
    lineHeight: "20px"
    letterSpacing: "0.08em"
  cell-meta:
    fontFamily: "Archivo, Helvetica Neue, Arial, sans-serif"
    fontSize: "12px"
    fontWeight: 600
    lineHeight: "16px"
    fontFeature: "tnum"
  display-mobile:
    fontFamily: "Archivo, Helvetica Neue, Arial, sans-serif"
    fontSize: "64px"
    fontWeight: 900
    lineHeight: "64px"
  display-compact:
    fontFamily: "Archivo, Helvetica Neue, Arial, sans-serif"
    fontSize: "32px"
    fontWeight: 900
    lineHeight: "32px"
  family-label:
    fontFamily: "Archivo, Helvetica Neue, Arial, sans-serif"
    fontSize: "16px"
    fontWeight: 800
    lineHeight: "20px"
    letterSpacing: "0.04em"
  note:
    fontFamily: "Source Serif 4, Georgia, serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: "24px"
  meta:
    fontFamily: "Archivo, Helvetica Neue, Arial, sans-serif"
    fontSize: "14px"
    fontWeight: 600
    lineHeight: "20px"
  cell-meta-mobile:
    fontFamily: "Archivo, Helvetica Neue, Arial, sans-serif"
    fontSize: "11px"
    fontWeight: 600
    lineHeight: "12px"
    fontFeature: "tnum"
  mono:
    fontFamily: "JetBrains Mono, ui-monospace, Menlo, monospace"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: "20px"
rounded:
  none: "0px"
spacing:
  unit: "4px"
  xs: "8px"
  sm: "16px"
  md: "24px"
  lg: "40px"
  page: "48px"
  page-mobile: "16px"
  section: "96px"
components:
  element-cell:
    textColor: "{colors.press-ink}"
    rounded: "{rounded.none}"
    padding: "8px"
    typography: "{typography.symbol}"
    height: "148px"
  element-cell-cobalt:
    backgroundColor: "{colors.coding-cobalt}"
    textColor: "{colors.fill-white}"
  key-swatch:
    rounded: "{rounded.none}"
    height: "24px"
    width: "40px"
  theme-toggle:
    textColor: "{colors.press-ink}"
    rounded: "{rounded.none}"
    size: "40px"
  theme-toggle-hover:
    backgroundColor: "{colors.press-ink}"
    textColor: "{colors.chart-paper}"
  nav-link:
    textColor: "{colors.press-ink}"
    typography: "{typography.label}"
    padding: "8px 0 4px"
  install-line:
    backgroundColor: "{colors.paper-tint}"
    textColor: "{colors.press-ink}"
    typography: "{typography.mono}"
    padding: "8px 12px"
    rounded: "{rounded.none}"
  report-row:
    textColor: "{colors.press-ink}"
    padding: "12px 8px"
  report-row-hover:
    backgroundColor: "{colors.paper-tint}"
---

# Design System: my-hermes-skills

## Overview

**Creative North Star: "The Reference Wall Chart"**

The site is a printed reference chart pinned to a workshop wall. Every skill is a numbered element cell carrying a two-letter symbol, the cells are grouped into flat colour-blocked families, and each cell is keyed to a handbook entry further down the sheet. The whole toolkit is visible at once in the first viewport; the key at the right explains how to read it. Reports are not a second visual world. They are the same paper and ink, set as a dated ledger and as long-form reading pages.

The material is print, not screen chrome: chart paper (light) or carbon ground (dark), near-black or bone ink, heavy 3px ink rules that open every block, 1px hairlines between rows, square corners everywhere, and no shadows. Colour is confined to the frame: the six family fills live on cells, key swatches and family heads. Running text, tables and the report column stay achromatic. Density is high in the chart and generous in the reader. Paragraphs and lists run the full column width; the owner rejected a narrow 65–75ch measure, and the system does not impose one.

Both themes are first-class. The theme follows the OS until the visitor toggles it, then the choice persists. Every page is generated by `scripts/generate_docs.py`; the design lives in that file and changes go through it, never through hand-edited HTML.

**Key Characteristics:**
- Element cells: number, three-letter family mark, version, two-letter symbol, skill name.
- Six flat process-colour families: Research, Productivity, Coding Agents, Design, Slack, Unfiled.
- Heavy grotesk (Archivo) for structure, reading serif (Source Serif 4) for prose, mono only for paths and commands.
- 3px ink rules open blocks; 1px hairlines separate rows; corners are square; nothing casts a shadow.
- Full-width paragraphs and lists; small-caps tabular figures for dates and versions.

## Colors

Chart paper and press ink carry the page; six flat process fills mark the families and appear nowhere else.

### Primary
- **Press Ink**: the light-theme ink and cell keyline, and the text on amber, vermilion, green and stone fills in both themes. All text, every 3px rule, focus outlines, the toggle border. On chart paper it reads at 16.3:1.
- **Bone Ink**: the dark-theme ink, on carbon ground at 15.2:1.

### Secondary (family fills)
Each fill is paired with a fixed text colour and a three-letter mark (RES, PRO, COD, DES, SLK, UNF) so family is never conveyed by hue alone.
- **Research Amber**: Research cells and swatch; press ink on top (8.3:1). Also the text-selection highlight.
- **Productivity Vermilion**: Productivity; press ink on top (5.2:1).
- **Coding Cobalt**: Coding Agents; white on top (5.7:1).
- **Design Violet**: Design; white on top (5.7:1).
- **Slack Green**: Slack; press ink on top (5.5:1).
- **Unfiled Stone**: Unfiled in light theme; press ink on top (12.1:1).
- **Unfiled Stone Dark**: Unfiled in dark theme, replacing the pale stone that was the loudest block on carbon; press ink on top (5.2:1).

The other five fills are identical in both themes.

### Neutral
- **Chart Paper**: light-theme ground. The warm off-white is the world's paper, specified by the direction contract, not a default cream.
- **Carbon Ground**: dark-theme ground; also the dark-theme cell keyline, so cell borders sink into the page.
- **Pencil Grey / Ash Grey**: muted text (meta lines, tags, verdict excerpts, A–Z numbers) in light / dark; 6.3:1 and 6.2:1 on their grounds.
- **Paper Hairline / Carbon Hairline**: 1px row dividers in lists, entries, ledgers, tables, TOC.
- **Paper Tint / Carbon Tint**: the one recessed surface: code blocks, install line, report-row hover.

### Named Rules
**The Colour In The Frame Rule.** Family fills appear only on cells, key swatches and family heads. Prose, tables, the report ledger and reader pages stay ink on paper.

**The Mark Plus Word Rule.** A family fill never appears without its three-letter mark or its name beside it.

## Typography

**Display Font:** Archivo variable (with Helvetica Neue, Arial)
**Body Font:** Source Serif 4 variable, roman and italic (with Georgia)
**Label/Mono Font:** JetBrains Mono 400 (with ui-monospace, Menlo), paths and commands only

All three are self-hosted WOFF2 in `docs/fonts/` under OFL; Archivo and Source Serif 4 roman are preloaded.

**Character:** A heavy, tightly tracked grotesk does the chart's work (symbols, masthead, rules, labels), and a calm optical-size serif carries everything meant to be read.

### Hierarchy
- **Display** (900, 88px/88px, -0.035em; 64px under 1100px, 40px under 640px): the masthead name only. Compact mastheads on report pages use 40px (32px mobile).
- **Symbol** (900, 48px, line-height 1, -0.02em; scales with cell width down to ~36% of the cell): the two-letter element symbol. 40px in the legend, 28px in entry cells.
- **Headline** (800, 40px/44px, -0.02em; 32px/36px mobile): section heads (Handbook entries, Index A–Z, Install). Page heads use 900 at 64px; report titles 900 at 48px/52px; report h2 800 at 28px/32px.
- **Title** (800, 20px/24px): key heading, family heads, entry names, month heads, report h3.
- **Body** (400, 17px/28px serif): catalog prose. **Body Reader** (400, 18px/32px; 17px/28px mobile) for report pages. No max line length: text fills its column.
- **Label** (800, 13px/20px, 0.08em, uppercase): key subheads, TOC title, ledger column heads. Nav links use 600 at 14px with the same tracking and case; current page goes to 800.
- **Cell meta** (600, 12px/16px, tabular figures): cell number, version, name. Family marks are 700 all-small-caps at 16px, 0.06em.
- **Mono** (400, 13px/20px): install line, entry paths, code. 14px/24px in report code blocks.

### Named Rules
**The Small-Caps Provenance Rule.** Dates, versions, editions and pager labels set in small caps with tabular figures (0.02em tracking).

**The Mono Is For Machines Rule.** JetBrains Mono appears only on paths, commands and code, never as a decorative voice.

## Layout

Page gutters are 48px (16px under 640px), sections are separated by 96px (64px mobile), and the rhythm is built on a 4px unit (4, 8, 12, 16, 24, 40). The catalog's first viewport is a two-column atlas: the chart fills a fluid left column and the key holds a fixed 320px right column with a 40px gap. Under 1100px the key drops below the chart and splits into two columns; under 640px it is one column.

The chart is a container-query grid. Cell width is computed from the container so a seven-cell row fills the chart column; each family is its own block, so no row mixes families. Under a 600px container, cells go four across. Handbook entries are a 320px head column beside a fluid body. The A–Z index runs in up to four 200px columns, Install as four numbered steps.

Report pages use a wide reading column (`max(gutter, 8vw)` side padding): paragraphs, lists and tables run the full width. Wide tables scroll horizontally inside their own wrapper. The reports catalog is a three-column ledger (112px date, title, verdict) that stacks to one column on mobile.

## Elevation & Depth

The system is flat. Nothing has a shadow. Depth comes from rules and tone only: 3px ink rules open blocks, 1px hairlines divide rows, the one tint surface recesses code and the install line, and hovering a key family recedes every other family block to 18% opacity in greyscale.

### Named Rules
**The Printed Sheet Rule.** No box-shadow, no blur, no raised cards. If an element needs separation, use a rule, a hairline or the tint.

## Shapes

Every corner is square (0px radius), including the theme toggle, cells, swatches and code blocks. Form is made of rectangles and rules: 3px ink rules head sections, family blocks, the key, the TOC, the pager and the foot band; 2px for table tops and bottoms and the toggle border; 1px for cell keylines, hairlines and blockquote rules. Hover and focus states are drawn as outlines, never as fills that change shape.

## Components

### Element Cell (signature)
A press-printed tile that is the catalog's unit.
- **Shape:** square corners, 1px keyline (press ink in light; carbon ground in dark), 8px padding, at least 144px tall (about 1.07× its width).
- **Content:** top row with number, family mark and version; symbol; optional "child of NN" line in small caps; skill name pinned to the bottom.
- **Colour:** the family fill with its paired text colour.
- **Hover:** a 3px outline in the cell's own text colour, inset 5px. **Focus:** 3px ink outline, offset 2px. The whole cell links to its handbook entry.

### Family Block and Key
- **Family block:** a 3px ink rule over an all-small-caps family label and count, then the cells.
- **Key row:** 40px swatch (fill, mark, 1px keyline) · family name · count, with a hairline below. Hovering or focusing a row underlines the name and recedes all other family blocks (0.2s, expo-out easing; motion off under reduced-motion).
- **Legend:** an example cell with hairline leaders to "Number, family, version / Symbol / Skill name".

### Buttons
The theme toggle is the only button.
- **Shape:** 40px square, 2px ink border, square corners, transparent fill, 20px line icon (sun or moon for the theme you will switch to).
- **Hover:** inverts to an ink fill with ground-coloured icon. **Focus:** global 3px ink outline.

### Navigation
Uppercase tracked Archivo labels (Chart, Entries, Index A–Z, Reports, Changelog, GitHub) right-aligned against the masthead name, which sits on a 3px ink rule. A 3px bottom border marks state: muted on hover, ink plus weight 800 on the current page. On mobile the row wraps at 13px.

### Handbook Entry
A 64px mini cell (number and 28px symbol on the family fill) beside the entry name and a muted meta line (family, small-caps version, parent link); the body holds the serif description, small-caps "Tags" line, and bold SKILL.md / Source links with the mono path. A targeted entry gets a 3px ink outline around its mini cell. Family sections open with a full-width fill band carrying the name and count.

### Report Ledger Row
The whole row is the link: small-caps date, bold Archivo title, muted serif verdict excerpt, hairline below. Hover adds the tint and a 2px title underline.

### Changelog Ledger Row
The report ledger's grid with a wider third column (112px date, skill, 2fr changes), on `changelog.html`. Rows are not links: the skill name links to its handbook entry, with a muted small-caps version below it. Changes are 15px serif square-bulleted lists, and Keep a Changelog `### Added`/`### Fixed` kinds become uppercase Archivo labels. Each row is anchored `#<skill>-<version>`, and the targeted row gets a 3px ink outline. Achromatic, like every ledger.

### Report Reader
Achromatic long-form page: a metadata table under the title (small-caps labels in a 144px hanging column, ink rules above and below), auto TOC in two columns under a 3px rule, h2s on 3px rules, booktabs-style tables (2px ink top and bottom, 1px under headers, hairline rows), tint code blocks, an italic blockquote on a 1px ink rule, and a three-column Older / All reports / Newer pager.

### Foot Band
A 3px ink rule closing every page, with licence, repo, source note, Hermes credit, and a small-caps edition date pushed to the right.

## Do's and Don'ts

### Do:
- **Do** make design changes in `scripts/generate_docs.py` and regenerate; the HTML is build output.
- **Do** ship both themes for every new element, with the theme following the OS until the visitor toggles it.
- **Do** pair every family fill with its three-letter mark or family name, and keep text-on-fill contrast at WCAG AA or better (the fill table records each ratio).
- **Do** open blocks with a 3px ink rule and divide rows with 1px hairlines.
- **Do** let paragraphs, lists and tables run the full column width.
- **Do** set dates and versions in small caps with tabular figures.

### Don't:
- **Don't** impose a 65–75ch measure or any narrow reading column; the owner rejected it.
- **Don't** round corners or add shadows; this is a printed sheet.
- **Don't** put family colour into prose, tables, the report ledger or reader pages.
- **Don't** convey family by hue alone.
- **Don't** use mono for anything but paths, commands and code.
- **Don't** add a seventh family fill ad hoc; unknown sections fall into Unfiled until a family is defined in `FAMILIES`.
