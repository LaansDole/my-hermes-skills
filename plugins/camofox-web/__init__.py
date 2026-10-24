"""camofox-web: Hermes web_search / web_extract provider backed by a local camofox-browser server."""
from __future__ import annotations

from .provider import CamofoxWebProvider


def register(ctx) -> None:
    ctx.register_web_search_provider(CamofoxWebProvider())
