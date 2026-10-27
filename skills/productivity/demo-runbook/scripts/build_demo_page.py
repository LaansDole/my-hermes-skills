#!/usr/bin/env python3
"""Build the demo page (video + clickable runbook steps) from templates/demo.html.

Usage: python3 build_demo_page.py <page.json> <caption_out_dir> <out.html>

<caption_out_dir> holds chapters.json and steps.json from caption_video.py (VIDEO seconds), so the
step list always matches the encoded video. <page.json>: see templates/page.example.json.
Plain-text fields are HTML-escaped; fields ending in _html are inserted as given.
"""
import html
import json
import os
import re
import sys

TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "templates", "demo.html")


def steps_html(chapters: list, steps: list) -> str:
    """Interleave chapter headings and list steps by video time (a chapter sorts before a step at the same time)."""
    items = [(c["t"], 0, f'      <span class="chapter" data-t="{c["t"]}">{html.escape(c["title"])}</span>') for c in chapters]
    items += [(s["t"], 1, f'      <li data-t="{s["t"]}"><span class="t"></span><span>{s["list"]}</span></li>') for s in steps]
    return "\n".join(line for _, _, line in sorted(items, key=lambda x: (x[0], x[1])))


def build(page: dict, chapters: list, steps: list, template: str) -> str:
    canonical = f'<link rel="canonical" href="{html.escape(page["canonical"])}">' if page.get("canonical") else ""
    values = {
        "TITLE": html.escape(page["title"]),
        "CANONICAL": canonical,
        "SUBTITLE": html.escape(page.get("subtitle", "")),
        "VIDEO": html.escape(page["video"]),
        "VIDEO_NOTE": html.escape(page.get("video_note", "Click any step in the list to jump there.")),
        "STEPS_HEADING": html.escape(page.get("steps_heading", "Steps in the video")),
        "STEPS_HTML": steps_html(chapters, steps),
        "EVIDENCE_HEADING": html.escape(page.get("evidence_heading", "What each run did")),
        "EVIDENCE_HTML": page.get("evidence_html", ""),
        "RUN_COMMANDS": html.escape("\n".join(page.get("run_commands", []))),
        "RUN_TEXT_HTML": page.get("run_text_html", ""),
        "FOOTER_HTML": page.get("footer_html", ""),
    }
    out = template
    for key, val in values.items():
        out = out.replace("{{" + key + "}}", val)
    left = re.findall(r"\{\{[A-Z_]+\}\}", out)
    if left:
        raise SystemExit(f"unfilled placeholders: {sorted(set(left))}")
    return out


def main() -> None:
    if len(sys.argv) != 4:
        raise SystemExit(__doc__)
    page = json.load(open(sys.argv[1]))
    chapters = json.load(open(os.path.join(sys.argv[2], "chapters.json")))
    steps = json.load(open(os.path.join(sys.argv[2], "steps.json")))
    out = build(page, chapters, steps, open(TEMPLATE).read())
    with open(sys.argv[3], "w") as f:
        f.write(out)
    print(f"wrote {sys.argv[3]} ({len(chapters)} chapters, {len(steps)} steps)")


if __name__ == "__main__":
    main()
