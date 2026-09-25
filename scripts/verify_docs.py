#!/usr/bin/env python3
"""Verify the generated Reports section of the docs/ site.

Usage:  python3 scripts/verify_docs.py

Regenerates the site, then checks routes and rendering the generator is
responsible for:

  - docs/reports.html exists and canonicalizes to /my-hermes-skills/reports.html
  - docs/daily-news.html still exists and points readers at reports.html
  - both root indexes list exactly one card per discovered report markdown
  - every card target is a real generated file
  - every report page links back with ../../reports.html
  - the SemIf guide renders with its overview, CLI name, TOC, and source link
  - every table-of-contents href resolves to exactly one heading id
  - every table is wrapped in .table-scroll
  - the light/dark toggle survives on index and report pages
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
        hrefs = re.findall(r'<a class="card card-report" href="([^"]+)"', page)
        check(f"{name}: {len(hrefs)} cards == {len(sources)} report sources",
              len(hrefs) == len(sources))
        check(f"{name}: every card target exists",
              all((DOCS / h).is_file() for h in hrefs))

    pages = sorted((DOCS / "reports").rglob("*.html"))
    check(f"{len(pages)} generated report pages == {len(sources)} sources",
          len(pages) == len(sources))

    back_ok = toc_ok = table_ok = theme_ok = True
    for p in pages:
        t = p.read_text()
        back_ok &= 'href="../../reports.html"' in t
        table_ok &= t.count("<table>") == t.count('<div class="table-scroll"><table>')
        theme_ok &= 'id="theme-toggle"' in t and 'localStorage.getItem("theme")' in t
        for target in re.findall(r'<a href="#([^"]+)"', t):
            hits = t.count('id="%s"' % target)
            if hits != 1:
                print(f"    {p.name}: anchor #{target} resolves {hits} times")
                toc_ok = False
    check("every report page links back to ../../reports.html", back_ok)
    check("every table wrapped in .table-scroll", table_ok)
    check("every TOC href resolves to exactly one heading id", toc_ok)
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
        check("SemIf card on reports index", f'href="{SEMIF}.html"' in reports_page)

    generate()
    check("deterministic (regen == identical)", snapshot() == first)

    if errors:
        print("\nFAILED:", ", ".join(errors))
        return 1
    print("\nAll checks passed (ad-hoc verification, not a suite run)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
