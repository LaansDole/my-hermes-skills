# Hermes DeepSeek Prefix-Cache

Hermes Agent's native DeepSeek prefix-cache feature — ported from the
[`ruanbw/pi-deepseek-cache`](https://github.com/ruanbw/pi-deepseek-cache) pi
extension on 2026-08-25. For DeepSeek-family providers it surfaces cumulative
cache-hit telemetry, warns on prefix rewrites that bust the KV cache, keeps
tool order stable, and reuses compaction summaries.

**Requires**: Hermes Agent (editable or pip install) with a DeepSeek-family
model — `deepseek` provider, or `deepseek/deepseek-v4-flash`/`v4-pro` routed
through an aggregator like `opencode-go`.

## Quick start

1. Confirm a DeepSeek model is active (any surface):
   - `hermes model` → pick a `deepseek/*` model, or
   - if using `opencode-go`, select a `deepseek-v4-flash`-type model.
2. The feature turns on automatically — it's gated to DeepSeek-family runs and
   is on by default. No install step.
3. In a chat, use:
   - `/cache-stats` — hit rate, cache read/miss/write tokens, turns, est. saved
   - `/cache-graph` — ASCII hit-rate trend chart
   - `/cache-reset` — zero stats + clear summary cache + delete persisted files

## Config

```yaml
deepseek_cache:
  enabled: true    # set false to fully disable (even for DeepSeek)
```

Persisted telemetry lives under `$HERMES_HOME/deepseek-cache/`
(`stats.json`, `history.json`, `summary-cache.json`).

## How it works

- Hit rate = cacheRead / (cacheRead + input) × 100.
- Prefix-break diagnostics: stable SHA-256 of the message prefix (all but the
  last message), key-sorted JSON so ordering can't jitter the hash. A rewrite
  (not a pure append) logs a warning; the request payload is never modified.
- Stable tool ordering: tools are sorted lexicographically by name before send.
- Cache-friendly compaction: summaries are keyed by SHA-256 of the redacted
  serialized input in a persistent LRU (cap 64); DeepSeek-flash aux prefers
  temperature 0.

Full detail: see `SKILL.md` in this folder; `references/migration-guide.md` has
the six wiring hooks, and `scripts/deepseek_cache.py` is the full drop-in module —
so this skill is self-contained and can be applied to any Hermes install that
doesn't already carry the DeepSeek prefix-cache feature.