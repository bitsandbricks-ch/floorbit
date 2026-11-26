"""Rule sources for the applications (issue #1503): rules files on the web that Floorbit fetches on
a schedule and keeps, so the games it recognises stay current without a Floorbit release.

- **A source** is an https URL with a name, how often to fetch it (every 24 hours unless set) and an
  on/off switch, kept in the event (``application_sources`` in data.json).
- **Its file** is the applications page's own shape, ``{"version": 1, "applications": [{id, name, kind,
  category, part_of, sites, ports, cidr, depots}]}``, or a plain domain list (uklans/cache-domains or
  v2fly/domain-list-community style), which becomes one site group named after the source.
- **Fetching** goes through the outbound guard (floorbit/outbound.py), refuses more than ``MAX_BYTES``
  and checks every entry as the page does. A source keeps its last good copy: a fetch that fails
  keeps it and shows why. The copies live in the event's ``application-sources.json``.
- **Order** when two name the same application: the event's own changes, then the sources from the
  top of the list down, then the lists Floorbit ships (``applications.builtin``), which stay the
  fallback for a hall without internet.
- **Freeze** stops all fetching, so the numbers don't move during the event.

The agent's flow rules come from the merged list (``applications.flow_rules``): nothing changes there.
"""
import contextlib
import json
import re
import threading
import time
import uuid

from . import store
from .store import load_data, save_data

KEY = 'application_sources'
FROZEN = 'application_sources_frozen'
MAX_SOURCES = 20
MAX_BYTES = 4 * 1024 * 1024
MAX_APPS = 2000
TIMEOUT = 20
EVERY_HOURS = 24
RETRY_AFTER = 15 * 60
NAME_MAX = 60
URL_RE = re.compile(r'^https://[^\s/?#@]+(?::\d{1,5})?(?:/[^\s]*)?\Z')
_lock = threading.Lock()
_cache = {'at': None, 'path': None, 'copies': {}}


class SourceError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.message = message
        self.status = status


# ── what is set up ──────────────────────────────────────────────────────────

def sources(data=None):
    data = load_data() if data is None else data
    return [s for s in data.get(KEY) or [] if isinstance(s, dict) and s.get('id')]


def frozen(data=None):
    data = load_data() if data is None else data
    return bool(data.get(FROZEN))


def _clean(body, current=None):
    if not isinstance(body, dict):
        raise SourceError('Send the source as a JSON object.')
    current = current or {}
    name = ' '.join(str(body.get('name', current.get('name')) or '').split())
    if not 1 <= len(name) <= NAME_MAX:
        raise SourceError(f'Give the source a name (up to {NAME_MAX} characters).')
    url = str(body.get('url', current.get('url')) or '').strip()
    if len(url) > 500 or not URL_RE.match(url):
        raise SourceError('The source is an https URL.')
    every = body.get('every_hours', current.get('every_hours', EVERY_HOURS))
    if not isinstance(every, int) or isinstance(every, bool) or not 1 <= every <= 24 * 30:
        raise SourceError('Fetch it every 1 to 720 hours.')
    on = body.get('on', current.get('on', True))
    return {'name': name, 'url': url, 'every_hours': every, 'on': bool(on)}


def add(body):
    with _lock:
        data = load_data()
        found = sources(data)
        if len(found) >= MAX_SOURCES:
            raise SourceError(f'Floorbit keeps at most {MAX_SOURCES} sources.')
        entry = {'id': uuid.uuid4().hex[:12], **_clean(body)}
        data[KEY] = [*found, entry]
        save_data(data)
    return entry


def change(source_id, body):
    with _lock:
        data = load_data()
        found = sources(data)
        current = next((s for s in found if s['id'] == source_id), None)
        if current is None:
            raise SourceError('No such source.', 404)
        entry = {'id': source_id, **_clean(body, current)}
        if 'position' in (body or {}):
            pos = body['position']
            if not isinstance(pos, int) or isinstance(pos, bool) or not 0 <= pos < len(found):
                raise SourceError('The position is a place in the list, from 0.')
            rest = [s for s in found if s['id'] != source_id]
            data[KEY] = [*rest[:pos], entry, *rest[pos:]]
        else:
            data[KEY] = [entry if s['id'] == source_id else s for s in found]
        save_data(data)
    return entry


def remove(source_id):
    with _lock:
        data = load_data()
        found = sources(data)
        gone = next((s for s in found if s['id'] == source_id), None)
        if gone is None:
            return None
        data[KEY] = [s for s in found if s['id'] != source_id]
        save_data(data)
        copies = _copies()
        copies.pop(source_id, None)
        _write_copies(copies)
    return gone


def set_frozen(value):
    with _lock:
        data = load_data()
        data[FROZEN] = bool(value)
        save_data(data)
    return bool(value)


# ── the copies ──────────────────────────────────────────────────────────────

def _path():
    return store.event_path('application-sources.json')


def _copies():
    found = store.read_json(_path(), {})
    return found if isinstance(found, dict) else {}


def _write_copies(copies):
    store.write_json(_path(), copies)
    _cache['at'] = None


def copies():
    """{source id: {at, ok, error, changed_at, applications}}, read again at most every few seconds:
    every page that lists applications asks."""
    now, path = time.monotonic(), _path()
    if _cache['at'] is None or _cache['path'] != path or now - _cache['at'] > 5:
        _cache['copies'] = _copies()
        _cache['at'], _cache['path'] = now, path
    return _cache['copies']


def status(data=None):
    """The sources as the page shows them: what is set up and how each last fetch went."""
    found = copies()
    out = []
    for s in sources(data):
        c = found.get(s['id']) or {}
        out.append({**s, 'at': c.get('at'), 'ok': c.get('ok'), 'error': c.get('error'),
                    'changed_at': c.get('changed_at'), 'count': len(c.get('applications') or [])})
    return out


def overlay(data=None):
    """[(source, [application])] of the sources that are on and have a good copy, lowest priority
    first, so a later one wins over an earlier one when both name the same application."""
    found = copies()
    out = []
    for s in reversed(sources(data)):
        apps = (found.get(s['id']) or {}).get('applications')
        if s.get('on') and apps:
            out.append((s, apps))
    return out


# ── reading a file ──────────────────────────────────────────────────────────

def parse(raw, source):
    """The applications in a fetched file. Raises SourceError when it is neither shape."""
    from . import applications
    text = raw.decode('utf-8', errors='replace') if isinstance(raw, bytes) else str(raw)
    try:
        doc = json.loads(text)
    except ValueError:
        doc = None
    if isinstance(doc, dict):
        return _from_json(doc, source, applications)
    if doc is not None:
        raise SourceError('A rules file is a JSON object with "applications", or a list of domains.')
    sites = _domains(text)
    if not sites:
        raise SourceError('The file has no applications and no domains.')
    try:
        matches = applications._matches({'sites': sites[:applications.MAX_ITEMS]})
    except applications.ApplicationError as exc:
        raise SourceError(exc.message) from exc
    return [{'id': f'src-{source["id"]}', 'name': source['name'], 'kind': 'sitegroup', 'category': 'other',
             'part_of': None, **matches}]


def _domains(text):
    """Domains from a cache-domains list (one per line, ``*.`` wildcards) or a v2fly one
    (``domain:``/``full:``, attributes after ``@``); ``include:`` and ``regexp:`` lines are left out."""
    out = []
    for line in text.splitlines():
        line = line.split('#', 1)[0].strip()
        if not line:
            continue
        kind, _, rest = line.partition(':') if ':' in line else ('domain', '', line)
        if kind not in ('domain', 'full'):
            continue
        words = rest.split('@', 1)[0].split()
        name = words[0].lstrip('*.').lower() if words else ''
        if '.' in name and name not in out:
            out.append(name)
    return out


def _from_json(doc, source, applications):
    if doc.get('version') != 1 or not isinstance(doc.get('applications'), list):
        raise SourceError('A rules file says "version": 1 and has a list of "applications".')
    if len(doc['applications']) > MAX_APPS:
        raise SourceError(f'A rules file has at most {MAX_APPS} applications.')
    out, seen = [], set()
    for i, entry in enumerate(doc['applications']):
        if not isinstance(entry, dict):
            raise SourceError(f'Application {i + 1} is not an object.')
        aid = str(entry.get('id') or '')
        if not applications.ID_RE.match(aid) or aid in seen:
            raise SourceError(f'Application {i + 1} needs an id of its own (a-z, 0-9 and -).')
        seen.add(aid)
        name = ' '.join(str(entry.get('name') or '').split())
        if not 1 <= len(name) <= 60:
            raise SourceError(f'Application {aid} needs a name (up to 60 characters).')
        kind = entry.get('kind') or 'game'
        if kind not in applications.KINDS:
            raise SourceError(f'Application {aid}: the kind is game, launcher or sitegroup.')
        category = entry.get('category') or ('gaming' if kind != 'sitegroup' else 'other')
        if category not in applications.CATEGORIES:
            raise SourceError(f'Application {aid}: the category is one of {", ".join(applications.CATEGORIES)}.')
        part_of = entry.get('part_of') or None
        if part_of is not None and (kind != 'game' or not applications.ID_RE.match(str(part_of))):
            raise SourceError(f'Application {aid}: only a game is part of something, and that is a launcher id.')
        try:
            matches = applications._matches(entry)
        except applications.ApplicationError as exc:
            raise SourceError(f'Application {aid}: {exc.message}') from exc
        out.append({'id': aid, 'name': name, 'kind': kind, 'category': category, 'part_of': part_of, **matches})
    return out


# ── fetching ────────────────────────────────────────────────────────────────

def _fetch(url):
    """The file's bytes. The outbound guard checks where the connection really went."""
    import requests

    from .marketplace import MarketError, _get_capped
    try:
        return _get_capped(url, MAX_BYTES, TIMEOUT)
    except MarketError as exc:
        raise SourceError(f'The file is larger than {MAX_BYTES // 1024 // 1024} MB.') from exc
    except requests.RequestException as exc:
        raise SourceError(f'Could not fetch it: {type(exc).__name__}.') from exc


def sync(source_id, now=None, fetch=None):
    """Fetch one source now. Returns its status row. A failure keeps the last good copy."""
    now = time.time() if now is None else now
    source = next((s for s in sources() if s['id'] == source_id), None)
    if source is None:
        raise SourceError('No such source.', 404)
    try:
        apps = parse((fetch or _fetch)(source['url']), source)
        result = {'ok': True, 'error': None, 'applications': apps}
    except SourceError as exc:
        result = {'ok': False, 'error': exc.message}
    with _lock:
        found = _copies()
        old = found.get(source_id) or {}
        entry = {**old, 'at': now, 'ok': result['ok'], 'error': result['error']}
        if result['ok']:
            if result['applications'] != old.get('applications'):
                entry['changed_at'] = now
            entry['applications'] = result['applications']
        found[source_id] = entry
        _write_copies(found)
    return next(s for s in status() if s['id'] == source_id)


def due(source, copy, now):
    if not source.get('on'):
        return False
    at = (copy or {}).get('at')
    if not isinstance(at, (int, float)) or now < at:
        return True
    wait = source.get('every_hours', EVERY_HOURS) * 3600
    return now - at >= (wait if (copy or {}).get('ok') else min(wait, RETRY_AFTER))


def tick(now=None, fetch=None):
    """One look at the schedule: fetch what is due unless the sources are frozen. The ids fetched."""
    now = time.time() if now is None else now
    data = load_data()
    if frozen(data):
        return []
    found = _copies()
    done = []
    for s in sources(data):
        if due(s, found.get(s['id']), now):
            with contextlib.suppress(SourceError):
                sync(s['id'], now, fetch)
            done.append(s['id'])
    return done


def _loop(app, stop):
    from . import cluster
    while not stop.wait(60):
        try:
            if cluster.leading():   # several pods fetch once
                with app.app_context():
                    tick()
        except Exception as exc:  # noqa: BLE001  # the loop must outlive one bad source
            print(f'[application-sources] scheduled fetch failed: {exc}')


def init_app(app, start_background=True):
    if not start_background:
        return None
    stop = threading.Event()
    threading.Thread(target=_loop, args=(app, stop), name='application-sources', daemon=True).start()
    return stop
