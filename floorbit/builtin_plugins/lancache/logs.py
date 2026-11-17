"""Reading the LAN cache's logs, in the hall, and counting them hall-wide (docs/lancache.md).

Two logs:

* the cache's **access log** (lancache.net's monolithic container), one line per request::

      [steam] 192.0.2.10 / - - - [14/Nov/2026:18:00:01 +0100] "GET /depot/228988/chunk/ab12.. HTTP/1.1"
          200 1048576 "-" "Valve/Steam HTTP Client 1.0" "HIT" "lancache.steamcontent.com" "-"

* **lancache-dns**'s query log (bind), one line per lookup::

      17-Nov-2026 18:00:01.123 queries: info: client @0x7f3b 192.0.2.10#53211 (cdn.example.com):
          query: cdn.example.com IN A + (198.51.100.2)

Client addresses are needed for one thing: counting how many different clients did something
in an hour. They are kept as keyed hashes (the key lives in memory only) while the hour is open
and only the count leaves this file. A download or a DNS site is only named once ``min_clients``
(5) different clients fetched or looked it up; below that it is counted without a name.

Reimplements ideas from regix1/lancache-manager (AGPL-3.0) without its code.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import threading
import time
from datetime import datetime

from floorbit import dns as dns_rules
from floorbit.lancache import HITS, LINE_RE

REQUEST_RE = re.compile(r'"(?:GET|HEAD) (?P<path>/\S*) HTTP/[\d.]+"')
CLIENT_RE = re.compile(r'^\[[^\]]{1,40}\]\s+(?P<client>[0-9A-Fa-f:.]{2,45})\s')
QUERY_RE = re.compile(r'^(?P<time>\d\d-\w{3}-\d{4} \d\d:\d\d:\d\d)(?:\.\d+)?\s.*?client (?:@\S+ )?'
                      r'(?P<client>[0-9A-Fa-f:.]{2,45})#\d+\s.*?query: (?P<name>\S+) IN (?P<type>\S+)')
HEX_RE = re.compile(r'^[0-9a-f]{16,}$', re.I)
KEEP_HOURS = 48
TOP_DOWNLOADS = 50
SUSPECT_MISSES = 3        # the same file missed this often in an hour: the cache isn't keeping it
# Sites the cache answers for (uklans/cache-domains, the parts every list has), per cache.
CACHED_SITES = {
    'steam': ('steamcontent.com', 'steampowered.com', 'steamserver.net'),
    'epicgames': ('epicgames.com', 'unrealengine.com'),
    'blizzard': ('blizzard.com', 'battle.net', 'blzddist1-a.akamaihd.net'),
    'riot': ('riotcdn.net', 'riotgames.com'),
    'origin': ('origin.com', 'ea.com'),
    'uplay': ('ubi.com', 'ubisoft.com'),
    'wsus': ('windowsupdate.com', 'delivery.mp.microsoft.com'),
    'xboxlive': ('xboxlive.com',),
    'sony': ('playstation.net',),
    'nintendo': ('nintendo.net',),
}


def item_of(cache, path):
    """What a request belongs to, as a short name without anything about the client: the Steam
    depot, or the first parts of the path that aren't hashes."""
    path = (path or '').split('?', 1)[0]
    parts = [p for p in path.strip('/').split('/') if p]
    if cache == 'steam' and len(parts) >= 2 and parts[0] == 'depot' and parts[1].isdigit():
        return f'depot {parts[1]}'
    keep = []
    for p in parts[:3]:
        if HEX_RE.match(p) or len(p) > 40 or '.' in p:
            break
        keep.append(p.lower())
    return '/'.join(keep[:2]) or '(root)'


def parse_access(line):
    """(hour, cache, bytes, hit, client, path) for a line the cache served, else None."""
    m = LINE_RE.match(line)
    if not m or m['bytes'] == '-' or not m['status'].startswith('2'):
        return None
    try:
        ts = datetime.strptime(m['time'], '%d/%b/%Y:%H:%M:%S %z').timestamp()
    except ValueError:
        return None
    c = CLIENT_RE.match(line)
    r = REQUEST_RE.search(line)
    return (int(ts // 3600 * 3600), m['cache'].strip().lower(), int(m['bytes']), m['result'].upper() in HITS,
            c['client'] if c else '', r['path'] if r else '')


def parse_query(line, tz_offset=None):
    """(hour, client, name) for a bind query log line, else None. Its times are local time."""
    m = QUERY_RE.match(line)
    if not m:
        return None
    try:
        ts = time.mktime(time.strptime(m['time'], '%d-%b-%Y %H:%M:%S'))
    except (ValueError, OverflowError):
        return None
    return int(ts // 3600 * 3600), m['client'], m['name'].rstrip('.').lower()


def service_of(site_name):
    for cache, sites in CACHED_SITES.items():
        if site_name in sites:
            return cache
    return None


class Counter:
    """Everything counted from both logs, by hour. Thread-safe; ``payload()`` is what goes out."""

    def __init__(self, min_clients=5, key=None):
        self.min_clients = max(2, int(min_clients or 5))
        self._key = key or os.urandom(32)
        self._lock = threading.Lock()
        self.cache = {}       # hour -> {cache: [hit, miss, requests]}
        self.clients = {}     # hour -> {hash}
        self.items = {}       # hour -> {(cache, item): [hit, miss, requests, {hash}]}
        self.misses = {}      # hour -> {(cache, item, path hash): misses}
        self.dns = {}         # hour -> {"lookups": n, "sites": {site: [lookups, {hash}]}}
        self.touched = set()  # hours changed since the last payload
        self.lines = 0

    def _h(self, text):
        return hmac.new(self._key, str(text).encode(), hashlib.sha256).digest()[:10]

    def add_access(self, lines, now=None):
        now = time.time() if now is None else now
        added = 0
        with self._lock:
            for line in lines:
                got = parse_access(line)
                if not got:
                    continue
                hour, cache, size, hit, client, path = got
                hour = min(hour, int(now // 3600 * 3600))
                row = self.cache.setdefault(hour, {}).setdefault(cache, [0, 0, 0])
                row[0 if hit else 1] += size
                row[2] += 1
                item = item_of(cache, path)
                irow = self.items.setdefault(hour, {}).setdefault((cache, item), [0, 0, 0, set()])
                irow[0 if hit else 1] += size
                irow[2] += 1
                if client:
                    who = self._h(client)
                    self.clients.setdefault(hour, set()).add(who)
                    irow[3].add(who)
                if not hit and path:
                    key = (cache, item, self._h(path.split('?', 1)[0]))
                    misses = self.misses.setdefault(hour, {})
                    misses[key] = misses.get(key, 0) + 1
                self.touched.add(hour)
                added += 1
            self.lines += added
            self._forget(now)
        return added

    def add_queries(self, lines, now=None):
        now = time.time() if now is None else now
        added = 0
        with self._lock:
            for line in lines:
                got = parse_query(line)
                if not got:
                    continue
                hour, client, name = got
                hour = min(hour, int(now // 3600 * 3600))
                h = self.dns.setdefault(hour, {'lookups': 0, 'sites': {}})
                h['lookups'] += 1
                site_name = dns_rules.site(name)
                if site_name:
                    row = h['sites'].setdefault(site_name, [0, set()])
                    row[0] += 1
                    row[1].add(self._h(client))
                self.touched.add(hour)
                added += 1
            self._forget(now)
        return added

    def _forget(self, now):
        oldest = int(now // 3600 * 3600) - KEEP_HOURS * 3600
        for table in (self.cache, self.clients, self.items, self.misses, self.dns):
            for h in [h for h in table if h < oldest]:
                del table[h]

    def payload(self, hours=24, now=None, everything=False):
        """Hall-wide numbers only: the hours that changed (whole, so the hosted side replaces
        them), the downloads of the last ``hours`` that enough clients fetched, DNS sites the same."""
        now = time.time() if now is None else now
        floor = self.min_clients
        start = int(now // 3600 * 3600) - (hours - 1) * 3600
        with self._lock:
            send = set(self.cache) | set(self.dns) if everything else set(self.touched)
            self.touched = set()
            out_hours = {str(h): {c: list(v) for c, v in self.cache.get(h, {}).items()} for h in sorted(send)
                         if h in self.cache}
            clients = {str(h): len(self.clients.get(h, ())) for h in sorted(send) if h in self.cache}
            dns_hours = {}
            services = {}
            for h in sorted(send):
                d = self.dns.get(h)
                if not d:
                    continue
                dns_hours[str(h)] = {'lookups': d['lookups'], 'blocked': 0,
                                     'sites': {s: [v[0], 0, len(v[1])] for s, v in d['sites'].items()
                                               if len(v[1]) >= floor}}
            for h, d in self.dns.items():
                if h < start:
                    continue
                for s, v in d['sites'].items():
                    svc = service_of(s)
                    if svc:
                        services[svc] = services.get(svc, 0) + v[0]
            merged = {}
            for h, rows in self.items.items():
                if h < start:
                    continue
                for key, (hit, miss, n, who) in rows.items():
                    m = merged.setdefault(key, [0, 0, 0, set()])
                    m[0] += hit
                    m[1] += miss
                    m[2] += n
                    m[3] |= who
            suspects = {}
            for h, rows in self.misses.items():
                if h < start:
                    continue
                for (cache, item, _path), n in rows.items():
                    if n >= SUSPECT_MISSES:
                        s = suspects.setdefault((cache, item), [0, 0])
                        s[0] += 1
                        s[1] += n
        named, other = [], {'hit_bytes': 0, 'miss_bytes': 0, 'requests': 0, 'items': 0}
        for (cache, item), (hit, miss, n, who) in merged.items():
            if len(who) >= floor:
                named.append({'cache': cache, 'item': item, 'hit_bytes': hit, 'miss_bytes': miss, 'requests': n,
                              'clients': len(who)})
            else:
                other['hit_bytes'] += hit
                other['miss_bytes'] += miss
                other['requests'] += n
                other['items'] += 1
        named.sort(key=lambda r: -(r['hit_bytes'] + r['miss_bytes']))
        suspect_rows = sorted(({'cache': c, 'item': i, 'files': f, 'misses': n} for (c, i), (f, n) in suspects.items()),
                              key=lambda r: -r['misses'])
        return {
            'hours': out_hours, 'clients': clients, 'window_hours': hours, 'min_clients': floor,
            'downloads': named[:TOP_DOWNLOADS], 'other_downloads': other,
            # A file only shows as suspect, not by name: the cache and the item (a Steam depot).
            'suspects': suspect_rows[:20],
            'dns': {'hours': dns_hours, 'services': services},
            'lines': self.lines,
        }


class Tail:
    """Reads what a log gained since last time; starts again after a rotation. The position is
    kept by the caller (``state``), so a restart doesn't count lines twice."""

    FIRST_READ = 20 * 1024 * 1024
    CHUNK = 4 * 1024 * 1024

    def __init__(self, path, state=None):
        self.path = path
        self.state = dict(state or {})
        self.error = None

    def read(self, limit=64 * 1024 * 1024):
        """New complete lines, at most ``limit`` bytes of them."""
        out = []
        try:
            st = os.stat(self.path)
            offset = self.state.get('offset') if self.state.get('inode') == st.st_ino else None
            fresh = offset is None
            if offset is None or offset > st.st_size:
                offset = max(0, st.st_size - self.FIRST_READ) if fresh else 0
            with open(self.path, 'rb') as f:
                f.seek(offset)
                if offset and fresh:
                    f.readline()          # started in the middle of a line
                read = 0
                while read < limit:
                    data = f.read(self.CHUNK)
                    if not data:
                        break
                    cut = data.rfind(b'\n') + 1
                    if not cut:
                        f.seek(f.tell() - len(data))
                        break
                    out.extend(data[:cut].decode('utf-8', 'replace').splitlines())
                    f.seek(f.tell() - len(data) + cut)
                    read += cut
                self.state = {'inode': st.st_ino, 'offset': f.tell()}
            self.error = None
        except OSError as exc:
            self.error = f"can't read {self.path}: {exc.strerror or exc}"
        return out
