---
name: camofox-browser
description: "Use when sites block bots. Start Camofox, saved logins."
version: 1.0.0
author: LaansDole
license: MIT
metadata:
  hermes:
    tags: [browser, camoufox, camofox, cloudflare, captcha, anti-bot, login, launchd]
    related_skills: [blocked-page-recovery, hermes-agent]
---

# Camofox (Camoufox) browser for Hermes - local setup

## When to Use
ANY web search, URL fetch or scraping - the user's standing rule is Camofox for all of it, including
cases where you would otherwise reach for curl/wget/requests against a web page.
- Search -> `web_search` (served by the camofox-web plugin: Camoufox opens DuckDuckGo, Bing fallback).
- Read a page -> `web_extract` (camofox-web renders it in Camoufox; Cloudflare interstitials waited out).
- Interactive pages / logins -> browser_* tools (Camofox backend).
- Scripted scraping -> Camofox REST (see Verify: POST /tabs, /evaluate, DELETE), not curl.
curl stays fine only for localhost services and plain JSON APIs you are calling as an API client.
If the user asks why searches go through DuckDuckGo: Camofox is a browser, not a search index, so it
must load some engine's results page; DuckDuckGo (default) / Bing (fallback) are just the sites Camoufox
visits - no external API. Google is skipped because its result links are opaque /goto tokens.
Details: plugins/camofox-web/README.md in the my-hermes-skills repo.
Also when: browsing hits Cloudflare / reCAPTCHA / bot walls, a site needs a saved login, or the
browser tools fail because the Camofox server is down.

Hermes' browser tools (browser_navigate, browser_snapshot, browser_click, ...) are routed through a
local Camofox server (Node REST wrapper around Camoufox, an anti-fingerprint Firefox fork). This gets
past Cloudflare challenges and most bot walls, and keeps per-profile logins across sessions.

## Layout (this machine)
- Server source: ~/Projects/camofox-browser (jo-inc/camofox-browser, installed `npm install --omit=dev`;
  full install fails: dev dep openclaw needs Node >=24).
- Runtime dir ~/.camofox: run.sh (launcher), env (CAMOFOX_ADMIN_KEY, telemetry off; chmod 600, never print it),
  mode (off|desktop), server.log, profiles/ (saved logins, storage-state.json per userId).
- launchd job: com.laansdole.camofox (~/Library/LaunchAgents/com.laansdole.camofox.plist), RunAtLoad + KeepAlive.
- Helper CLI: `camofox` (~/.local/bin -> ~/.camofox/camofox): status | start | login | headless | save | restart | log.
- Hermes side: CAMOFOX_URL=http://localhost:9377 in ~/.hermes/.env; config `browser.cloud_provider: camofox`
  (warns "not a recognized key" - it IS read by tools/browser_camofox.py:is_camofox_mode), and
  `browser.camofox.managed_persistence: true` (deterministic per-profile userId -> logins persist).
- `hermes plugins install camofox` is installed+enabled but inactive while core still bundles
  tools/browser_camofox.py; `hermes camofox status` does not exist until then - use `camofox status`.

## Install / repair (fresh machine or missing ~/.camofox)
`bash <skill_dir>/scripts/install.sh` - clones+installs the server if absent, writes ~/.camofox (run.sh,
camofox CLI, env with a fresh admin key), the launchd plist, CAMOFOX_URL and both Hermes config keys.
Idempotent. It does NOT load launchd: hand the printed `launchctl bootstrap ...` line to the user.
Source of truth for run.sh / camofox / the plist is `scripts/` in this skill; re-run install.sh after editing.

## Start / check (do this first when browsing is needed and fails)
1. `camofox status` - waits up to 15s; prints launchd state + /health JSON (`"ok":true` = ready).
2. Down -> `camofox start` (kickstarts the launchd job; may raise an approval prompt - the user approves).
3. "launchd job not loaded" -> agents are BLOCKED from `launchctl bootstrap` inside the gateway (do not
   work around the guard, not even by writing it into a script). Ask the user to run in their own terminal:
   `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.laansdole.camofox.plist`
4. Stopgap only if the user is unavailable: `terminal(command="bash ~/.camofox/run.sh >> ~/.camofox/server.log 2>&1", background=true)`.
   It dies with the session, and it will collide on :9377 with the launchd job - kill it (SIGTERM, never -9)
   before the user bootstraps.
5. Browser tools only pick up Camofox in NEW sessions after env/config changes.

## One-time logins (sites that need sign-in)
1. `camofox login` - checkpoints state, restarts with a VISIBLE Camoufox window (mode=desktop).
2. browser_navigate to each site's login page; the USER types credentials in the window (never type
   passwords yourself; use browser_vault if the user wants it automated).
3. `camofox headless` - checkpoints (POST /stop, HTTP 200) and restarts invisible. Logins now persist.
Redo only when a site expires the session. State is also checkpointed on 10-min idle and graceful
shutdown; `kill -9` loses un-checkpointed cookies.

## Verify
- Persistence: open https://httpbin.org/cookies/set?x=1 in one session, `camofox restart`, then a new
  session on https://httpbin.org/cookies must still show x.
- Anti-bot: https://www.scrapingcourse.com/cloudflare-challenge should say "You bypassed the Cloudflare challenge".
- Direct REST (no Hermes): POST /tabs {userId,sessionKey,url} -> GET /tabs/:id/snapshot?userId= ->
  POST /tabs/:id/evaluate {userId,expression} -> DELETE /tabs/:id?userId=. Useful for fetching pages
  that block curl (e.g. reddit) from inside an agent turn.

## Pitfalls
- `camofox status` right after bootstrap/restart may need its 15s wait; "server down" within seconds of start is normal.
- Revert to Chromium: `hermes config set browser.cloud_provider local`.
- A CDP override (BROWSER_CDP_URL / browser.cdp_url / /browser connect) wins over Camofox.
- Hard CAPTCHAs that still appear: CapSolver (paid API key) is the reported next step - not set up; ask first.
- Bot Screen (Hermes per-bot desktop) is Linux-only; not applicable on this Mac.
- npm audit reported 9 vulns in server deps (unreviewed); server binds localhost only.
