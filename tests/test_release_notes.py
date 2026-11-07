#!/usr/bin/env python3
"""Tests for scripts/release_notes.py.

Run:  python3 -m unittest -v tests.test_release_notes
"""

import importlib.util
import unittest
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "release_notes_under_test", Path(__file__).resolve().parent.parent / "scripts" / "release_notes.py")
rn = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rn)

CL = """# Changelog — x

## [2.10.0] - 2026-11-08

- New thing.

## [2.1.0] - 2026-11-01

- Old thing.
"""


class ReleaseNotesTest(unittest.TestCase):
    def test_section_stops_at_next_heading_and_matches_exact_version(self):
        self.assertEqual(rn.changelog_section(CL, "2.10.0"), "- New thing.")
        self.assertEqual(rn.changelog_section(CL, "2.1.0"), "- Old thing.")
        self.assertIsNone(rn.changelog_section(CL, "2.1"))

    def test_bumped_includes_new_and_changed_versioned_skills_only(self):
        old = {"a": "1.0.0", "b": "1.0.0", "c": ""}
        new = {"a": "1.0.0", "b": "1.1.0", "c": "", "d": "0.1.0", "e": ""}
        self.assertEqual(rn.bumped(old, new), ["b", "d"])


if __name__ == "__main__":
    unittest.main()
