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
import os
import re
import threading
import time
from datetime import datetime

from integrations import config

from . import features, store

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
        self._load()

    # ── storage ──────────────────────────────────────────────────────────────
    def _file(self):
        return self.path or os.path.join(os.path.dirname(os.path.abspath(store.DATA_FILE)), FILE)

    def _load(self):
        try:
            raw = store.read_json(self._file(), {}) or {}
        except (OSError, ValueError):
            raw = {}
        if not isinstance(raw, dict):
            return
        for key, caches in (raw.get('hours') or {}).items():
            try:
                self.hours[int(key)] = {str(c): [int(v[0]), int(v[1]), int(v[2])] for c, v in caches.items()}
            except (TypeError, ValueError, IndexError, AttributeError):
                continue
        if isinstance(raw.get('position'), dict):
            self.position = raw['position']

    def _save(self):
        try:
            store.write_json(self._file(), {'version': 1, 'position': self.position,
                                            'hours': {str(k): v for k, v in self.hours.items()}})
        except OSError as exc:
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

    def read_log(self, now=None):
        """Read what the log gained since last time. Starts again at the top after a rotation."""
        path = settings()['log']
        if not path:
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
            if features.on('games') and (settings()['log'] or self.demo):
                try:
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
            'configured': bool(settings()['log']) or self.demo or bool(self.hours), 'demo': self.demo, 'hours': series,
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
