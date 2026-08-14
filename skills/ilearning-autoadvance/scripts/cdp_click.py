#!/usr/bin/env python3
"""Send trusted CDP Input mouse events to a target at given coordinates.

Usage: cdp_click.py <target-match> <x> <y> [--double]

IMPORTANT (ilearning-autoadvance v3.0.0): JS-dispatched MouseEvents do NOT
register in the Articulate Storyline player. Only trusted CDP
Input.dispatchMouseEvent works. The iframe fills the parent viewport, so
iframe element rect coordinates map 1:1 to page coordinates — pass the
element center from the probe directly.
"""
import asyncio
import json
import sys
import urllib.request

import websockets


async def find_target(match: str):
    with urllib.request.urlopen("http://localhost:9222/json", timeout=5) as r:
        targets = json.loads(r.read().decode())
    for t in targets:
        if t.get("type") == "page" and match in t.get("url", ""):
            return t
    return None


async def click(ws_url: str, x: int, y: int, double: bool = False, timeout: float = 20.0):
    async with websockets.connect(ws_url, max_size=10 * 1024 * 1024) as ws:
        mid = 0

        async def send(method, params):
            nonlocal mid
            mid += 1
            await ws.send(json.dumps({"id": mid, "method": method, "params": params}))
            while True:
                msg = json.loads(await asyncio.wait_for(ws.recv(), timeout))
                if msg.get("id") == mid:
                    return msg

        await send("Input.dispatchMouseEvent", {
            "type": "mousePressed", "x": x, "y": y, "button": "left",
            "buttons": 1, "clickCount": 1,
        })
        await send("Input.dispatchMouseEvent", {
            "type": "mouseReleased", "x": x, "y": y, "button": "left",
            "buttons": 0, "clickCount": 1,
        })
        if double:
            await send("Input.dispatchMouseEvent", {
                "type": "mousePressed", "x": x, "y": y, "button": "left",
                "buttons": 1, "clickCount": 2,
            })
            await send("Input.dispatchMouseEvent", {
                "type": "mouseReleased", "x": x, "y": y, "button": "left",
                "buttons": 0, "clickCount": 2,
            })
    return {"ok": True, "clicked": [x, y], "double": double}


async def main():
    match = sys.argv[1]
    x, y = int(sys.argv[2]), int(sys.argv[3])
    double = "--double" in sys.argv
    target = await find_target(match)
    if not target:
        print(json.dumps({"error": f"no page target matching '{match}'"}))
        return
    out = await click(target["webSocketDebuggerUrl"], x, y, double)
    print(json.dumps(out))


if __name__ == "__main__":
    asyncio.run(main())
