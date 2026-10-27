#!/usr/bin/env python3
"""Burn step captions into screencast frames and encode the demo MP4.

Usage: python3 caption_video.py <frames_dir> <captions.json> <out_dir> [--width 1280] [--crf 27]

<frames_dir> comes from record_screencast.py (JPEGs + times.txt). <captions.json> (see
templates/captions.example.json) lists captions keyed to WALL-CLOCK times of the recording
("HH:MM:SS" or "HH:MM:SS.f" on "date"), so each caption shows what is on screen at that moment.
Idle gaps between frames are capped at "max_gap" seconds; nothing else is cut.

Outputs in <out_dir>: <video>.mp4, chapters.json ([{title, t}]) and steps.json
([{t, label, line1, list}] for captions that carry a "list" entry), both in VIDEO seconds,
which build_demo_page.py turns into the clickable step list.
"""
import argparse
import datetime
import json
import os
import shutil
import subprocess
import sys

FONT_CANDIDATES = [
    ("/System/Library/Fonts/HelveticaNeue.ttc", 1, 0),          # macOS: bold face index 1, regular 0
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 0, None),
]


def parse_wall(date: str, hms: str) -> float:
    """Epoch seconds for 'HH:MM:SS' or 'HH:MM:SS.f' on date (local time, like times.txt)."""
    fmt = "%Y-%m-%d %H:%M:%S.%f" if "." in hms else "%Y-%m-%d %H:%M:%S"
    return datetime.datetime.strptime(f"{date} {hms}", fmt).timestamp()


def load_spec(path: str) -> dict:
    with open(path) as f:
        spec = json.load(f)
    for cap in spec["captions"]:
        cap["_t"] = parse_wall(spec["date"], cap["at"])
    spec["captions"].sort(key=lambda c: c["_t"])
    return spec


def caption_at(captions: list, t: float):
    """The last caption whose time is <= t (None before the first)."""
    cur = None
    for cap in captions:
        if cap["_t"] <= t:
            cur = cap
        else:
            break
    return cur


def read_times(frames_dir: str) -> list:
    rows = []
    with open(os.path.join(frames_dir, "times.txt")) as f:
        for line in f:
            if line.strip():
                name, t = line.split()
                rows.append((name, float(t)))
    return rows


def plan(rows: list, spec: dict) -> tuple:
    """Return (entries, chapters, steps).

    entries: [(source_frame_or_card, duration, wall_time_or_None)] in video order;
    chapters/steps carry VIDEO seconds. Intro/outro cards are optional.
    """
    max_gap = float(spec.get("max_gap", 2.5))
    intro_s = float(spec.get("intro", {}).get("seconds", 6)) if spec.get("intro") else 0.0
    outro_s = float(spec.get("outro", {}).get("seconds", 7)) if spec.get("outro") else 0.0
    entries = []
    if intro_s:
        entries.append(("__intro__", intro_s, None))
    for i, (name, t) in enumerate(rows):
        nxt = rows[i + 1][1] if i + 1 < len(rows) else t + 1.5
        entries.append((name, min(max(nxt - t, 0.04), max_gap), t))
    if outro_s:
        entries.append(("__outro__", outro_s, None))

    chapters = [{"title": spec["intro"].get("chapter", "Intro"), "t": 0.0}] if intro_s else []
    steps, seen_caps = [], set()
    vt = 0.0
    for _, dur, wall in entries:
        if wall is not None:
            cap = caption_at(spec["captions"], wall)
            if cap is not None and id(cap) not in seen_caps:
                seen_caps.add(id(cap))
                if cap.get("chapter"):
                    chapters.append({"title": cap["chapter"], "t": round(vt, 1)})
                if cap.get("list"):
                    steps.append({"t": round(vt, 1), "list": cap["list"], "label": cap.get("label", ""),
                                  "chapter": cap.get("chapter")})
        vt += dur
    return entries, chapters, steps


def _fonts():
    from PIL import ImageFont
    for path, bold, regular in FONT_CANDIDATES:
        if os.path.exists(path):
            def f(size, b=True, path=path, bold=bold, regular=regular):
                idx = bold if b else (regular if regular is not None else bold)
                return ImageFont.truetype(path, size, index=idx)
            return f
    return lambda size, b=True: ImageFont.load_default()


def draw_caption(img, cap, font):
    from PIL import Image, ImageDraw
    if cap is None:
        return img
    label, line1, line2 = cap.get("label", ""), cap.get("line1", ""), cap.get("line2", "")
    img = img.convert("RGBA")
    w, h = img.size
    bar_h = 118 if line2 else 84
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    d.rectangle([0, h - bar_h, w, h], fill=(15, 15, 20, 215))
    d.rectangle([0, h - bar_h, 10, h], fill=(66, 133, 244, 255))
    d.text((34, h - bar_h + 14), label.upper(), font=font(22), fill=(140, 180, 255, 255))
    d.text((34, h - bar_h + 42), line1, font=font(34), fill=(255, 255, 255, 255))
    if line2:
        d.text((34, h - bar_h + 84), line2, font=font(24, False), fill=(205, 205, 210, 255))
    return Image.alpha_composite(img, overlay).convert("RGB")


def draw_card(title, lines, size, font):
    from PIL import Image, ImageDraw
    img = Image.new("RGB", size, (17, 17, 22))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 14, size[1]], fill=(66, 133, 244))
    d.text((90, int(size[1] * 0.27)), title, font=font(64), fill=(255, 255, 255))
    y = int(size[1] * 0.27) + 110
    for ln in lines:
        d.text((90, y), ln, font=font(30, False), fill=(210, 210, 215))
        y += 50
    return img


def render(frames_dir, spec, out_dir, width=1280, crf=27):
    from PIL import Image
    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg not found")
    rows = read_times(frames_dir)
    entries, chapters, steps = plan(rows, spec)
    font = _fonts()
    work = os.path.join(out_dir, "frames")
    os.makedirs(work, exist_ok=True)
    size = Image.open(os.path.join(frames_dir, rows[0][0])).size
    files = []
    for src, dur, wall in entries:
        if src in ("__intro__", "__outro__"):
            card = spec["intro" if src == "__intro__" else "outro"]
            out = os.path.join(work, src.strip("_") + ".jpg")
            draw_card(card["title"], card.get("lines", []), size, font).save(out, quality=90)
        else:
            out = os.path.join(work, src)
            draw_caption(Image.open(os.path.join(frames_dir, src)), caption_at(spec["captions"], wall), font).save(out, quality=85)
        files.append((out, dur))
    lst = os.path.join(out_dir, "concat.txt")
    with open(lst, "w") as f:
        for path, dur in files:
            f.write(f"file '{os.path.abspath(path)}'\nduration {dur:.3f}\n")
        f.write(f"file '{os.path.abspath(files[-1][0])}'\n")
    mp4 = os.path.join(out_dir, spec.get("video", "demo.mp4"))
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst,
                    "-vf", f"fps=25,scale={width}:-2,format=yuv420p", "-c:v", "libx264", "-crf", str(crf),
                    "-preset", "slow", "-movflags", "+faststart", "-an", mp4], check=True)
    json.dump(chapters, open(os.path.join(out_dir, "chapters.json"), "w"), indent=1)
    json.dump(steps, open(os.path.join(out_dir, "steps.json"), "w"), indent=1)
    total = sum(d for _, d in files)
    print(f"wrote {mp4} ({total:.1f} s), {len(chapters)} chapters, {len(steps)} list steps")
    return mp4


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("frames_dir")
    ap.add_argument("captions")
    ap.add_argument("out_dir")
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--crf", type=int, default=27)
    a = ap.parse_args()
    os.makedirs(a.out_dir, exist_ok=True)
    render(os.path.abspath(a.frames_dir), load_spec(a.captions), os.path.abspath(a.out_dir), a.width, a.crf)


if __name__ == "__main__":
    main()
