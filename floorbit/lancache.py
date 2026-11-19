"""What the LAN cache served (issue #88), read from its access log. See docs/games.md.

The lancache.net containers log each request with the cache it belongs to and whether nginx
answered it from disk::

    [steam] 192.0.2.10 / - - - [14/Nov/2026:18:00:01 +0100] "GET /depot/..." 200 1048576 "-"
        "Valve/Steam HTTP Client 1.0" "HIT" "lancache.steamcontent.com" "-"

(one line in the log)

``LANCACHE_LOG`` is the path of that log (mounted into Floorbit's container, read-only). Floorbit
reads what was added since the last time, every ``LANCACHE_INTERVAL`` seconds, and keeps per hour
and per cache only the bytes served from disk and from the internet. The client address on each
line is never kept: the numbers are hall-wide.
"""
import math
import os
import re
import threading
import time
from datetime import datetime

from integrations import config

from . import database, features, store

FILE = 'lancache.json'
FIRST_READ = 50 * 1024 * 1024    # a log Floorbit hasn't seen is read from at most this far back
CHUNK = 4 * 1024 * 1024
LINE_RE = re.compile(r'^\[(?P<cache>[^\]]{1,40})\]\s.*?\[(?P<time>\d\d/\w{3}/\d{4}:\d\d:\d\d:\d\d [+-]\d{4})\]\s+'
                     r'"[^"]*"\s+(?P<status>\d{3})\s+(?P<bytes>\d+|-)\s+"[^"]*"\s+"[^"]*"\s+"(?P<result>[^"]*)"')
# nginx's $upstream_cache_status: these were answered from disk.
HITS = {'HIT', 'STALE', 'UPDATING', 'REVALIDATED'}

_stats = None


def settings():
    return {'log': (config.get('LANCACHE_LOG') or '').strip(),
            'interval': config.get_int('LANCACHE_INTERVAL', 30, minimum=5),
            'retention_hours': config.get_int('LANCACHE_RETENTION_HOURS', 168, minimum=1)}


def parse(line):
    """(hour, cache, bytes, hit) for a line the cache served, else None."""
    m = LINE_RE.match(line)
    if not m or m['bytes'] == '-' or not m['status'].startswith('2'):
        return None
    try:
        ts = datetime.strptime(m['time'], '%d/%b/%Y:%H:%M:%S %z').timestamp()
    except ValueError:
        return None
    return int(ts // 3600 * 3600), m['cache'].strip().lower(), int(m['bytes']), m['result'].upper() in HITS


# What a local agent sends, kept in the shapes the LAN cache page adds up and draws. An agent of
# another version (or a broken one) must not leave a value there that breaks the page for everyone.
def _count(value):
    return value if isinstance(value, int) and not isinstance(value, bool) and 0 <= value < 2 ** 63 else 0


def _rows(raw, text, counts, limit):
    rows = []
    for r in (raw if isinstance(raw, list) else [])[:limit]:
        if isinstance(r, dict):
            rows.append({**{k: str(r.get(k) or '')[:120] for k in text}, **{k: _count(r.get(k)) for k in counts}})
    return rows


def _tally(raw, limit=200):
    return {str(k)[:120]: _count(v) for k, v in list(raw.items())[:limit]} if isinstance(raw, dict) else {}


def _number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and abs(v) < 2 ** 63


def _check(raw, keys):
    if not isinstance(raw, dict):
        return None
    out = {}
    for k, kind in keys.items():
        v = raw.get(k)
        if (kind is bool and isinstance(v, bool)) or (kind is int and _number(v)):
            out[k] = v
        elif kind is str and v is not None and not isinstance(v, (dict, list)):
            out[k] = str(v)[:300]
    return out


def clean_status(status):
    """The cache machine as an agent saw it, in the shape the page draws."""
    status = status if isinstance(status, dict) else {}
    out = {'at': status['at'] if _number(status.get('at')) else None}
    for key, keys in (('disk', {'used': int, 'total': int, 'free': int, 'error': str}),
                      ('heartbeat', {'ok': bool, 'ms': int, 'error': str, 'processed_by': str}),
                      ('dns_check', {'ok': bool, 'error': str}),
                      ('clearing', {'running': bool, 'started': int, 'finished': int, 'removed': int, 'errors': int})):
        if key in status:
            out[key] = _check(status.get(key), keys)
    return out


def _small(value):
    return value if isinstance(value, int) and not isinstance(value, bool) and 0 <= value < 10 ** 9 else None


class LancacheStats:
    def __init__(self, path=None):
        self.path = path
        self._lock = threading.Lock()
        self._thread = None
        self._stop = threading.Event()
        self.hours = {}       # {hour: {cache: [hit_bytes, miss_bytes, requests]}}
        self.position = {}    # {"inode": .., "offset": ..} in the log
        self.last_read = None
        self.last_error = None
        self.demo = False     # FLOORBIT_DEMO=1 with no log: made-up lines (demo_lines)
        self._loaded = False   # False while the database was away at start (docs/database.md)
        # What local agents sent (the LAN cache plugin, docs/lancache.md): {agent id: {...}}.
        self.remote = {}
        self._load()

    # ── storage ──────────────────────────────────────────────────────────────
    def _file(self):
        return self.path or store.event_path(FILE)

    def _load(self):
        """Read what was counted before. While the database is away this stays undone, and
        counting waits (``ready``): saving a count that started from nothing would overwrite the
        stored hours once it is back."""
        try:
            raw = store.read_json(self._file(), {}) or {}
        except database.DatabaseUnavailable:
            return
        except (OSError, ValueError):
            raw = {}
        self._loaded = True
        if not isinstance(raw, dict):
            return
        for key, caches in (raw.get('hours') or {}).items():
            try:
                self.hours[int(key)] = {str(c): [int(v[0]), int(v[1]), int(v[2])] for c, v in caches.items()}
            except (TypeError, ValueError, IndexError, AttributeError, KeyError, OverflowError):
                continue
        if isinstance(raw.get('position'), dict):
            self.position = raw['position']
        if isinstance(raw.get('remote'), dict):
            self.remote = {str(k): v for k, v in raw['remote'].items() if isinstance(v, dict)}

    def ready(self):
        if not self._loaded:
            self._load()
        return self._loaded

    def _save(self):
        if not self._loaded:
            return
        try:
            store.write_json(self._file(), {'version': 1, 'position': self.position, 'remote': self.remote,
                                            'hours': {str(k): v for k, v in self.hours.items()}})
        except (OSError, database.DatabaseError) as exc:
            print(f'[lancache] could not save {self._file()}: {exc}')

    # ── counting ─────────────────────────────────────────────────────────────
    def add_lines(self, lines, now=None):
        now = time.time() if now is None else now
        with self._lock:
            for line in lines:
                got = parse(line)
                if not got:
                    continue
                hour, cache, size, hit = got
                row = self.hours.setdefault(min(hour, int(now // 3600 * 3600)), {}).setdefault(cache, [0, 0, 0])
                row[0 if hit else 1] += size
                row[2] += 1
            keep = settings()['retention_hours'] * 3600
            for h in [h for h in self.hours if h < now - keep]:
                del self.hours[h]

    def merge_agent(self, agent, payload, now=None):
        """Counts a local agent read in the hall (``stats`` of the LAN cache plugin). Its hours are
        whole hours so far: they replace what it sent for them before."""
        now = time.time() if now is None else now
        name = str(agent.get('name') or agent.get('id'))
        hours = payload.get('hours')
        with self._lock:
            for key, caches in (hours.items() if isinstance(hours, dict) else ()):
                try:
                    hour = int(key)
                    rows = {str(c)[:40]: [int(v[0]), int(v[1]), int(v[2])] for c, v in caches.items()}
                except (TypeError, ValueError, IndexError, AttributeError, KeyError, OverflowError):
                    continue
                if hour > now + 3600:
                    continue
                self.hours.setdefault(hour, {}).update(rows)
            keep = settings()['retention_hours'] * 3600
            for h in [h for h in self.hours if h < now - keep]:
                del self.hours[h]
            mine = self.remote.setdefault(str(agent.get('id')), {})
            dns = payload.get('dns') if isinstance(payload.get('dns'), dict) else {}
            mine.update(name=name, updated=now, lines=_small(payload.get('lines')),
                        downloads=_rows(payload.get('downloads'), ('cache', 'item'),
                                        ('hit_bytes', 'miss_bytes', 'requests', 'clients'), 50),
                        other_downloads={k: _count(v) for k, v in _tally(payload.get('other_downloads')).items()
                                         if k in ('hit_bytes', 'miss_bytes', 'requests', 'items')},
                        suspects=_rows(payload.get('suspects'), ('cache', 'item'), ('files', 'misses'), 20),
                        min_clients=_small(payload.get('min_clients')),
                        window_hours=_small(payload.get('window_hours')),
                        dns_services=_tally(dns.get('services')))
            clients = mine.get('clients') if isinstance(mine.get('clients'), dict) else {}
            mine['clients'] = clients
            for key, n in _tally(payload.get('clients'), 100).items():
                if key.isascii() and key.isdigit():          # an hour: the page sorts them as numbers
                    clients[key] = n
            for key in sorted(clients)[:-48]:
                del clients[key]
            self.last_read = now
            self.last_error = None
        self._save()

    def merge_status(self, agent, status, now=None):
        """The cache machine as a local agent sees it: disk, heartbeat, DNS check, clearing."""
        now = time.time() if now is None else now
        with self._lock:
            mine = self.remote.setdefault(str(agent.get('id')), {})
            mine.update(name=str(agent.get('name') or agent.get('id')),
                        status={**clean_status(status), 'received': now})
        self._save()

    def read_log(self, now=None):
        """Read what the log gained since last time. Starts again at the top after a rotation."""
        path = settings()['log']
        if not path or not self.ready():   # where it stopped reading is in the database
            return
        try:
            st = os.stat(path)
            offset = self.position.get('offset', 0) if self.position.get('inode') == st.st_ino else None
            if offset is None or offset > st.st_size:
                offset = max(0, st.st_size - FIRST_READ) if offset is None and not self.hours else 0
            with open(path, 'rb') as f:
                f.seek(offset)
                if offset and not self.position:
                    f.readline()   # started in the middle of a line
                while True:
                    data = f.read(CHUNK)
                    if not data:
                        break
                    cut = data.rfind(b'\n') + 1
                    if not cut:
                        if len(data) < CHUNK:
                            f.seek(f.tell() - len(data))   # half a line at the end: read it next time
                            break
                        cut = len(data)
                    self.add_lines(data[:cut].decode('utf-8', 'replace').splitlines(), now)
                    f.seek(f.tell() - len(data) + cut)
                self.position = {'inode': st.st_ino, 'offset': f.tell()}
            self.last_error = None
        except OSError as exc:
            self.last_error = f'Can\'t read {path}: {exc.strerror or exc}'
        self.last_read = time.time() if now is None else now
        self._save()

    def start(self):
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, name='lancache-watch', daemon=True)
            self._thread.start()

    def stop(self):
        self._stop.set()

    def _run(self):
        while not self._stop.is_set():
            try:
                if features.on('games') and (settings()['log'] or self.demo):
                    if settings()['log']:
                        self.read_log()
                    else:
                        self.add_lines(demo_lines(time.time(), settings()['interval']))
                        self.last_read = time.time()
            except Exception as exc:  # noqa: BLE001  # keep the thread alive no matter what
                print(f'[lancache] read failed: {exc}')
            self._stop.wait(settings()['interval'])

    # ── reading ──────────────────────────────────────────────────────────────
    def start_demo(self, now=None):
        """FLOORBIT_DEMO=1 and no log: a made-up last day, then lines as the demo hall plays."""
        if settings()['log']:
            return
        now = time.time() if now is None else now
        self.demo = True
        for k in range(24 * 6, 0, -1):
            self.add_lines(demo_lines(now - k * 600, step=600), now)
        self.last_read = now

    def snapshot(self, hours=24, now=None):
        now = time.time() if now is None else now
        last = int(now // 3600 * 3600)
        start = last - (hours - 1) * 3600
        with self._lock:
            kept = {h: {c: list(v) for c, v in caches.items()} for h, caches in self.hours.items() if h >= start}
        series, caches = [], {}
        for h in range(start, last + 1, 3600):
            hit = miss = 0
            for cache, (hb, mb, n) in (kept.get(h) or {}).items():
                hit += hb
                miss += mb
                row = caches.setdefault(cache, {'cache': cache, 'hit_bytes': 0, 'miss_bytes': 0, 'requests': 0})
                row['hit_bytes'] += hb
                row['miss_bytes'] += mb
                row['requests'] += n
            series.append({'t': h, 'hit_bytes': hit, 'miss_bytes': miss})
        hit = sum(c['hit_bytes'] for c in caches.values())
        miss = sum(c['miss_bytes'] for c in caches.values())
        return {
            'configured': bool(settings()['log']) or self.demo or bool(self.hours) or bool(self.remote),
            'demo': self.demo, 'hours': series,
            'hit_bytes': hit, 'miss_bytes': miss,
            'hit_ratio': round(hit / (hit + miss), 4) if hit + miss else None,
            'caches': sorted(caches.values(), key=lambda c: -(c['hit_bytes'] + c['miss_bytes'])),
            'last_read': self.last_read, 'error': self.last_error,
        }


def demo_lines(now, step=60):
    """FLOORBIT_DEMO=1: log lines like the demo hall's cache would write in the last ``step`` seconds."""
    import math
    import random

    from .builtin_plugins.demo.plugin import _ip, _seats, _taken
    stamp = time.strftime('%d/%b/%Y:%H:%M:%S +0000', time.gmtime(now))
    # (cache, how often it's picked, how much of it is on disk already)
    caches = (('steam', 10, 0.8), ('blizzard', 3, 0.6), ('riot', 2, 0.7), ('epicgames', 2, 0.5), ('wsus', 2, 0.9))
    hour = time.gmtime(now).tm_hour + time.gmtime(now).tm_min / 60
    busy = 0.3 + 0.7 * math.sin((hour - 9) / 24 * 2 * math.pi) ** 2   # quiet at night, busy in the evening
    rnd = random.Random(int(now // step))
    out = []
    for _seat, _b, _n, i in _seats():
        if not _taken(i) or rnd.random() > busy / 3:
            continue
        cache, _w, on_disk = rnd.choices(caches, weights=[c[1] for c in caches])[0]
        size = rnd.randint(1, 8) * 8 * 1024 * 1024 * step // 60
        result = 'HIT' if rnd.random() < on_disk else 'MISS'
        out.append(f'[{cache}] {_ip(i)} / - - - [{stamp}] "GET /depot/1/chunk/{i} HTTP/1.1" 200 {size} "-" '
                   f'"Demo client" "{result}" "cache.example.com" "-"')
    return out


def init_lancache(app, start_background=True):
    global _stats
    stats = _stats = LancacheStats()
    app.extensions['floorbit_lancache'] = stats
    started = threading.Event()

    @app.before_request
    def start_lancache_once():
        if start_background and not started.is_set():
            started.set()
            stats.start()

    return stats


# The LAN cache page (blueprints/lancache.py) reads the agents' reports here, in the core, so it
# works whichever version of the plugin (bitsandbricks-ch/floorbit-plugin-lancache) is installed.
STALE_AFTER = 300     # seconds without word from the agent: the page says so


def overview(stats, health=None, hours=24, now=None):
    """Everything the LAN cache page shows. Hall-wide numbers only."""
    now = time.time() if now is None else now
    snap = stats.snapshot(hours=hours, now=now) if stats is not None else {'configured': False}
    agents = []
    downloads, suspects, services = {}, {}, {}
    other = {'hit_bytes': 0, 'miss_bytes': 0, 'requests': 0, 'items': 0}
    clients = {}
    for agent_id, r in sorted((stats.remote if stats is not None else {}).items()):
        status = r.get('status') or {}
        agents.append({'id': agent_id, 'name': r.get('name'), 'updated': r.get('updated'),
                       'stale': not r.get('updated') or now - r['updated'] > STALE_AFTER,
                       'disk': status.get('disk'), 'heartbeat': status.get('heartbeat'),
                       'dns_check': status.get('dns_check'), 'clearing': status.get('clearing'),
                       'health': ((health or {}).get(agent_id) or {}).get('health')})
        for d in r.get('downloads') or []:
            key = (d.get('cache'), d.get('item'))
            row = downloads.setdefault(key, {'cache': key[0], 'item': key[1], 'hit_bytes': 0, 'miss_bytes': 0,
                                             'requests': 0, 'clients': 0})
            for k in ('hit_bytes', 'miss_bytes', 'requests'):
                row[k] += d.get(k) or 0
            row['clients'] = max(row['clients'], d.get('clients') or 0)
        for k in other:
            other[k] += (r.get('other_downloads') or {}).get(k) or 0
        for s in r.get('suspects') or []:
            key = (s.get('cache'), s.get('item'))
            row = suspects.setdefault(key, {'cache': key[0], 'item': key[1], 'files': 0, 'misses': 0})
            row['files'] += s.get('files') or 0
            row['misses'] += s.get('misses') or 0
        for svc, n in (r.get('dns_services') or {}).items():
            services[svc] = services.get(svc, 0) + n
        for h, n in (r.get('clients') or {}).items():
            clients[h] = clients.get(h, 0) + n
    for d in downloads.values():
        total = d['hit_bytes'] + d['miss_bytes']
        d['hit_ratio'] = round(d['hit_bytes'] / total, 4) if total else None
    first = next(iter(stats.remote.values()), {}) if stats is not None and stats.remote else {}
    return {
        **snap,
        'agents': agents,
        'downloads': sorted(downloads.values(), key=lambda d: -(d['hit_bytes'] + d['miss_bytes']))[:50],
        'other_downloads': other,
        'suspects': sorted(suspects.values(), key=lambda s: -s['misses'])[:20],
        'dns_services': sorted(({'cache': k, 'lookups': v} for k, v in services.items()), key=lambda r: -r['lookups']),
        'clients': [{'t': int(h), 'clients': n} for h, n in sorted(clients.items(), key=lambda kv: int(kv[0]))],
        'min_clients': first.get('min_clients') or 5,
        'window_hours': first.get('window_hours') or 24,
        'saved_bytes': snap.get('hit_bytes', 0),
    }
