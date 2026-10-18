"""Alert on Anthropic classifier refusals (cyber / bio / frontier_llm / reasoning_extraction).

Hermes maps Anthropic ``stop_reason: refusal`` to ``content_filter`` and, in
``agent/turn_truncation.py::handle_content_policy_refusal``, fires the
``api_request_error`` hook (reason=content_policy_blocked) and then activates the
``fallback_providers`` chain. This hook only observes: it appends a JSON line to
``$HERMES_HOME/logs/refusal-fallback.log`` and posts a macOS notification.
Delegated subagents run in-process, so their refusals hit this hook too.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

_REASON = "content_policy_blocked"


def _home() -> Path:
    try:
        from hermes_constants import get_hermes_home
        return Path(get_hermes_home())
    except Exception:
        return Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))


def _notify(title: str, msg: str) -> None:
    if sys.platform != "darwin":
        return
    esc = lambda s: s.replace("\\", "\\\\").replace('"', '\\"')[:200]
    try:
        subprocess.Popen(
            ["osascript", "-e", f'display notification "{esc(msg)}" with title "{esc(title)}"'],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass


def on_api_request_error(**kw) -> None:
    if kw.get("reason") != _REASON:
        return
    err = kw.get("error") or {}
    record = {
        "at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "session_id": kw.get("session_id"),
        "task_id": kw.get("task_id"),
        "provider": kw.get("provider"),
        "model": kw.get("model"),
        "message": (err.get("message") or "")[:500],
        "next": "fallback_providers chain (claude-opus-4-8, xhigh) if configured",
    }
    try:
        log = _home() / "logs" / "refusal-fallback.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
    except Exception:
        pass
    _notify(f"Hermes refusal on {record['model']}", record["message"] or "classifier block -> falling back")


def register(ctx) -> None:
    ctx.register_hook("api_request_error", on_api_request_error)
