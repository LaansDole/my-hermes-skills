#!/usr/bin/env python3
"""Regression tests for scripts/generate_docs.py (reports and the skills chart).

Pure helpers are imported straight from the generator; anything touching the
filesystem runs a *copy* of the generator inside a temporary fixture repo, so
the live reports/, skills/ and docs/ trees are never written to.

Run:  python3 -m unittest -v tests.test_generate_docs_reports
"""

import importlib.util
import json
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
GH = gd.GH

SKILL_MD = """---
name: fixture-skill
version: 1.0.0
description: Fixture skill used only by the generator tests.
tags: [fixture]
---

# fixture-skill
"""


def skill_md(name: str, version: str = "1.0.0") -> str:
    ver = f"version: {version}\n" if version else ""
    return f"---\nname: {name}\n{ver}description: Fixture {name}.\ntags: [fixture]\n---\n"


# Two mapped families, a nested child, a symbol collision (Dr) and an
# unmapped top-level dir that must land in Unfiled.
CHART_SKILLS = {
    "skills/productivity/demo-runbook/SKILL.md": skill_md("demo-runbook", "0.1.0"),
    "skills/productivity/dev-runbook/SKILL.md": skill_md("dev-runbook", ""),
    "skills/covidence-full-text-retrieval/SKILL.md": skill_md("covidence-full-text-retrieval"),
    "skills/covidence-full-text-retrieval/covidence-full-text-review/SKILL.md":
        skill_md("covidence-full-text-review", "2.0.0"),
    "skills/zz-unknown/SKILL.md": skill_md("zz-unknown"),
}

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


def build_fixture_repo(root: Path, reports: dict, skills: dict = None) -> None:
    """Minimal repo: a copy of the generator, given skills, docs/, given reports."""
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    shutil.copy2(GEN, root / "scripts" / "generate_docs.py")
    (root / "docs").mkdir(parents=True, exist_ok=True)
    files = dict(skills or {"skills/fixture-skill/SKILL.md": SKILL_MD})
    files.update(reports)
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)


def generate(root: Path, *args: str) -> None:
    r = subprocess.run(
        [sys.executable, str(root / "scripts" / "generate_docs.py"), *args],
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

    def test_lead_metadata_labels_drop_their_colon_only_under_the_title(self):
        md = ("# Title\n\n- **Date:** 2026-09-25\n- **Scope**: Fixture.\n\n"
              "## Body\n\n- **Hybrid:** keep it.\n")
        out = gd.md_to_html(md)
        self.assertIn("<li><strong>Date</strong> 2026-09-25</li>"
                      "<li><strong>Scope</strong> Fixture.</li>", out)
        self.assertIn("<li><strong>Hybrid:</strong> keep it.</li>", out)

    def test_tables_are_wrapped_for_horizontal_overflow(self):
        out = gd.md_to_html(LONG_REPORT)
        self.assertEqual(out.count("<table>"), 1)
        self.assertEqual(out.count('<div class="table-scroll"><table>'), 1)
        self.assertEqual(out.count("</table></div>"), 1)

    def test_numbered_sources_render_as_individual_linked_list_items(self):
        md = "## Sources\n\n[1] https://example.com/one — First source\n[2] https://example.com/two — Second source\n"
        out = gd.md_to_html(md)
        self.assertIn('<ol class="refs">', out)
        self.assertIn('<li id="ref-1" value="1">', out)
        self.assertIn('<li id="ref-2" value="2">', out)
        self.assertEqual(out.count("<li"), 2)
        self.assertIn('href="https://example.com/one"', out)
        self.assertIn('href="https://example.com/two"', out)

    def test_inline_citations_link_both_ways_with_a_hover_title(self):
        md = ("# T\n\n## Body\n\nClaim one [2]. Claim two [1, 2]. Not a ref [9]. "
              "Code `x[1]` stays. A [link](https://e.com) too. Once [3].\n\n"
              "| a | b |\n| --- | --- |\n| cell [1] | y |\n\n"
              "## References\n\n- First: <https://one.example/a>\n- Second title (2026): <https://two.example/b>\n"
              "- <https://three.example/c>\n")
        out = gd.md_to_html(md)
        # every marker links to its reference and carries the reference title for the preview
        self.assertIn('<a id="cite-2-1" href="#ref-2" data-ref="Second title (2026)"', out)
        self.assertIn('<a id="cite-1-1" href="#ref-1" data-ref="First"', out)
        self.assertIn('<a id="cite-1-2" href="#ref-1"', out)  # the table cell citation
        self.assertIn('<sup class="cite">[<a id="cite-1-1"', out)
        # the space before a marker is absorbed so the superscript sits on its word
        self.assertIn('Claim one<sup class="cite">', out)
        # GFM alignment hints survive as classes
        self.assertIn("al-right", gd.md_to_html("| a | n |\n| --- | ---: |\n| x | 1 |\n"))
        # unknown numbers and code are left alone
        self.assertIn("Not a ref [9].", out)
        self.assertIn("<code>x[1]</code>", out)
        # plain bullets in a References section are numbered in order
        self.assertIn('<li id="ref-1" value="1"><span class="ref-num">[1]</span> First:', out)
        self.assertIn('<li id="ref-2" value="2"><span class="ref-num">[2]</span> Second title (2026):', out)
        # back-links: a single citation gets one link, several get numbered links
        ref1 = out[out.index('id="ref-1"'):].split("</li>")[0]
        self.assertIn('href="#cite-1-1"', ref1)
        self.assertIn('href="#cite-1-2"', ref1)
        ref3 = out[out.index('id="ref-3"'):].split("</li>")[0]
        self.assertIn('class="ref-back" href="#cite-3-1"', ref3)
        # a URL-only reference falls back to its domain for the preview
        self.assertIn('data-ref="three.example"', out)
        # every citation anchor id is unique and every back-link target exists
        ids = re.findall(r'id="(cite-[^"]+)"', out)
        self.assertEqual(len(ids), len(set(ids)))
        for target in re.findall(r'href="#(cite-[^"]+)"', out):
            self.assertIn(target, ids)
        # headings never get citation markup
        self.assertNotIn("cite-", out[: out.index("<p>")])

    def test_reports_without_references_are_untouched_by_citation_pass(self):
        md = "# T\n\n## Body\n\nArray index [0] and [1] stay literal.\n"
        self.assertIn("Array index [0] and [1] stay literal.", gd.md_to_html(md))

    def test_symbols_are_unique_and_overrides_are_reserved_first(self):
        names = ["demo-runbook", "dev-runbook", "data-run", "d", "dr"]
        syms = gd.assign_symbols(names)
        self.assertEqual(len(set(syms.values())), len(names))
        self.assertEqual(syms["demo-runbook"], "Dr")
        for name, sym in syms.items():
            self.assertRegex(sym, r"^[A-Z][a-z0-9]$")
            self.assertEqual(sym[0], name[0].upper())

        # an override claims its symbol even when a later-derived name wants it
        old = dict(gd.SYMBOL_OVERRIDES)
        self.addCleanup(lambda: (gd.SYMBOL_OVERRIDES.clear(), gd.SYMBOL_OVERRIDES.update(old)))
        gd.SYMBOL_OVERRIDES.clear()
        gd.SYMBOL_OVERRIDES["dev-runbook"] = "Dr"
        syms = gd.assign_symbols(["demo-runbook", "dev-runbook"])
        self.assertEqual(syms["dev-runbook"], "Dr")
        self.assertNotEqual(syms["demo-runbook"], "Dr")


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
        # edition comes from the newest report, never the clock
        self.assertIn("Edition 25 Sep 2026", reports_html)
        self.assertIn("Edition 25 Sep 2026", index_html)
        self.assertIn(
            '<link rel="canonical" href="https://laansdole.github.io/'
            'my-hermes-skills/reports.html" />', reports_html)
        self.assertIn(
            '<link rel="canonical" href="https://laansdole.github.io/'
            'my-hermes-skills/reports.html" />', compat_html)
        self.assertIn('href="reports.html"', compat_html)

        # both root-level indexes list every report, pointing at generated HTML
        for page in (reports_html, compat_html):
            hrefs = re.findall(r'<a class="report-row" href="([^"]+)"', page)
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


class ChartTests(unittest.TestCase):
    """The skills chart: cells, symbols, entries, links, fonts, manifest."""

    @classmethod
    def setUpClass(cls):
        tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(tmp.cleanup)
        cls.root = Path(tmp.name)
        build_fixture_repo(cls.root, {
            "reports/2026-09/2026-09-25-long.md": LONG_REPORT,
        }, CHART_SKILLS)
        generate(cls.root)
        cls.index = (cls.root / "docs" / "index.html").read_text()
        cls.chart = re.search(r'<ol class="chart">(.*?)</ol>', cls.index, re.S).group(1)

    def test_one_cell_per_skill_in_chart_order(self):
        cells = re.findall(r'<a class="cell f-([a-z-]+)" href="#entry-([^"]+)"', self.chart)
        self.assertEqual(cells, [
            ("research", "covidence-full-text-retrieval"),
            ("research", "covidence-full-text-review"),  # child right after parent
            ("productivity", "demo-runbook"),
            ("productivity", "dev-runbook"),
            ("unfiled", "zz-unknown"),
        ])
        self.assertIn("child of 01", self.chart.split('href="#entry-covidence-full-text-review"')[1]
                      .split("</li>")[0])
        self.assertIn('aria-label="03 demo-runbook, Productivity, version 0.1.0"', self.chart)
        self.assertIn('aria-label="04 dev-runbook, Productivity, unversioned"', self.chart)

    def test_symbols_are_unique(self):
        syms = re.findall(r'<span class="c-sym">([^<]+)</span>', self.chart)
        self.assertEqual(len(syms), len(CHART_SKILLS))
        self.assertEqual(len(set(syms)), len(syms))

    def test_each_family_is_one_labelled_block_of_marked_cells(self):
        blocks = re.findall(
            r'<li class="fam-block" data-fam="([a-z-]+)"[^>]*>\s*'
            r'<p class="fb-h"><span>([^<]+)</span><span class="fb-n">(\d+)'
            r'.*?<ul class="fb-cells">(.*?)</ul>', self.chart, re.S)
        self.assertEqual([(slug, word, n) for slug, word, n, _ in blocks], [
            ("research", "Research", "2"),
            ("productivity", "Productivity", "2"),
            ("unfiled", "Unfiled", "1"),
        ])
        marks = {gd.slugify(f): m for f, (_, _, m) in gd.FAMILIES.items()}
        for slug, _, n, body in blocks:
            fams = re.findall(r'<a class="cell f-([a-z-]+)"', body)
            self.assertEqual(fams, [slug] * int(n), f"block {slug} mixes families")
            self.assertEqual(re.findall(r'<span class="c-mark">([^<]+)</span>', body),
                             [marks[slug]] * int(n), f"{slug} cells lack their mark")

    def test_every_cell_resolves_to_exactly_one_entry(self):
        for name in re.findall(r'href="#(entry-[^"]+)"', self.chart):
            self.assertEqual(self.index.count(f'id="{name}"'), 1, name)

    def test_entries_link_skill_md_and_source_to_real_paths(self):
        entries = re.findall(r'<article class="entry" id="entry-[^"]+".*?</article>', self.index, re.S)
        self.assertEqual(len(entries), len(CHART_SKILLS))
        for e in entries:
            md = re.search(rf'href="{GH}/blob/main/([^"]+/SKILL\.md)"[^>]*>SKILL\.md</a>', e)
            src = re.search(rf'href="{GH}/tree/main/([^"]+)"[^>]*>Source</a>', e)
            self.assertTrue(md and src, e[:120])
            self.assertTrue((self.root / md.group(1)).is_file(), md.group(1))
            self.assertTrue((self.root / src.group(1)).is_dir(), src.group(1))

    def test_font_faces_point_at_committed_fonts(self):
        report = (self.root / "docs/reports/2026-09/2026-09-25-long.html").read_text()
        for page, prefix in ((self.index, ""), (report, "../../")):
            urls = re.findall(r'url\("([^"]+)"\)', page)
            self.assertTrue(urls)
            for u in urls:
                self.assertTrue(u.startswith(prefix + "fonts/"), u)
                self.assertTrue((REPO / "docs" / u[len(prefix):]).is_file(), u)

    def test_manifest_keeps_section_titles_and_child_order(self):
        generate(self.root, "--json")
        manifest = json.loads((self.root / "skills.json").read_text())
        self.assertEqual([s["title"] for s in manifest["sections"]],
                         ["Research", "Productivity", "zz-unknown"])
        self.assertEqual([s["name"] for s in manifest["sections"][0]["skills"]],
                         ["covidence-full-text-retrieval", "covidence-full-text-review"])
        self.assertEqual(sorted(manifest["skills"][0]), sorted(
            ["name", "version", "description", "category", "path", "url"]))


class ChangelogTests(unittest.TestCase):
    """docs/changelog.html: dated sections only, newest first, bullets rendered."""

    def test_dated_sections_sorted_and_rendered(self):
        with tempfile.TemporaryDirectory() as d:
            for name, text in (
                    ("a", "# x\n\n## [Unreleased]\n\n- wip\n\n## [1.1.0] - 2026-11-02\n\n"
                          "### Fixed\n- one `x`\n  continued\n\n## [1.0.0] - 2026-10-01\n\n- old\n"),
                    ("b", "## [2.0.0] - 2026-11-02\n\nPlain note.\n")):
                (Path(d) / name).mkdir()
                (Path(d) / name / "CHANGELOG.md").write_text(text)
            old = gd.REPO
            gd.REPO = Path(d)
            try:
                entries = gd.find_changelog([{"name": n, "rel_dir": n} for n in ("b", "a")])
            finally:
                gd.REPO = old
        self.assertEqual([(e["name"], e["version"]) for e in entries],
                         [("a", "1.1.0"), ("b", "2.0.0"), ("a", "1.0.0")])
        self.assertEqual(gd.changes_html(entries[0]["lines"]),
                         '<p class="cl-kind">Fixed</p><ul><li>one <code>x</code> continued</li></ul>')
        self.assertEqual(gd.changes_html(entries[1]["lines"]), "<p>Plain note.</p>")


if __name__ == "__main__":
    unittest.main()
