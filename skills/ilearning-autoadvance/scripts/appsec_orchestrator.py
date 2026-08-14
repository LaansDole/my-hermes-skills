#!/usr/bin/env python3
"""Application Security (Appsec_may12) course auto-advance orchestrator.

Direct HTML SVG-slide course at
  https://hclt.lms.hr.cloud.sap/icontent_e/CUSTOM_fra/hcl/self-managed/LSS/Appsec_may12/index_lms.html
Format: SVG slide deck inside the page (no iframe), PREV/NEXT buttons in a
bottom player bar, per-slide audio elements (do not auto-play), slide number
in the footer, occasional interactive SVG elements and quiz questions.

User rule: click NEXT whenever possible; search for clickable items on slides.

Usage:
  /usr/bin/python3 appsec_orchestrator.py [max_slides] [session_id]

Prints one JSON handoff line and exits 0 on QUIZ/STUCK/DONE/UNKNOWN.
"""
import asyncio
import json
import sys
import urllib.request
import datetime

import websockets

TARGET = "index_lms.html"
MAX_SLIDES = int(sys.argv[1]) if len(sys.argv) > 1 else 60
SESSION_ID = sys.argv[2] if len(sys.argv) > 2 else datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
LOG_PATH = f"/Users/laansdole/.hermes/logs/ilearning-autoadvance-{SESSION_ID}.jsonl"

PROBE_JS = r"""
(() => {
  const out = {};
  // buttons: add csDisabled flag for the CSS-class disabled state (this course
  // greys buttons via class, NOT the disabled attribute)
  const btns = [...document.querySelectorAll('button')].map(b => {
    const r = b.getBoundingClientRect();
    return {text: (b.textContent||'').trim(), cls: String(b.className||'').slice(0,40),
      vis: getComputedStyle(b).display !== 'none' && r.width > 0 && r.height > 0,
      disabled: b.disabled, csDisabled: String(b.className||'').includes('cs-disabled'),
      rect: {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)}};
  }).filter(b => b.vis);
  out.nextBtn = btns.find(b => b.text === 'NEXT') || null;
  out.prevBtn = btns.find(b => b.text === 'PREV') || null;
  out.otherBtns = btns.filter(b => !['NEXT','PREV'].includes(b.text));
  // audio playing state
  const audios = [...document.querySelectorAll('audio')].filter(a => a.duration > 1);
  out.playing = audios.filter(a => !a.paused && !a.ended).map(a => Math.round(a.currentTime) + '/' + Math.round(a.duration));
  out.audioPlayingCount = audios.filter(a => !a.paused && !a.ended).length;
  // slide number in footer: "<n> Copyright" on the same line (nbsp-separated)
  const bodyText = document.body.innerText;
  const m = bodyText.match(/(\d+)\s*(?:\u00a0|\s)*Copyright/i);
  out.page = m ? m[1] : null;
  // interactive SVG elements (cursor pointer, not player bar, not hyperlinks)
  out.svgClickables = [...document.querySelectorAll('svg *')].filter(e => {
    const st = getComputedStyle(e);
    const r = e.getBoundingClientRect();
    if (r.width < 8 || r.height < 8 || r.y > 780) return false;
    if (e.closest && e.closest('a')) return false;  // external hyperlinks are not course interactions
    return st.cursor === 'pointer' || e.hasAttribute('onclick');
  }).map(e => {
    const r = e.getBoundingClientRect();
    return {text: (e.textContent||'').trim().replace(/\s+/g,' ').slice(0, 40),
      rect: {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)}};
  }).filter((c, i, arr) => arr.findIndex(x => x.rect.x === c.rect.x && x.rect.y === c.rect.y) === i);
  // quiz inputs / submit
  out.inputs = [...document.querySelectorAll('input[type="radio"], input[type="checkbox"], input[type="text"], textarea')].filter(e => {
    const r = e.getBoundingClientRect();
    return r.width > 0 && r.y < 780;
  }).map(e => {
    const r = e.getBoundingClientRect();
    return {type: e.type, id: e.id, checked: e.checked, disabled: e.disabled,
      rect: {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)}};
  });
  out.submitBtn = btns.find(b => b.text.toUpperCase().includes('SUBMIT') && b.rect.y > 0 && b.rect.y < 780) || null;
  // instruction text mentioning click
  out.instructions = (bodyText.match(/[^\n]*(click|select|choose|tap|press)[^\n]*/gi) || []).slice(0, 4).map(s => s.trim().slice(0, 70));
  // main heading text from SVG
  out.heading = [...document.querySelectorAll('svg text, svg tspan')].map(t => t.textContent.trim()).filter(t => t.length > 6 && t.length < 60).slice(0, 2).join(' | ');
  return JSON.stringify(out);
})()
"""

CLICK_JS = "JSON.stringify({ok:true})"  # clicks are dispatched via CDP, not JS


async def find_target(match: str):
    with urllib.request.urlopen("http://localhost:9222/json", timeout=5) as r:
        targets = json.loads(r.read().decode())
    for t in targets:
        if t.get("type") == "page" and match in t.get("url", ""):
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
    last_page = None
    no_change = 0
    slides = 0
    wait_ticks = 0

    for _ in range(600):
        p = await eval_js(ws, PROBE_JS)
        if not p:
            await asyncio.sleep(5)
            continue
        try:
            p = json.loads(p) if isinstance(p, str) else p
        except Exception:
            await asyncio.sleep(5)
            continue

        page = p.get("page")
        heading = p.get("heading") or ""
        inputs = p.get("inputs", [])
        submit = p.get("submitBtn")
        svgClickables = p.get("svgClickables", [])
        nextBtn = p.get("nextBtn")
        playing = p.get("playing", [])

        # Quiz detection
        if inputs and len(inputs) > 0:
            log({"state": "QUIZ", "page": page, "heading": heading, "inputs": len(inputs)})
            print(json.dumps({"handoff": "QUIZ", "reason": f"quiz inputs={len(inputs)}",
                              "page": page, "heading": heading, "probe": p}))
            return

        # page change = slide advanced
        if page and last_page and page != last_page:
            log({"state": "TRANSITION", "from": last_page, "to": page, "heading": heading})
            no_change = 0
            wait_ticks = 0
            slides += 1
            if slides >= MAX_SLIDES:
                print(json.dumps({"handoff": "DONE", "reason": f"max_slides={MAX_SLIDES}", "slides": slides}))
                return
        last_page = page or last_page

        # Wait out any audio (NEXT stays cs-disabled until narration ends)
        if playing or p.get("audioPlayingCount", 0) > 0:
            await asyncio.sleep(5)
            continue

        # USER RULE: NEXT has priority over everything. If NEXT is enabled, click it.
        if nextBtn and not nextBtn.get("disabled") and not nextBtn.get("csDisabled"):
            nx, ny = nextBtn["rect"]["x"] + nextBtn["rect"]["w"] // 2, nextBtn["rect"]["y"] + nextBtn["rect"]["h"] // 2
            await click(ws, nx, ny)
            log({"state": "CLICK", "action": "next", "at": [nx, ny], "page": page, "heading": heading})
            no_change += 1
            if no_change >= 6:
                print(json.dumps({"handoff": "STUCK", "reason": "next clicked 6x, page unchanged",
                                  "page": page, "probe": p}))
                return
            await asyncio.sleep(3)
            continue

        # NEXT exists but is disabled (audio mid-play / button greyed).
        # USER RULE: stop waiting after ~10s — hand off instead of sleeping forever.
        if nextBtn:
            wait_ticks += 1
            log({"state": "WAIT_NEXT", "page": page, "heading": heading, "tick": wait_ticks,
                 "csDisabled": nextBtn.get("csDisabled"), "audio": p.get("audioPlayingCount")})
            if wait_ticks >= 2:  # 2 x 5s = 10s
                print(json.dumps({"handoff": "STUCK", "reason": "NEXT disabled for 10s+ (audio stuck)",
                                  "page": page, "heading": heading, "probe": p, "wait_ticks": wait_ticks}))
                return
            await asyncio.sleep(5)
            continue

        # Interactive slide: NEXT unavailable, click SVG targets (dedupe by rect)
        if svgClickables:
            log({"state": "CLICKABLE", "targets": svgClickables, "page": page})
            print(json.dumps({"handoff": "INTERACTIVE", "reason": f"{len(svgClickables)} svg clickables",
                              "page": page, "heading": heading, "probe": p}))
            return

        # Nothing to do
        log({"state": "UNKNOWN", "page": page, "heading": heading})
        print(json.dumps({"handoff": "UNKNOWN", "reason": "no next button, no clickables, no quiz",
                          "page": page, "probe": p}))
        return

    print(json.dumps({"handoff": "DONE", "reason": "iteration cap", "slides": slides}))


if __name__ == "__main__":
    asyncio.run(main())
