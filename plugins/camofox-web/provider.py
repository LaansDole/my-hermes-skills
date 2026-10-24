"""web_search + web_extract through camofox-browser's REST API.

Search: open the engine's results page in a Camoufox tab, scrape result rows in-page, decode the
engine's redirect links to real URLs. DuckDuckGo's HTML endpoint is primary (real URLs, ~1 s);
Bing is the fallback. Google is not used: its result links are opaque /goto tokens.
Extract: render each URL, wait out Cloudflare-style interstitials, return the main text.
"""
from __future__ import annotations

import base64
import json
import logging
import time
import uuid
from typing import Any, Optional
from urllib.parse import parse_qs, quote_plus, urlparse

import httpx

from agent.web_search_provider import WebSearchProvider, get_provider_env

logger = logging.getLogger(__name__)

USER_ID = "hermes_web"
DEFAULT_ENGINES = ("duckduckgo", "bing")
CHALLENGE_TITLES = ("just a moment", "attention required", "checking your browser", "verify you are human",
                    "please wait", "ddos-guard")
EXTRACT_CHAR_CAP = 100_000

ENGINES: dict[str, tuple[str, str]] = {
    "duckduckgo": (
        "https://html.duckduckgo.com/html/?q={q}",
        """[...document.querySelectorAll('.result')].filter(r=>!r.classList.contains('result--ad')).map(r=>{
             const a=r.querySelector('a.result__a'); const s=r.querySelector('.result__snippet');
             return a && {title:a.innerText.trim(), url:a.href, description:s?s.innerText.trim():''}}).filter(Boolean)""",
    ),
    "bing": (
        "https://www.bing.com/search?setlang=en&cc=US&q={q}",
        """[...document.querySelectorAll('#b_results li.b_algo')].map(r=>{
             const a=r.querySelector('h2 a'); const s=r.querySelector('.b_caption p, p');
             return a && {title:a.innerText.trim(), url:a.href, description:s?s.innerText.trim():''}}).filter(Boolean)""",
    ),
}

EXTRACT_JS = """(() => {
  const pick = ['article', 'main', '[role=main]', '#content', '.post-content', '.entry-content', '.td-post-content'];
  let root = null;
  for (const sel of pick) { const el = document.querySelector(sel); if (el && el.innerText.trim().length > 400) { root = el; break; } }
  root = root || document.body;
  const clone = root.cloneNode(true);
  clone.querySelectorAll('script,style,noscript,nav,footer,header,aside,form,iframe,svg').forEach(e => e.remove());
  document.body.appendChild(clone); clone.style.display = 'block';
  const text = (clone.innerText || '').replace(/\\n{3,}/g, '\\n\\n').trim();
  clone.remove();
  return JSON.stringify({title: document.title, url: location.href, text});
})()"""


def _decode_url(href: str) -> str:
    """Strip DuckDuckGo (/l/?uddg=) and Bing (/ck/a?u=a1<base64url>) redirect wrappers."""
    try:
        p = urlparse(href)
        qs = parse_qs(p.query)
        if "duckduckgo.com" in p.netloc and "uddg" in qs:
            return qs["uddg"][0]
        if "bing.com" in p.netloc and p.path.startswith("/ck/") and "u" in qs:
            u = qs["u"][0]
            if u.startswith("a1"):
                b = u[2:]
                return base64.urlsafe_b64decode(b + "=" * (-len(b) % 4)).decode("utf-8", "replace")
    except Exception:  # pragma: no cover - best effort
        pass
    return href


class CamofoxClient:
    def __init__(self, base: str, api_key: str = "", timeout: float = 60.0):
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self.base = base.rstrip("/")
        self.http = httpx.Client(base_url=self.base, headers=headers, timeout=timeout)

    def close(self) -> None:
        self.http.close()

    def _req(self, method: str, path: str, **kw) -> dict[str, Any]:
        try:
            r = self.http.request(method, path, **kw)
        except httpx.ConnectError as exc:
            raise ValueError(f"Camofox server not reachable at {self.base} (run `camofox start`): {exc}") from exc
        if r.status_code >= 400:
            raise ValueError(f"Camofox {method} {path.split('?')[0]} -> HTTP {r.status_code}: {r.text[:200]}")
        return r.json() if r.content else {}

    def open_tab(self, url: str) -> str:
        return self._req("POST", "/tabs", json={"userId": USER_ID, "sessionKey": f"web-{uuid.uuid4().hex[:8]}", "url": url})["tabId"]

    def evaluate(self, tab: str, expression: str) -> Any:
        return self._req("POST", f"/tabs/{tab}/evaluate", json={"userId": USER_ID, "expression": expression}).get("result")

    def close_tab(self, tab: str) -> None:
        try:
            self.http.delete(f"/tabs/{tab}", params={"userId": USER_ID})
        except Exception:
            pass

    def wait_past_challenge(self, tab: str, max_wait: float = 20.0) -> None:
        """Camoufox usually clears Cloudflare's JS challenge by itself; poll the title until it does."""
        deadline = time.time() + max_wait
        while time.time() < deadline:
            title = str(self.evaluate(tab, "document.title") or "").lower()
            if not any(t in title for t in CHALLENGE_TITLES):
                return
            time.sleep(1.5)


class CamofoxWebProvider(WebSearchProvider):
    @property
    def name(self) -> str:
        return "camofox"

    @property
    def display_name(self) -> str:
        return "Camofox (Camoufox browser)"

    def _client(self) -> CamofoxClient:
        base = (get_provider_env("CAMOFOX_URL") or "").strip()
        if not base:
            raise ValueError("CAMOFOX_URL is not set")
        return CamofoxClient(base, (get_provider_env("CAMOFOX_API_KEY") or "").strip())

    def is_available(self) -> bool:
        return bool((get_provider_env("CAMOFOX_URL") or "").strip())

    def supports_search(self) -> bool:
        return True

    def supports_extract(self) -> bool:
        return True

    def get_setup_schema(self) -> dict[str, Any]:
        return {"name": "Camofox", "badge": "free · local", "tag": "Search + extract via a local Camoufox browser",
                "env_vars": [{"key": "CAMOFOX_URL", "prompt": "camofox-browser URL (e.g. http://localhost:9377)",
                              "url": "https://github.com/jo-inc/camofox-browser"}]}

    # ---- search -------------------------------------------------------------------------------
    def _engines(self) -> list[str]:
        raw = (get_provider_env("CAMOFOX_SEARCH_ENGINES") or "").strip()
        names = [e.strip().lower() for e in raw.split(",") if e.strip()] if raw else list(DEFAULT_ENGINES)
        return [e for e in names if e in ENGINES] or list(DEFAULT_ENGINES)

    def _search_engine(self, client: CamofoxClient, engine: str, query: str) -> list[dict[str, Any]]:
        url_tmpl, js = ENGINES[engine]
        tab = client.open_tab(url_tmpl.format(q=quote_plus(query)))
        try:
            client.wait_past_challenge(tab, max_wait=10)
            rows = json.loads(client.evaluate(tab, f"JSON.stringify({js})") or "[]")
        finally:
            client.close_tab(tab)
        out, seen = [], set()
        for r in rows:
            url = _decode_url(r.get("url", ""))
            if not url.startswith("http") or url in seen:
                continue
            seen.add(url)
            out.append({"title": r.get("title", ""), "url": url, "description": r.get("description", "")})
        return out

    def search(self, query: str, limit: int = 5) -> dict[str, Any]:
        limit = max(1, min(int(limit or 5), 20))
        errors: list[str] = []
        try:
            client = self._client()
        except ValueError as exc:
            return {"success": False, "error": str(exc)}
        try:
            for engine in self._engines():
                try:
                    rows = self._search_engine(client, engine, query)
                except Exception as exc:
                    errors.append(f"{engine}: {exc}")
                    logger.warning("camofox search via %s failed: %s", engine, exc)
                    continue
                if rows:
                    logger.info("camofox search '%s' via %s: %d results", query, engine, len(rows))
                    web = [{"title": r["title"], "url": r["url"], "description": r["description"], "position": i + 1}
                           for i, r in enumerate(rows[:limit])]
                    return {"success": True, "data": {"web": web}}
                errors.append(f"{engine}: no results")
        finally:
            client.close()
        return {"success": False, "error": "Camofox search failed: " + "; ".join(errors)}

    # ---- extract ------------------------------------------------------------------------------
    def _extract_one(self, client: CamofoxClient, url: str, max_chars: Optional[int]) -> dict[str, Any]:
        tab = client.open_tab(url)
        try:
            client.wait_past_challenge(tab)
            time.sleep(0.5)  # let late client-side rendering settle
            data = json.loads(client.evaluate(tab, EXTRACT_JS) or "{}")
        finally:
            client.close_tab(tab)
        text = data.get("text", "")
        cap = min(int(max_chars), EXTRACT_CHAR_CAP) if max_chars else EXTRACT_CHAR_CAP
        if not text.strip():
            return {"url": url, "title": data.get("title", ""), "content": "", "error": "page rendered no text"}
        title = data.get("title", "")
        if any(t in title.lower() for t in CHALLENGE_TITLES):
            return {"url": url, "title": title, "content": "", "error": "blocked by an anti-bot challenge"}
        content = text[:cap]
        return {"url": url, "title": title, "content": content, "raw_content": content,
                "metadata": {"sourceURL": data.get("url", url), "title": title}}

    def extract(self, urls: list[str], **kwargs: Any) -> list[dict[str, Any]]:
        try:
            client = self._client()
        except ValueError as exc:
            return [{"url": u, "title": "", "content": "", "error": str(exc)} for u in urls]
        results = []
        try:
            for u in urls:
                try:
                    results.append(self._extract_one(client, u, kwargs.get("max_chars")))
                except Exception as exc:
                    logger.warning("camofox extract %s failed: %s", u, exc)
                    results.append({"url": u, "title": "", "content": "", "error": f"Camofox extract failed: {exc}"})
        finally:
            client.close()
        return results
