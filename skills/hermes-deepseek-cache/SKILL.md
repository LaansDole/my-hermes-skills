---
name: hermes-deepseek-cache
description: "Use when running Hermes Agent with a DeepSeek-family model (deepseek, or deepseek-v4-flash/pro via an aggregator like opencode-go) and want to see, graph, or reset DeepSeek's prefix-cache hit rate, diagnose cache misses, or confirm the deepseek_cache.enabled config. Covers the /cache-stats, /cache-graph, and /cache-reset commands and the agent/deepseek_cache.py telemetry module."
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [deepseek, prefix-cache, cache-hit, telemetry, hit-rate, kv-cache, slash-command, hermes]
---

# Hermes DeepSeek Prefix-Cache (ported pi-deepseek-cache)

Hermes has a native DeepSeek prefix-cache feature (ported from the
`ruanbw/pi-deepseek-cache` pi extension on 2026-08-25). For DeepSeek-family
providers it tracks cumulative cache-hit telemetry, warns on prefix rewrites
(which break DeepSeek's byte-exact KV prefix cache), keeps tool order stable,
and reuses compaction summaries. Non-DeepSeek sessions are untouched.

## When to use
- You're running Hermes on a DeepSeek model and want to see how well its
  context cache is hitting (`/cache-stats`, `/cache-graph`).
- A turn logs `deepseek-cache: prefix rewrite detected` and you want to know
  why the cache missed.
- You want to zero out accumulated cache stats (`/cache-reset`).
- You're deciding whether to enable/disable the feature (`config.yaml`).

## Where it lives
- Module: `agent/deepseek_cache.py` in the hermes source
  (`~/.hermes/hermes-agent/agent/deepseek_cache.py` on the editable install).
- Persisted telemetry: `$HERMES_HOME/deepseek-cache/` →
  `stats.json`, `history.json`, `summary-cache.json`.
- Hook points: usage capture in `agent/conversation_loop.py`; transport
  (`agent/transports/chat_completions.py`) for tool sorting + prefix hash;
  `agent/context_compressor.py` for the summary cache.
- Slash-command surfaces (must all be updated together when editing):
  `cli.py`, `gateway/run.py`, `tui_gateway/server.py`, `acp_adapter/server.py`.
  (On Slack these are namespaced `/hermes cache-stats` etc. to respect the 50
  native slash-command cap.)

## Gating
Only active when BOTH hold:
- the active provider AND/OR model is DeepSeek-family —
  `is_deepseek_family(provider, model)` matches the substring "deepseek" in
  either, so aggregator-routed models (`opencode-go` + `deepseek-v4-flash`)
  count too;
- `deepseek_cache.enabled` is true in `config.yaml` (default: enabled; read at
  runtime via `load_config_readonly()`, no `DEFAULT_CONFIG` entry needed).

## Slash commands
| Command | Output |
|---|---|
| `/cache-stats` | Hit rate %, cache-read / cache-miss / cache-write tokens, turn count, estimated $ saved |
| `/cache-graph` | ASCII hit-rate trend chart over the turn history (≤100 points) |
| `/cache-reset` | Zero all counters, clear the summary cache, delete the persisted files |

## Config
```yaml
deepseek_cache:
  enabled: true    # set false to fully disable for DeepSeek sessions too
```

## Internals worth knowing
- Hit rate = `cacheRead / (cacheRead + input) * 100`.
- Cost estimate (display only): DeepSeek pricing $0.027/MTok cache-read vs
  $0.27/MTok input.
- Prefix-break detection: stable SHA-256 of every message except the last
  (deterministic key-sorted JSON — no key-order jitter). A rewrite (not a
  pure append) logs a warning once per break; the payload is never mutated.
- Tool ordering: tools are sorted lexicographically by name before send so
  tool-order jitter can't bust the byte-exact prefix.
- Compaction: summaries are keyed on the redacted serialized input (SHA-256)
  in a persistent LRU (cap 64) so identical conversation state across sessions
  is not re-summarized; a DeepSeek-flash aux model prefers temperature 0.

## Verification
- Unit tests: `scripts/run_tests.sh tests/agent/test_deepseek_cache.py tests/hermes_cli/test_cache_slash_commands.py -q`
  (originally 60/60 passing).
- Live spot-check: run a few DeepSeek turns, then `/cache-stats`, `/cache-graph`, `/cache-reset`.

## Port reference
Feature→surface mapping, pi→Hermes, and the dispatch constraints are in the
`omp-implementation-dispatch` skill's `references/deepseek-cache-migration.md`.