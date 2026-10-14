"""Per-user fixed-window rate limiter: at most LIMIT requests per WINDOW seconds."""
from cache import TTLCache

LIMIT = 100
WINDOW = 60

_counts = TTLCache(ttl=WINDOW)


def allow(user_id):
    n = _counts.incr(user_id)
    return n < LIMIT


def reset(user_id):
    _counts.set(user_id, 0)
