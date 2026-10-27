#!/usr/bin/env python3
"""Record a sandbox Chrome page as timestamped JPEG frames (CDP Page.startScreencast).

Usage: python3 record_screencast.py <frames_dir> <stop_file> [--port 9333]

Writes <frames_dir>/NNNNNN.jpg plus <frames_dir>/times.txt ("<file> <epoch seconds>" per line)
and stops when <stop_file> exists. Chrome only sends frames when the screen changes, so the
timestamps (not a fixed frame rate) carry the timing; caption_video.py rebuilds real durations.
"""
import argparse
import base64
import json
import os
import time
import urllib.request

import websocket  # pip install websocket-client


def page_ws_url(port: int) -> str:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=5) as r:
        pages = [t for t in json.loads(r.read()) if t.get("type") == "page"]
    if not pages:
        raise SystemExit(f"no page target on :{port}")
    return pages[0]["webSocketDebuggerUrl"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("frames_dir")
    ap.add_argument("stop_file")
    ap.add_argument("--port", type=int, default=int(os.environ.get("CDP_PORT", "9333")))
    ap.add_argument("--quality", type=int, default=80)
    ap.add_argument("--max-width", type=int, default=1600)
    ap.add_argument("--max-height", type=int, default=1000)
    a = ap.parse_args()

    os.makedirs(a.frames_dir, exist_ok=True)
    ws = websocket.create_connection(page_ws_url(a.port), timeout=2, suppress_origin=True)
    msg_id = 1
    ws.send(json.dumps({"id": msg_id, "method": "Page.startScreencast", "params": {
        "format": "jpeg", "quality": a.quality, "maxWidth": a.max_width, "maxHeight": a.max_height, "everyNthFrame": 1}}))
    n = 0
    with open(os.path.join(a.frames_dir, "times.txt"), "w") as times:
        while not os.path.exists(a.stop_file):
            try:
                m = json.loads(ws.recv())
            except websocket.WebSocketTimeoutException:
                continue
            if m.get("method") != "Page.screencastFrame":
                continue
            p = m["params"]
            name = f"{n:06d}.jpg"
            with open(os.path.join(a.frames_dir, name), "wb") as f:
                f.write(base64.b64decode(p["data"]))
            times.write(f"{name} {time.time():.3f}\n")
            times.flush()
            n += 1
            msg_id += 1
            ws.send(json.dumps({"id": msg_id, "method": "Page.screencastFrameAck", "params": {"sessionId": p["sessionId"]}}))
    msg_id += 1
    ws.send(json.dumps({"id": msg_id, "method": "Page.stopScreencast"}))
    print(f"frames={n}")


if __name__ == "__main__":
    main()
