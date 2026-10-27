"""Tiny raw-CDP driver for a sandbox headless Chrome.

Usage (CDP_PORT env, default 9333):
  python3 cdp.py nav <url>
  python3 cdp.py eval '<js>'            # awaits promises, prints JSON value
  python3 cdp.py shot <out.png>
  python3 cdp.py click <x> <y>
  python3 cdp.py type <file> [enter]    # focuses the first textarea, inserts file text
  python3 cdp.py enter
"""
import base64
import json
import os
import sys
import time
import urllib.request

import websocket  # pip install websocket-client

PORT = int(os.environ.get("CDP_PORT", "9333"))


def target() -> str:
    with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json", timeout=5) as r:
        pages = [t for t in json.loads(r.read()) if t.get("type") == "page"]
    return pages[0]["webSocketDebuggerUrl"]


class CDP:
    def __init__(self) -> None:
        # suppress_origin: Chrome rejects the default Origin header on remote-debugging sockets
        self.ws = websocket.create_connection(target(), timeout=120, suppress_origin=True)
        self.i = 0

    def send(self, method: str, **params):
        self.i += 1
        self.ws.send(json.dumps({"id": self.i, "method": method, "params": params}))
        while True:
            m = json.loads(self.ws.recv())
            if m.get("id") == self.i:
                return m


def enter(c: CDP) -> None:
    for t in ("keyDown", "keyUp"):
        c.send("Input.dispatchKeyEvent", type=t, key="Enter", code="Enter",
               windowsVirtualKeyCode=13, text="\r" if t == "keyDown" else None)


def main() -> None:
    c = CDP()
    cmd = sys.argv[1]
    if cmd == "nav":
        c.send("Emulation.setDeviceMetricsOverride", width=1600, height=1000, deviceScaleFactor=1, mobile=False)
        print(c.send("Page.navigate", url=sys.argv[2]).get("result"))
    elif cmd == "eval":
        r = c.send("Runtime.evaluate", expression=sys.argv[2], returnByValue=True, awaitPromise=True)
        print(json.dumps(r.get("result", {}).get("result", {}).get("value", r.get("result")), ensure_ascii=False)[:6000])
    elif cmd == "shot":
        r = c.send("Page.captureScreenshot", format="png")
        open(sys.argv[2], "wb").write(base64.b64decode(r["result"]["data"]))
        print("saved", sys.argv[2])
    elif cmd == "type":
        c.send("Runtime.evaluate", expression="document.querySelector('textarea').focus()")
        c.send("Input.insertText", text=open(sys.argv[2]).read().strip())
        if len(sys.argv) > 3 and sys.argv[3] == "enter":
            enter(c)
        print("typed")
    elif cmd == "enter":
        enter(c)
        print("enter")
    elif cmd == "click":
        x, y = float(sys.argv[2]), float(sys.argv[3])
        c.send("Input.dispatchMouseEvent", type="mouseMoved", x=x, y=y, button="none", buttons=0)
        time.sleep(0.4)
        for t, b in (("mousePressed", 1), ("mouseReleased", 0)):
            c.send("Input.dispatchMouseEvent", type=t, x=x, y=y, button="left", buttons=b, clickCount=1)
        print("clicked", x, y)


main()
