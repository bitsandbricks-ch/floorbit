"""The last good answer from the monitoring source, for when it drops out (uplink down, NMS restart).

Kept in memory and saved to the event's ``monitoring-cache.json`` document in Floorbit's database
at most once a minute, for 7 days, so another worker or pod (which reads it when it has no answer
of its own) and a restart during an outage still have something to show. See docs/offline.md.
"""
from __future__ import annotations

import os
import threading
import time

from .. import store

TTL = 7 * 24 * 3600
MAX_ENTRIES = 5000
WRITE_EVERY = 60
RELOAD_EVERY = 10    # seconds: how often a miss asks the database for what other workers saved

_lock = threading.Lock()
_memory: dict[str, list] = {}       # key -> [at, value]
_loaded = False
_last_write = 0.0
_last_load = 0.0


def path():
    configured = os.environ.get('MONITORING_CACHE_FILE')
    return store.event_file(configured) if configured else store.event_path('monitoring-cache.json')


def _fresh(entry, now):
    return isinstance(entry, list) and len(entry) == 2 and isinstance(entry[0], (int, float)) \
        and now - entry[0] < TTL


def _load(force=False):
    """Take in what the database has that is newer than ours. Under the lock."""
    global _loaded, _last_load
    now = time.time()
    if _loaded and not (force and now - _last_load >= RELOAD_EVERY):
        return
    _loaded, _last_load = True, now
    try:
        raw = store.read_json(path(), {})
    except Exception as exc:  # noqa: BLE001  # the database away: what is in memory will do
        print(f'[sources] could not read the last good data: {exc}')
        return
    for key, entry in raw.items():
        if _fresh(entry, now) and (key not in _memory or _memory[key][0] < entry[0]):
            _memory[key] = list(entry)


def _trim():
    if len(_memory) > MAX_ENTRIES:
        for old in sorted(_memory, key=lambda k: _memory[k][0])[:len(_memory) - MAX_ENTRIES]:
            _memory.pop(old, None)


def _write():
    """Save at most once a minute, keeping what other workers saved since (the newest per key wins)."""
    global _last_write
    now = time.time()
    if 0 <= now - _last_write < WRITE_EVERY:
        return
    _last_write = now
    try:
        saved = store.read_json(path(), {})
        for key in [k for k, entry in saved.items() if not _fresh(entry, now)]:
            del saved[key]
        for key, entry in _memory.items():
            if key not in saved or saved[key][0] < entry[0]:
                saved[key] = entry
        if len(saved) > MAX_ENTRIES:
            for old in sorted(saved, key=lambda k: saved[k][0])[:len(saved) - MAX_ENTRIES]:
                del saved[old]
        store.write_json(path(), saved)
    except Exception as exc:  # noqa: BLE001  # a monitoring answer must not fail over its backup
        print(f'[sources] could not save the last good data: {exc}')


def put(key, value):
    with _lock:
        _load()
        _memory[key] = [time.time(), value]
        _trim()
        _write()


def get(key):
    """(at, value) of the last good answer, or None."""
    with _lock:
        _load()
        entry = _memory.get(key)
        if entry is None:
            _load(force=True)       # another worker or pod may have it
            entry = _memory.get(key)
    return tuple(entry) if entry and _fresh(entry, time.time()) else None


def clear():
    """Tests only."""
    global _loaded, _last_write, _last_load
    with _lock:
        _memory.clear()
        _loaded, _last_write, _last_load = True, 0.0, 0.0
