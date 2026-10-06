"""Per-user, short-TTL cache around the resolver (guideline 3 and 15: keyed per user, never shared)."""
from __future__ import annotations

import threading
import time
from collections import OrderedDict

from ..config import Settings
from ..odoo.client import OdooReadClient
from .resolver import SOResolver


class TTLCache:
    def __init__(self, maxsize: int = 200, clock=time.monotonic):
        self._d: OrderedDict = OrderedDict()
        self._lock = threading.Lock()
        self.maxsize = maxsize
        self.clock = clock

    def get(self, key):
        with self._lock:
            item = self._d.get(key)
            if not item:
                return None
            exp, val = item
            if exp < self.clock():
                del self._d[key]
                return None
            self._d.move_to_end(key)
            return val

    def set(self, key, val, ttl: float):
        with self._lock:
            self._d[key] = (self.clock() + ttl, val)
            self._d.move_to_end(key)
            while len(self._d) > self.maxsize:
                self._d.popitem(last=False)

    def clear(self):
        with self._lock:
            self._d.clear()


so_cache = TTLCache(maxsize=100)
fields_cache = TTLCache(maxsize=200)


def get_resolved(client: OdooReadClient, settings: Settings, so_name: str, *, refresh: bool = False) -> dict:
    """Resolve an SO as the logged-in user. Cache key includes the uid so users never see each other's data."""
    key = (client.uid, so_name.strip().lower())
    if not refresh:
        hit = so_cache.get(key)
        if hit is not None:
            return hit
    fkey = ("fields", client.uid)
    fields = fields_cache.get(fkey)
    if fields is None:
        fields = {}
    resolver = SOResolver(client, settings, fields)
    result = resolver.resolve(so_name)
    fields_cache.set(fkey, fields, 600)
    so_cache.set(key, result, settings.cache_ttl_seconds)
    return result
