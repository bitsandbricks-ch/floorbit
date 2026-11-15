"""Wi-Fi view (issue #98): access point load, clients per AP and a channel map on the floor plan.

Plugins with ``uses: [wifi]`` answer ``wifi_aps()`` with one entry per access point::

    {"name": "ap-hall-01", "model": "U6-Pro", "status": "up",
     "radios": [{"band": "5", "channel": 36, "width": 80, "utilization": 42, "clients": 18}]}

Floorbit keeps client counts only: whatever else a plugin sends (client names, MACs) is dropped
here and never stored. APs are matched by name to the inventory, and an AP placed on the floor
plan is drawn there. Answers are kept for ``CACHE_SECONDS`` so a room of open pages asks the
controller once.
"""
import math
import threading
import time

from .plugins import PluginError

BANDS = ('2.4', '5', '6')
CACHE_SECONDS = 20
MAX_APS = 2000
BUSY = 70          # channel utilization (%) past which an AP is busy
CROWDED = 40       # clients on one AP past which it is crowded
# Two APs on the same channel closer than this (percent of the plan's width) hear each other: a
# rough rule, since the plan has no scale and walls aren't drawn. 2.4 GHz reaches furthest.
NEAR = {'2.4': 30.0, '5': 25.0, '6': 20.0}
_lock = threading.Lock()
_cache = {'at': 0.0, 'value': None}


def _int(value, lo, hi):
    try:
        n = round(float(value))
    except (TypeError, ValueError, OverflowError):
        return None
    return n if lo <= n <= hi else None


def _band(value):
    v = str(value or '').strip().lower().replace('ghz', '').strip()
    return {'2': '2.4', '2.4': '2.4', 'ng': '2.4', '5': '5', 'na': '5', '6': '6', '6e': '6'}.get(v)


def clean_ap(raw):
    """One plugin answer as an AP, keeping counts only. None when it has no name."""
    if not isinstance(raw, dict):
        return None
    name = ' '.join(str(raw.get('name') or '').split())[:80]
    if not name:
        return None
    radios = []
    for r in raw.get('radios') or []:
        if not isinstance(r, dict) or not _band(r.get('band')):
            continue
        radios.append({'band': _band(r.get('band')), 'channel': _int(r.get('channel'), 1, 233),
                       'width': _int(r.get('width'), 20, 320), 'utilization': _int(r.get('utilization'), 0, 100),
                       'clients': _int(r.get('clients'), 0, 10000) or 0})
    radios.sort(key=lambda r: BANDS.index(r['band']))
    clients = _int(raw.get('clients'), 0, 100000)
    status = 'down' if str(raw.get('status') or '').lower() in ('down', 'offline', '0', 'false') else 'up'
    return {'name': name, 'model': ' '.join(str(raw.get('model') or '').split())[:60], 'status': status,
            'clients': clients if clients is not None else sum(r['clients'] for r in radios), 'radios': radios}


def ask(registry):
    """Every AP the wifi plugins know now: (aps, errors). Cached for CACHE_SECONDS."""
    with _lock:
        if _cache['value'] is not None and time.time() - _cache['at'] < CACHE_SECONDS:
            return _cache['value']
    aps, errors = {}, []
    for spec in registry.feeders('wifi'):
        try:
            for raw in registry.call(spec, 'wifi_aps') or []:
                ap = clean_ap(raw)
                if ap and ap['name'].lower() not in aps and len(aps) < MAX_APS:
                    aps[ap['name'].lower()] = {**ap, 'source': spec.name}
        except PluginError as exc:
            errors.append(f'{spec.name}: {exc}')
    value = (list(aps.values()), errors)
    with _lock:
        _cache.update(at=time.time(), value=value)
    return value


def reset():
    with _lock:
        _cache.update(at=0.0, value=None)


def _overlaps(placed):
    """Pairs of placed, up APs on the same channel of a band that are near each other."""
    from .blueprints.screen import PLAN_H, PLAN_W
    tall = PLAN_H / PLAN_W   # x and y are percent of the plan's width and height
    out = []
    for i, a in enumerate(placed):
        for b in placed[i + 1:]:
            if a['status'] != 'up' or b['status'] != 'up' or a.get('hall_id') != b.get('hall_id'):
                continue
            dist = math.hypot(a['x'] - b['x'], (a['y'] - b['y']) * tall)
            for ra in a['radios']:
                for rb in b['radios']:
                    if ra['band'] == rb['band'] and ra['channel'] and ra['channel'] == rb['channel'] \
                            and dist < NEAR[ra['band']]:
                        out.append({'band': ra['band'], 'channel': ra['channel'], 'aps': [a['name'], b['name']]})
    return out


def overview(registry, data):
    """The APs with where they are on the floor plan, totals and what needs a look."""
    from . import halls, inventory
    aps, errors = ask(registry)
    aps = [dict(a) for a in aps]   # the cache is shared: don't write into it
    default = halls.default_id(data)
    by_name = {d['name'].lower(): d for d in inventory.devices(data) if d.get('name')}
    for ap in aps:
        dev = by_name.get(ap['name'].lower())
        placed = bool(dev and dev.get('x') is not None and dev.get('y') is not None)
        ap.update(x=dev['x'] if placed else None, y=dev['y'] if placed else None,
                  hall_id=(dev or {}).get('hall_id') or default, placed=placed)
        top = max((r['utilization'] or 0 for r in ap['radios']), default=0)
        ap['busy'] = ap['status'] == 'up' and (top >= BUSY or ap['clients'] >= CROWDED)
    aps.sort(key=lambda a: a['name'].lower())
    bands = {}
    for band in BANDS:
        radios = [r for a in aps if a['status'] == 'up' for r in a['radios'] if r['band'] == band]
        if radios:
            used = [r['utilization'] for r in radios if r['utilization'] is not None]
            bands[band] = {'clients': sum(r['clients'] for r in radios), 'radios': len(radios),
                           'utilization': round(sum(used) / len(used)) if used else None}
    return {
        'aps': aps,
        'clients': sum(a['clients'] for a in aps if a['status'] == 'up'),
        'up': sum(a['status'] == 'up' for a in aps),
        'down': [a['name'] for a in aps if a['status'] == 'down'],
        'busy': [a['name'] for a in aps if a['busy']],
        'overlaps': _overlaps([a for a in aps if a['placed']]),
        'bands': bands,
        'sources': [s.name for s in registry.feeders('wifi')],
        'errors': errors,
        'thresholds': {'busy': BUSY, 'crowded': CROWDED},
    }
