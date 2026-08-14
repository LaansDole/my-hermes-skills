#!/usr/bin/env python3
"""GoEthena course auto-advance orchestrator (COBEC / AML course).

The course runs in a cross-origin iframe (app.goethena.com) inside the
scorm2004contentplayer page. The iframe is its own CDP target, so we drive
it directly: probe its DOM, scroll the slide container to bottom (Continue
sits below the fold on long slides), click Continue, detect slide change.

Usage:
  /usr/bin/python3 goe_orchestrator.py [max_slides] [session_id]

Prints one JSON handoff line and exits 0 on QUIZ/STUCK/DONE.
"""
import asyncio
import json
import sys
import urllib.request
import datetime

import websockets

TARGET = "goethena.com/learning/assignments"
MAX_SLIDES = int(sys.argv[1]) if len(sys.argv) > 1 else 50
SESSION_ID = sys.argv[2] if len(sys.argv) > 2 else datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
LOG_PATH = f"/Users/laansdole/.hermes/logs/ilearning-autoadvance-{SESSION_ID}.jsonl"

PROBE_JS = r"""
(() => {
  const conts = [...document.querySelectorAll('button')].filter(b => /continue/i.test(b.textContent || '')).map(b => {
    const r = b.getBoundingClientRect();
    return {text: b.textContent.trim().slice(0, 20), rect: {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)},
      inViewport: r.top < window.innerHeight && r.bottom > 0 && r.width > 0, disabled: b.disabled};
  });
  const inputs = [...document.querySelectorAll('input[type="radio"], input[type="checkbox"], input[type="text"], textarea')]
    .map(i => ({type: i.type, id: i.id, checked: i.checked, disabled: i.disabled}));
  const scrollers = [...document.querySelectorAll('*')].filter(e => {
    const st = getComputedStyle(e);
    return (st.overflowY === 'auto' || st.overflowY === 'scroll') && e.scrollHeight > e.clientHeight + 5;
  }).map(e => ({cls: String(e.className||'').slice(0, 60), scrollH: e.scrollHeight, clientH: e.clientHeight,
    scrollTop: Math.round(e.scrollTop), y: Math.round(e.getBoundingClientRect().y)}));
  const h = document.querySelector('h1, h2, h3, [class*="title" i]');
  // all visible buttons (for quiz option detection)
  const btns = [...document.querySelectorAll('button')].filter(b => {
    const r = b.getBoundingClientRect(); const st = getComputedStyle(b);
    return r.width > 0 && r.height > 0 && st.visibility !== 'hidden' && st.display !== 'none';
  }).map(b => ({text: (b.textContent||'').trim().replace(/\s+/g,' ').slice(0, 50),
    rect: (() => { const r = b.getBoundingClientRect(); return {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)}; })(),
    disabled: b.disabled}));
  return JSON.stringify({
    title: document.title.slice(0, 90),
    heading: h ? h.textContent.trim().slice(0, 90) : null,
    continues: conts, inputs, scrollers, buttons: btns.slice(0, 20),
    bodyScrollH: document.body.scrollHeight, bodyClientH: document.body.clientHeight
  });
})()
"""

SCROLL_JS = r"""
(() => {
  const scrollers = [...document.querySelectorAll('*')].filter(e => {
    const st = getComputedStyle(e);
    return (st.overflowY === 'auto' || st.overflowY === 'scroll') && e.scrollHeight > e.clientHeight + 5;
  });
  let moved = false;
  for (const e of scrollers) {
    if (e.scrollHeight - e.scrollTop - e.clientHeight > 5) { e.scrollTop = e.scrollHeight; moved = true; }
  }
  // also nudge window scroll
  if (document.documentElement.scrollHeight > document.documentElement.clientHeight + 5) {
    window.scrollTo(0, document.documentElement.scrollHeight); moved = true;
  }
  return JSON.stringify({moved});
})()
"""


async def find_target(match: str):
    with urllib.request.urlopen("http://localhost:9222/json", timeout=5) as r:
        targets = json.loads(r.read().decode())
    for t in targets:
        if t.get("type") in ("page", "iframe") and match in t.get("url", ""):
            return t
    return None


async def send(ws_url: str, method: str, params: dict, timeout: float = 20.0):
    async with websockets.connect(ws_url, max_size=50 * 1024 * 1024) as ws:
        await ws.send(json.dumps({"id": 1, "method": method, "params": params}))
        while True:
            msg = json.loads(await asyncio.wait_for(ws.recv(), timeout))
            if msg.get("id") == 1:
                return msg


async def eval_js(ws_url: str, expression: str, timeout: float = 20.0) -> dict:
    r = await send(ws_url, "Runtime.evaluate",
                   {"expression": expression, "returnByValue": True, "awaitPromise": True}, timeout)
    return r.get("result", {}).get("result", {}).get("value")


async def click(ws_url: str, x: int, y: int):
    await send(ws_url, "Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y, "button": "left", "buttons": 1, "clickCount": 1})
    await send(ws_url, "Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y, "button": "left", "buttons": 0, "clickCount": 1})


def log(entry: dict):
    entry["ts"] = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    with open(LOG_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")


async def main():
    t = await find_target(TARGET)
    if not t:
        print(json.dumps({"handoff": "STOP", "reason": f"no target matching {TARGET}"}))
        return
    ws = t["webSocketDebuggerUrl"]
    last_heading = None
    no_change = 0
    slides = 0

    for _ in range(400):
        p = await eval_js(ws, PROBE_JS)
        if not p:
            await asyncio.sleep(5)
            continue
        try:
            p = json.loads(p) if isinstance(p, str) else p
        except Exception:
            await asyncio.sleep(5)
            continue

        heading = (p.get("heading") or p.get("title") or "")[:80]
        conts = p.get("continues", [])
        inputs = p.get("inputs", [])

        # Quiz detection: radio/checkbox inputs present
        if any(i["type"] in ("radio", "checkbox") for i in inputs):
            log({"state": "QUIZ", "heading": heading, "inputs": len(inputs)})
            print(json.dumps({"handoff": "QUIZ", "reason": f"quiz inputs={len(inputs)}",
                              "heading": heading, "probe": p}))
            return

        # heading change = slide advanced
        if heading and last_heading and heading != last_heading:
            log({"state": "TRANSITION", "from": last_heading, "to": heading})
            no_change = 0
            slides += 1
            if slides >= MAX_SLIDES:
                print(json.dumps({"handoff": "DONE", "reason": f"max_slides={MAX_SLIDES}", "slides": slides}))
                return
        last_heading = heading or last_heading

        # Find an enabled Continue in viewport; else scroll and retry
        cont = next((c for c in conts if c["inViewport"] and not c["disabled"]), None)
        if cont:
            cx, cy = cont["rect"]["x"] + cont["rect"]["w"] // 2, cont["rect"]["y"] + cont["rect"]["h"] // 2
            await click(ws, cx, cy)
            log({"state": "CLICK", "action": "continue", "at": [cx, cy], "heading": heading})
            no_change += 1
            if no_change >= 4:  # 4 clicks without heading change
                print(json.dumps({"handoff": "STUCK", "reason": "continue clicked 4x, no slide change",
                                  "heading": heading, "probe": p}))
                return
            await asyncio.sleep(3)
            continue

        # No visible Continue: scroll to bottom (Continue may be below fold)
        s = await eval_js(ws, SCROLL_JS)
        if s and s.get("moved"):
            log({"state": "SCROLL", "heading": heading})
            await asyncio.sleep(2)
            continue

        # Nothing scrollable and no Continue — maybe slide auto-advances or needs interaction
        log({"state": "UNKNOWN", "heading": heading, "buttons": len(p.get("buttons", []))})
        print(json.dumps({"handoff": "UNKNOWN", "reason": "no continue visible after scroll",
                          "heading": heading, "probe": p}))
        return

    print(json.dumps({"handoff": "DONE", "reason": "iteration cap", "slides": slides}))


if __name__ == "__main__":
    asyncio.run(main())
