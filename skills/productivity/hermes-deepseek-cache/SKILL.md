---
name: hermes-deepseek-cache
description: "Use when running Hermes Agent with a DeepSeek-family model (deepseek, or deepseek-v4-flash/pro via an aggregator like opencode-go) and want to see, graph, or reset DeepSeek's prefix-cache hit rate, diagnose cache misses, or confirm the deepseek_cache.enabled config — OR when you want to port/apply the deepseek_cache.py module (DeepSeek prefix-cache telemetry, /cache-stats /cache-graph /cache-reset, prefix-break diagnostics, stable tool ordering, cache-friendly compaction) into a Hermes source tree. Covers use + integration."
version: 1.1.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [deepseek, prefix-cache, cache-hit, telemetry, hit-rate, kv-cache, slash-command, hermes, port, integration]
---

# Hermes DeepSeek Prefix-Cache (ported from pi-deepseek-cache)

Hermes has a DeepSeek prefix-cache feature, **ported** from the
`ruanbw/pi-deepseek-cache` pi extension (2026-08-25). For DeepSeek-family
providers it tracks cumulative cache-hit telemetry, warns on prefix rewrites
(which break DeepSeek's byte-exact KV prefix cache), keeps tool order stable,
and reuses compaction summaries. Non-DeepSeek sessions are untouched.

> **IMPORTANT — this skill is self-contained.** `scripts/deepseek_cache.py` is
> the full implementing module, and `references/migration-guide.md` has the
> six wiring hooks. Upstream Hermes does NOT ship this feature — if you cloned
> this skill, you must drop the module in and wire the hooks before any of the
> commands below exist. See "Port into your Hermes".

## When to use
- You're running Hermes on a DeepSeek model and want to see/persist its cache
  hit rate (`/cache-stats`, `/cache-graph`, `/cache-reset`).
- A turn logs `deepseek-cache: prefix rewrite detected` and you want to know
  why the cache missed.
- You want to zero out accumulated cache stats.
- You want to **add this feature to your own Hermes** (no upstream support).

## Port into your Hermes (first-time setup on any install)
1. Copy `scripts/deepseek_cache.py` → `<your-hermes>/agent/deepseek_cache.py`.
2. Follow `references/migration-guide.md` for the six hooks:
   F1 telemetry in `agent/conversation_loop.py`; F2 status-bar in `cli.py`;
   F3 `/cache-*` commands on all four surfaces (`hermes_cli/commands.py`,
   `hermes_cli/slash_exec.py`, `cli.py`, `gateway/run.py`,
   `tui_gateway/server.py`, `acp_adapter/server.py`); F4 prefix-break
   diagnostics + F5 stable tool ordering in
   `agent/transports/chat_completions.py`; F6 summary cache / temp-0 flash in
   `agent/context_compressor.py`.
3. Enable per your `config.yaml` (`deepseek_cache.enabled`, default true).
4. Verify: `scripts/run_tests.sh tests/agent/test_deepseek_cache.py tests/hermes_cli/test_cache_slash_commands.py -q`.

If you already have the feature, skip to "When to use".

## Where it lives (when installed)
- Module: `agent/deepseek_cache.py`.
- Persisted telemetry: `$HERMES_HOME/deepseek-cache/` →
  `stats.json`, `history.json`, `summary-cache.json`.
- Slash-command surfaces: `cli.py`, `gateway/run.py`, `tui_gateway/server.py`,
  `acp_adapter/server.py`. (On Slack these are namespaced `/hermes cache-stats`
  etc. to respect the 50-native-slash cap.)

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

## Files
- `scripts/deepseek_cache.py` — full implementing module (571 lines, drop-in).
- `references/migration-guide.md` — six wiring hooks + constraints + verification.

## Hermes ≥0.21.0 adaptation notes (rebased 2026-09-04)
- Upstream 0.21.0 ships its OWN status-bar cache hit-rate display
  (`_cache_hit_rate` / `cache_hit_pct` in cli.py) — the F2 status-bar hook is
  superseded; do not re-add the `cache_segment` snapshot key.
- Upstream removed pre-call aux route resolution in `_generate_summary`
  (route is filled by `call_llm` into `route_info`). The F6 temp-0 flash gate
  must read `self.summary_model or self.model` pre-call instead of patching
  `_resolve_task_provider_model`; tests set `compressor.summary_model`.
- The same-provider credential-preservation fix (old local commit) is native
  in 0.21.0 — drop it when rebasing.
- `_close_cached_client` now takes `close_async=` keyword; keep upstream call
  shape and only swap the return to `_compat_model(client, model, default_model)`.

## Verification
- Unit tests: `scripts/run_tests.sh tests/agent/test_deepseek_cache.py tests/hermes_cli/test_cache_slash_commands.py -q`.
- Live spot-check: run a few DeepSeek turns, then `/cache-stats`, `/cache-graph`, `/cache-reset`; watch the status-bar segment; force a prefix break and check agent.log.