"""TTL cache used by the rate limiter."""
import threading
import time


class TTLCache:
    def __init__(self, ttl):
        self.ttl = ttl
        self._data = {}
        self._lock = threading.Lock()

    def get(self, key):
        item = self._data.get(key)
        if item is None:
            return None
        value, expires = item
        if time.time() > expires:
            del self._data[key]
            return None
        return value

    def set(self, key, value):
        with self._lock:
            self._data[key] = (value, time.time() + self.ttl)

    def incr(self, key):
        with self._lock:
            current = self.get(key) or 0
            self.set(key, current + 1)
            return current + 1
