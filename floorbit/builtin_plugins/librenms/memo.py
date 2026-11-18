"""A small in-process cache with one loader per key at a time.

The local agent runs the LibreNMS plugin without Redis, so without this every seat lookup read the
whole MAC table of every switch the MAC was seen on, and searched LibreNMS for each switch by name
again. At a 400-switch event a check-in burst then managed 9 lookups a second. Redis (when there is
one) stays the shared cache between pods; this sits in front of it.
"""
import threading
import time
from collections import OrderedDict


class Memo:
    def __init__(self, max_items=5000):
        self.max_items = max_items
        self._lock = threading.Lock()
        self._items = OrderedDict()      # key -> (expires, value)
        self._loading = {}               # key -> Lock held by the one thread loading it

    def get(self, key, now=None):
        now = time.monotonic() if now is None else now
        with self._lock:
            hit = self._items.get(key)
            if hit and hit[0] > now:
                return True, hit[1]
        return False, None

    def put(self, key, value, ttl, now=None):
        if ttl <= 0:
            return
        now = time.monotonic() if now is None else now
        with self._lock:
            self._items[key] = (now + ttl, value)
            self._items.move_to_end(key)
            while len(self._items) > self.max_items:
                self._items.popitem(last=False)

    def load(self, key, loader, ttl, keep=lambda value: True):
        """The cached value, else ``loader()``'s, kept for ``ttl`` seconds when ``keep(value)``.
        Callers asking for the same key at once wait for the first one instead of all asking
        LibreNMS (a check-in page reloaded by a whole row)."""
        found, value = self.get(key)
        if found:
            return value
        with self._lock:
            gate = self._loading.setdefault(key, threading.Lock())
        with gate:
            found, value = self.get(key)
            if found:
                return value
            try:
                value = loader()
                if keep(value):
                    self.put(key, value, ttl() if callable(ttl) else ttl)
                return value
            finally:
                with self._lock:
                    if self._loading.get(key) is gate:
                        del self._loading[key]

    def clear(self):
        with self._lock:
            self._items.clear()
