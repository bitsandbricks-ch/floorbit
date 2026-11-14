"""The last good answer from the monitoring source, for when it drops out (uplink down, NMS restart).

Kept in Redis when there is one (shared by every worker, 7 days), otherwise in memory and written
to ``monitoring-cache.json`` next to data.json at most once a minute, so a restart during an
outage still has something to show. See docs/offline.md.
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
import time

TTL = 7 * 24 * 3600
MAX_ENTRIES = 5000
WRITE_EVERY = 60

_lock = threading.Lock()
_memory: dict[str, list] = {}       # key -> [at, value]
_loaded = False
_last_write = 0.0


def _redis():
    try:
        from ..cache import get_redis_client
        return get_redis_client()
    except Exception:  # noqa: BLE001  # no cache module or no Redis: memory and disk instead
        return None


def path():
    from .. import store
    configured = os.environ.get('MONITORING_CACHE_FILE')
    return configured or os.path.join(os.path.dirname(os.path.abspath(store.DATA_FILE)), 'monitoring-cache.json')


def _load():
    global _loaded
    if _loaded:
        return
    _loaded = True
    try:
        with open(path(), encoding='utf-8') as f:
            raw = json.load(f)
        if isinstance(raw, dict):
            _memory.update({k: v for k, v in raw.items() if isinstance(v, list) and len(v) == 2})
    except (OSError, ValueError):
        pass


def _write():
    global _last_write
    now = time.time()
    if now - _last_write < WRITE_EVERY:
        return
    _last_write = now
    target = path()
    try:
        directory = os.path.dirname(target) or '.'
        fd, tmp = tempfile.mkstemp(dir=directory, prefix='.monitoring-cache-')
        with os.fdopen(fd, 'w') as f:
            json.dump(_memory, f)
        os.replace(tmp, target)
    except OSError as exc:
        print(f'[sources] could not write {target}: {exc}')


def put(key, value):
    entry = [time.time(), value]
    client = _redis()
    if client:
        try:
            client.setex(f'lastgood:{key}', TTL, json.dumps(entry))
            return
        except Exception:  # noqa: BLE001  # Redis gone: fall through to memory
            pass
    with _lock:
        _load()
        _memory[key] = entry
        if len(_memory) > MAX_ENTRIES:
            for old in sorted(_memory, key=lambda k: _memory[k][0])[:len(_memory) - MAX_ENTRIES]:
                _memory.pop(old, None)
        _write()


def get(key):
    """(at, value) of the last good answer, or None."""
    client = _redis()
    if client:
        try:
            raw = client.get(f'lastgood:{key}')
            if raw:
                at, value = json.loads(raw)
                return at, value
        except Exception:  # noqa: BLE001
            pass
    with _lock:
        _load()
        entry = _memory.get(key)
    return tuple(entry) if entry else None


def clear():
    """Tests only."""
    global _loaded, _last_write
    with _lock:
        _memory.clear()
        _loaded, _last_write = True, 0.0
