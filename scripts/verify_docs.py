#!/usr/bin/env python3
"""Verify the generated docs/ site.

Usage:  python3 scripts/verify_docs.py

Regenerates the site, then checks routes and rendering the generator is
responsible for:

  - docs/reports.html exists and canonicalizes to /my-hermes-skills/reports.html
  - docs/daily-news.html still exists and points readers at reports.html
  - both root indexes list exactly one row link per discovered report markdown
  - every row target is a real generated file
  - every report page links back with ../../reports.html
  - the SemIf guide renders with its overview, CLI name, TOC, and source link
  - every table-of-contents href resolves to exactly one heading id
  - every table is wrapped in .table-scroll
  - the skills chart has one cell per SKILL.md, unique symbols, and every
    cell resolves to exactly one handbook entry
  - every chart family is one block holding only its own cells, each marked
  - every entry links SKILL.md and Source to paths that exist in the repo
  - every @font-face url resolves to a committed file under docs/fonts/
  - the light/dark toggle survives on index and report pages
  - CSS braces balance on every page
  - regenerating twice is byte-identical

Exit 0 = all green. Ad-hoc verification, not a test suite
(see tests/test_generate_docs_reports.py for those).
"""

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DOCS = REPO / "docs"
CANONICAL = "https://laansdole.github.io/my-hermes-skills/reports.html"
GH = "https://github.com/LaansDole/my-hermes-skills"
SEMIF = "reports/2026-09/2026-09-25-semif-openjev-integration-guide"

errors = []


def check(name: str, ok: bool) -> None:
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    if not ok:
        errors.append(name)


def generate() -> None:
    r = subprocess.run([sys.executable, str(REPO / "scripts" / "generate_docs.py")],
                       capture_output=True, text=True, cwd=REPO)
    if r.returncode != 0:
        print(f"FAIL: generator exit {r.returncode}: {r.stderr.strip()}")
        sys.exit(1)


def snapshot() -> dict:
    return {str(p.relative_to(DOCS)): p.read_bytes()
            for p in sorted(DOCS.rglob("*"))
            if p.is_file() and "superpowers" not in p.parts}


def css_balanced(page: str) -> bool:
    # an unclosed rule silently nests everything after it; nothing else catches this
    style = re.search(r"<style>\n(.*?)\n  </style>", page, re.S)
    return bool(style) and style.group(1).count("{") == style.group(1).count("}")


def fonts_resolve(page_path: Path, page: str) -> bool:
    urls = re.findall(r'url\("([^"]+)"\)', page)
    return bool(urls) and all((page_path.parent / u).resolve().is_file() for u in urls)


def main() -> int:
    generate()
    first = snapshot()

    sources = sorted((REPO / "reports").rglob("*.md"))
    index = (DOCS / "index.html").read_text()
    reports_page = (DOCS / "reports.html").read_text()
    compat_page = (DOCS / "daily-news.html").read_text()

    check("docs/reports.html canonical", f'<link rel="canonical" href="{CANONICAL}" />' in reports_page)
    check("docs/reports.html titled Reports", "<h1>Reports</h1>" in reports_page)
    check("docs/daily-news.html canonicalizes to reports.html",
          f'<link rel="canonical" href="{CANONICAL}" />' in compat_page)
    check("docs/daily-news.html routes to reports.html", 'href="reports.html"' in compat_page)
    check("skills index links Reports", '<a href="reports.html">Reports</a>' in index)

    for name, page in (("reports.html", reports_page), ("daily-news.html", compat_page)):
        hrefs = re.findall(r'<a class="report-row" href="([^"]+)"', page)
        check(f"{name}: {len(hrefs)} rows == {len(sources)} report sources",
              len(hrefs) == len(sources))
        check(f"{name}: every row target exists",
              all((DOCS / h).is_file() for h in hrefs))

    skill_count = sum(1 for p in (REPO / "skills").rglob("SKILL.md")
                      if re.search(r"^name:\s*\S", p.read_text(), re.M))
    chart = re.search(r'<ol class="chart">(.*?)</ol>', index, re.S)
    cells = re.findall(r'<a class="cell f-[a-z-]+" href="#(entry-[^"]+)"', chart.group(1)) if chart else []
    syms = re.findall(r'<span class="c-sym">([^<]+)</span>', chart.group(1)) if chart else []
    check(f"chart: {len(cells)} cells == {skill_count} SKILL.md files", len(cells) == skill_count)
    blocks = re.findall(r'<li class="fam-block" data-fam="([a-z-]+)".*?<ul class="fb-cells">(.*?)</ul>',
                        chart.group(1), re.S) if chart else []
    check("chart: one block per family, no block mixes families",
          bool(blocks) and len({f for f, _ in blocks}) == len(blocks)
          and all(set(re.findall(r'<a class="cell f-([a-z-]+)"', b)) == {f} for f, b in blocks))
    check("chart: every cell carries a family mark",
          len(re.findall(r'<span class="c-mark">[A-Z]{3}</span>', chart.group(1) if chart else "")) == len(cells))
    check("chart: symbols unique", len(syms) == len(cells) and len(set(syms)) == len(syms))
    check("chart: every cell resolves to exactly one entry",
          all(index.count(f'id="{c}"') == 1 for c in cells))
    entries = re.findall(r'<article class="entry" id="entry-[^"]+".*?</article>', index, re.S)
    links_ok = len(entries) == len(cells)
    for e in entries:
        md = re.search(rf'href="{GH}/blob/main/([^"]+/SKILL\.md)"[^>]*>SKILL\.md</a>', e)
        src = re.search(rf'href="{GH}/tree/main/([^"]+)"[^>]*>Source</a>', e)
        links_ok &= bool(md and src) and (REPO / md.group(1)).is_file() and (REPO / src.group(1)).is_dir()
    check("entries: SKILL.md + Source link to real repo paths", links_ok)
    check("index: theme toggle present", 'id="theme-toggle"' in index)
    root_pages = (("index.html", index), ("reports.html", reports_page), ("daily-news.html", compat_page))
    check("root pages: CSS braces balanced", all(css_balanced(t) for _, t in root_pages))
    check("root pages: @font-face files exist", all(fonts_resolve(DOCS / n, t) for n, t in root_pages))

    pages = sorted((DOCS / "reports").rglob("*.html"))
    check(f"{len(pages)} generated report pages == {len(sources)} sources",
          len(pages) == len(sources))

    back_ok = toc_ok = table_ok = theme_ok = css_ok = font_ok = True
    for p in pages:
        t = p.read_text()
        back_ok &= 'href="../../reports.html"' in t
        table_ok &= t.count("<table>") == t.count('<div class="table-scroll"><table>')
        theme_ok &= 'id="theme-toggle"' in t and 'localStorage.getItem("theme")' in t
        css_ok &= css_balanced(t)
        font_ok &= fonts_resolve(p, t)
        for target in re.findall(r'<a href="#([^"]+)"', t):
            hits = t.count('id="%s"' % target)
            if hits != 1:
                print(f"    {p.name}: anchor #{target} resolves {hits} times")
                toc_ok = False
    check("every report page links back to ../../reports.html", back_ok)
    check("every table wrapped in .table-scroll", table_ok)
    check("every TOC href resolves to exactly one heading id", toc_ok)
    check("report page CSS braces balanced", css_ok)
    check("report page @font-face files exist", font_ok)
    check("theme toggle present on every report page", theme_ok)
    check("theme toggle present on reports index",
          'id="theme-toggle"' in reports_page and ':root[data-theme="light"]' in reports_page)

    semif = DOCS / f"{SEMIF}.html"
    check("SemIf report generated", semif.is_file())
    if semif.is_file():
        t = semif.read_text()
        check("SemIf title", "SemIf (formerly OpenJev)" in t)
        check("SemIf 5-minute overview", 'id="5-minute-overview"' in t)
        check("SemIf semif-score CLI named", "semif-score" in t)
        check("SemIf table of contents", 'class="toc"' in t)
        check("SemIf markdown source link", f"blob/main/{SEMIF}.md" in t)
        check("SemIf row on reports index", f'href="{SEMIF}.html"' in reports_page)

    generate()
    check("deterministic (regen == identical)", snapshot() == first)

    if errors:
        print("\nFAILED:", ", ".join(errors))
        return 1
    print("\nAll checks passed (ad-hoc verification, not a suite run)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
