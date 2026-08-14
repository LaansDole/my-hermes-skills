#!/usr/bin/env python3
"""Evaluate JS in a specific Chrome tab via CDP WebSocket.

Usage:
  cdp_eval.py <target-match> <js-expression-file-or-'-'> [--sub KEY=VALUE ...]

Connects to the first page target whose URL contains <target-match> (use
"scorm2004contentplayer" for the iLearning player tab), runs the JS (read from
the file, or stdin if '-'), returns the JSON result. Any --sub KEY=VALUE pairs
replace {{KEY}} placeholders in the JS text.

Requires: python3 with `websockets` installed (use /usr/bin/python3 if the
bare python3 in background shells lacks it).
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


async def evaluate(ws_url: str, expression: str, timeout: float = 20.0) -> dict:
    async with websockets.connect(ws_url, max_size=50 * 1024 * 1024) as ws:
        await ws.send(json.dumps({"id": 1, "method": "Runtime.enable", "params": {}}))
        await asyncio.wait_for(ws.recv(), timeout)
        await ws.send(json.dumps({
            "id": 2, "method": "Runtime.evaluate",
            "params": {"expression": expression, "returnByValue": True, "awaitPromise": True},
        }))
        while True:
            msg = json.loads(await asyncio.wait_for(ws.recv(), timeout))
            if msg.get("id") != 2:
                continue
            result = msg.get("result", {})
            if "exceptionDetails" in result:
                return {"error": result["exceptionDetails"].get("text", "exception"),
                        "details": str(result["exceptionDetails"])[:500]}
            return result.get("result", {})


async def main():
    match = sys.argv[1]
    expr_src = sys.argv[2]
    subs = {}
    for arg in sys.argv[3:]:
        if arg.startswith("--sub="):
            arg = arg[len("--sub="):]
        if "=" in arg:
            k, v = arg.split("=", 1)
            subs[k] = v

    if expr_src == "-":
        expression = sys.stdin.read()
    else:
        with open(expr_src) as f:
            expression = f.read()
    for k, v in subs.items():
        expression = expression.replace("{{" + k + "}}", v)

    target = await find_target(match)
    if not target:
        print(json.dumps({"error": f"no page target matching '{match}'"}))
        return
    out = await evaluate(target["webSocketDebuggerUrl"], expression)
    print(json.dumps(out))


if __name__ == "__main__":
    asyncio.run(main())
