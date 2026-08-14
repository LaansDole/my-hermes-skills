#!/usr/bin/env python3
"""Capture a screenshot of a CDP target. Usage: cdp_shot.py <target-match> <out.png>"""
import asyncio
import base64
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


async def shot(ws_url: str, out_path: str, timeout: float = 20.0):
    async with websockets.connect(ws_url, max_size=50 * 1024 * 1024) as ws:
        mid = 0

        async def send(method, params):
            nonlocal mid
            mid += 1
            await ws.send(json.dumps({"id": mid, "method": method, "params": params}))
            while True:
                msg = json.loads(await asyncio.wait_for(ws.recv(), timeout))
                if msg.get("id") == mid:
                    return msg

        await send("Page.enable", {})
        r = await send("Page.captureScreenshot", {"format": "png"})
        data = r.get("result", {}).get("data")
        if not data:
            print(json.dumps({"error": "no screenshot data", "resp": str(r)[:300]}))
            return
        with open(out_path, "wb") as f:
            f.write(base64.b64decode(data))
        print(json.dumps({"ok": True, "path": out_path, "bytes": len(data)}))


async def main():
    match = sys.argv[1]
    out = sys.argv[2]
    target = await find_target(match)
    if not target:
        print(json.dumps({"error": f"no page target matching '{match}'"}))
        return
    await shot(target["webSocketDebuggerUrl"], out)


if __name__ == "__main__":
    asyncio.run(main())
