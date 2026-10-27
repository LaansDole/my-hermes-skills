#!/usr/bin/env python3
"""Tests for skills/productivity/demo-runbook/scripts (no browser, no ffmpeg).

Run:  python3 -m unittest -v tests.test_demo_runbook
"""

import importlib.util
import json
import re
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent / "skills/productivity/demo-runbook"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"{name}_under_test", SKILL / "scripts" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cv = _load("caption_video")
bp = _load("build_demo_page")


def _spec(captions, **extra):
    spec = {"date": "2026-10-27", "max_gap": 2.5, "captions": captions, **extra}
    for c in spec["captions"]:
        c["_t"] = cv.parse_wall(spec["date"], c["at"])
    return spec


class CaptionPlanTests(unittest.TestCase):
    def setUp(self):
        base = cv.parse_wall("2026-10-27", "10:00:00")
        # frames at 0, 1, 10 (idle gap 9 s -> capped to 2.5), 11 s
        self.rows = [("000000.jpg", base), ("000001.jpg", base + 1), ("000002.jpg", base + 10), ("000003.jpg", base + 11)]

    def test_parse_wall_accepts_fractional_seconds(self):
        self.assertAlmostEqual(cv.parse_wall("2026-10-27", "10:00:01.5") - cv.parse_wall("2026-10-27", "10:00:00"), 1.5)

    def test_caption_at_returns_last_started_caption(self):
        spec = _spec([{"at": "10:00:00", "line1": "a"}, {"at": "10:00:05", "line1": "b"}])
        t0 = cv.parse_wall("2026-10-27", "10:00:00")
        self.assertIsNone(cv.caption_at(spec["captions"], t0 - 1))
        self.assertEqual(cv.caption_at(spec["captions"], t0 + 4)["line1"], "a")
        self.assertEqual(cv.caption_at(spec["captions"], t0 + 5)["line1"], "b")

    def test_idle_gaps_are_capped_and_cards_added(self):
        spec = _spec([{"at": "10:00:00", "line1": "a"}], intro={"seconds": 6, "title": "T"}, outro={"seconds": 7, "title": "E"})
        entries, _, _ = cv.plan(self.rows, spec)
        self.assertEqual(entries[0][0], "__intro__")
        self.assertEqual(entries[-1][0], "__outro__")
        durations = [d for _, d, _ in entries]
        self.assertEqual(durations[1:4], [1.0, 2.5, 1.0])   # 9 s idle gap capped at 2.5

    def test_chapters_and_steps_use_video_time(self):
        spec = _spec(
            [{"at": "10:00:00", "chapter": "Setup", "list": "step one", "line1": "a"},
             {"at": "10:00:10", "chapter": "Run", "list": "step two", "line1": "b"}],
            intro={"seconds": 6, "title": "T", "chapter": "Intro"})
        _, chapters, steps = cv.plan(self.rows, spec)
        self.assertEqual([c["title"] for c in chapters], ["Intro", "Setup", "Run"])
        # "Run" starts at frame 2: intro 6 + 1 + 2.5 (capped) = 9.5 video seconds, not 16 wall seconds
        self.assertEqual(chapters[2]["t"], 9.5)
        self.assertEqual([(s["t"], s["list"]) for s in steps], [(6.0, "step one"), (9.5, "step two")])

    def test_example_captions_are_valid(self):
        spec = cv.load_spec(SKILL / "templates/captions.example.json")
        self.assertTrue(spec["captions"])
        for cap in spec["captions"]:
            self.assertIn("line1", cap)
            self.assertIn("label", cap)


class PageBuildTests(unittest.TestCase):
    def setUp(self):
        self.template = (SKILL / "templates/demo.html").read_text()
        self.page = json.loads((SKILL / "templates/page.example.json").read_text())

    def test_build_fills_every_placeholder(self):
        out = bp.build(self.page, [{"title": "Intro", "t": 0.0}], [{"t": 7.2, "list": "3.1 Open"}], self.template)
        self.assertEqual(re.findall(r"\{\{[A-Z_]+\}\}", out), [])
        self.assertIn('<li data-t="7.2">', out)
        self.assertIn('<span class="chapter" data-t="0.0">Intro</span>', out)

    def test_chapter_sorts_before_step_at_same_time(self):
        html = bp.steps_html([{"title": "Run", "t": 5.0}], [{"t": 5.0, "list": "go"}])
        self.assertLess(html.index("chapter"), html.index("<li"))

    def test_plain_fields_are_escaped(self):
        page = dict(self.page, title="A <b> & B")
        out = bp.build(page, [], [], self.template)
        self.assertIn("A &lt;b&gt; &amp; B", out)

    def test_missing_placeholder_value_is_an_error(self):
        with self.assertRaises(SystemExit):
            bp.build(self.page, [], [], self.template + "{{NOT_A_FIELD}}")

    def test_published_examples_have_no_machine_local_paths(self):
        for name in ("page.example.json", "captions.example.json", "demo.html", "pages.yml"):
            text = (SKILL / "templates" / name).read_text()
            self.assertNotRegex(text, r"/Users/|/home/", name)


if __name__ == "__main__":
    unittest.main()
