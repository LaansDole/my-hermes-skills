#!/usr/bin/env python3
"""iLearning auto-advance orchestrator — implements ilearning-autoadvance skill v3.

Drives the SCORM player tab (hclt.lms.hr.cloud.sap scorm2004contentplayer) over
raw CDP. Probe -> classify -> act -> log. Hands off (exits 0 with a JSON marker
on stdout) when it needs the agent: QUIZ_SLIDE, UNKNOWN streak, STUCK, STOP,
DONE, or CLICK_REPEAT (a card clicked more than once — must never happen).

Usage: python3 ilearn_orchestrator.py [max_modules] [session_id]

Run with /usr/bin/python3 (background shells' bare python3 lacks websockets).
ALWAYS kill all previously-started orchestrator sessions before starting a new
one — a stale process from older code keeps clicking and corrupts state.
"""
from collections import defaultdict
import asyncio
import datetime
import json
import os
import re
import sys
import time
import urllib.request

import websockets

MATCH = "scorm2004contentplayer"
TICK = 5
UNKNOWN_LIMIT = 6
NO_NEXT_TICKS = 12          # 60s without finding Next after SLIDE_DONE
STUCK_AFTER = 10            # failed next-clicks before STUCK handoff (transitions can take >10s)
MAX_MODULES = int(sys.argv[1]) if len(sys.argv) > 1 else 50
SESSION_ID = sys.argv[2] if len(sys.argv) > 2 else datetime.datetime.now().strftime("%Y%m%d-%H%M%S")

LOG_PATH = os.path.expanduser(f"~/.hermes/logs/ilearning-autoadvance-{SESSION_ID}.jsonl")
RESUME_PATH = os.path.expanduser("~/.hermes/logs/ilearning-autoadvance-resume.json")

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROBE_DEFAULT = os.path.join(_HERE, "ilearn_probe.js")
PROBE = open(os.environ.get("ILEARN_PROBE", _PROBE_DEFAULT)).read()

NAV_NAMES = re.compile(
    r"^(next|back|previous|pause|play|resume|submit|continue|replay|close|menu|"
    r"transcript|backbtn|nextbtn|exit|finish|complete|retry|restart)(\W|$)",
    re.I,
)
STATIC_NAMES = re.compile(
    r"(\.png|\.jpg|\.jpeg|\.gif|\.svg$|rectangle\s*\d*|triangle\s*\d*|parallelogram|"
    r"group|logo|hcl_lates|^f\d+\.png$|shape|oval|line \d|textbox)",
    re.I,
)


def log(entry: dict):
    entry["ts"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")


async def find_target(match: str):
    with urllib.request.urlopen("http://localhost:9222/json", timeout=5) as r:
        targets = json.loads(r.read().decode())
    for t in targets:
        if t.get("type") == "page" and match in t.get("url", ""):
            return t
    return None


async def evaluate(ws_url: str, expression: str, timeout: float = 25.0) -> dict:
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
                return {"error": result["exceptionDetails"].get("text", "exception")}
            return result.get("result", {})


async def probe(target) -> dict:
    out = await evaluate(target["webSocketDebuggerUrl"], PROBE)
    if "error" in out:
        return {"_error": out["error"]}
    try:
        return json.loads(out.get("value", "{}"))
    except Exception:
        return {"_error": "probe JSON parse failed", "raw": str(out)[:300]}


async def cdp_click(target, x: int, y: int, double: bool = False) -> dict:
    """Dispatch trusted CDP Input mouse events at page coordinates."""
    ws_url = target["webSocketDebuggerUrl"]
    async with websockets.connect(ws_url, max_size=10 * 1024 * 1024) as ws:
        mid = 0

        async def send(method, params):
            nonlocal mid
            mid += 1
            await ws.send(json.dumps({"id": mid, "method": method, "params": params}))
            while True:
                msg = json.loads(await asyncio.wait_for(ws.recv(), 20))
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
    return {"ok": True, "at": [x, y]}


def center(c: dict) -> tuple:
    r = c.get("clickRect") or c.get("rect") or {}
    return (int(r.get("x", 0) + r.get("w", 0) / 2),
            int(r.get("y", 0) + r.get("h", 0) / 2))


def click_key(c: dict) -> str:
    """Stable identity for click-tracking.

    Must match the dedupe identity (_phys_key): the physical click location
    (clickRect/stategroup rect, else own rect). Duplicate DOM layers of one
    card (frame image + label, stategroup + label, different modelIds) all
    resolve to the SAME physical location — so this key guarantees a card is
    never clicked twice, which is the hard user requirement. The human
    readable label is kept for logs via acc-text."""
    r = c.get("clickRect") or c.get("rect") or {}
    return f"{r.get('x')},{r.get('y')},{r.get('w')},{r.get('h')}"


def _phys_key(c: dict):
    """Physical identity of a click target: its clickRect (stategroup) if
    present, else its own rect. Duplicate DOM layers of one card share the
    same physical location even when acc-texts/modelIds differ (e.g. a frame
    image F12-01.png and its label 'Usage of' both resolve to the same
    stategroup)."""
    r = c.get("clickRect") or c.get("rect") or {}
    return (r.get("x"), r.get("y"), r.get("w"), r.get("h"))


def dedupe_by_acc(candidates: list) -> list:
    """Each card appears in multiple DOM layers (stategroup copy + plain label
    copy, frame image + label text — possibly different modelIds/acc-texts).
    Keep ONE candidate per PHYSICAL location, preferring the copy with the
    more meaningful acc-text (non-static, non-png, longer)."""
    by_phys = {}
    for c in candidates:
        key = _phys_key(c)
        if key[2] == 0 and key[3] == 0:
            continue
        cur = by_phys.get(key)
        if cur is None:
            by_phys[key] = c
            continue
        cur_acc = (cur.get("accText") or "").strip()
        new_acc = (c.get("accText") or "").strip()
        cur_bad = bool(re.search(r"\.(png|jpg|jpeg|gif)$|^f\d+", cur_acc, re.I)) or is_static(cur_acc)
        new_bad = bool(re.search(r"\.(png|jpg|jpeg|gif)$|^f\d+", new_acc, re.I)) or is_static(new_acc)
        if new_bad and not cur_bad:
            continue  # keep current (better acc-text)
        if cur_bad and not new_bad:
            by_phys[key] = c  # replace with the meaningful label
            continue
        if len(new_acc) > len(cur_acc):
            by_phys[key] = c  # tie-break: longer label
    return list(by_phys.values())


def is_background(c: dict) -> bool:
    """A clickRect that spans most of the slide content area is the background
    layer (e.g. Hcl_lates.png 1236x714), not an interactive target. Cards and
    buttons are much smaller. Skip anything covering >50% of the slide."""
    cr = c.get("clickRect") or c.get("rect") or {}
    w, h = cr.get("w", 0), cr.get("h", 0)
    return w * h > 0.5 * 1512 * 806


def is_nav(name: str) -> bool:
    return bool(name and (NAV_NAMES.match(name.strip()) or "button" in name.lower()))


def is_static(name: str) -> bool:
    if not name:
        return True
    # page counters ("02/29"), timers ("1s"), pure numbers
    if re.match(r"^\d{1,3}/\d{1,3}$", name.strip()) or re.match(r"^\d+s?$", name.strip()):
        return True
    return bool(STATIC_NAMES.search(name))


def classify(p: dict):
    """Return (state, reason)."""
    if p.get("_error"):
        return "UNKNOWN", p["_error"]
    if p.get("page") == "parent":
        if p.get("hasContinueBtn"):
            return "COURSE_OVERVIEW", "continue button on parent"
        return "UNKNOWN", "parent page, no continue btn: " + p.get("url", "")[:90]
    if p.get("page") == "error":
        return "UNKNOWN", p.get("error", "iframe inaccessible")
    if p.get("hostname") != "hclt.lms.hr.cloud.sap":
        return "STOP", f"hostname {p.get('hostname')} outside LMS"

    sl = p.get("sl", {})
    title = (sl.get("slideTitle") or "").lower()
    scene_title = ""
    idx = sl.get("currentIdx")
    scene_slides = sl.get("sceneSlides") or []
    if isinstance(idx, int) and 0 <= idx < len(scene_slides):
        scene_title = (scene_slides[idx].get("title") or "").lower()

    playing = p.get("playing", 0)
    quiz_inputs = p.get("quizInputs") or []

    # QUIZ detection
    if quiz_inputs or any(k in (title + " " + scene_title) for k in
                          ("quiz", "question", "assessment", "multiple choice")):
        return "QUIZ_SLIDE", f"quiz inputs={len(quiz_inputs)} title='{title or scene_title}'"

    if playing > 0:
        return "TIMELINE_PLAYING", f"audio playing={playing}"

    # clickable topics: meaningful, non-static, non-nav, in the content area.
    # Static-named elements ("Oval 2") are KEPT when they carry a stategroup
    # clickRect — that means they are real interactive targets, not decoration.
    clickables = []
    for c in p.get("visibleClickables", []):
        name = (c.get("accText") or "").strip()
        if not name or is_nav(name) or is_background(c):
            continue
        if not c.get("clickRect") and is_static(name):
            continue
        clickables.append(c)
    instructions = p.get("instructions") or []
    if instructions:
        # USER RULE: interactive targets exist ONLY when the slide itself
        # mentions "Click ...". The term cards are everything non-static/non-nav
        # that is NOT the instruction banner or the slide title.
        interactive = [c for c in clickables
                       if not re.search(r"click|select|choose|tap|press|drag|hover|rollover|know (the|its)|see (the|its)|view (the|its)",
                                        (c.get("accText") or ""), re.I)
                       and (c.get("accText") or "").strip().lower() != title
                       and (c.get("rect") or {}).get("y", 999) >= 100]
        interactive = dedupe_by_acc(interactive)
        if interactive:
            return "INTERACTIVE_SLIDE", f"{len(interactive)} interactive topic(s) e.g. '{interactive[0].get('accText')}'"

    # Next affordance
    has_std_next = p.get("hasNext") and p.get("nextAriaHidden") != "true"
    next_clickables = [c for c in p.get("visibleClickables", []) if
                       is_nav(c.get("accText")) and "next" in (c.get("accText") or "").lower()]
    has_png_next = len(next_clickables) > 0

    # USER RULE: otherwise it is a normal slide — click Next.
    if has_std_next or has_png_next:
        return "SLIDE_DONE", f"next available (std={has_std_next} png={has_png_next})"
    return "UNKNOWN", "no playing audio, no quiz, no click instructions, no next"


def load_resume_state() -> dict:
    try:
        with open(RESUME_PATH) as f:
            data = json.load(f)
        return data.get("slides", {})
    except Exception:
        return {}


def save_resume_state(slide_id: str, clicked_ids: set, clicked_accs: set, counts: dict):
    data = {"slides": {}}
    try:
        with open(RESUME_PATH) as f:
            data = json.load(f)
    except Exception:
        pass
    data.setdefault("slides", {})[slide_id] = {
        "clicked_model_ids": sorted(clicked_ids),
        "clicked_acc_texts": sorted(clicked_accs),
        "click_counts": dict(counts),
        "updated": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    tmp = RESUME_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=1)
    os.replace(tmp, RESUME_PATH)


async def main():
    target = await find_target(MATCH)
    if not target:
        print(json.dumps({"handoff": "STOP", "reason": f"no player tab matching {MATCH}"}))
        return

    state = {
        "modules_advanced": 0,
        "unknown_streak": 0,
        "last_slide_id": None,
        "no_change_ticks": 0,
        "last_action": None,
        "clicked_model_ids": set(),
        "clicked_acc_texts": set(),
        "click_counts": defaultdict(int),
        "submitted_quiz_ids": set(),
        "slide_done_ticks": 0,
        "last_3_slide_ids": [],
        "start": time.monotonic(),
    }
    resume_slides = load_resume_state()
    p0 = await probe(target)
    cur_id = (p0.get("sl") or {}).get("slideId")
    if cur_id and cur_id in resume_slides:
        prev = resume_slides[cur_id]
        state["clicked_model_ids"] = set(prev.get("clicked_model_ids", []))
        state["clicked_acc_texts"] = set(prev.get("clicked_acc_texts", []))
        state["click_counts"] = defaultdict(int, prev.get("click_counts", {}))
        log({"slide": (p0.get("sl") or {}).get("slideTitle"), "state": "RESUME",
             "reason": f"seeded {len(state['clicked_acc_texts'])} previously-clicked cards",
             "cards_clicked": dict(state["click_counts"]), "module": 0})

    while True:
        p = await probe(target)
        slide_id = (p.get("sl") or {}).get("slideId")
        slide_title = (p.get("sl") or {}).get("slideTitle") or ""
        st, reason = classify(p)

        # Real slide transition after a Next click — clear per-slide click
        # history ONLY then (failed Next clicks keep state so cards are never
        # re-clicked on the same slide).
        if state["last_action"] == "next-click" and slide_id != state["last_slide_id"]:
            state["clicked_model_ids"] = set()
            state["clicked_acc_texts"] = set()
            state["click_counts"] = defaultdict(int)
            state["last_action"] = None
            log({"slide": slide_title, "state": "TRANSITION",
                 "reason": "slide advanced, per-slide click state reset",
                 "module": state["modules_advanced"]})

        log({"slide": slide_title, "slideId": slide_id, "state": st, "reason": reason,
             "audio_playing": p.get("playing", 0), "module": state["modules_advanced"]})

        if st == "STOP":
            print(json.dumps({"handoff": "STOP", "reason": reason, "slide": slide_title,
                              "modules_advanced": state["modules_advanced"]}))
            return

        if st == "UNKNOWN":
            state["unknown_streak"] += 1
            if state["unknown_streak"] > UNKNOWN_LIMIT:
                print(json.dumps({"handoff": "UNKNOWN", "reason": reason, "slide": slide_title,
                                  "probe": p, "modules_advanced": state["modules_advanced"]}))
                return
            await asyncio.sleep(TICK)
            continue
        state["unknown_streak"] = 0

        if st == "COURSE_OVERVIEW":
            print(json.dumps({"handoff": "COURSE_OVERVIEW",
                              "reason": "Launch/Continue button on parent page — needs agent click + tab retarget",
                              "modules_advanced": state["modules_advanced"]}))
            return

        if st == "TIMELINE_PLAYING":
            await asyncio.sleep(TICK)
            continue

        if st == "QUIZ_SLIDE":
            print(json.dumps({"handoff": "QUIZ", "reason": reason, "slide": slide_title,
                              "probe": p, "modules_advanced": state["modules_advanced"]}))
            return

        if st == "INTERACTIVE_SLIDE":
            clickables = [c for c in p.get("visibleClickables", []) if
                          (not is_static(c.get("accText")) or c.get("clickRect"))
                          and not is_nav(c.get("accText"))
                          and not is_background(c)]
            instructions = p.get("instructions") or []
            if instructions:
                interactive = [c for c in clickables
                               if not re.search(r"click|select|choose|tap|press|drag|hover|rollover|know (the|its)|see (the|its)|view (the|its)",
                                                (c.get("accText") or ""), re.I)
                               and (c.get("accText") or "").strip().lower() != (slide_title or "").lower()
                               and (c.get("rect") or {}).get("y", 999) >= 100]
                interactive = dedupe_by_acc(interactive)
            else:
                interactive = []
            target_c = None
            for c in interactive:
                key = click_key(c)
                if key and key not in state["clicked_acc_texts"]:
                    target_c = c
                    break
            if not target_c:
                # all cards clicked and audio finished — slide should now
                # enable Next. Fall through to SLIDE_DONE handling.
                log({"slide": slide_title, "state": st,
                     "action": "all-cards-clicked", "ok": True,
                     "cards_clicked": dict(state["click_counts"]),
                     "module": state["modules_advanced"]})
                st = "SLIDE_DONE"
                reason = "all interactive cards clicked"
            else:
                x, y = center(target_c)
                r = await cdp_click(target, x, y)
                acc = (target_c.get("accText") or "").strip() or click_key(target_c)
                key = click_key(target_c)
                state["clicked_acc_texts"].add(key)
                state["click_counts"][key] += 1
                if state["click_counts"][key] > 1:
                    print(json.dumps({
                        "handoff": "CLICK_REPEAT",
                        "reason": f"card '{acc}' clicked {state['click_counts'][key]} times",
                        "click_counts": dict(state["click_counts"]),
                        "slide": slide_title, "probe": p,
                        "modules_advanced": state["modules_advanced"]}))
                    return
                state["last_action"] = f"click topic:{acc}"
                log({"slide": slide_title, "state": st, "action": state["last_action"],
                     "ok": r.get("ok"), "click_count": state["click_counts"].get(key, 1),
                     "cards_clicked": dict(state["click_counts"]),
                     "detail": str(r)[:200], "module": state["modules_advanced"]})
                save_resume_state(slide_id or "", state["clicked_model_ids"],
                                  state["clicked_acc_texts"], state["click_counts"])
                await asyncio.sleep(2)
                continue

        if st == "SLIDE_DONE":
            if state["last_action"] == "next-click" and slide_id == state["last_slide_id"]:
                state["no_change_ticks"] += 1
            else:
                state["no_change_ticks"] = 0

            if state["no_change_ticks"] >= STUCK_AFTER:
                print(json.dumps({"handoff": "STUCK", "reason": "slideId unchanged after 3 next-clicks",
                                  "slide": slide_title, "slideId": slide_id,
                                  "probe": p, "modules_advanced": state["modules_advanced"]}))
                return

            state["slide_done_ticks"] += 1
            if state["slide_done_ticks"] > NO_NEXT_TICKS:
                print(json.dumps({"handoff": "STOP", "reason": "no next found after 60s",
                                  "slide": slide_title, "modules_advanced": state["modules_advanced"]}))
                return

            # find next button (PNG slide-object or standard)
            acc = ""
            next_c = None
            for c in p.get("visibleClickables", []):
                name = (c.get("accText") or "").lower()
                if "next" in name or "continue" in name or "complete" in name or "finish" in name:
                    acc = c.get("accText") or ""
                    next_c = c
                    break
            if not acc:
                await asyncio.sleep(TICK)
                continue
            state["last_slide_id"] = slide_id
            x, y = center(next_c)
            r = await cdp_click(target, x, y)
            state["last_action"] = "next-click"
            state["slide_done_ticks"] = 0
            state["modules_advanced"] += 1
            log({"slide": slide_title, "state": st, "action": f"next:{acc}",
                 "ok": r.get("ok"), "detail": str(r)[:200], "module": state["modules_advanced"]})
            if state["modules_advanced"] >= MAX_MODULES:
                print(json.dumps({"handoff": "DONE", "reason": f"reached max_modules={MAX_MODULES}",
                                  "slide": slide_title, "modules_advanced": state["modules_advanced"],
                                  "elapsed_s": round(time.monotonic() - state["start"], 1)}))
                return
            await asyncio.sleep(4)
            continue

        await asyncio.sleep(TICK)


if __name__ == "__main__":
    asyncio.run(main())
