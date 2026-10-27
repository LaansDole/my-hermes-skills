"""Full-page screenshots of a URL at several viewport widths (layout and line-break check).

Uses the sandbox Chrome on CDP_PORT (default 9333).
Usage: python3 shots_widths.py <url> <out_prefix> <w1,w2,...>
"""
import base64
import json
import os
import sys
import time
import urllib.request

import websocket  # pip install websocket-client

PORT = int(os.environ.get("CDP_PORT", "9333"))

url, prefix, widths = sys.argv[1], sys.argv[2], [int(w) for w in sys.argv[3].split(",")]
with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json", timeout=5) as r:
    ws_url = [t for t in json.loads(r.read()) if t.get("type") == "page"][0]["webSocketDebuggerUrl"]
ws = websocket.create_connection(ws_url, timeout=60, suppress_origin=True)
i = 0


def send(method, **params):
    global i
    i += 1
    ws.send(json.dumps({"id": i, "method": method, "params": params}))
    while True:
        m = json.loads(ws.recv())
        if m.get("id") == i:
            return m.get("result", {})


for w in widths:
    send("Emulation.setDeviceMetricsOverride", width=w, height=900, deviceScaleFactor=1, mobile=False)
    send("Page.navigate", url=url)
    time.sleep(2.5)
    h = send("Runtime.evaluate", expression="document.documentElement.scrollHeight", returnByValue=True)["result"]["value"]
    send("Emulation.setDeviceMetricsOverride", width=w, height=int(h), deviceScaleFactor=1, mobile=False)
    time.sleep(0.8)
    data = send("Page.captureScreenshot", format="png")["data"]
    open(f"{prefix}-{w}.png", "wb").write(base64.b64decode(data))
    print("saved", f"{prefix}-{w}.png", w, h)
