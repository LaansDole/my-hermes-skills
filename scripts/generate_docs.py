#!/usr/bin/env python3
"""Generate the docs/ site from skills/**/SKILL.md and reports/YYYY-MM/*.md.

Zero dependencies (no PyYAML): parses the frontmatter subset used in this
repo — name, version, description (plain or double-quoted), tags (inline
list). Parent/child nesting is inferred from the folder tree: a SKILL.md
whose parent folder also contains a SKILL.md is a child of that skill.

The skills catalog is a reference wall chart: every skill is a numbered
cell with a two-letter symbol, coloured by family, keyed to a handbook
entry below the chart.

Run:  python3 scripts/generate_docs.py          (site)
      python3 scripts/generate_docs.py --json   (skills.json instead of index.html)
Out:  docs/index.html, docs/reports.html, docs/daily-news.html and
      docs/reports/YYYY-MM/<slug>.html (overwritten). Fonts are committed
      under docs/fonts/ and only referenced from here.
"""

import html
import json
import re
import string
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SKILLS = REPO / "skills"
REPORTS = REPO / "reports"
OUT = REPO / "docs" / "index.html"
GH = "https://github.com/LaansDole/my-hermes-skills"
HERMES = "https://hermes-agent.nousresearch.com"

# top-level skills/ dir -> section title. Unknown dirs become their own
# section (titled by the dir) and sit in the Unfiled family on the chart.
CATEGORY_MAP = {
    "covidence-screening":           "Research",
    "covidence-full-text-retrieval": "Research",
    "sci-hub-access":                "Research",
    "productivity":                  "Productivity",
    "oh-my-pi":                      "Coding Agents",
    "creative":                      "Design",
    "slack":                         "Slack",
}
# fixed section order; unknown sections append alphabetically
SECTION_ORDER = ["Research", "Productivity", "Coding Agents", "Design", "Slack"]

INK = "#17171b"
# family -> (flat process fill, text on fill, mark). The three-letter mark
# rides on every cell and key swatch, so family is never hue alone.
# Contrast (WCAG), text on fill: 8.28, 5.22, 5.74, 5.70, 5.45, 12.06 : 1.
FAMILIES = {
    "Research":      ("#e8a33a", INK, "RES"),
    "Productivity":  ("#e2643f", INK, "PRO"),
    "Coding Agents": ("#3a63b8", "#ffffff", "COD"),
    "Design":        ("#7a52b3", "#ffffff", "DES"),
    "Slack":         ("#4f9e63", INK, "SLK"),
    "Unfiled":       ("#d8d4c8", INK, "UNF"),
}
# dark-theme fill overrides; pale Unfiled was the loudest block on carbon.
# #8f8a7e under ink: 5.20 : 1.
DARK_FILLS = {"Unfiled": "#8f8a7e"}
UNFILED = "Unfiled"

# skill name -> two-letter symbol, when the derived one reads badly.
SYMBOL_OVERRIDES: dict = {}

MONTHS = ("January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December")


def parse_frontmatter(text: str) -> dict:
    """Extract name/version/description/tags from a SKILL.md frontmatter block."""
    m = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    if not m:
        return {}
    fm = m.group(1)
    out = {}

    name = re.search(r"^name:\s*(.+)$", fm, re.MULTILINE)
    if name:
        out["name"] = name.group(1).strip().strip('"')

    version = re.search(r"^version:\s*(.+)$", fm, re.MULTILINE)
    if version:
        out["version"] = version.group(1).strip().strip('"')

    desc = re.search(r"^description:\s*(.+)$", fm, re.MULTILINE)
    if desc:
        d = desc.group(1).strip()
        if d.startswith('"') and d.endswith('"'):
            d = d[1:-1].replace('\\"', '"')
        elif d.startswith("'") and d.endswith("'"):
            d = d[1:-1].replace("\\'", "'")
        out["description"] = d

    tags = re.search(r"^\s*tags:\s*\[(.*?)\]", fm, re.MULTILINE)
    if tags:
        out["tags"] = [t.strip().strip('"').strip("'")
                       for t in tags.group(1).split(",") if t.strip()]
    return out


def find_skills() -> list:
    """Return dicts for every SKILL.md under skills/, with category/nesting."""
    skills = []
    for p in sorted(SKILLS.rglob("SKILL.md")):
        skill_dir = p.parent
        top = skill_dir.relative_to(SKILLS).parts[0]
        fm = parse_frontmatter(p.read_text())
        if not fm.get("name"):
            continue

        # child if the parent folder is itself a skill (has its own SKILL.md)
        parent_skill = None
        if (skill_dir.parent / "SKILL.md").exists():
            parent_skill = skill_dir.parent.name

        skills.append({
            "name": fm["name"],
            "version": fm.get("version", ""),
            "description": fm.get("description", ""),
            "tags": fm.get("tags", []),
            "rel_dir": str(skill_dir.relative_to(REPO)),
            "top": top,
            "parent_skill": parent_skill,
        })
    return skills


def find_reports() -> list:
    """Return dicts for report Markdown under reports/YYYY-MM/.

    Expected naming: YYYY-MM-DD-<slug>.md; the leading date becomes the row
    date and the slug becomes the title. Hidden/private scratch and dot-prefixed
    paths are never published, including nested report directories.
    """
    reports = []
    if not REPORTS.is_dir():
        return reports
    for p in sorted(REPORTS.rglob("*.md"), reverse=True):
        rel = p.relative_to(REPO)
        # Personal report libraries may contain hidden session/task notes.
        # Publish only dated, top-level month folders; private dot directories
        # and nested scratch reports are excluded by default.
        if any(part.startswith(".") for part in rel.parts) or len(rel.parts) != 3:
            continue
        if not re.fullmatch(r"\d{4}-\d{2}", rel.parts[1]):
            continue
        if not re.match(r"^\d{4}-\d{2}-\d{2}-.+\.md$", p.name):
            continue
        stem = p.stem
        m = re.match(r"^(\d{4}-\d{2}-\d{2})-(.+)$", stem)
        date, slug = (m.group(1), m.group(2)) if m else ("", stem)
        # Human title from slug: first paragraph of the file is the fallback.
        title = slug.replace("-", " ").replace("_", " ").strip()
        text = p.read_text()
        h1 = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
        if h1:
            title = h1.group(1).strip()
        # Verdict = first non-empty line after a '## Verdict' heading, if any.
        verdict = ""
        vm = re.search(r"^##\s+Verdict\s*$\n+(.+)$", text, re.MULTILINE)
        if vm:
            verdict = vm.group(1).strip().split("\n")[0]
        reports.append({
            "rel_path": str(rel),
            "date": date,
            "title": title,
            "verdict": verdict,
        })
    return reports


def inline_md(text: str) -> str:
    """Render inline markdown (bold/italic/code/links) to HTML."""
    s = html.escape(text, quote=False)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<em>\1</em>", s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    return s


def section_title(s: dict) -> str:
    return CATEGORY_MAP.get(s["top"], s["top"])


def ordered_sections(skills: list) -> list:
    """[(section title, skills)] in SECTION_ORDER; children right after their parent."""
    by_section = {}
    for s in sorted(skills, key=lambda x: x["name"]):
        by_section.setdefault(section_title(s), []).append(s)
    ordered = sorted(by_section, key=lambda t: (SECTION_ORDER.index(t)
                                                if t in SECTION_ORDER
                                                else len(SECTION_ORDER) + 1))
    out = []
    for title in ordered:
        rows = []
        for s in by_section[title]:
            if s["parent_skill"]:
                continue  # placed right after its parent below
            rows.append(s)
            rows.extend(c for c in by_section[title] if c["parent_skill"] == s["name"])
        out.append((title, rows))
    return out


def entry_json(s: dict, title: str) -> dict:
    """One flat manifest entry for a skill."""
    return {
        "name": s["name"],
        "version": s["version"],
        "description": s["description"],
        "category": title,
        "path": s["rel_dir"],
        "url": f"{GH}/tree/main/{s['rel_dir']}",
    }


def manifest_json(skills: list) -> dict:
    """Build the skills.json manifest (deterministic: no timestamps)."""
    return {
        "source_repo": GH,
        "skills": [entry_json(s, section_title(s))
                   for s in sorted(skills, key=lambda x: x["name"])],
        "sections": [{"title": t, "skills": [entry_json(s, t) for s in rows]}
                     for t, rows in ordered_sections(skills)],
    }


def assign_symbols(names: list) -> dict:
    """Unique element-style symbol per skill, in chart order.

    First letter upper, then the first free distinguishing lower letter:
    second word's initial, last word's initial, middle initials, then the
    remaining letters of the name. Overrides are reserved before anything
    is derived.
    """
    used = set(SYMBOL_OVERRIDES.values())
    if len(used) != len(SYMBOL_OVERRIDES):
        raise SystemExit("SYMBOL_OVERRIDES assigns one symbol twice")
    out = {}
    for name in names:
        if name in SYMBOL_OVERRIDES:
            out[name] = SYMBOL_OVERRIDES[name]
            continue
        words = re.findall(r"[a-z0-9]+", name.lower()) or ["x"]
        head = words[0][0].upper()
        initials = [w[0] for w in words[1:]]
        tail = (initials[:1] + initials[-1:] + initials[1:-1]
                + list("".join(words)[1:]) + list(string.ascii_lowercase))
        # ponytail: 26+ skills sharing a first letter exhaust this; add overrides then
        sym = next((head + c for c in tail if head + c not in used), None)
        if sym is None:
            raise SystemExit(f"no free symbol for {name}; add a SYMBOL_OVERRIDES entry")
        used.add(sym)
        out[name] = sym
    return out


def chart_cells(skills: list) -> list:
    """Skills in chart order with number, symbol, family and parent number."""
    rows = [(t, s) for t, ss in ordered_sections(skills) for s in ss]
    width = max(2, len(str(len(rows))))
    syms = assign_symbols([s["name"] for _, s in rows])
    nums, cells = {}, []
    for i, (title, s) in enumerate(rows, 1):
        fam = title if title in FAMILIES else UNFILED
        nums[s["name"]] = f"{i:0{width}d}"
        cells.append({**s, "n": nums[s["name"]], "sym": syms[s["name"]],
                      "family": fam, "fam": slugify(fam), "mark": FAMILIES[fam][2],
                      "parent_n": nums.get(s["parent_skill"] or "")})
    return cells


def family_groups(cells: list) -> list:
    """[(family, cells)] in chart order; families are contiguous in chart order."""
    groups = []
    for c in cells:
        if not groups or groups[-1][0] != c["family"]:
            groups.append((c["family"], []))
        groups[-1][1].append(c)
    return groups


def short_date(d: str) -> str:
    """2026-10-24 -> '24 Oct'."""
    return f"{int(d[8:10])} {MONTHS[int(d[5:7]) - 1][:3]}"


def long_date(d: str) -> str:
    """2026-10-24 -> '24 Oct 2026'."""
    return f"{short_date(d)} {d[:4]}"


def month_label(d: str) -> str:
    return f"{MONTHS[int(d[5:7]) - 1]} {d[:4]}" if d else "Undated"


def edition_date(reports: list) -> str:
    """Newest report date: deterministic, unlike the clock."""
    return max((r["date"] for r in reports if r["date"]), default="")


def report_href(r: dict) -> str:
    """docs-relative page path, without '..' so the project base path holds."""
    return "reports/" + r["rel_path"][len("reports/"):-3] + ".html"


# ---------------------------------------------------------------------------
# Frame: fonts, tokens, masthead, foot band (every page)
# ---------------------------------------------------------------------------

FONT_FACES = (
    ("Archivo", "archivo-latin-wght-normal.woff2", "100 900", "normal"),
    ("Source Serif 4", "source-serif-4-latin-wght-normal.woff2", "200 900", "normal"),
    ("Source Serif 4", "source-serif-4-latin-wght-italic.woff2", "200 900", "italic"),
    ("JetBrains Mono", "jetbrains-mono-latin-400-normal.woff2", "400", "normal"),
)

BASE_CSS = """    :root, :root[data-theme="light"] {
      color-scheme: light;
      --ground: #f6f4ee; --ink: #17171b; --muted: #5d5a52;
      --hair: #cfcabd; --tint: #ebe7dc; --keyline: #17171b;
    }
    :root[data-theme="dark"] {
      color-scheme: dark;
      --ground: #141416; --ink: #ece9e0; --muted: #9a968b;
      --hair: #38373a; --tint: #1e1e21; --keyline: #141416;
    }
    :root {
      --display: "Archivo", "Helvetica Neue", Arial, sans-serif;
      --serif: "Source Serif 4", Georgia, serif;
      --mono: "JetBrains Mono", ui-monospace, Menlo, monospace;
      --pad: 48px;
      --ease: cubic-bezier(0.16, 1, 0.3, 1);
    }
    *, *::before, *::after { box-sizing: border-box; }
    html { background: var(--ground); color: var(--ink);
           scrollbar-color: var(--muted) var(--ground); -webkit-text-size-adjust: 100%; }
    body { margin: 0; font: 400 17px/28px var(--serif); caret-color: var(--ink);
           font-optical-sizing: auto; overflow-wrap: break-word; }
    ::selection { background: #e8a33a; color: #17171b; }
    a { color: inherit; text-decoration-thickness: 1px; text-underline-offset: 3px; }
    a:hover { text-decoration-thickness: 2px; }
    :focus-visible { outline: 3px solid var(--ink); outline-offset: 2px; }
    code, pre { font-family: var(--mono); }
    h1, h2, h3, h4 { text-wrap: balance; }
    .sc { font-variant-caps: small-caps; font-variant-numeric: tabular-nums;
          letter-spacing: 0.02em; }
    .vh { position: absolute; width: 1px; height: 1px; overflow: hidden;
          clip-path: inset(50%); white-space: nowrap; }
    .skip { position: absolute; left: var(--pad); top: -80px; z-index: 10;
            padding: 8px 16px; background: var(--ink); color: var(--ground);
            font: 700 14px/20px var(--display); text-decoration: none; }
    .skip:focus { top: 8px; }

    .mast { padding: 32px var(--pad) 0; }
    .mast-in { display: flex; flex-wrap: wrap; align-items: flex-end;
               justify-content: space-between; gap: 16px 40px;
               padding-bottom: 16px; border-bottom: 3px solid var(--ink); }
    .mast-name { margin: 0; font: 900 88px/88px var(--display); letter-spacing: -0.035em; }
    .mast-name a { text-decoration: none; }
    .mast-compact .mast-name { font-size: 40px; line-height: 40px; letter-spacing: -0.03em; }
    .nav ul { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 28px;
              margin: 0; padding: 0; list-style: none; }
    .nav a { display: block; padding: 8px 0 4px; border-bottom: 3px solid transparent;
             font: 600 14px/20px var(--display); letter-spacing: 0.08em;
             text-transform: uppercase; text-decoration: none; }
    .nav a:hover { border-bottom-color: var(--muted); }
    .nav a[aria-current] { font-weight: 800; border-bottom-color: var(--ink); }
    .theme-toggle { display: grid; place-items: center; width: 40px; height: 40px;
                    padding: 0; border: 2px solid var(--ink); border-radius: 0;
                    background: none; color: var(--ink); cursor: pointer; }
    .theme-toggle:hover { background: var(--ink); color: var(--ground); }
    .theme-toggle svg { display: block; width: 20px; height: 20px; }
    :root[data-theme="dark"] .i-moon, :root[data-theme="light"] .i-sun { display: none; }

    .band { margin-top: 96px; padding: 0 var(--pad) 32px; }
    .band ul { display: flex; flex-wrap: wrap; gap: 8px 32px; margin: 0;
               padding: 16px 0 0; border-top: 3px solid var(--ink); list-style: none;
               font: 500 14px/20px var(--display); }
    .band code { font-size: 13px; }
    .band-ed { margin-left: auto; font-weight: 700; }

    @media (prefers-reduced-motion: no-preference) {
      html { scroll-behavior: smooth; }
    }
    @media (max-width: 1100px) {
      .mast-name { font-size: 64px; line-height: 64px; }
    }
    @media (max-width: 640px) {
      :root { --pad: 16px; }
      .mast { padding-top: 24px; }
      .mast-name { font-size: 40px; line-height: 40px; }
      .mast-compact .mast-name { font-size: 32px; line-height: 32px; }
      .nav ul { gap: 4px 20px; }
      .nav a { font-size: 13px; }
      .band { margin-top: 64px; }
      .band ul { flex-direction: column; }
      .band-ed { margin-left: 0; }
    }"""


def base_css(root: str) -> str:
    """Fonts (paths relative to the page's depth), tokens, family fills, frame."""
    faces = "\n".join(
        f'    @font-face {{ font-family: "{fam}"; src: url("{root}fonts/{f}") format("woff2");'
        f" font-weight: {w}; font-style: {st}; font-display: swap; }}"
        for fam, f, w, st in FONT_FACES)
    fills = "\n".join(f"    .f-{slugify(name)} {{ background: {bg}; color: {fg}; }}"
                      for name, (bg, fg, _) in FAMILIES.items())
    dark = "\n".join(f'    :root[data-theme="dark"] .f-{slugify(name)} {{ background: {bg}; }}'
                     for name, bg in DARK_FILLS.items())
    return f"{faces}\n{BASE_CSS}\n{fills}\n{dark}"


# Set data-theme before first paint: stored choice wins, else follow the OS.
PREPAINT_JS = """  <script>
    (function () {
      var t = null;
      try { t = localStorage.getItem("theme"); } catch (e) {}
      if (!t) {
        var m = window.matchMedia && window.matchMedia("(prefers-color-scheme: light)");
        t = m && m.matches ? "light" : "dark";
      }
      document.documentElement.setAttribute("data-theme", t);
    })();
  </script>"""

# Header toggle: flips the theme, persists the choice; auto-follows the OS
# until the user overrides it. CSS shows the icon of the theme you'll get.
TOGGLE_JS = """  <script>
    (function () {
      var root = document.documentElement;
      var btn = document.getElementById("theme-toggle");
      var stored = null;
      try { stored = localStorage.getItem("theme"); } catch (e) {}
      if (!btn) return;
      function paint() {
        var label = root.getAttribute("data-theme") === "light"
          ? "Switch to dark theme" : "Switch to light theme";
        btn.setAttribute("aria-label", label);
        btn.title = label;
      }
      btn.addEventListener("click", function () {
        var next = root.getAttribute("data-theme") === "light" ? "dark" : "light";
        root.setAttribute("data-theme", next);
        try { localStorage.setItem("theme", next); } catch (e) {}
        paint();
      });
      paint();
      var m = window.matchMedia && window.matchMedia("(prefers-color-scheme: light)");
      if (m && !stored) {
        m.addEventListener("change", function (e) {
          root.setAttribute("data-theme", e.matches ? "light" : "dark");
          paint();
        });
      }
    })();
  </script>"""

THEME_TOGGLE = (
    '<button id="theme-toggle" class="theme-toggle" type="button" '
    'aria-label="Toggle light/dark theme" title="Toggle light/dark theme">'
    '<span id="theme-icon" aria-hidden="true">'
    '<svg class="i-sun" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
    'stroke-width="2" stroke-linecap="square"><circle cx="12" cy="12" r="4"/>'
    '<path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9 7 7M17 17l2.1 2.1M4.9 19.1 7 17M17 7l2.1-2.1"/></svg>'
    '<svg class="i-moon" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
    'stroke-width="2" stroke-linejoin="miter"><path d="M20 14.5A8.5 8.5 0 0 1 9.5 4 8.5 8.5 0 1 0 20 14.5Z"/></svg>'
    "</span></button>")

NAME_HTML = "my-<wbr>hermes-<wbr>skills"


def masthead(root: str, current: str, home: bool = False, compact: bool = False) -> str:
    """Name + nav. root: prefix back to docs/; current: nav label to mark."""
    index = "" if home else f"{root}index.html"
    items = [("Chart", f"{index}#chart"), ("Entries", f"{index}#entries"),
             ("Index A–Z", f"{index}#a-z"), ("Reports", f"{root}reports.html"),
             ("Changelog", f"{root}changelog.html")]
    cur = ' aria-current="page"'
    links = "".join(
        f'\n        <li><a href="{href}"{cur if label == current else ""}>{label}</a></li>'
        for label, href in items)
    name = (f'<h1 class="mast-name">{NAME_HTML}</h1>' if home else
            f'<p class="mast-name"><a href="{root}index.html">{NAME_HTML}</a></p>')
    cls = "mast mast-compact" if compact else "mast"
    return f"""<header class="{cls}">
  <div class="mast-in">
    {name}
    <nav class="nav" aria-label="Site">
      <ul>{links}
        <li><a href="{GH}" target="_blank" rel="noopener">GitHub</a></li>
        <li>{THEME_TOGGLE}</li>
      </ul>
    </nav>
  </div>
</header>"""


def foot_band(source: str, edition: str) -> str:
    ed = f'\n    <li class="band-ed sc">Edition {long_date(edition)}</li>' if edition else ""
    return f"""<footer class="band">
  <ul>
    <li><a href="{GH}/blob/main/LICENSE" target="_blank" rel="noopener">MIT License</a></li>
    <li><a href="{GH}" target="_blank" rel="noopener">LaansDole/my-hermes-skills</a></li>
    <li>{source}</li>
    <li><a href="{HERMES}" target="_blank" rel="noopener">Hermes Agent</a> by Nous Research</li>{ed}
  </ul>
</footer>"""


def page_html(*, title: str, root: str, css: str, body: str, canonical: str = "") -> str:
    canon = f'\n  <link rel="canonical" href="{canonical}" />' if canonical else ""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <meta name="color-scheme" content="light dark" />
  <title>{title}</title>{canon}
  <link rel="preload" href="{root}fonts/archivo-latin-wght-normal.woff2" as="font" type="font/woff2" crossorigin />
  <link rel="preload" href="{root}fonts/source-serif-4-latin-wght-normal.woff2" as="font" type="font/woff2" crossorigin />
  <style>
{base_css(root)}
{css}
  </style>
{PREPAINT_JS}
</head>
<body>
<a class="skip" href="#main">Skip to content</a>
{body}
{TOGGLE_JS}
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Skills catalog: chart, key, handbook entries, A-Z index, install
# ---------------------------------------------------------------------------

INDEX_CSS = """    .atlas { display: grid; grid-template-columns: minmax(0, 1fr) 320px; gap: 40px;
             align-items: start; padding: 24px var(--pad) 0; }
    .chart-wrap { container-type: inline-size; }
    .chart { --gap: 4px; --bgap: 16px;
             --cell: calc((100cqi - 4 * var(--gap) - 2 * var(--bgap) - 1px) / 7);
             display: flex; flex-wrap: wrap; align-items: flex-start; gap: 20px var(--bgap);
             margin: 0; padding: 0; list-style: none; }
    .fam-block { flex: none; width: min-content;
                 transition: opacity 0.2s var(--ease), filter 0.2s var(--ease); }
    .fb-h { display: flex; justify-content: space-between; align-items: baseline;
            gap: 8px; margin: 0 0 6px; padding-top: 4px; border-top: 3px solid var(--ink);
            font-family: var(--display); font-weight: 800; font-size: 16px; line-height: 20px;
            font-variant-caps: all-small-caps; letter-spacing: 0.04em; }
    .fb-n { flex: none; font-variant-numeric: tabular-nums; }
    .fb-cells { display: grid; grid-template-columns: repeat(var(--cols), var(--cell));
                gap: var(--gap); margin: 0; padding: 0; list-style: none; }
    .fb-cells li { display: flex; }
    .cell, .legend-cell { display: flex; flex-direction: column; min-height: 148px;
                          padding: 8px; border: 1px solid var(--keyline);
                          font-family: var(--display); text-decoration: none; }
    .cell { flex: 1; min-height: max(144px, calc(var(--cell) * 1.07)); }
    .cell:hover { outline: 3px solid currentColor; outline-offset: -5px; }
    .cell:focus-visible { outline: 3px solid var(--ink); outline-offset: 2px; }
    .c-top { display: flex; justify-content: space-between; align-items: baseline; gap: 4px;
             font: 600 12px/16px var(--display); font-variant-numeric: tabular-nums; }
    .c-mark { font-weight: 700; font-size: 16px; font-variant-caps: all-small-caps;
              letter-spacing: 0.06em; }
    .c-sym { margin-top: 8px; font: 900 48px/48px var(--display); letter-spacing: -0.02em;
             white-space: nowrap; }
    .chart .c-sym { font-size: min(48px, calc(var(--cell) * 0.36)); line-height: 1; }
    .c-child { margin-top: 2px; font: 600 12px/16px var(--display);
               font-variant-caps: small-caps; letter-spacing: 0.02em; }
    .c-name { margin-top: auto; padding-top: 4px; font: 600 12px/16px var(--display); }

    .key-sum { margin: 0 0 12px; font-size: 15px; line-height: 24px; color: var(--muted); }
    .key h2 { margin: 0 0 4px; font: 800 20px/24px var(--display); }
    .key h3 { margin: 24px 0 8px; font: 800 13px/20px var(--display);
              letter-spacing: 0.08em; text-transform: uppercase; }
    .key-fams { margin: 0; padding: 0; list-style: none; border-top: 3px solid var(--ink); }
    .key-fam { display: grid; grid-template-columns: 40px 1fr auto; gap: 12px;
               align-items: center; padding: 6px 0; border-bottom: 1px solid var(--hair);
               font: 600 15px/20px var(--display); text-decoration: none; }
    .key-fam:hover .kf-name, .key-fam:focus-visible .kf-name {
      text-decoration: underline 2px; text-underline-offset: 4px; }
    .kf-n { font-variant-numeric: tabular-nums; }
    .sw { display: grid; place-items: center; height: 24px; border: 1px solid var(--keyline);
          font-weight: 700; font-size: 16px; line-height: 16px;
          font-variant-caps: all-small-caps; letter-spacing: 0.06em; }
    .legend { display: grid; grid-template-columns: 104px 1fr; gap: 0 12px; margin: 0; }
    .legend-cell { min-height: 112px; }
    .legend-cell .c-sym { margin-top: 8px; font-size: 40px; line-height: 40px; }
    .legend-labels { display: flex; flex-direction: column; justify-content: space-between;
                     margin: 0; padding: 4px 0; list-style: none;
                     font: 600 13px/20px var(--display); }
    .legend-labels li::before { content: ""; display: inline-block; width: 16px; height: 1px;
                                margin-right: 8px; vertical-align: middle; background: var(--ink); }
    .legend-note { margin: 12px 0 0; font-size: 15px; line-height: 24px; }
    .key-install { margin: 0; padding: 8px 12px; background: var(--tint);
                   font: 400 13px/20px var(--mono); overflow-wrap: anywhere; }
    .key-more { margin: 8px 0 0; font: 600 14px/20px var(--display); }

    .sect { margin-top: 96px; padding: 0 var(--pad); }
    .sect > h2 { margin: 0; padding-top: 16px; border-top: 3px solid var(--ink);
                 font: 800 40px/44px var(--display); letter-spacing: -0.02em; }
    .fam-h { display: flex; justify-content: space-between; align-items: baseline;
             gap: 16px; margin: 40px 0 0; padding: 8px 12px;
             font: 800 20px/24px var(--display); scroll-margin-top: 24px; }
    .fam-h span { font: 600 14px/20px var(--display); font-variant-numeric: tabular-nums; }
    .entry { display: grid; grid-template-columns: minmax(0, 320px) minmax(0, 1fr);
             gap: 12px 40px; padding: 24px 0; border-bottom: 1px solid var(--hair);
             scroll-margin-top: 24px; }
    .e-head { display: grid; grid-template-columns: 64px minmax(0, 1fr); gap: 16px;
              align-items: start; }
    .e-cell { display: flex; flex-direction: column; justify-content: space-between;
              height: 64px; padding: 4px 6px; border: 1px solid var(--keyline);
              font-family: var(--display); }
    .e-n { font: 600 11px/12px var(--display); font-variant-numeric: tabular-nums; }
    .e-s { font: 900 24px/24px var(--display); letter-spacing: -0.02em; white-space: nowrap; }
    .entry:target .e-cell { outline: 3px solid var(--ink); outline-offset: 2px; }
    .e-name { margin: 0; font: 800 20px/24px var(--display); overflow-wrap: anywhere; }
    .e-meta { display: flex; flex-wrap: wrap; gap: 0 12px; margin: 4px 0 0;
              font: 500 14px/20px var(--display); color: var(--muted); }
    .e-desc { margin: 0; }
    .e-tags { margin: 8px 0 0; font: 400 14px/20px var(--display); color: var(--muted); }
    .e-links { display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 24px;
               margin: 12px 0 0; font: 700 14px/20px var(--display); }
    .e-links code { font: 400 13px/20px var(--mono); color: var(--muted); overflow-wrap: anywhere; }

    .az { columns: 4 200px; column-gap: 40px; margin: 24px 0 0; padding: 0; list-style: none; }
    .az li { break-inside: avoid; }
    .az a { display: grid; grid-template-columns: 32px minmax(0, 1fr); gap: 8px;
            padding: 6px 0; border-bottom: 1px solid var(--hair);
            font: 600 15px/20px var(--display); text-decoration: none; }
    .az a:hover span + span { text-decoration: underline; text-underline-offset: 3px; }
    .az-n { color: var(--muted); font-variant-numeric: tabular-nums; }

    .steps { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 24px 40px;
             margin: 24px 0 0; padding: 0; list-style: none; counter-reset: step; }
    .steps li { counter-increment: step; padding-top: 12px; border-top: 1px solid var(--ink); }
    .steps li::before { content: counter(step, decimal-leading-zero); display: block;
                        margin-bottom: 8px; font: 900 40px/44px var(--display);
                        font-variant-numeric: tabular-nums; }
    .steps code { font-size: 15px; }

    @media (prefers-reduced-motion: reduce) {
      .fam-block { transition: none; }
    }
    @media (max-width: 1100px) {
      .atlas { grid-template-columns: minmax(0, 1fr); }
      .key { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0 40px; }
      .steps { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }
    @container (max-width: 600px) {
      .chart { --bgap: 12px; --cell: calc((100cqi - 3 * var(--gap)) / 4); row-gap: 16px;
               align-items: flex-start; }
      .fb-cells { grid-template-columns: repeat(var(--cols-s), var(--cell)); }
      /* two-line head (2x20px lines + 4px pad + 3px rule, border-box): rules and labels share y per row */
      .fb-h { font-size: 16px; min-height: 47px; align-items: flex-end; }
      .cell { min-height: 120px; padding: 6px; }
      .c-top { font-size: 11px; line-height: 12px; }
      .c-mark { font-size: 14px; }
      .c-sym { margin-top: 4px; }
      .c-child { font-size: 11px; line-height: 12px; }
      .c-name { font-size: 11px; line-height: 12px; overflow-wrap: anywhere; }
    }
    @media (max-width: 640px) {
      .atlas { padding-top: 24px; gap: 32px; }
      .key { grid-template-columns: minmax(0, 1fr); }
      .sect { margin-top: 64px; }
      .sect > h2 { font-size: 32px; line-height: 36px; }
      .entry { grid-template-columns: minmax(0, 1fr); }
      .az { columns: 2; column-gap: 24px; }
      .steps { grid-template-columns: minmax(0, 1fr); }
    }"""


def recede_css(cells: list) -> str:
    """Pointing at a key family recedes every other family's block."""
    sel = ",\n".join(
        f'    .atlas:has(.key-fam[data-fam="{slugify(f)}"]:is(:hover, :focus-visible))'
        f' .fam-block:not([data-fam="{slugify(f)}"])'
        for f, _ in family_groups(cells))
    return f"{sel} {{\n      opacity: 0.18; filter: grayscale(1);\n    }}"


def version_label(v: str) -> str:
    return f"v{html.escape(v)}" if v else "unversioned"


def cell_top(c: dict) -> str:
    ver = html.escape(c["version"]) if c["version"] else ""
    return (f'<span class="c-top"><span>{c["n"]}</span><span class="c-mark">{c["mark"]}</span>'
            f'<span class="c-v">{ver}</span></span>')


def cell_html(c: dict) -> str:
    label = f"{c['n']} {c['name']}, {c['family']}, " + (
        f"version {c['version']}" if c["version"] else "unversioned")
    child = ""
    if c["parent_n"]:
        label += f", child of {c['parent_n']} {c['parent_skill']}"
        child = f'\n          <span class="c-child">child of {c["parent_n"]}</span>'
    return f"""        <li><a class="cell f-{c['fam']}" href="#entry-{c['name']}" aria-label="{html.escape(label)}">
          {cell_top(c)}
          <span class="c-sym">{html.escape(c['sym'])}</span>{child}
          <span class="c-name">{html.escape(c['name']).replace('-', '-<wbr>')}</span>
        </a></li>"""


CHART_COLS = 7  # desktop chart width in cells; narrow charts use 4


def chart_html(cells: list) -> str:
    """One labelled block per family, each its own grid, so no row mixes families.

    A block wraps into as few rows as the chart width allows, balanced
    (10 cells -> 5 x 2, not 7 + 3).
    """
    blocks = []
    for fam, cs in family_groups(cells):
        n, slug = len(cs), slugify(fam)
        cols = -(-n // -(-n // CHART_COLS))
        unit = "skill" if n == 1 else "skills"
        body = "\n".join(cell_html(c) for c in cs)
        blocks.append(f"""    <li class="fam-block" data-fam="{slug}" style="--cols: {cols}; --cols-s: {min(n, 4)}">
      <p class="fb-h"><span>{html.escape(fam)}</span><span class="fb-n">{n}<span class="vh"> {unit}</span></span></p>
      <ul class="fb-cells">
{body}
      </ul>
    </li>""")
    return '<ol class="chart">\n' + "\n".join(blocks) + "\n    </ol>"


def key_html(cells: list) -> str:
    fams = family_groups(cells)
    rows = "".join(
        f'\n        <li><a class="key-fam" href="#family-{slugify(f)}" data-fam="{slugify(f)}">'
        f'<span class="sw f-{slugify(f)}" aria-hidden="true">{FAMILIES[f][2]}</span>'
        f'<span class="kf-name">{html.escape(f)}</span><span class="kf-n">{len(cs)}</span></a></li>'
        for f, cs in fams)
    n_fam = "1 family" if len(fams) == 1 else f"{len(fams)} families"
    n_sk = "1 skill" if len(cells) == 1 else f"{len(cells)} skills"
    ex = cells[0]
    return f"""    <aside class="key" aria-labelledby="key-h">
      <div>
      <h2 id="key-h">Key</h2>
      <p class="key-sum">{n_sk} in {n_fam}.</p>
      <ul class="key-fams">{rows}
      </ul>
      </div>
      <div>
      <h3>Reading a cell</h3>
      <figure class="legend">
        <div class="legend-cell f-{ex['fam']}" aria-hidden="true">
          {cell_top(ex)}
          <span class="c-sym">{html.escape(ex['sym'])}</span>
          <span class="c-name">{html.escape(ex['name']).replace('-', '-<wbr>')}</span>
        </div>
        <ul class="legend-labels">
          <li>Number, family, version</li>
          <li>Symbol</li>
          <li>Skill name</li>
        </ul>
      </figure>
      <p class="legend-note">Cells run in chart order, one per skill; open one for its handbook entry, SKILL.md and source. Point at a family to pick out its cells.</p>
      <h3>Install</h3>
      <p class="key-install">ln -s &lt;repo&gt;/skills/&lt;path&gt; ~/.hermes/skills/&lt;name&gt;</p>
      <p class="key-more"><a href="#install">All install steps</a></p>
      </div>
    </aside>"""


def entry_html(c: dict) -> str:
    meta = [html.escape(c["family"]), f'<span class="sc">{version_label(c["version"])}</span>']
    if c["parent_n"]:
        meta.append(f'<span>child of <a href="#entry-{c["parent_skill"]}">'
                    f'{c["parent_n"]} {html.escape(c["parent_skill"])}</a></span>')
    tags = ""
    if c["tags"]:
        tags = (f'\n      <p class="e-tags"><span class="sc">Tags</span> '
                f'{" / ".join(html.escape(t) for t in c["tags"])}</p>')
    nid = f"entry-{c['name']}"
    return f"""  <article class="entry" id="{nid}" aria-labelledby="{nid}-h">
    <div class="e-head">
      <span class="e-cell f-{c['fam']}" aria-hidden="true"><span class="e-n">{c['n']}</span><span class="e-s">{html.escape(c['sym'])}</span></span>
      <div>
        <h4 class="e-name" id="{nid}-h">{html.escape(c['name'])}</h4>
        <p class="e-meta">{"".join(f"<span>{m}</span>" for m in meta)}</p>
      </div>
    </div>
    <div class="e-body">
      <p class="e-desc">{html.escape(c['description'])}</p>{tags}
      <p class="e-links"><a href="{GH}/blob/main/{c['rel_dir']}/SKILL.md" target="_blank" rel="noopener">SKILL.md</a><a href="{GH}/tree/main/{c['rel_dir']}" target="_blank" rel="noopener">Source</a><code>{html.escape(c['rel_dir'])}</code></p>
    </div>
  </article>"""


def entries_html(cells: list) -> str:
    blocks = []
    for fam, group in family_groups(cells):
        slug = slugify(fam)
        count = "1 skill" if len(group) == 1 else f"{len(group)} skills"
        body = "\n".join(entry_html(c) for c in group)
        blocks.append(f"""<section aria-labelledby="family-{slug}">
  <h3 class="fam-h f-{slug}" id="family-{slug}">{html.escape(fam)} <span>{count}</span></h3>
{body}
</section>""")
    return "\n".join(blocks)


def az_html(cells: list) -> str:
    return "\n".join(
        f'    <li><a href="#entry-{c["name"]}"><span class="az-n">{c["n"]}</span>'
        f'<span>{html.escape(c["name"])}</span></a></li>'
        for c in sorted(cells, key=lambda c: c["name"]))


def index_html(skills: list, edition: str) -> str:
    cells = chart_cells(skills)
    body = f"""{masthead("", "Chart", home=True)}

<main id="main">

<section class="atlas" id="chart" aria-labelledby="chart-h">
  <h2 class="vh" id="chart-h">Chart of skills</h2>
  <div class="chart-wrap">
    {chart_html(cells)}
  </div>
{key_html(cells)}
</section>

<section class="sect" id="entries" aria-labelledby="entries-h">
<h2 id="entries-h">Handbook entries</h2>
{entries_html(cells)}
</section>

<section class="sect" id="a-z" aria-labelledby="a-z-h">
  <h2 id="a-z-h">Index A–Z</h2>
  <ul class="az">
{az_html(cells)}
  </ul>
</section>

<section class="sect" id="install" aria-labelledby="install-h">
  <h2 id="install-h">Install</h2>
  <ol class="steps">
    <li>Clone or fork this repo, then symlink (or copy) any skill folder into <code>~/.hermes/skills/</code></li>
    <li>Merge <code>.hermes-config/config-patch.yaml</code> into <code>~/.hermes/config.yaml</code> for auto-approvals needed by CDP browser skills</li>
    <li>For skills with a <code>README.md</code>, follow the per-skill setup steps (env vars, browser profiles, criteria files)</li>
    <li><a href="{HERMES}/docs" target="_blank" rel="noopener">Hermes</a> auto-discovers skills in <code>~/.hermes/skills/</code>; start a new session and the skill is available</li>
  </ol>
</section>

</main>

{foot_band("Generated from <code>skills/**/SKILL.md</code>", edition)}"""
    return page_html(title="my-hermes-skills — LaansDole", root="",
                     css=f"{INDEX_CSS}\n{recede_css(cells)}", body=body,
                     canonical="https://laansdole.github.io/my-hermes-skills/")


# ---------------------------------------------------------------------------
# Reports: catalog table, compat route, reader pages
# ---------------------------------------------------------------------------

def slugify(text: str) -> str:
    """Heading text -> stable anchor id; inline markdown is stripped first."""
    s = re.sub(r"`([^`]*)`", r"\1", text)
    s = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", s)
    s = re.sub(r"[*_]+", "", s)
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return s or "section"


def heading_index(lines: list) -> list:
    """(level, text, id) per heading, in document order.

    Repeated heading text gets -2, -3, … so every anchor target is unique;
    the counter skips ids a literal heading already took (a "Notes-2"
    heading pushes the second "Notes" to notes-3).
    """
    out, used = [], set()
    for ln in lines:
        h = re.match(r"^(#{1,6})\s+(.*)$", ln)
        if not h:
            continue
        slug = hid = slugify(h.group(2))
        n = 1
        while hid in used:
            n += 1
            hid = f"{slug}-{n}"
        used.add(hid)
        out.append((len(h.group(1)), h.group(2), hid))
    return out


# A table of contents only earns its space once a report has real sections.
TOC_MIN_SECTIONS = 4

REF_HEADING = re.compile(r"^##\s+(?:Sources|References)\s*$")
# A reference entry: "[n] ...", "- [n] ...", "n. ...", or a plain "- ..." bullet (numbered in order).
REF_NUMBERED = re.compile(r"^\s*(?:[-*]\s+)?\[(\d+)\]\s+(.*)$")
REF_ORDERED = re.compile(r"^\s*(\d+)\.\s+(.*)$")
REF_BULLET = re.compile(r"^\s*[-*]\s+(.*)$")
# Inline marker: [3] or [1, 4]; never a markdown link label "[3](...)".
CITE = re.compile(r"[ \t]?\[(\d+(?:\s*,\s*\d+)*)\](?!\()")  # a leading space is absorbed


def ref_title(md: str) -> str:
    """Plain-text label for a reference entry, used as the citation hover preview."""
    urls = re.findall(r"https?://[^\s>)]+", md)
    s = re.sub(r"<https?://[^>]+>|https?://\S+", "", md)
    s = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", s)
    s = re.sub(r"[`*_]", "", s)
    s = re.sub(r"\s+", " ", s).strip(" :—–-,;")
    if not s and urls:
        s = re.sub(r"^https?://(www\.)?", "", urls[0]).split("/")[0]
    return s


def collect_references(lines: list) -> dict:
    """Number -> reference markdown, from every Sources/References section."""
    refs: dict = {}
    in_refs = False
    for ln in lines:
        if REF_HEADING.match(ln):
            in_refs = True; continue
        if re.match(r"^#{1,6}\s+", ln):
            in_refs = False; continue
        if not in_refs or not ln.strip():
            continue
        m = REF_NUMBERED.match(ln) or REF_ORDERED.match(ln)
        if m:
            refs[int(m.group(1))] = m.group(2).strip()
        elif (b := REF_BULLET.match(ln)):
            refs[max(refs, default=0) + 1] = b.group(1).strip()
    return refs


def md_to_html(text: str) -> str:
    """Minimal zero-dependency markdown -> HTML for report files.

    Handles the constructs the writing-reports template produces: headings
    (with stable anchor ids), bold/italic/inline code, fenced code blocks,
    GFM tables (wrapped so they scroll instead of overflowing), ordered and
    unordered lists, blockquotes, hr, and links. Escapes everything else.
    Reports with several sections also get a table of contents, inserted
    after the lead-in and before the first H2.
    """
    # fenced code blocks first (protect from other passes)
    blocks: list[str] = []

    def _fence(m: re.Match) -> str:
        blocks.append(f"<pre><code>{html.escape(m.group(1))}</code></pre>")
        return f"\x00FENCE{len(blocks) - 1}\x00"

    text = re.sub(r"```[^\n]*\n(.*?)```", _fence, text, flags=re.S)

    lines = text.split("\n")
    refs = collect_references(lines)
    cite_count: dict = {}

    def cite_link(n: int) -> str:
        cite_count[n] = cite_count.get(n, 0) + 1
        label = html.escape(ref_title(refs[n]))
        return (f'<a id="cite-{n}-{cite_count[n]}" href="#ref-{n}" data-ref="{label}" '
                f'aria-label="Reference {n}: {label}">{n}</a>')

    def cite_markers(s: str) -> str:
        """[n] / [n, m] -> linked markers, skipping code, existing links and unknown numbers."""
        parts = re.split(r"(<code>.*?</code>|<a [^>]*>.*?</a>)", s)
        for k in range(0, len(parts), 2):
            def _one(m: re.Match) -> str:
                nums = [int(x) for x in re.split(r"\s*,\s*", m.group(1))]
                if not all(n in refs for n in nums):
                    return m.group(0)
                return '<sup class="cite">[' + ", ".join(cite_link(n) for n in nums) + "]</sup>"
            parts[k] = CITE.sub(_one, parts[k])
        return "".join(parts)

    def inline(s: str, cite: bool = True) -> str:
        s = html.escape(s, quote=False)
        s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
        # markdown autolink <URL> -> anchor (before other substitutions)
        s = re.sub(r"&lt;(https?://[^&\s]+)&gt;",
                   rf'<a href="\1" target="_blank">\1</a>', s)
        s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
        s = re.sub(r"(?<!\*)\*([^*\n]+?)\*(?!\*)", r"<em>\1</em>", s)
        s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)",
                   rf'<a href="\2" target="_blank">\1</a>', s)
        # autolink bare URLs not already inside an href
        s = re.sub(r'(?<!href=")(?<!">)(https?://[^\s<)"]+)',
                   rf'<a href="\1" target="_blank">\1</a>', s)
        return cite_markers(s) if cite and refs else s

    def flush_source_list(items: list) -> None:
        """Numbered reference list; back-links to each citation are filled in at the end."""
        if items:
            out.append('<ol class="refs">' + "".join(
                f'<li id="ref-{n}" value="{n}"><span class="ref-num">[{n}]</span> '
                f'{inline(md, cite=False)}\x00REFBACK{n}\x00</li>'
                for n, md in items) + "</ol>")

    headings = heading_index(lines)
    toc = ""
    if sum(1 for lvl, _, _ in headings if lvl == 2) >= TOC_MIN_SECTIONS:
        items = "".join(
            f'<li class="toc-{"sub" if lvl == 3 else "top"}">'
            f'<a href="#{hid}">{inline(txt, cite=False)}</a></li>'
            for lvl, txt, hid in headings if lvl in (2, 3))
        toc = ('<nav class="toc" aria-label="Contents">'
               '<p class="toc-title">Contents</p>'
               f"<ul>{items}</ul></nav>")

    out: list[str] = []
    source_items: list = []
    in_sources = False
    ref_seq = 0
    hpos = 0
    i = 0
    while i < len(lines):
        ln = lines[i]
        if REF_HEADING.match(ln):
            in_sources = True
        elif re.match(r"^#{1,6}\s+", ln):
            in_sources = False
        if in_sources and ln.strip():
            m = REF_NUMBERED.match(ln) or REF_ORDERED.match(ln)
            entry = m.group(2) if m else ((b := REF_BULLET.match(ln)) and b.group(1))
            if entry:
                ref_seq = int(m.group(1)) if m else ref_seq + 1
                source_items.append((ref_seq, entry.strip()))
                i += 1
                continue
        if source_items:
            flush_source_list(source_items)
            source_items = []
        if ln.startswith("\x00FENCE"):
            out.append(ln); i += 1; continue
        if re.match(r"^\s*(---+|\*\*\*+)\s*$", ln):
            out.append("<hr>"); i += 1; continue
        h = re.match(r"^(#{1,6})\s+(.*)$", ln)
        if h:
            lvl, _, hid = headings[hpos]
            hpos += 1
            if toc and lvl == 2:
                out.append(toc); toc = ""
            out.append(f'<h{lvl} id="{hid}">{inline(h.group(2), cite=False)}</h{lvl}>'); i += 1; continue
        # table: header row then a |---| separator
        if "|" in ln and i + 1 < len(lines) and re.match(r"^\s*\|?[\s:|-]+\|[\s:|-]*$", lines[i + 1] or ""):
            rows = []
            header = [c.strip() for c in ln.strip().strip("|").split("|")]
            # GFM alignment row: "---:" right, ":---:" centre; numbers line up on the right
            aligns = [("right" if c.strip().endswith(":") and not c.strip().startswith(":") else
                       "center" if c.strip().startswith(":") and c.strip().endswith(":") else "")
                      for c in lines[i + 1].strip().strip("|").split("|")]
            i += 2
            while i < len(lines) and "|" in lines[i] and lines[i].strip():
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            def _al(k: int) -> str:
                a = aligns[k] if k < len(aligns) else ""
                return f' class="al-{a}"' if a else ""
            th = "".join(f"<th{_al(k)}>{inline(c)}</th>" for k, c in enumerate(header))
            out.append(f'<div class="table-scroll"><table><thead><tr>{th}</tr></thead><tbody>')
            for r in rows:
                out.append("<tr>" + "".join(f"<td{_al(k)}>{inline(c)}</td>" for k, c in enumerate(r)) + "</tr>")
            out.append("</tbody></table></div>")
            continue
        m_ol = re.match(r"^\s*(\d+)\.\s+(.*)$", ln)
        if m_ol:
            items = []
            while i < len(lines) and re.match(r"^\s*\d+\.\s+", lines[i]):
                items.append(re.sub(r"^\s*\d+\.\s+", "", lines[i])); i += 1
            out.append("<ol>" + "".join(f"<li>{inline(x)}</li>" for x in items) + "</ol>")
            continue
        m_ul = re.match(r"^\s*[-*]\s+(.*)$", ln)
        if m_ul:
            items = []
            while i < len(lines) and re.match(r"^\s*[-*]\s+", lines[i]):
                items.append(re.sub(r"^\s*[-*]\s+", "", lines[i])); i += 1
            if out and out[-1].startswith("<h1"):
                # lead-in metadata: "**Date:**" lifts into a label column, colon dropped
                items = [re.sub(r"^\*\*([^*]+?):?\*\*:?", r"**\1**", x) for x in items]
            out.append("<ul>" + "".join(f"<li>{inline(x)}</li>" for x in items) + "</ul>")
            continue
        if ln.startswith(">"):
            quote = []
            while i < len(lines) and lines[i].startswith(">"):
                quote.append(lines[i].lstrip("> ").rstrip()); i += 1
            out.append(f"<blockquote>{inline(' '.join(quote))}</blockquote>")
            continue
        if ln.strip():
            para = [ln]
            while i + 1 < len(lines) and lines[i + 1].strip() and not re.match(r"^(#|\||\s*[-*]\s|\s*\d+\.\s|>|```|\s*---)", lines[i + 1]):
                i += 1; para.append(lines[i])
            out.append(f"<p>{inline(' '.join(p.strip() for p in para))}</p>")
        i += 1
    flush_source_list(source_items)
    html_out = "\n".join(out)

    def _backlinks(m: re.Match) -> str:
        n = int(m.group(1))
        k = cite_count.get(n, 0)
        if not k:
            return ""
        if k == 1:
            return (f' <a class="ref-back" href="#cite-{n}-1" '
                    f'aria-label="Back to the citation of reference {n}">back to text</a>')
        links = " ".join(f'<a href="#cite-{n}-{j}" aria-label="Back to citation {j} of reference {n}">'
                         f'{j}</a>' for j in range(1, k + 1))
        return f' <span class="ref-back">back to text {links}</span>'
    html_out = re.sub(r"\x00REFBACK(\d+)\x00", _backlinks, html_out)
    for n, b in enumerate(blocks):
        html_out = html_out.replace(f"\x00FENCE{n}\x00", b)
    return html_out


def prune_report_pages(reports: list) -> None:
    """Delete generated report pages whose markdown source is gone.

    Only *.html under docs/reports/ is touched; assets and anything outside
    that generated tree are left alone.
    """
    base = REPO / "docs" / "reports"
    if not base.is_dir():
        return
    keep = {base / Path(*Path(r["rel_path"]).with_suffix(".html").parts[1:])
            for r in reports}
    for p in sorted(base.rglob("*.html")):
        if p not in keep:
            p.unlink()
    for d in sorted(base.rglob("*"), reverse=True):
        if d.is_dir() and not any(d.iterdir()):
            d.rmdir()


READER_CSS = """    .reader { padding: 48px max(var(--pad), 8vw) 0; }
    article { font: 400 18px/32px var(--serif); font-variant-numeric: oldstyle-nums proportional-nums;
              hanging-punctuation: first; }
    article h1, article h2, article h3, article h4, article h5, article h6 {
      font-family: var(--serif); font-variant-numeric: lining-nums; }
    article h1 { margin: 0 0 28px; font-size: 44px; line-height: 52px; font-weight: 700;
                 letter-spacing: -0.012em; }
    article h2 { margin: 72px 0 12px; font-size: 28px; line-height: 36px; font-weight: 650;
                 letter-spacing: -0.006em; }
    article h3 { margin: 40px 0 8px; font-size: 21px; line-height: 28px; font-weight: 600; }
    article h4, article h5, article h6 { margin: 32px 0 8px; font-size: 18px; line-height: 28px;
                                         font-weight: 600; font-style: italic; }
    article h1, article h2, article h3 { overflow-wrap: anywhere; scroll-margin-top: 24px; }
    article p { margin: 0 0 16px; }
    article ul, article ol { margin: 0 0 20px; padding-left: 28px; }
    article li { margin: 6px 0; }
    article li::marker { font-variant-numeric: lining-nums tabular-nums; color: var(--muted); }
    article a { overflow-wrap: anywhere; }
    article strong { font-weight: 650; }
    article > h1 + ul { margin: 0 0 48px; padding: 0; list-style: none;
                        font-size: 16px; line-height: 26px; color: var(--muted); }
    article > h1 + ul li { position: relative; margin: 0; padding: 3px 0 3px 128px; }
    article > h1 + ul li > strong:first-child { position: absolute; left: 0; top: 3px; width: 112px;
                        color: var(--ink); font-weight: 600; font-variant-caps: all-small-caps;
                        letter-spacing: 0.04em; }
    article code { font-size: 0.85em; overflow-wrap: anywhere; }
    article pre { margin: 24px 0; padding: 16px 20px; overflow-x: auto; background: var(--tint);
                  font: 400 14px/24px var(--mono); }
    article pre code { font-size: inherit; overflow-wrap: normal; }
    .table-scroll { overflow-x: auto; -webkit-overflow-scrolling: touch; margin: 28px 0 32px; }
    article table { width: 100%; min-width: 560px; margin: 0; border-collapse: collapse;
                    border-top: 1.5px solid var(--ink); border-bottom: 1.5px solid var(--ink);
                    font: 400 15px/24px var(--serif);
                    font-variant-numeric: lining-nums tabular-nums; }
    article th { padding: 8px 20px 6px 0; border-bottom: 1px solid var(--ink); text-align: left;
                 vertical-align: bottom; font: 600 15px/22px var(--serif); }
    article td { padding: 5px 20px 5px 0; vertical-align: top; }
    article th.al-right, article td.al-right { text-align: right; }
    article th.al-center, article td.al-center { text-align: center; }
    article th:last-child, article td:last-child { padding-right: 0; }
    article tbody tr:first-child td { padding-top: 10px; }
    article tbody tr:last-child td { padding-bottom: 10px; }
    article blockquote { margin: 24px 0; padding: 0 0 0 24px; border-left: 1px solid var(--ink);
                         font-style: italic; }
    article hr { display: none; }
    .toc { margin: 8px 0 8px; }
    .toc-title { margin: 0 0 4px; font: 600 16px/24px var(--serif); font-variant-caps: all-small-caps;
                 letter-spacing: 0.06em; color: var(--muted); }
    .toc ul { columns: 2 320px; column-gap: 48px; margin: 0; padding: 0; list-style: none; }
    .toc li { margin: 0; break-inside: avoid; }
    .toc a { display: block; padding: 2px 0; font: 400 16px/26px var(--serif);
             text-decoration: none; }
    .toc a:hover { text-decoration: underline; }
    .toc-sub a { padding-left: 20px; color: var(--muted); }
    .cite { font-size: max(0.72em, 11px); line-height: 0; vertical-align: 0.42em;
            font-variant-numeric: lining-nums tabular-nums; white-space: nowrap; }
    .cite a { position: relative; padding: 0 1px; text-decoration: none; }
    .cite a:hover, .cite a:focus-visible { text-decoration: underline; }
    .cite a::after { content: attr(data-ref); position: absolute; left: var(--tip-x, 0px);
                     bottom: calc(100% + 6px);
                     z-index: 5; width: max-content; max-width: min(26rem, 80vw); padding: 6px 10px;
                     background: var(--ink); color: var(--ground); font: 400 14px/20px var(--serif);
                     font-variant-numeric: lining-nums; letter-spacing: 0; white-space: normal;
                     text-align: left; pointer-events: none; opacity: 0; visibility: hidden; }
    .cite a:hover::after, .cite a:focus-visible::after { opacity: 1; visibility: visible; }
    .refs { padding-left: 0; list-style: none; font-size: 16px; line-height: 26px; }
    .refs li { position: relative; margin: 0 0 10px; padding-left: 44px; }
    .ref-num { position: absolute; left: 0; width: 36px; color: var(--muted);
               font-variant-numeric: lining-nums tabular-nums; }
    .refs li:target { background: var(--tint); outline: 6px solid var(--tint); }
    .ref-back { margin-left: 4px; color: var(--muted); font-variant-caps: all-small-caps;
                letter-spacing: 0.04em; white-space: nowrap; }
    .ref-back a, a.ref-back { color: var(--muted); }
    [id^="cite-"]:target { background: var(--tint); outline: 3px solid var(--tint); }
    .pager { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 24px 40px;
             margin-top: 72px; padding-top: 16px; border-top: 1px solid var(--hair);
             font: 600 16px/22px var(--serif); }
    .pager a { text-decoration: none; }
    .pager a:hover span + span { text-decoration: underline; }
    .pager .sc { display: block; color: var(--muted); font-weight: 500;
                 font-variant-caps: all-small-caps; letter-spacing: 0.04em; }
    .pager-next { text-align: right; }
    @media (prefers-reduced-motion: no-preference) {
      .cite a::after { transition: opacity 0.15s var(--ease), visibility 0.15s; }
    }
    @media (max-width: 640px) {
      .reader { padding: 32px var(--pad) 0; }
      article { font-size: 17px; line-height: 28px; }
      article h1 { font-size: 32px; line-height: 38px; }
      article h2 { margin-top: 56px; font-size: 24px; line-height: 30px; }
      article > h1 + ul li { padding-left: 0; }
      article > h1 + ul li > strong:first-child { position: static; display: block; width: auto; }
      .refs li { padding-left: 40px; }
      .pager { grid-template-columns: minmax(0, 1fr); }
      .pager-next { text-align: left; }
    }"""


# Keeps a citation's hover preview inside the viewport: the preview is the marker's ::after,
# so measure its used width and shift it left when it would run past the right edge.
CITE_JS = """  <script>
    (function () {
      function place(a) {
        a.style.removeProperty("--tip-x");
        var w = parseFloat(getComputedStyle(a, "::after").width) || 0;
        var room = document.documentElement.clientWidth - 16 - a.getBoundingClientRect().left;
        if (w > room) a.style.setProperty("--tip-x", Math.min(0, room - w) + "px");
      }
      document.querySelectorAll(".cite a").forEach(function (a) {
        a.addEventListener("mouseenter", function () { place(a); });
        a.addEventListener("focus", function () { place(a); });
      });
    })();
  </script>"""


def write_report_pages(reports: list, edition: str) -> None:
    """Render each report markdown file as a reader page under docs/reports/."""
    base = REPO / "docs" / "reports"
    prune_report_pages(reports)
    root = "../../"
    for i, r in enumerate(reports):
        src = REPO / r["rel_path"]
        rel_html = Path(r["rel_path"]).with_suffix(".html")
        dst = base / Path(*rel_html.parts[1:])  # strip leading reports/
        dst.parent.mkdir(parents=True, exist_ok=True)
        # reports are newest first: i-1 is newer, i+1 is older
        newer = reports[i - 1] if i > 0 else None
        older = reports[i + 1] if i + 1 < len(reports) else None
        older_html = (f'<a href="{root}{report_href(older)}" rel="prev"><span class="sc">Older</span>'
                      f'<span>{inline_md(older["title"])}</span></a>') if older else "<span></span>"
        newer_html = (f'<a class="pager-next" href="{root}{report_href(newer)}" rel="next">'
                      f'<span class="sc">Newer</span><span>{inline_md(newer["title"])}</span></a>'
                      ) if newer else "<span></span>"
        source = (f'Filed by the writing-reports skill · <a href="{GH}/blob/main/{r["rel_path"]}" '
                  f'target="_blank" rel="noopener">Markdown source</a>')
        body = f"""{masthead(root, "Reports", compact=True)}

<main id="main" class="reader">
  <article>
{md_to_html(src.read_text())}
  </article>
  <nav class="pager" aria-label="More reports">
    {older_html}
    <a href="{root}reports.html"><span class="sc">Back to</span><span>All reports</span></a>
    {newer_html}
  </nav>
</main>

{foot_band(source, edition)}
{CITE_JS}"""
        dst.write_text(page_html(title=f"{html.escape(r['title'])} — Reports",
                                 root=root, css=READER_CSS, body=body))


REPORTS_CSS = """    .page-head { padding: 48px var(--pad) 0; }
    .page-head h1 { margin: 0; font: 900 64px/64px var(--display); letter-spacing: -0.03em; }
    .lede { margin: 16px 0 0; }
    .compat { margin: 8px 0 0; color: var(--muted); }
    .ledger { --cols: 112px minmax(0, 1fr) minmax(0, 1fr); margin-top: 48px; padding: 0 var(--pad); }
    .ledger-head { display: grid; grid-template-columns: var(--cols); gap: 32px;
                   padding: 0 8px 8px; border-bottom: 3px solid var(--ink);
                   font: 700 13px/20px var(--display); letter-spacing: 0.08em; text-transform: uppercase; }
    .month h2 { margin: 32px 0 0; padding: 0 8px 8px; border-bottom: 1px solid var(--ink);
                font: 800 20px/24px var(--display); }
    .rows { margin: 0; padding: 0; list-style: none; }
    .report-row { display: grid; grid-template-columns: var(--cols); gap: 32px;
                  padding: 12px 8px; border-bottom: 1px solid var(--hair);
                  text-decoration: none; }
    .report-row:hover { background: var(--tint); }
    .report-row:hover .r-title { text-decoration: underline; text-decoration-thickness: 2px; }
    .r-date { font-family: var(--display); font-weight: 600; font-size: 16px; line-height: 24px; }
    .r-title { font: 700 17px/24px var(--display); }
    .r-title code { font: 400 15px/24px var(--mono); }
    .r-verdict { font-size: 15px; line-height: 24px; color: var(--muted); }
    .r-verdict code { font-size: 14px; }
    @media (max-width: 640px) {
      .page-head { padding-top: 32px; }
      .page-head h1 { font-size: 40px; line-height: 40px; }
      .ledger-head { display: none; }
      .report-row { grid-template-columns: minmax(0, 1fr); gap: 4px; }
    }"""

REPORTS_CANONICAL = "https://laansdole.github.io/my-hermes-skills/reports.html"

COMPAT_NOTE = """
    <p class="compat">
      This page is kept so older links keep working. The canonical index is
      <a href="reports.html">reports.html</a>.
    </p>"""


def verdict_excerpt(v: str) -> str:
    if len(v) <= 280:
        return inline_md(v)
    return inline_md(v[:280].rsplit(" ", 1)[0]) + "…"


def report_row_html(r: dict) -> str:
    """One ledger row; the WHOLE row is the link to the report page."""
    date = (f'<time class="r-date sc" datetime="{r["date"]}">{short_date(r["date"])}</time>'
            if r["date"] else '<span class="r-date sc">undated</span>')
    return f"""        <li><a class="report-row" href="{report_href(r)}">
          {date}
          <span class="r-title">{inline_md(r["title"])}</span>
          <span class="r-verdict">{verdict_excerpt(r["verdict"])}</span>
        </a></li>"""


def reports_index_html(reports: list, edition: str, note: str = "") -> str:
    """The report catalog page; identical body for the canonical and compat routes."""
    if not reports:
        ledger = '    <p class="lede">No reports filed yet.</p>'
    else:
        months = {}
        for r in reports:
            months.setdefault(month_label(r["date"]), []).append(r)
        groups = "\n".join(
            f"""    <section class="month" aria-labelledby="m-{slugify(m)}">
      <h2 id="m-{slugify(m)}">{m}</h2>
      <ol class="rows">
{chr(10).join(report_row_html(r) for r in rs)}
      </ol>
    </section>""" for m, rs in months.items())
        ledger = f"""    <div class="ledger-head" aria-hidden="true"><span>Date</span><span>Report</span><span>Verdict</span></div>
{groups}"""
    n = len(reports)
    count = "1 report" if n == 1 else f"{n} reports"
    body = f"""{masthead("", "Reports")}

<main id="main">
  <div class="page-head">
    <h1>Reports</h1>
    <p class="lede">
      {count} filed by the <a href="{GH}/blob/main/skills/productivity/writing-reports/SKILL.md" target="_blank" rel="noopener">writing-reports</a> skill,
      newest first. Each row opens the full report.
    </p>{note}
  </div>
  <div class="ledger">
{ledger}
  </div>
</main>

{foot_band("Generated from <code>reports/YYYY-MM/*.md</code>", edition)}"""
    return page_html(title="Reports — my-hermes-skills", root="", css=REPORTS_CSS,
                     body=body, canonical=REPORTS_CANONICAL)


def write_report_indexes(reports: list, edition: str) -> None:
    """Write canonical docs/reports.html plus the legacy docs/daily-news.html route."""
    docs = REPO / "docs"
    (docs / "reports.html").write_text(reports_index_html(reports, edition))
    (docs / "daily-news.html").write_text(reports_index_html(reports, edition, COMPAT_NOTE))
    print(f"wrote {docs / 'reports.html'} + daily-news.html ({len(reports)} reports)")


# ---------------------------------------------------------------------------
# Changelog: every dated `## [x.y.z] - YYYY-MM-DD` section of skills/**/CHANGELOG.md
# ---------------------------------------------------------------------------

CHANGELOG_HEAD = re.compile(r"^## \[([^\]]+)\]\s*-\s*(\d{4}-\d{2}-\d{2})\s*$")


def find_changelog(skills: list) -> list:
    """One entry per dated version section, newest first, then by skill name.

    Undated sections (e.g. `## [Unreleased]`) are not published.
    """
    out = []
    for s in skills:
        p = REPO / s["rel_dir"] / "CHANGELOG.md"
        if not p.exists():
            continue
        cur = None
        for line in p.read_text().splitlines():
            m = CHANGELOG_HEAD.match(line)
            if m:
                cur = {"name": s["name"], "version": m[1], "date": m[2], "lines": []}
                out.append(cur)
            elif line.startswith("## "):
                cur = None
            elif cur is not None:
                cur["lines"].append(line)
    out.sort(key=lambda e: e["name"])
    out.sort(key=lambda e: e["date"], reverse=True)
    return out


def changes_html(lines: list) -> str:
    """Bullets (with indented continuations), `### Kind` labels, and plain paragraphs."""
    out, items = [], []

    def flush():
        if items:
            out.append("<ul>" + "".join(f"<li>{inline_md(i)}</li>" for i in items) + "</ul>")
            items.clear()

    for line in lines:
        t = line.strip()
        if not t:
            continue
        if t.startswith(("- ", "* ")):
            items.append(t[2:])
        elif items and line[:1] in (" ", "\t"):
            items[-1] += " " + t
        elif t.startswith("### "):
            flush()
            out.append(f'<p class="cl-kind">{inline_md(t[4:])}</p>')
        else:
            flush()
            out.append(f"<p>{inline_md(t)}</p>")
    flush()
    return "".join(out)


def changelog_row_html(e: dict) -> str:
    name, ver = html.escape(e["name"]), html.escape(e["version"])
    return f"""        <li class="cl-row" id="{name}-{ver}">
          <time class="r-date sc" datetime="{e["date"]}">{short_date(e["date"])}</time>
          <p class="cl-skill"><a href="index.html#entry-{name}">{name}</a><span class="sc">v{ver}</span></p>
          <div class="cl-changes">{changes_html(e["lines"])}</div>
        </li>"""


CHANGELOG_CSS = REPORTS_CSS + """
    .cl { --cols: 112px minmax(0, 1fr) minmax(0, 2fr); }
    .cl-row { display: grid; grid-template-columns: var(--cols); gap: 32px;
              padding: 12px 8px; border-bottom: 1px solid var(--hair); scroll-margin-top: 24px; }
    .cl-row:target { outline: 3px solid var(--ink); outline-offset: -3px; }
    .cl-skill { margin: 0; font: 700 17px/24px var(--display); overflow-wrap: anywhere; }
    .cl-skill a { text-decoration: none; }
    .cl-skill a:hover { text-decoration: underline 2px; text-underline-offset: 4px; }
    .cl-skill .sc { display: block; font-weight: 600; font-size: 15px; color: var(--muted); }
    .cl-changes { font-size: 15px; line-height: 24px; }
    .cl-changes p, .cl-changes ul { margin: 0; }
    .cl-changes ul { padding-left: 20px; list-style: square; }
    .cl-changes * + p, .cl-changes * + ul { margin-top: 8px; }
    .cl-changes code { font-size: 14px; }
    .cl-kind { font: 800 13px/20px var(--display); letter-spacing: 0.08em; text-transform: uppercase; }
    @media (max-width: 640px) {
      .cl-row { grid-template-columns: minmax(0, 1fr); gap: 4px; }
    }"""


def changelog_html(entries: list, edition: str) -> str:
    if not entries:
        ledger = '    <p class="lede">No changelog entries yet.</p>'
    else:
        months = {}
        for e in entries:
            months.setdefault(month_label(e["date"]), []).append(e)
        groups = "\n".join(
            f"""    <section class="month" aria-labelledby="m-{slugify(m)}">
      <h2 id="m-{slugify(m)}">{m}</h2>
      <ol class="rows">
{chr(10).join(changelog_row_html(e) for e in es)}
      </ol>
    </section>""" for m, es in months.items())
        ledger = f"""    <div class="ledger-head" aria-hidden="true"><span>Date</span><span>Skill</span><span>Changes</span></div>
{groups}"""
    n, k = len(entries), len({e["name"] for e in entries})
    count = (f"{n} {'entry' if n == 1 else 'entries'} across "
             f"{k} {'skill' if k == 1 else 'skills'}")
    body = f"""{masthead("", "Changelog")}

<main id="main">
  <div class="page-head">
    <h1>Changelog</h1>
    <p class="lede">
      {count}, newest first, from each skill's <code>CHANGELOG.md</code>.
      Every push that bumps a version is also published as a
      <a href="{GH}/releases" target="_blank" rel="noopener">GitHub release</a>.
    </p>
  </div>
  <div class="ledger cl">
{ledger}
  </div>
</main>

{foot_band("Generated from <code>skills/**/CHANGELOG.md</code>", edition)}"""
    return page_html(title="Changelog — my-hermes-skills", root="", css=CHANGELOG_CSS, body=body,
                     canonical="https://laansdole.github.io/my-hermes-skills/changelog.html")



def main() -> int:
    skills = find_skills()
    if not skills:
        print("error: no skills found under skills/", file=sys.stderr)
        return 1

    reports = find_reports()
    edition = edition_date(reports)
    write_report_pages(reports, edition)
    write_report_indexes(reports, edition)
    entries = find_changelog(skills)
    (REPO / "docs" / "changelog.html").write_text(changelog_html(entries, edition))
    print(f"wrote docs/changelog.html ({len(entries)} entries)")

    if "--json" in sys.argv:
        manifest = manifest_json(skills)
        json_out = REPO / "skills.json"
        json_out.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
        print(f"wrote {json_out} ({len(manifest['skills'])} skills)")
        return 0

    OUT.write_text(index_html(skills, edition))
    print(f"wrote {OUT} ({len(skills)} skills)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
