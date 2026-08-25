"""DeepSeek prefix-cache telemetry, diagnostics, and request stabilization.

Python port of the pi-deepseek-cache extension (ruanbw/pi-deepseek-cache)
mapped onto Hermes surfaces:

- Telemetry: cumulative cache-read / input / cache-write / turn counters with
  a hit-rate history, persisted atomically (tmp+rename) under
  ``$HERMES_HOME/deepseek-cache/`` with a debounced flush and a flush at
  process exit.

Everything is gated by ``deepseek_cache.enabled`` in config.yaml (default
true) AND the active provider/model being DeepSeek-family, so non-DeepSeek
sessions never pay for any of this.
"""

from __future__ import annotations

import atexit
import hashlib
import json
import logging
import os
import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, List, Optional

from hermes_constants import get_hermes_home

logger = logging.getLogger(__name__)

MAX_HISTORY_POINTS = 100
WRITE_DEBOUNCE_SECONDS = 1.0

# DeepSeek pricing per million tokens (USD): cache-hit vs cache-miss input.
# Snapshot from pi-deepseek-cache; used only for the "estimated saved" line.
COST_PER_MILLION_CACHE_READ = 0.027
COST_PER_MILLION_INPUT = 0.27

STATS_FILENAME = "stats.json"
HISTORY_FILENAME = "history.json"
SUMMARY_CACHE_FILENAME = "summary-cache.json"


# ---------------------------------------------------------------------------
# Gating
# ---------------------------------------------------------------------------

def is_deepseek_family(provider: Any, model: Any) -> bool:
    """True when the provider or model is DeepSeek-family.

    Matches DeepSeek models routed through aggregators (opencode-go,
    OpenRouter, ...) via the model name, not just ``provider == deepseek``.
    """
    blob = f"{provider or ''} {model or ''}".lower()
    return "deepseek" in blob


def _config_flag_enabled() -> bool:
    """Read ``deepseek_cache.enabled`` from config.yaml (default: enabled)."""
    try:
        from hermes_cli.config import load_config_readonly

        section = load_config_readonly().get("deepseek_cache") or {}
        return bool(section.get("enabled", True))
    except Exception:
        return True


def is_enabled(provider: Any = None, model: Any = None) -> bool:
    """Master gate: DeepSeek-family runtime AND config flag on."""
    return is_deepseek_family(provider, model) and _config_flag_enabled()


# ---------------------------------------------------------------------------
# Deterministic serialization + prefix-break diagnostics
# ---------------------------------------------------------------------------

def stable_stringify(value: Any) -> str:
    """Deterministic JSON: sorted keys, compact separators.

    Mirrors pi's ``stableStringify`` so key-order jitter never produces a
    different hash for byte-identical semantic content.
    """
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    )


def hash_messages(messages: Any) -> str:
    """Stable SHA-256 hex digest of a message list."""
    return hashlib.sha256(stable_stringify(messages).encode("utf-8")).hexdigest()


_prefix_lock = threading.Lock()
# session_id -> (prefix_hash, prefix_len); break counters kept per session.
_prefix_state: Dict[str, tuple] = {}
_prefix_breaks: Dict[str, int] = {}


def check_prefix_stability(session_id: Any, messages: Any) -> bool:
    """Diagnose prefix rewrites between consecutive provider requests.

    The prefix is every message but the last. An append (old prefix is a
    hash-identical head of the new one) or an identical prefix is stable;
    anything else is a rewrite that will miss DeepSeek's byte-exact KV
    prefix cache — warn once per break. Purely diagnostic: never mutates
    ``messages``. Returns False only on a detected rewrite.
    """
    if not isinstance(messages, list) or len(messages) < 2:
        return True
    prefix = messages[:-1]
    key = str(session_id or "default")
    with _prefix_lock:
        cur_hash = hash_messages(prefix)
        cur_len = len(prefix)
        stable = True
        prev = _prefix_state.get(key)
        if prev is not None:
            prev_hash, prev_len = prev
            is_equal = cur_len == prev_len and cur_hash == prev_hash
            is_append = (
                cur_len >= prev_len and hash_messages(prefix[:prev_len]) == prev_hash
            )
            if not (is_equal or is_append):
                breaks = _prefix_breaks.get(key, 0) + 1
                _prefix_breaks[key] = breaks
                logger.warning(
                    "deepseek-cache: prefix rewrite detected (break #%d, "
                    "session=%s) — this turn will likely miss the prefix cache",
                    breaks,
                    key,
                )
                stable = False
        _prefix_state[key] = (cur_hash, cur_len)
        return stable


def _tool_name(tool: Any) -> str:
    """Tool name for OpenAI-format ({'function': {'name': ...}}) or flat shapes."""
    if not isinstance(tool, dict):
        return ""
    name = tool.get("name")
    if isinstance(name, str):
        return name
    fn = tool.get("function")
    if isinstance(fn, dict) and isinstance(fn.get("name"), str):
        return fn["name"]
    return ""


def sort_tools(tools: List[Any]) -> List[Any]:
    """New list of tools sorted lexicographically by name (elements shared).

    Tool-order jitter changes the serialized request prefix and busts
    DeepSeek's byte-exact KV cache; a deterministic order keeps the prefix
    stable across turns.
    """
    return sorted(tools, key=_tool_name)


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------

def stats_dir() -> Path:
    """Profile-aware telemetry directory (resolved at call time)."""
    return get_hermes_home() / "deepseek-cache"


def atomic_write_json(path: Path, data: Any) -> None:
    """Write JSON via tmp+rename so readers never see a torn file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _load_json(path: Path, default: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("deepseek-cache: %s unreadable (%s), resetting", path.name, exc)
    return default


# ---------------------------------------------------------------------------
# Telemetry
# ---------------------------------------------------------------------------

class CacheTelemetry:
    """Cumulative DeepSeek cache counters with persisted hit-rate history.

    Thread-safe. Writes are debounced (one timer per burst); ``flush()``
    forces pending state to disk; ``reset()`` zeroes state and deletes the
    persisted files.
    """

    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir)
        self._lock = threading.Lock()
        self._flush_timer: Optional[threading.Timer] = None
        self._dirty = False

        stats = _load_json(self.stats_file, {})
        if not isinstance(stats, dict):
            stats = {}
        self.cache_read = int(stats.get("cacheRead", 0) or 0)
        self.input_tokens = int(stats.get("input", 0) or 0)
        self.cache_write = int(stats.get("cacheWrite", 0) or 0)
        self.turns = int(stats.get("turns", 0) or 0)

        history = _load_json(self.history_file, [])
        if not isinstance(history, list):
            history = []
        self.history: List[Dict[str, Any]] = [
            p for p in history if isinstance(p, dict)
        ][-MAX_HISTORY_POINTS:]
        self._last_hit_rate = (
            float(self.history[-1].get("hitRate", 0.0)) if self.history else 0.0
        )

    @property
    def stats_file(self) -> Path:
        return self.base_dir / STATS_FILENAME

    @property
    def history_file(self) -> Path:
        return self.base_dir / HISTORY_FILENAME

    @property
    def hit_rate(self) -> float:
        denom = self.cache_read + self.input_tokens
        return (self.cache_read / denom) * 100.0 if denom else 0.0

    def record_turn(
        self,
        *,
        cache_read: int = 0,
        input_tokens: int = 0,
        cache_write: int = 0,
    ) -> None:
        with self._lock:
            self.cache_read += max(0, int(cache_read or 0))
            self.input_tokens += max(0, int(input_tokens or 0))
            self.cache_write += max(0, int(cache_write or 0))
            self.turns += 1
            rate = self.hit_rate
            # Fixed-point comparison so float noise doesn't defeat dedupe.
            if f"{rate:.1f}" != f"{self._last_hit_rate:.1f}":
                self.history.append(
                    {
                        "turn": self.turns,
                        "hitRate": rate,
                        "timestamp": int(time.time() * 1000),
                    }
                )
                del self.history[:-MAX_HISTORY_POINTS]
                self._last_hit_rate = rate
            self._dirty = True
            self._schedule_flush_locked()

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "cacheRead": self.cache_read,
                "input": self.input_tokens,
                "cacheWrite": self.cache_write,
                "turns": self.turns,
                "hitRate": self.hit_rate,
            }

    def history_snapshot(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self.history)

    # -- flushing -----------------------------------------------------------

    def _schedule_flush_locked(self) -> None:
        if self._flush_timer is not None:
            return
        timer = threading.Timer(WRITE_DEBOUNCE_SECONDS, self._flush_from_timer)
        timer.daemon = True
        self._flush_timer = timer
        timer.start()

    def _flush_from_timer(self) -> None:
        with self._lock:
            self._flush_timer = None
            self._write_locked()

    def flush(self) -> None:
        """Force pending state to disk (session end / before reset)."""
        with self._lock:
            if self._flush_timer is not None:
                self._flush_timer.cancel()
                self._flush_timer = None
            self._write_locked()

    def _write_locked(self) -> None:
        if not self._dirty:
            return
        try:
            atomic_write_json(
                self.stats_file,
                {
                    "cacheRead": self.cache_read,
                    "input": self.input_tokens,
                    "cacheWrite": self.cache_write,
                    "turns": self.turns,
                },
            )
            atomic_write_json(self.history_file, self.history[-MAX_HISTORY_POINTS:])
            self._dirty = False
        except Exception as exc:
            logger.warning("deepseek-cache: persist failed: %s", exc)

    def reset(self) -> None:
        """Zero all counters and delete the persisted files."""
        with self._lock:
            if self._flush_timer is not None:
                self._flush_timer.cancel()
                self._flush_timer = None
            self.cache_read = 0
            self.input_tokens = 0
            self.cache_write = 0
            self.turns = 0
            self.history = []
            self._last_hit_rate = 0.0
            self._dirty = False
            for name in (STATS_FILENAME, HISTORY_FILENAME, SUMMARY_CACHE_FILENAME):
                try:
                    (self.base_dir / name).unlink(missing_ok=True)
                except Exception as exc:
                    logger.warning("deepseek-cache: could not remove %s: %s", name, exc)


_telemetry_lock = threading.Lock()
_telemetry: Optional[CacheTelemetry] = None


def get_telemetry() -> CacheTelemetry:
    """Process-wide telemetry, re-anchored when HERMES_HOME/profile changes."""
    global _telemetry
    base = stats_dir()
    with _telemetry_lock:
        if _telemetry is None or _telemetry.base_dir != base:
            _telemetry = CacheTelemetry(base)
        return _telemetry


# ---------------------------------------------------------------------------
# Summary cache (cache-friendly compaction)
# ---------------------------------------------------------------------------

SUMMARY_CACHE_MAX_ENTRIES = 64


def summary_cache_key(text: str) -> str:
    """SHA-256 hex key for a redacted serialized summarizer input."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class SummaryCache:
    """Persistent LRU (cap 64) of compaction summaries, keyed by SHA-256.

    Identical conversation state across sessions reuses the stored summary
    instead of re-summarizing. Thread-safe; every ``put`` persists the whole
    map atomically (writes are compaction-rate, not per-turn).
    """

    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir)
        self._lock = threading.Lock()
        data = _load_json(self.file, {})
        if not isinstance(data, dict):
            data = {}
        self._data: "OrderedDict[str, str]" = OrderedDict(
            (k, v) for k, v in data.items() if isinstance(v, str)
        )
        while len(self._data) > SUMMARY_CACHE_MAX_ENTRIES:
            self._data.popitem(last=False)

    @property
    def file(self) -> Path:
        return self.base_dir / SUMMARY_CACHE_FILENAME

    def get(self, key: str) -> Optional[str]:
        with self._lock:
            value = self._data.get(key)
            if value is not None:
                self._data.move_to_end(key)
            return value

    def put(self, key: str, value: str) -> None:
        with self._lock:
            self._data[key] = value
            self._data.move_to_end(key)
            while len(self._data) > SUMMARY_CACHE_MAX_ENTRIES:
                self._data.popitem(last=False)
            try:
                atomic_write_json(self.file, dict(self._data))
            except Exception as exc:
                logger.warning("deepseek-cache: summary cache persist failed: %s", exc)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()
            try:
                self.file.unlink(missing_ok=True)
            except Exception as exc:
                logger.warning("deepseek-cache: could not remove %s: %s", self.file.name, exc)


_summary_cache: Optional[SummaryCache] = None


def get_summary_cache() -> SummaryCache:
    """Process-wide summary cache, re-anchored when HERMES_HOME changes."""
    global _summary_cache
    base = stats_dir()
    with _telemetry_lock:
        if _summary_cache is None or _summary_cache.base_dir != base:
            _summary_cache = SummaryCache(base)
        return _summary_cache


def record_usage(
    provider: Any,
    model: Any,
    *,
    cache_read: int = 0,
    input_tokens: int = 0,
    cache_write: int = 0,
) -> None:
    """Per-turn accumulator hook — no-op unless the DeepSeek gate is open."""
    if not is_enabled(provider, model):
        return
    get_telemetry().record_turn(
        cache_read=cache_read,
        input_tokens=input_tokens,
        cache_write=cache_write,
    )


def status_bar_segment(provider: Any = None, model: Any = None) -> str:
    """``cache 87.3% · 12t`` status-bar segment; ``""`` when gated or no data."""
    if not is_enabled(provider, model):
        return ""
    telemetry = get_telemetry()
    if telemetry.turns <= 0:
        return ""
    return f"cache {telemetry.hit_rate:.1f}% · {telemetry.turns}t"


# ---------------------------------------------------------------------------
# Slash-command formatters (/cache-stats, /cache-graph, /cache-reset)
# ---------------------------------------------------------------------------

CHART_HEIGHT = 10
CHART_MAX_WIDTH = 48
FLAT_CHART_EPSILON = 0.05


def estimated_savings_usd(cache_read: int) -> float:
    """Dollars saved by cache hits vs paying full input price."""
    return (cache_read / 1_000_000) * (
        COST_PER_MILLION_INPUT - COST_PER_MILLION_CACHE_READ
    )


def format_stats_text() -> str:
    """Plain-text /cache-stats body (surface-independent)."""
    stats = get_telemetry().snapshot()
    saved = estimated_savings_usd(stats["cacheRead"])
    saved_str = f"${saved:.2f}" if saved >= 0.01 else "< $0.01"
    return "\n".join(
        [
            "DeepSeek prefix-cache stats",
            f"  Hit rate:     {stats['hitRate']:.1f}%",
            f"  Cache read:   {stats['cacheRead']:,} tokens",
            f"  Cache miss:   {stats['input']:,} tokens",
            f"  Cache write:  {stats['cacheWrite']:,} tokens",
            f"  Turns:        {stats['turns']}",
            f"  Est. saved:   {saved_str}",
        ]
    )


def _x_axis_labels(data: List[Dict[str, Any]], *, mid_label: bool) -> str:
    """Fixed-position turn labels: first at 0, mid centered, last right-aligned."""
    n = len(data)
    chars = [" "] * n

    def place(text: str, start: int) -> None:
        for i, ch in enumerate(text):
            pos = start + i
            if 0 <= pos < n:
                chars[pos] = ch

    place(str(data[0].get("turn", "")), 0)
    if mid_label and n > 2:
        mid_str = str(data[n // 2].get("turn", ""))
        place(mid_str, (n - len(mid_str)) // 2)
    last_str = str(data[-1].get("turn", ""))
    place(last_str, n - len(last_str))
    return "".join(chars)


def render_hit_rate_chart(history: List[Dict[str, Any]]) -> str:
    """ASCII hit-rate trend chart (port of pi's CacheGraphOverlay)."""
    if not history:
        return "No hit-rate data yet — complete a few DeepSeek turns first."

    rates = [float(p.get("hitRate", 0.0)) for p in history]
    max_rate, min_rate = max(rates), min(rates)
    chart_w = min(len(history), CHART_MAX_WIDTH)
    step = max(1, len(history) // chart_w)
    data = [p for i, p in enumerate(history) if i % step == 0][-chart_w:]
    y_w = max(len(f"{max_rate:.0f}"), len(f"{min_rate:.0f}")) + 1

    lines: List[str] = []
    if max_rate - min_rate < FLAT_CHART_EPSILON:
        mid = len(data) // 2
        flat_line = " " * mid + "━" + " " * (len(data) - mid - 1)
        lines.append(f"{min_rate:.0f}%".rjust(y_w) + flat_line)
        lines.append(" " * y_w + "─" * len(data))
        lines.append(" " * y_w + _x_axis_labels(data, mid_label=False))
    else:
        data_rates = [float(p.get("hitRate", 0.0)) for p in data]
        for row in range(CHART_HEIGHT, -1, -1):
            threshold = min_rate + (max_rate - min_rate) * (row / CHART_HEIGHT)
            if row == CHART_HEIGHT:
                label = f"{max_rate:.0f}%".rjust(y_w)
            elif row == 0:
                label = f"{min_rate:.0f}%".rjust(y_w)
            else:
                label = " " * y_w
            lines.append(
                label + "".join("█" if r >= threshold else " " for r in data_rates)
            )
        lines.append(" " * y_w + "─" * len(data))
        lines.append(" " * y_w + _x_axis_labels(data, mid_label=True))
    return "\n".join(lines)


def format_graph_text() -> str:
    """Plain-text /cache-graph body (surface-independent)."""
    history = get_telemetry().history_snapshot()
    header = f"DeepSeek cache hit-rate trend ({len(history)} points)"
    return f"{header}\n{render_hit_rate_chart(history)}"


def reset_all() -> str:
    """Zero telemetry, clear the summary cache, delete every persisted file."""
    get_telemetry().reset()
    get_summary_cache().clear()
    return "DeepSeek cache stats reset."


@atexit.register
def _flush_at_exit() -> None:  # pragma: no cover - exercised at interpreter exit
    telemetry = _telemetry
    if telemetry is not None:
        try:
            telemetry.flush()
        except Exception:
            pass
