"""Tenants and their events (issue #466). See docs/tenancy.md.

A tenant is a club or organisation; an event is one LAN party it runs. A tenant's events are listed
in ``tenant.json`` in the tenant's folder. Exactly one of them is live: background workers, the
agent and live monitoring serve it, while the others are being planned or are closed.

Without ``tenant.json`` (every install before tenants existed) the tenant has one event, ``main``:
live, kept in the tenant's folder itself, so its documents are exactly where they always were.
Later events keep theirs in ``event-data/<id>/``. Paths come from ``store.tenant_path`` and
``store.event_path``; never build one from ``store.DATA_FILE``.
"""
import re
import threading
import time

from . import store

TENANT_FILE = 'tenant.json'
EVENT_FOLDER = 'event-data'
FIRST_EVENT = 'main'
STATUSES = ('planning', 'live', 'closed')
ID_RE = re.compile(r'^[a-z0-9][a-z0-9-]{0,39}$')
# How long the live event's folder is trusted before tenant.json is looked at again. Workers and
# requests ask on every path they build; this keeps that from being a read each time.
RECHECK = 2.0

_lock = threading.RLock()
_cache = {}     # tenant.json path -> (monotonic time, stamp, registry)


def _first():
    return {'id': FIRST_EVENT, 'name': '', 'status': 'live', 'folder': ''}


def _clean(raw):
    """The registry as stored, made safe: known statuses, unique ids, folders only under
    ``event-data/`` (or the tenant folder for the first event), and exactly one live event."""
    events, seen = [], set()
    for e in (raw or {}).get('events') or []:
        if not isinstance(e, dict):
            continue
        eid = e.get('id')
        if not isinstance(eid, str) or not ID_RE.match(eid) or eid in seen:
            continue
        seen.add(eid)
        folder = '' if eid == FIRST_EVENT else f'{EVENT_FOLDER}/{eid}'
        status = e.get('status') if e.get('status') in STATUSES else 'planning'
        events.append({**{k: v for k, v in e.items() if k not in ('id', 'folder', 'status')},
                       'id': eid, 'status': status, 'folder': folder})
    if not events:
        events = [_first()]
    live = [e for e in events if e['status'] == 'live']
    if len(live) != 1:
        # None or several (edited by hand): the first live one wins, else the first event.
        keep = (live or events)[0]['id']
        for e in events:
            if e['status'] == 'live' and e['id'] != keep:
                e['status'] = 'planning'
            elif e['id'] == keep:
                e['status'] = 'live'
    return {'events': events}


def path():
    return store.tenant_path(TENANT_FILE)


def registry(fresh=False):
    """{'events': [...]} for the current tenant. While the database is away, the last copy read;
    with none read yet, the default (one live event in the tenant folder)."""
    from .database import DatabaseUnavailable
    key = path()
    now = time.monotonic()
    hit = _cache.get(key)
    if hit and not fresh and now - hit[0] < RECHECK:
        return hit[2]
    try:
        stamp = store.stamp(key)
        unchanged = hit and hit[1] == stamp
        found = hit[2] if unchanged else _clean(store.read_json(key, {}) if stamp is not None else {})
    except DatabaseUnavailable:
        found = hit[2] if hit else _clean({})
        stamp = hit[1] if hit else None
    with _lock:
        _cache[key] = (now, stamp, found)
    return found


def events():
    return [dict(e) for e in registry()['events']]


def find(event_id):
    for e in registry()['events']:
        if e['id'] == event_id:
            return dict(e)
    return None


def live():
    return next(dict(e) for e in registry()['events'] if e['status'] == 'live')


def _live_folder():
    return live()['folder']


def forget():
    """Read tenant.json again on the next question (after a change, in tests)."""
    with _lock:
        _cache.clear()


def current():
    """The event this request or block works on: the one it picked, else the live one."""
    folder = store.event_dir()
    for e in registry()['events']:
        if e['folder'] == folder:
            return dict(e)
    return live()


def is_live():
    return current()['status'] == 'live'


def using_event(event):
    """Read and write the documents of this event (a dict from ``events()``) in a ``with`` block."""
    return store.using(event=event['folder'])


# ── Changing the event list ─────────────────────────────────────────────────────────────────

MAX_NAME = 120
MAX_EVENTS = 200


class EventError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def _name(value):
    name = ' '.join(str(value or '').split())[:MAX_NAME]
    if not name:
        raise EventError('Give the event a name.')
    return name


def _new_id(name, taken):
    base = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')[:32].strip('-') or 'event'
    candidate, n = base, 2
    while candidate in taken or candidate == FIRST_EVENT:
        candidate, n = f'{base}-{n}', n + 1
    return candidate


def _save(events):
    store.write_json(path(), {'events': [{k: v for k, v in e.items() if k != 'folder'} for e in events]})
    forget()


def create(name, copy_from=None, now=None):
    """Add an event in planning, starting from a copy of ``copy_from``'s floor plan (an event id;
    see event_copy.py) or empty."""
    name = _name(name)
    with _lock:
        events = [dict(e) for e in registry(fresh=True)['events']]
        if len(events) >= MAX_EVENTS:
            raise EventError('This tenant has too many events.')
        source = None
        if copy_from:
            source = next((e for e in events if e['id'] == copy_from), None)
            if source is None:
                raise EventError('No such event.', 404)
        event = {'id': _new_id(name, {e['id'] for e in events}), 'name': name, 'status': 'planning',
                 'created_at': now or time.time()}
        event['folder'] = f"{EVENT_FOLDER}/{event['id']}"
        _save([*events, event])
    if source:
        from . import event_copy
        event_copy.copy(source['id'], event['id'], mode='replace')
    return find(event['id'])


def update(event_id, name=None, status=None):
    """Rename an event or change its status. Making one live sets the live one back to planning."""
    with _lock:
        events = [dict(e) for e in registry(fresh=True)['events']]
        event = next((e for e in events if e['id'] == event_id), None)
        if event is None:
            raise EventError('No such event.', 404)
        if name is not None:
            event['name'] = _name(name)
        if status is not None:
            if status not in STATUSES:
                raise EventError('The status must be planning, live or closed.')
            if event['status'] == 'live' and status != 'live':
                raise EventError('Make another event live first: one event is always live.', 409)
            if status == 'live':
                for e in events:
                    if e['status'] == 'live':
                        e['status'] = 'planning'
            event['status'] = status
        _save(events)
    return find(event_id)


store.live_event_dir = _live_folder
