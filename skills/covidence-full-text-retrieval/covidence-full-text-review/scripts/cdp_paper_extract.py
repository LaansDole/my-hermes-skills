#!/usr/bin/env python3
"""Open a URL in a new Brave tab via CDP, extract full-text info, close the tab.

Used by Mode 3 (websearch_queue) of the covidence-full-text-review skill.

Usage: python3 cdp_paper_extract.py <url> [out_prefix]
For PDFs: fetches bytes through the tab (uses the browser session cookies, so
institutional/papers access applies), runs pdftotext, returns a text digest.
For HTML: extracts innerText + section excerpts directly.
Writes extracted text to <out_prefix>.txt when given.
Prints one JSON object: {ok, title, url, is_pdf, len, digest, error?}
"""
import asyncio, base64, json, os, subprocess, sys, urllib.parse, urllib.request, tempfile, websockets

# Papers-access profile CDP port (Research profile). Change per environment.
CDP = "http://127.0.0.1:9254"
DIGEST = 9000  # chars of text returned inline

async def cdp_get(path):
    with urllib.request.urlopen(CDP + path, timeout=5) as r:
        return json.loads(r.read().decode())

async def main(url, out_prefix):
    # 1. create new tab
    try:
        t = await cdp_get("/json/new?" + urllib.parse.quote(url, safe=""))
        target_id = t["id"]
    except Exception:
        ver = await cdp_get("/json/version")
        async with websockets.connect(ver["webSocketDebuggerUrl"], max_size=50*1024*1024) as ws:
            await ws.send(json.dumps({"id": 1, "method": "Target.createTarget", "params": {"url": url}}))
            while True:
                msg = json.loads(await ws.recv())
                if msg.get("id") == 1:
                    target_id = msg["result"]["targetId"]
                    break

    port = CDP.rsplit(":", 1)[-1]
    ws_url_page = f"ws://127.0.0.1:{port}/devtools/page/{target_id}"
    out = {"ok": True, "url": url}

    try:
        async with websockets.connect(ws_url_page, max_size=100*1024*1024) as ws:
            mid = 0
            async def send(method, params=None):
                nonlocal mid
                mid += 1
                await ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
                while True:
                    msg = json.loads(await asyncio.wait_for(ws.recv(), 40))
                    if msg.get("id") == mid:
                        return msg

            await send("Page.enable")
            await send("Runtime.enable")
            try:
                await asyncio.wait_for(ws.recv(), 30)
            except asyncio.TimeoutError:
                pass
            await asyncio.sleep(4)

            # detect pdf
            probe = await send("Runtime.evaluate", {"expression":
                "({isPdf: /(\\.pdf($|\\?))/i.test(location.href) || (document.contentType||'').includes('pdf'), title: document.title||'', href: location.href})",
                "returnByValue": True})
            info = probe.get("result", {}).get("result", {}).get("value", {})
            out.update(info)

            if info.get("isPdf"):
                # fetch bytes through tab (session cookies included)
                expr = ("fetch(location.href, {credentials:'include'})"
                        ".then(r => r.ok ? r.arrayBuffer() : Promise.reject('HTTP '+r.status))"
                        ".then(b => {const bytes=new Uint8Array(b); let bin='';"
                        "const CH=0x8000; for(let i=0;i<bytes.length;i+=CH){bin+=String.fromCharCode.apply(null,bytes.subarray(i,i+CH));}"
                        "return btoa(bin);})")
                msg = await send("Runtime.evaluate", {"expression": expr, "returnByValue": True, "awaitPromise": True})
                val = msg.get("result", {}).get("result", {}).get("value")
                if not val:
                    out["error"] = "pdf_fetch_failed"
                    out["digest"] = ""
                else:
                    pdf_bytes = base64.b64decode(val)
                    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
                    tmp.write(pdf_bytes); tmp.close()
                    txt = subprocess.run(["pdftotext", tmp.name, "-"], capture_output=True, text=True).stdout
                    os.unlink(tmp.name)
                    out["len"] = len(txt)
                    out["digest"] = txt[:DIGEST]
                    if out_prefix:
                        with open(out_prefix + ".txt", "w") as f:
                            f.write(txt)
            else:
                expr = r'''(() => {
                  let body = '';
                  if (document.body) body = document.body.innerText || '';
                  const len = body.length;
                  const headers = ['abstract','introduction','background','methods','method','study design','participants','results','discussion','conclusion','related work','materials and methods'];
                  const excerpts = [];
                  const lines = body.split('\n');
                  const re = new RegExp('^(' + headers.join('|') + ')\\b', 'i');
                  for (let i=0;i<lines.length;i++){
                    const l = lines[i].trim();
                    if (l.length>3 && l.length<90 && re.test(l) && excerpts.length<6){
                      const chunk = lines.slice(i, i+90).join(' ').replace(/\s+/g,' ').trim();
                      excerpts.push({h: l.slice(0,60), t: chunk.slice(0,1200)});
                      i += 60;
                    }
                  }
                  return {len, body, excerpts};
                })()'''
                msg = await send("Runtime.evaluate", {"expression": expr, "returnByValue": True})
                val = msg.get("result", {}).get("result", {}).get("value", {})
                out["len"] = val.get("len", 0)
                body = val.get("body", "")
                if out_prefix:
                    with open(out_prefix + ".txt", "w") as f:
                        f.write(body)
                # build digest: head + excerpts
                dig = body[:2500]
                for ex in val.get("excerpts", []):
                    dig += "\n\n[SEC:" + ex["h"] + "]\n" + ex["t"]
                out["digest"] = dig[:DIGEST]
    except Exception as e:
        out["error"] = f"extract_error: {e}"
        out["digest"] = ""
    finally:
        try:
            ver = await cdp_get("/json/version")
            async with websockets.connect(ver["webSocketDebuggerUrl"], max_size=10*1024*1024) as ws:
                await ws.send(json.dumps({"id": 1, "method": "Target.closeTarget", "params": {"targetId": target_id}}))
                await asyncio.sleep(0.5)
        except Exception:
            pass

    print(json.dumps(out))

if __name__ == "__main__":
    url = sys.argv[1]
    prefix = sys.argv[2] if len(sys.argv) > 2 else None
    asyncio.run(main(url, prefix))
