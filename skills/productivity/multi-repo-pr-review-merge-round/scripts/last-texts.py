#!/usr/bin/env python3
"""Print the last assistant texts of the newest omp session for each cwd.

usage: last-texts.py [-n N] <abs-cwd> [...]
omp transcripts: ~/.omp/agent/sessions/<cwd-relative-to-HOME with / -> ->/*.jsonl
Records: type=="message" -> message.role=="assistant" -> message.content[] (type text).
"""
import glob, json, os, sys

args = sys.argv[1:]
n = 6
if args[:1] == ["-n"]:
    n, args = int(args[1]), args[2:]
home = os.path.expanduser("~")
for cwd in args:
    slug = os.path.abspath(cwd).replace(home, "", 1).replace("/", "-")
    files = sorted(glob.glob(f"{home}/.omp/agent/sessions/{slug}/*.jsonl"), key=os.path.getmtime)
    print(f"=== {cwd}")
    if not files:
        print("  (no session)")
        continue
    texts = []
    with open(files[-1]) as fh:
        for line in fh:
            try:
                r = json.loads(line)
            except ValueError:
                continue
            m = r.get("message") if r.get("type") == "message" else None
            if not m or m.get("role") != "assistant":
                continue
            for c in m.get("content", []):
                if c.get("type") == "text" and c.get("text", "").strip():
                    texts.append(c["text"].strip())
    for t in texts[-n:]:
        print("  -", t[:400].replace("\n", " "))
