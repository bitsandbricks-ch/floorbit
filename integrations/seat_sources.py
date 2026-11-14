"""Pluggable sources for the seat → user / IP mapping.

The floor plan needs, per seat number, who sits there and which IP their
machine has. Today that is the hand-edited ``seats.json``. Later it can come
from a DHCP server, an event/registration backend, or anything else, without
touching the rest of the app: write a ``SeatSource`` subclass, register it,
and list it in ``SEAT_SOURCES``.

Every source returns the same shape::

    {"A-1": {"username": "alice", "ip_address": "10.0.1.11"}, ...}

``SEAT_SOURCES`` is a comma-separated list, e.g. ``json`` (default) or
``http,json``. Sources are merged in order: the first source that has a value
for a field wins, so a live source can sit in front of the static file and
the file fills the gaps.

Hand entries (Floorbit's seat mapping page, ``floorbit/seatmap.py``) always come first, so
what people type in wins; plugins with ``uses: [mapping]`` follow them, then ``SEAT_SOURCES``.

Built-in sources:

* ``manual``   the entries on the Seat mapping page (always first, never needs listing)
* ``json``     reads ``SEAT_SOURCE_JSON_PATH`` (default ``seats.json``)
* ``http``     GETs ``SEAT_SOURCE_HTTP_URL``; the response must be the shape
               above, either at the top level or under ``"seats"``. Optional
               ``SEAT_SOURCE_HTTP_TOKEN`` is sent as a Bearer token.
* ``checkin``  the seat check-in page (see ``checkin.py``)
"""
import json
import threading
import time

import requests

from . import config


class SeatSource:
    """Base class. Subclasses set ``name`` and implement ``fetch``."""
    name = 'base'
    label = 'Base'

    def fetch(self):
        """Return {seat_number: {'username': str|None, 'ip_address': str|None, ...}}."""
        raise NotImplementedError

    def configured(self):
        return True


class JsonFileSource(SeatSource):
    name = 'json'
    label = 'seats.json file'

    def path(self):
        return config.get('SEAT_SOURCE_JSON_PATH', 'seats.json')

    def fetch(self):
        with open(self.path()) as f:
            data = json.load(f)
        return data.get('seats', data) if isinstance(data, dict) else {}


class HttpJsonSource(SeatSource):
    name = 'http'
    label = 'HTTP JSON endpoint'

    def configured(self):
        return bool(config.get('SEAT_SOURCE_HTTP_URL'))

    def fetch(self):
        url = config.get('SEAT_SOURCE_HTTP_URL')
        if not url:
            raise RuntimeError('SEAT_SOURCE_HTTP_URL is not set')
        headers = {'Accept': 'application/json'}
        token = config.get('SEAT_SOURCE_HTTP_TOKEN')
        if token:
            headers['Authorization'] = f'Bearer {token}'
        resp = requests.get(url, headers=headers, timeout=10,
                            verify=config.get_bool('SEAT_SOURCE_HTTP_VERIFY_SSL', True))
        resp.raise_for_status()
        data = resp.json()
        return data.get('seats', data) if isinstance(data, dict) else {}


_registry = {}
_cache = {'ts': 0.0, 'data': None, 'errors': {}}
_cache_lock = threading.Lock()


def register(source_cls):
    """Register a SeatSource subclass (usable as a decorator)."""
    _registry[source_cls.name] = source_cls()
    return source_cls


class ManualSource(SeatSource):
    name = 'manual'
    label = 'Entered by hand'

    def fetch(self):
        from floorbit import seatmap, store
        # Only the mapping itself: who typed it in and when stays on the Seat mapping page.
        return {seat: {k: v for k, v in entry.items() if k in seatmap.FIELDS}
                for seat, entry in seatmap.entries(store.load_data()).items()}


register(JsonFileSource)
register(HttpJsonSource)
register(ManualSource)

# Set by floorbit.plugins: returns [(name, label, fetch)] for the plugins that feed the mapping.
plugin_sources = None


def configured_names():
    raw = config.get('SEAT_SOURCES', 'json') or 'json'
    return [n.strip().lower() for n in str(raw).split(',') if n.strip() and n.strip().lower() != 'manual']


def _plugins():
    try:
        return list(plugin_sources()) if plugin_sources else []
    except Exception as exc:  # noqa: BLE001  # never let the plugin list break the mapping
        print(f'[integrations] could not list plugin seat sources: {exc}')
        return []


def active_names():
    return ['manual', *[p[0] for p in _plugins()], *configured_names()]


def _normalise(entry):
    if not isinstance(entry, dict):
        return {}
    out = dict(entry)
    # Accept a few common spellings so sources don't need adapters
    if 'ip_address' not in out:
        out['ip_address'] = out.get('ip') or out.get('ipv4')
    if 'username' not in out:
        out['username'] = out.get('user') or out.get('name')
    return out


def load(max_age=None):
    """Merged mapping from all active sources. Cached for SEAT_SOURCE_CACHE_SECONDS."""
    ttl = config.get_int('SEAT_SOURCE_CACHE_SECONDS', 30, minimum=0) if max_age is None else max_age
    with _cache_lock:
        if _cache['data'] is not None and time.time() - _cache['ts'] < ttl:
            return _cache['data']

    merged, errors = {}, {}
    plugins = {name: fetch for name, _label, fetch in _plugins()}
    for name in active_names():
        source = _registry.get(name)
        fetch = plugins.get(name) or (source.fetch if source else None)
        if fetch is None:
            errors[name] = 'unknown source'
            continue
        try:
            data = fetch() or {}
        except Exception as exc:  # noqa: BLE001  # a failing source is reported, the rest still load
            errors[name] = str(exc)
            print(f"[integrations] seat source {name} failed: {exc}")
            continue
        for seat, entry in data.items():
            entry = _normalise(entry)
            target = merged.setdefault(str(seat), {})
            sources_of = target.setdefault('field_sources', {})
            for key, value in entry.items():
                if key in ('sources', 'field_sources'):
                    continue
                if target.get(key) in (None, '') and value not in (None, ''):
                    target[key] = value
                    sources_of[key] = name
            target.setdefault('sources', [])
            target['sources'].append(name)

    with _cache_lock:
        _cache.update(ts=time.time(), data=merged, errors=errors)
    return merged


def invalidate():
    with _cache_lock:
        _cache['data'] = None


def info():
    with _cache_lock:
        errors = dict(_cache['errors'])
        last = _cache['ts'] or None
    active = active_names()
    return {
        'active': active,
        'available': [{'name': s.name, 'label': s.label, 'configured': s.configured()}
                      for s in _registry.values()] +
                     [{'name': n, 'label': label, 'configured': True, 'plugin': True} for n, label, _ in _plugins()],
        'last_load': last,
        'errors': errors,
    }
