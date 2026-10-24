# camofox-web

Hermes `web_search` + `web_extract` provider backed by the local Camofox server
(set up by [`skills/productivity/camofox-browser/`](../../skills/productivity/camofox-browser/README.md)).
Replaces SearXNG: every search and page fetch goes through Camoufox, the anti-fingerprint Firefox.

## How search works (why DuckDuckGo shows up)

Camofox is a browser, not a search index. To find pages it has to open a search engine's results
page, just like a person would. DuckDuckGo is not a separate service or API here: Camoufox loads
duckduckgo.com in its own Firefox, and the plugin reads the result links off that page. (SearXNG, by
contrast, called the engines from its own server.)

So the only choice is which site Camoufox searches on:

| Engine | Role | Notes |
|---|---|---|
| DuckDuckGo (`html.duckduckgo.com`) | default | ~1 s, real result URLs (its `/l/?uddg=` redirect is decoded), relevant results |
| Bing | automatic fallback | redirect links (`/ck/a?u=a1<base64>`) decoded; weaker relevance on niche queries |
| Google | not used | loads without CAPTCHA, but result links are opaque `/goto` tokens: getting real URLs would mean opening every result (~1 s each) |

Override the order with `CAMOFOX_SEARCH_ENGINES=duckduckgo,bing` in `~/.hermes/.env`.

## How extract works

Each URL is opened in a Camoufox tab; Cloudflare-style interstitials ("Just a moment...") are waited
out (up to 20 s), then the main text (`article` / `main` / content containers, nav and footer stripped)
is returned, capped at 100k chars. Pages still stuck on a challenge come back with an `error`.

## Install

```bash
ln -s ~/Projects/auto-learn-for-me/plugins/camofox-web ~/.hermes/plugins/camofox-web
hermes plugins enable camofox-web
hermes config set web.backend camofox
hermes config set web.search_backend camofox
hermes config set web.extract_backend camofox
hermes config set web.keyless_fallback false   # fail loudly instead of silently using another provider
```

Needs `CAMOFOX_URL` in `~/.hermes/.env` and the server running (`camofox status`). Takes effect in new sessions.

## Verified

Fresh Hermes session: `web_search` returned 10 DuckDuckGo results via Camoufox in ~1.5 s; `web_extract`
read the MarkTechPost article and passed the scrapingcourse.com Cloudflare challenge.
Known gap: extracted text can begin with menu or tag links before the article body.
