# DeepSeek prefix-cache — porting guide (pi-deepseek-cache → Hermes)

This skill is self-contained: `scripts/deepseek_cache.py` is the full Python
module that implements every feature. It is a **port** of the TS pi extension
`ruanbw/pi-deepseek-cache`, mapped onto Hermes's Python surfaces (not a
1:1 transliteration). To use it you must (1) drop the module into your Hermes
source, and (2) wire six small hooks. Upstream Hermes does NOT ship this
feature — you are adding it.

Reference source for semantics: `https://github.com/ruanbw/pi-deepseek-cache`
(`index.ts`). Verified 2026-08-25 on Hermes Agent v0.20.0, editable install at
`~/.hermes/hermes-agent`, provider `opencode-go` + `deepseek-v4-flash`.

## Step 0 — Drop in the module

Copy `scripts/deepseek_cache.py` → `agent/deepseek_cache.py` in your Hermes
source tree. Requirements it pulls in (already present in Hermes):
- `from hermes_constants import get_hermes_home`
- `from hermes_cli.config import load_config_readonly` (lazy, at call time)

It self-registers an `atexit` flush. No new dependency.

## Gating (read this first)

Everything is gated by BOTH:
1. `deepseek_cache.enabled` in config.yaml (default **true**, read at runtime
   via `load_config_readonly()` — no `DEFAULT_CONFIG` edit needed); and
2. `is_deepseek_family(provider, model)` — True when the substring `deepseek`
   appears in either the provider or model name, so aggregator-routed models
   (`opencode-go` + `deepseek-v4-flash`) count too.

Non-DeepSeek sessions pay nothing and their behavior is bit-for-bit unchanged.

## The six hooks (one per feature)

### F1 — telemetry (accumulate + persist hit-rate)
File: `agent/conversation_loop.py` (in `run_conversation`, at the canonical
usage-capture block where `agent.session_cache_write_tokens += …` is done):
```python
try:
    from agent.deepseek_cache import record_usage as _dsc_record_usage
    _dsc_record_usage(
        agent.provider, agent.model,
        cache_read=canonical_usage.cache_read_tokens,
        input_tokens=canonical_usage.input_tokens,
        cache_write=canonical_usage.cache_write_tokens,
    )
except Exception:
    pass
```
Persistence: `$HERMES_HOME/deepseek-cache/{stats.json,history.json}` —
cumulative `cacheRead/input/cacheWrite/turns` + a hit-rate trend history capped
at 100 points, written atomically (tmp+rename), debounced (1s), flushed on
`atexit` and on `reset()`.

### F2 — status-bar segment
File: `cli.py`, in the status-bar snapshot builder set `snapshot["cache_segment"]`
from `agent.deepseek_cache.status_bar_segment(provider, model_name)`
(`""` unless DeepSeek-family with recorded turns), then append that segment in
both the flat-text and fragment renderers where "🗜️ compressions" is appended.
Segment text: `cache 87.3% · 12t`.

### F3 — slash commands on ALL surfaces
Registry owns the canonical text; every surface just dispatches to it.

`hermes_cli/commands.py` — add to `COMMAND_REGISTRY`:
```python
CommandDef("cache-stats", "Show DeepSeek prefix-cache hit-rate stats", "Info",
           aliases=("cache_stats",), execute="cache_stats"),
CommandDef("cache-graph", "Show DeepSeek cache hit-rate trend chart", "Info",
           aliases=("cache_graph",), execute="cache_graph"),
CommandDef("cache-reset", "Reset DeepSeek prefix-cache stats and history", "Info",
           aliases=("cache_reset",), execute="cache_reset"),
```
Also add them to `_SLACK_VIA_HERMES_ONLY` (routed `/hermes cache-stats` on
Slack to stay under the 50-native-slash cap — `_SLACK_MAX_SLASH_COMMANDS`).

`hermes_cli/slash_exec.py` — add executors + register:
```python
def _exec_cache_stats(ctx):  from agent.deepseek_cache import format_stats_text; return CommandReply(format_stats_text())
def _exec_cache_graph(ctx):  from agent.deepseek_cache import format_graph_text; return CommandReply(format_graph_text())
def _exec_cache_reset(ctx):  from agent.deepseek_cache import reset_all; return CommandReply(reset_all())
EXECUTORS["cache_stats"] = _exec_cache_stats  # + cache_graph, cache_reset
```
Surface dispatch (each calls the `slash_exec` executor with a `CommandContext`):
- `cli.py` canonical chain → `elif canonical in ("cache-stats","cache-graph","cache-reset"):`
- `gateway/run.py` → `if canonical in (…): return execute_command(canonical, CommandContext(surface="gateway")).text`
- `tui_gateway/server.py` → add to `_LIVE_SESSION_DIRECT_COMMANDS` and in `_live_slash_command_output`
- `acp_adapter/server.py` → add to `_SLASH_COMMANDS`, `_ADVERTISED_COMMANDS`, the dispatcher dict, and three `_cmd_cache_*` handlers
  (optionally `COMMAND_DEFINITIONS` in `_ADVERTISED_COMMANDS`).

### F4 — prefix-break diagnostics
In `agent/transports/chat_completions.py`, define a request hook that calls
`deepseek_cache.check_prefix_stability(session_id, api_kwargs.get("messages"))`
when `is_enabled(provider, model)`, and wrap BOTH the provider-profile return
path and the legacy fallback return path with it. Purely observational — the
payload is never mutated. A rewrite (prefix not an append/identical of the
previous prefix) logs one `logger.warning` per break.

### F5 — stable tool ordering
In the same transport hook (before the prefix check):
```python
tools = api_kwargs.get("tools")
if isinstance(tools, list) and len(tools) > 1:
    api_kwargs["tools"] = deepseek_cache.sort_tools(tools)
```
`sort_tools` returns a NEW lexicographically-sorted list; the caller's list is
never mutated, and only DeepSeek-family providers change order.

### F6 — cache-friendly compaction (summary cache + temp-0 flash)
File: `agent/context_compressor.py`, method `ContextCompressor._generate_summary`:
- Before the aux call, if `deepseek_cache.is_enabled(self.provider, self.model)`:
  compute `key = deepseek_cache.summary_cache_key(prompt)`
  (the prompt is built from already-redacted inputs), look up
  `deepseek_cache.get_summary_cache().get(key)`; on a hit, set
  `self._previous_summary = cached` and return it immediately.
- In the call-kwargs block, when the resolved aux model is DeepSeek-flash
  (`"deepseek" in model and "flash" in model`), set `call_kwargs["temperature"] = 0`
  (deterministic, cache-friendly summaries).
- After a successful summary, `deepseek_cache.get_summary_cache().put(key, summary)`.
- `reset_all()` (via `/cache-reset`) also clears the summary cache.

The summary cache is a persistent SHA-256-keyed LRU capped at 64, stored at
`$HERMES_HOME/deepseek-cache/summary-cache.json`.

## Config
```yaml
deepseek_cache:
  enabled: true    # false disables for DeepSeek sessions too
```

## Constraints that held for the port
- Gate every behavior behind `deepseek_cache.enabled` + DeepSeek-family so
  non-DeepSeek behavior stays bit-for-bit identical. Test that.
- Single git commit per feature (TDD: failing test → implement → passing →
  commit).
- The reference port committed to a locally-diverged Hermes install; never
  pushed. If you're adding this to Hermes upstream, keep the same discipline.

## Verification
- Unit tests: `scripts/run_tests.sh tests/agent/test_deepseek_cache.py tests/hermes_cli/test_cache_slash_commands.py -q` (60/60 at port time).
- Live: run a few DeepSeek turns → `/cache-stats`, `/cache-graph`, `/cache-reset`; watch the status-bar segment appear; force a prefix break and see the warning in agent.log.