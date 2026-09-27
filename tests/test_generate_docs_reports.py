#!/usr/bin/env python3
"""Regression tests for the report side of scripts/generate_docs.py.

Pure helpers are imported straight from the generator; anything touching the
filesystem runs a *copy* of the generator inside a temporary fixture repo, so
the live reports/ and docs/ trees are never written to.

Run:  python3 -m unittest -v tests.test_generate_docs_reports
"""

import importlib.util
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
GEN = REPO / "scripts" / "generate_docs.py"


def _load_generator():
    spec = importlib.util.spec_from_file_location("generate_docs_under_test", GEN)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


gd = _load_generator()

SKILL_MD = """---
name: fixture-skill
version: 1.0.0
description: Fixture skill used only by the generator tests.
tags: [fixture]
---

# fixture-skill
"""

LONG_REPORT = """# Fixture Long Report

- **Date:** 2026-09-25
- **Scope:** Fixture.

---

## Verdict

It works.

---

## 1. What It Does

Body text.

### Field reference

| Field | Meaning |
| --- | --- |
| `id` | Row identifier. |
| `state` | Evidence. |

## 2. Naming Boundary

Body text.

```bash
# Torch: CUDA, MPS, or explicit CPU
pip install -e '.[test]'

## not a heading either
echo done
```

### Notes

First notes block.

## 3. Requirements

Body text.

### Notes

Second notes block, duplicate heading on purpose.

## 4. Deployment

Body text.
"""

SHORT_REPORT = """# Fixture Short Report

## Verdict

Short.

## Detail

One section only.
"""


def build_fixture_repo(root: Path, reports: dict) -> None:
    """Minimal repo: a copy of the generator, one skill, docs/, given reports."""
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    shutil.copy2(GEN, root / "scripts" / "generate_docs.py")
    skill = root / "skills" / "fixture-skill"
    skill.mkdir(parents=True, exist_ok=True)
    (skill / "SKILL.md").write_text(SKILL_MD)
    (root / "docs").mkdir(parents=True, exist_ok=True)
    for rel, text in reports.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)


def generate(root: Path) -> None:
    r = subprocess.run(
        [sys.executable, str(root / "scripts" / "generate_docs.py")],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        raise AssertionError(f"generator failed ({r.returncode}): {r.stderr}")


def docs_snapshot(root: Path) -> dict:
    docs = root / "docs"
    return {str(p.relative_to(docs)): p.read_bytes()
            for p in sorted(docs.rglob("*")) if p.is_file()}


class HelperTests(unittest.TestCase):
    """Pure functions: slugs, heading ids, table of contents, table wrappers."""

    def test_heading_ids_are_stable_and_duplicates_are_disambiguated(self):
        self.assertEqual(gd.slugify("5-minute overview"), "5-minute-overview")
        self.assertEqual(
            gd.slugify("Choosing Between `direct`, `serial`, and `shared`"),
            "choosing-between-direct-serial-and-shared")
        self.assertEqual(gd.slugify("**Bold** heading!"), "bold-heading")
        self.assertEqual(gd.slugify("7. Output API"), "7-output-api")
        self.assertEqual(gd.slugify("???"), "section")

        md = "## Notes\n\none\n\n## Notes\n\ntwo\n\n### Notes\n\nthree\n"
        out = gd.md_to_html(md)
        self.assertEqual(re.findall(r'<h[23] id="([^"]+)"', out),
                         ["notes", "notes-2", "notes-3"])
        # stable: same input renders byte-identically on a second call
        self.assertEqual(out, gd.md_to_html(md))

    def test_natural_suffix_slug_cannot_collide_with_a_disambiguated_id(self):
        # "Notes-2" slugifies to the id the second "Notes" would otherwise claim.
        md = "## Notes\n\none\n\n## Notes-2\n\ntwo\n\n## Notes\n\nthree\n"
        ids = [hid for _, _, hid in gd.heading_index(md.split("\n"))]
        self.assertEqual(ids, ["notes", "notes-2", "notes-3"])
        out = gd.md_to_html(md)
        self.assertEqual(re.findall(r'<h2 id="([^"]+)"', out), ids)

    def test_long_report_toc_targets_generated_heading_ids(self):
        out = gd.md_to_html(LONG_REPORT)
        hrefs = re.findall(r'<a href="#([^"]+)"', out)
        self.assertGreaterEqual(len(hrefs), 5, "long report should get a TOC")
        for href in hrefs:
            self.assertEqual(out.count(f'id="{href}"'), 1,
                             f"TOC target #{href} must exist exactly once")
        # duplicate H3 headings are still individually reachable
        self.assertIn("notes-2", hrefs)
        # TOC sits after the lead-in and before the first H2 section
        self.assertLess(out.index('class="toc"'), out.index("<h2 "))
        self.assertLess(out.index("<h1"), out.index('class="toc"'))

        # '#' lines inside a fence are shell comments, not headings: no id is
        # minted for them, they stay verbatim in the <pre>, and the heading
        # pass stays aligned with the rendered document.
        self.assertEqual(out.count("<h1"), 1)
        self.assertNotIn("torch-cuda-mps-or-explicit-cpu", out)
        self.assertNotIn("not-a-heading-either", out)
        self.assertIn("# Torch: CUDA, MPS, or explicit CPU", out)
        self.assertEqual(len(re.findall(r'<h[123] id="', out)),
                         len(re.findall(r"^#{1,3} ", LONG_REPORT, re.M)) - 2)

        short = gd.md_to_html(SHORT_REPORT)
        self.assertNotIn('class="toc"', short)

    def test_tables_are_wrapped_for_horizontal_overflow(self):
        out = gd.md_to_html(LONG_REPORT)
        self.assertEqual(out.count("<table>"), 1)
        self.assertEqual(out.count('<div class="table-scroll"><table>'), 1)
        self.assertEqual(out.count("</table></div>"), 1)

    def test_numbered_sources_render_as_individual_linked_list_items(self):
        md = "## Sources\n\n[1] https://example.com/one — First source\n[2] https://example.com/two — Second source\n"
        out = gd.md_to_html(md)
        self.assertIn("<ul>", out)
        self.assertIn("<li>[1]", out)
        self.assertIn("<li>[2]", out)
        self.assertEqual(out.count("<li>"), 2)
        self.assertIn('href="https://example.com/one"', out)
        self.assertIn('href="https://example.com/two"', out)


class FixtureRepoTests(unittest.TestCase):
    """Filesystem behaviour, exercised against a throwaway repo copy."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def test_reports_index_is_canonical_and_daily_news_is_compatible(self):
        build_fixture_repo(self.root, {
            "reports/2026-09/2026-09-25-long.md": LONG_REPORT,
            "reports/2026-09/2026-09-24-short.md": SHORT_REPORT,
        })
        generate(self.root)

        reports_html = (self.root / "docs" / "reports.html").read_text()
        compat_html = (self.root / "docs" / "daily-news.html").read_text()
        index_html = (self.root / "docs" / "index.html").read_text()

        self.assertIn("<h1>Reports</h1>", reports_html)
        self.assertIn(
            '<link rel="canonical" href="https://laansdole.github.io/'
            'my-hermes-skills/reports.html" />', reports_html)
        self.assertIn(
            '<link rel="canonical" href="https://laansdole.github.io/'
            'my-hermes-skills/reports.html" />', compat_html)
        self.assertIn('href="reports.html"', compat_html)

        # both root-level indexes list every report, pointing at generated HTML
        for page in (reports_html, compat_html):
            hrefs = re.findall(r'<a class="card card-report" href="([^"]+)"', page)
            self.assertEqual(sorted(hrefs), [
                "reports/2026-09/2026-09-24-short.html",
                "reports/2026-09/2026-09-25-long.html",
            ])
            for h in hrefs:
                self.assertTrue((self.root / "docs" / h).is_file(), h)

        # skills index routes to the canonical page, no stale label anywhere
        self.assertIn('<a href="reports.html">Reports</a>', index_html)
        self.assertNotIn("Daily News", index_html)
        self.assertNotIn("Daily News", reports_html)
        self.assertNotIn("Daily News", compat_html)

    def test_report_detail_uses_depth_aware_reports_route(self):
        build_fixture_repo(self.root, {
            "reports/2026-09/2026-09-25-long.md": LONG_REPORT,
        })
        generate(self.root)

        page = (self.root / "docs" / "reports" / "2026-09"
                / "2026-09-25-long.html").read_text()
        self.assertGreaterEqual(page.count('href="../../reports.html"'), 2)
        self.assertNotIn('href="daily-news.html"', page)
        self.assertNotIn("Daily News", page)
        self.assertIn('id="theme-toggle"', page)

    def test_stale_generated_report_pages_are_removed(self):
        build_fixture_repo(self.root, {
            "reports/2026-09/2026-09-25-long.md": LONG_REPORT,
            "reports/2026-09/2026-09-24-short.md": SHORT_REPORT,
        })
        generate(self.root)
        gen_dir = self.root / "docs" / "reports" / "2026-09"
        keeper = gen_dir / "2026-09-25-long.html"
        stale = gen_dir / "2026-09-24-short.html"
        self.assertTrue(stale.is_file())

        # non-HTML assets and files outside docs/reports/ must survive
        asset = gen_dir / "diagram.png"
        asset.write_bytes(b"png")
        outside = self.root / "docs" / "keep-me.html"
        outside.write_text("keep")

        (self.root / "reports" / "2026-09" / "2026-09-24-short.md").unlink()
        old_month = self.root / "docs" / "reports" / "2026-08"
        old_month.mkdir(parents=True, exist_ok=True)
        (old_month / "2026-08-01-gone.html").write_text("gone")
        generate(self.root)

        self.assertTrue(keeper.is_file())
        self.assertFalse(stale.exists())
        self.assertFalse(old_month.exists(), "emptied month dir should be removed")
        self.assertTrue(asset.is_file())
        self.assertTrue(outside.is_file())

    def test_private_and_noncanonical_report_paths_are_not_published(self):
        build_fixture_repo(self.root, {
            "reports/2026-09/2026-09-25-long.md": LONG_REPORT,
            "reports/2026-09/.private/2026-09-26-secret.md": SHORT_REPORT,
            "reports/2026-09/nested/2026-09-27-scratch.md": SHORT_REPORT,
            "reports/2026-09/session-notes.md": SHORT_REPORT,
        })
        generate(self.root)

        reports_html = (self.root / "docs" / "reports.html").read_text()
        self.assertIn("2026-09-25-long.html", reports_html)
        self.assertNotIn("secret", reports_html)
        self.assertNotIn("scratch", reports_html)
        self.assertNotIn("session-notes", reports_html)
        self.assertTrue((self.root / "docs/reports/2026-09/2026-09-25-long.html").is_file())
        self.assertFalse((self.root / "docs/reports/2026-09/.private/2026-09-26-secret.html").exists())
        self.assertFalse((self.root / "docs/reports/2026-09/nested/2026-09-27-scratch.html").exists())

    def test_report_generation_is_deterministic(self):
        build_fixture_repo(self.root, {
            "reports/2026-09/2026-09-25-long.md": LONG_REPORT,
            "reports/2026-09/2026-09-24-short.md": SHORT_REPORT,
        })
        generate(self.root)
        first = docs_snapshot(self.root)
        generate(self.root)
        self.assertEqual(first, docs_snapshot(self.root))


if __name__ == "__main__":
    unittest.main()
