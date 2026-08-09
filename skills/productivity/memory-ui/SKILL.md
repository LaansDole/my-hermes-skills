---
name: memory-ui
description: Launch the Mnemosyne browser UI to inspect stored memory.
trigger: User wants to see Mnemosyne memory visually or open the memory dashboard.
---

# Mnemosyne UI / Browser Dashboard

Mnemosyne ships a read-only **local web dashboard** (`mnemosyne-browser`) for viewing memory. It binds to `127.0.0.1` (loopback only) and opens the SQLite DB read-only — use the CLI for any write/management action.

## Environment

Mnemosyne is installed into the Hermes venv. Always invoke its binaries through the venv PATH:

```bash
export PATH="$HOME/.hermes/hermes-agent/venv/bin:$PATH"
```

Key paths:
- Venv Python: `~/.hermes/hermes-agent/venv/bin/python`
- DB: `~/.hermes/mnemosyne/data/mnemosyne.db` (fully local, no cloud)
- Plugin: `~/.hermes/plugins/mnemosyne` (symlink)
- Provider: `memory.provider = mnemosyne` (already active)

## Start the browser UI (background process)

Prefer a Hermes-tracked background process over nohup/disown:

```bash
export PATH="$HOME/.hermes/hermes-agent/venv/bin:$PATH"
mnemosyne-browser --port 8081   # run via terminal(background=true)
```

Then verify readiness before reporting success:

```bash
curl -s http://127.0.0.1:8081/api/stats   # expect {"tiers": {...}, "total": N}
```

Open http://127.0.0.1:8081 in the browser (default browser is Brave, profile 'brave-live').

## Read-only UI actions

The dashboard supports browse, search, tier/source filtering, sort, and per-memory detail via endpoints:
- `GET /` — HTML page
- `GET /api/stats` — tier counts
- `GET /api/search?q=&src=&tier=&sort=&limit=&offset=` — JSON results
- `GET /detail/<memory_id>` — single-memory detail

## Write/management actions are CLI (NOT the UI)

The browser is read-only. For writes use the CLI:

```bash
export PATH="$HOME/.hermes/hermes-agent/venv/bin:$PATH"
mnemosyne store "content" [source] [importance]      # add
mnemosyne recall "<query>" [top_k]                   # search
mnemosyne update <id> "<content>" [importance]        # update
mnemosyne delete <id>                                 # remove
mnemosyne stats                                       # totals
mnemosyne sleep                                       # consolidation
mnemosyne export <file.json>                          # portable backup (push to cloud only when user chooses)
mnemosyne backup <dir> / restore <backup.db.gz>       # compressed snapshots
mnemosyne sync ...                                    # encrypted remote sync to a server YOU run
```

## Stop the server

If it was started as a tracked process, kill that session. The loopback server is safe to leave running, but stop it when the user is done to avoid a stray process.

## Gotchas

- Only use `mnemosyne-browser` through the venv PATH; the bare `mnemosyne-browser` may not resolve outside it.
- macOS `grep` lacks `-P`; find memory IDs with `mnemosyne recall "<q>" 10 | grep "ID:"` instead.
- Requires `fastapi` + `uvicorn` (both already installed in the Hermes venv).
- New session / gateway restart is required for `mnemosyne_*` provider tools to appear in an already-running session.
- The bundled `mnemosyne-memory-override` skill handles memory ROUTING; this skill handles the VISUAL UI + CLI management.
