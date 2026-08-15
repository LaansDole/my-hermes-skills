#!/usr/bin/env python3
"""Silent full-text extractor for the Research Brave profile (CDP port 9254).

Strategy (most silent first):
  1. COOKIE MODE (default): attach CDP to an EXISTING tab (never creates one),
     read the profile's cookies via Network.getCookies, write a Netscape cookie
     jar, and download the URL with curl. No tab is created, the window is
     never raised, focus never moves.
  2. BACKGROUND TAB MODE (fallback): only when curl yields no usable content
     (JS-rendered pages / fetch-protected sites). Creates a tab with
     Target.createTarget({background:true}) which does NOT activate it, runs
     the in-page extraction, then closes the tab.

Usage: python3 cdp_paper_extract.py <url> [out_prefix]
For PDFs: pdftotext after download. For HTML: text-extraction.
Writes extracted text to <out_prefix>.txt when given.
Prints one JSON object: {ok, title, url, is_pdf, len, digest, error?, mode}
"""
import asyncio, base64, json, os, re, subprocess, sys, tempfile, urllib.parse, urllib.request, websockets

CDP = "http://127.0.0.1:9254"
DIGEST = 9000  # chars of text returned inline

# ---------------------------------------------------------------- helpers
def cdp_get(path):
    with urllib.request.urlopen(CDP + path, timeout=5) as r:
        return json.loads(r.read().decode())


def write_cookie_jar(cookies, path):
    """Convert CDP cookie objects to a Netscape cookie jar."""
    with open(path, "w") as f:
        f.write("# Netscape HTTP Cookie File\n")
        for c in cookies:
            domain = c.get("domain", "")
            if not domain:
                continue
            flags = "TRUE" if domain.startswith(".") else "FALSE"
            secure = "TRUE" if c.get("secure") else "FALSE"
            exp = c.get("expires", -1)
            if exp is None or exp < 0:
                exp = 2147483647  # session cookie -> far future
            http_only = "#HttpOnly_" if c.get("httpOnly") else ""
            f.write(f"{http_only}{domain}\t{flags}\t{c.get('path','/')}\t{secure}\t{int(exp)}\t{c.get('name','')}\t{c.get('value','')}\n")


def html_to_text(html: bytes) -> str:
    """Crude HTML -> visible text (fallback when no JS rendering available)."""
    text = html.decode("utf-8", errors="replace")
    text = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", "\n", text)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"').replace("&#39;", "'")
    text = re.sub(r"\n{3,}", "\n\n", text)
    lines = [l.strip() for l in text.split("\n")]
    return "\n".join(l for l in lines if l)


# ---------------------------------------------------------------- mode 1: cookie+curl
async def cookie_mode(url, out_prefix, ua=None, cookies=None):
    """Download via curl using the profile's session cookies. No tabs."""
    out = {"mode": "cookie"}
    jar = tempfile.NamedTemporaryFile(suffix=".cookies", delete=False)
    jar.close()
    try:
        write_cookie_jar(cookies or [], jar.name)
        dl = tempfile.NamedTemporaryFile(suffix=".dl", delete=False)
        dl.close()
        curl_cmd = ["curl", "-sL", "--max-time", "60", "-A",
                    ua or "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36",
                    "-b", jar.name, "-o", dl.name, url]
        p = subprocess.run(curl_cmd, capture_output=True, text=True, timeout=90)
        data = open(dl.name, "rb").read()
        os.unlink(dl.name)
        if p.returncode != 0 or len(data) < 1024:
            out["error"] = "download_failed"
            return out
        # sniff type
        head = data[:2048]
        if head.lstrip().startswith(b"%PDF"):
            out["is_pdf"] = True
            tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
            tmp.write(data); tmp.close()
            txt = subprocess.run(["pdftotext", tmp.name, "-"], capture_output=True, text=True).stdout
            os.unlink(tmp.name)
            out["len"] = len(txt)
            out["digest"] = txt[:DIGEST]
            if out_prefix:
                with open(out_prefix + ".txt", "w") as f:
                    f.write(txt)
        else:
            out["is_pdf"] = False
            body = html_to_text(data)
            out["len"] = len(body)
            out["digest"] = body[:DIGEST]
            if out_prefix:
                with open(out_prefix + ".txt", "w") as f:
                    f.write(body)
        return out
    finally:
        os.unlink(jar.name)


async def get_cookies_and_ua():
    """Attach to an existing page target, read cookies + UA. Never creates a tab."""
    tabs = [t for t in cdp_get("/json/list") if t.get("type") == "page"]
    if not tabs:
        return None, None, "no_page_tabs"
    ws_url = tabs[0]["webSocketDebuggerUrl"]
    cookies = []
    ua = None
    async with websockets.connect(ws_url, max_size=50 * 1024 * 1024) as ws:
        mid = 0
        async def send(method, params=None):
            nonlocal mid
            mid += 1
            await ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
            while True:
                msg = json.loads(await asyncio.wait_for(ws.recv(), 30))
                if msg.get("id") == mid:
                    return msg
        await send("Network.enable")
        r = await send("Network.getCookies")
        cookies = r.get("result", {}).get("cookies", [])
        r2 = await send("Runtime.enable")
        r2 = await send("Runtime.evaluate", {"expression": "navigator.userAgent", "returnByValue": True})
        ua = r2.get("result", {}).get("result", {}).get("value")
    return cookies, ua, None


# ---------------------------------------------------------------- mode 2: background tab
async def background_tab_mode(url, out_prefix):
    """Create a NON-activated tab (background:true), extract, close."""
    out = {"mode": "background_tab"}
    ver = cdp_get("/json/version")
    async with websockets.connect(ver["webSocketDebuggerUrl"], max_size=50 * 1024 * 1024) as ws:
        await ws.send(json.dumps({"id": 1, "method": "Target.createTarget",
                                  "params": {"url": url, "background": True}}))
        target_id = None
        while True:
            msg = json.loads(await asyncio.wait_for(ws.recv(), 30))
            if msg.get("id") == 1:
                target_id = msg["result"]["targetId"]
                break

    ws_url_page = f"ws://127.0.0.1:9254/devtools/page/{target_id}"
    try:
        async with websockets.connect(ws_url_page, max_size=100 * 1024 * 1024) as ws:
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
            # wait for load event (Cloudflare challenges can take several seconds)
            try:
                await asyncio.wait_for(ws.recv(), 45)
            except asyncio.TimeoutError:
                pass
            await asyncio.sleep(6)

            probe = await send("Runtime.evaluate", {"expression":
                "({isPdf: /(\\.pdf($|\\?))/i.test(location.href) || (document.contentType||'').includes('pdf'), title: document.title||'', href: location.href})",
                "returnByValue": True})
            info = probe.get("result", {}).get("result", {}).get("value", {})
            out.update(info)

            # if page looks like a bot challenge stub, wait for it to pass
            body_len_probe = await send("Runtime.evaluate", {"expression": "document.body ? document.body.innerText.length : 0", "returnByValue": True})
            bl = body_len_probe.get("result", {}).get("result", {}).get("value", 0)
            if not info.get("isPdf") and bl < 2000:
                await asyncio.sleep(8)
                probe = await send("Runtime.evaluate", {"expression":
                    "({isPdf: /(\\.pdf($|\\?))/i.test(location.href) || (document.contentType||'').includes('pdf'), title: document.title||'', href: location.href})",
                    "returnByValue": True})
                info = probe.get("result", {}).get("result", {}).get("value", {})
                out.update(info)

            if info.get("isPdf"):
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
                dig = body[:2500]
                for ex in val.get("excerpts", []):
                    dig += "\n\n[SEC:" + ex["h"] + "]\n" + ex["t"]
                out["digest"] = dig[:DIGEST]
    except Exception as e:
        out["error"] = f"extract_error: {e}"
        out["digest"] = ""
    finally:
        try:
            ver = cdp_get("/json/version")
            async with websockets.connect(ver["webSocketDebuggerUrl"], max_size=10 * 1024 * 1024) as ws:
                await ws.send(json.dumps({"id": 1, "method": "Target.closeTarget", "params": {"targetId": target_id}}))
                await asyncio.sleep(0.5)
        except Exception:
            pass
    return out


# ---------------------------------------------------------------- main
async def main(url, out_prefix):
    out = {"ok": True, "url": url}
    # try cookie mode first
    try:
        cookies, ua, err = await get_cookies_and_ua()
        if err:
            out["error"] = err
            print(json.dumps(out))
            return
        res = await cookie_mode(url, out_prefix, ua=ua, cookies=cookies)
        out.update(res)
        if not res.get("error") and res.get("len", 0) >= 1024:
            print(json.dumps(out))
            return
        # fall through to background tab if cookie mode produced nothing usable
    except Exception as e:
        out["error"] = f"cookie_mode_error: {e}"

    # fallback: background (non-activated) tab
    try:
        res = await background_tab_mode(url, out_prefix)
        out.update(res)
    except Exception as e:
        out["error"] = f"background_tab_error: {e}"
        out["digest"] = ""

    print(json.dumps(out))


if __name__ == "__main__":
    url = sys.argv[1]
    prefix = sys.argv[2] if len(sys.argv) > 2 else None
    asyncio.run(main(url, prefix))
