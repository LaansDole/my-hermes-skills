# camofox-browser

Routes Hermes' browser tools through a local [Camofox](https://github.com/jo-inc/camofox-browser) server
(a REST wrapper around [Camoufox](https://github.com/daijro/camoufox), an anti-fingerprint Firefox fork),
so the agent gets past Cloudflare challenges and keeps site logins between sessions. Runs as a macOS
launchd job; logins are done once by hand in a visible window, then reused headless.

## Install

```bash
ln -s ~/Projects/auto-learn-for-me/skills/productivity/camofox-browser ~/.hermes/skills/productivity/camofox-browser
bash ~/.hermes/skills/productivity/camofox-browser/scripts/install.sh
# then, in your own terminal (Hermes agents are blocked from loading launchd jobs):
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.laansdole.camofox.plist
camofox status
```

## Use

| Command | Effect |
|---|---|
| `camofox status` | launchd state + server health (waits up to 15 s) |
| `camofox start` | start the launchd job if the server is down |
| `camofox login` | restart with a visible window; sign in to your sites via Hermes |
| `camofox headless` | save logins and go back to invisible mode |
| `camofox save` / `restart` / `log` | checkpoint logins / restart / tail the log |

## Files

- `SKILL.md` - agent procedure (start, login flow, verification, pitfalls)
- `scripts/install.sh` - idempotent installer (server, ~/.camofox, CLI, plist, Hermes config)
- `scripts/run.sh` - launchd entry point (reads ~/.camofox/env and ~/.camofox/mode)
- `scripts/camofox` - helper CLI
- `scripts/com.laansdole.camofox.plist.template` - launchd job (RunAtLoad, KeepAlive)

Verified on macOS (Apple M4): Cloudflare test page passed, cookies survived a server restart.
Crash telemetry of the Camofox server is turned off (`CAMOFOX_CRASH_REPORT_ENABLED=false`).
