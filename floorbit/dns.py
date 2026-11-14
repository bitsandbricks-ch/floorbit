"""DNS analytics (issue #87): what the hall looks up, hall-wide only. See docs/dns.md.

Plugins with ``uses: [dns]`` read the event's resolver (AdGuard Home, Pi-hole, ...) and define
``dns_queries(since)``, the lookups after that unix time::

    [{"ts": 1794652800.5, "domain": "cdn.steamcontent.example", "client": "198.51.100.10", "blocked": false}]

Privacy, the same rule as NetFlow (docs/flows.md):

- Names are cut to the site (``cdn.steamcontent.example`` → ``steamcontent.example``), and local names
  (single labels, ``.lan``, ``.local``, reverse lookups) are dropped: they name people's machines.
- A site is only named once ``DNS_MIN_SEATS`` (5) different clients looked it up within an hour.
  Below that, its lookups count in the totals without a name.
- Clients are never kept: while an hour is open they are counted as keyed hashes (a key that only
  lives in memory), and when it closes only the count stays. Nothing is per seat or per person.
- Closed hours are kept ``DNS_RETENTION_HOURS`` (168, a week) in ``dns.json`` next to data.json.
"""
import hashlib
import hmac
import os
import re
import threading
import time

from integrations import config

from . import features, store
from .plugins import PluginError

FILE = 'dns.json'
MAX_PER_POLL = 50000
NEW_WINDOW = 6 * 3600          # a site first seen this recently is "new" ...
NEW_HISTORY = 24 * 3600        # ... when there are this many hours of history before it
LOCAL_SUFFIXES = ('lan', 'local', 'localdomain', 'home', 'home.arpa', 'internal', 'intranet', 'corp', 'arpa',
                  'invalid', 'localhost', 'test')
# Second-level suffixes where the site is three labels (example.co.uk).
MULTI_SUFFIXES = {'co.uk', 'org.uk', 'ac.uk', 'gov.uk', 'com.au', 'net.au', 'co.nz', 'co.jp', 'co.za', 'com.br',
                  'com.cn', 'com.tr', 'co.kr', 'com.mx', 'co.in'}
# Site -> category. Hall-wide, so a coarse list is enough; anything else is "other".
CATEGORIES = {
    'gaming': ('steampowered.com', 'steamcontent.com', 'steamstatic.com', 'steamserver.net', 'steamcommunity.com',
               'epicgames.com', 'epicgames.dev', 'unrealengine.com', 'riotgames.com', 'leagueoflegends.com',
               'battle.net', 'blizzard.com', 'ea.com', 'origin.com', 'ubi.com', 'ubisoft.com', 'xboxlive.com',
               'playstation.net', 'playstation.com', 'nintendo.net', 'gog.com', 'faceit.com', 'minecraft.net',
               'mojang.com', 'roblox.com', 'valvesoftware.com', 'rockstargames.com', 'curseforge.com'),
    'streaming': ('twitch.tv', 'ttvnw.net', 'jtvnw.net', 'youtube.com', 'googlevideo.com', 'ytimg.com',
                  'netflix.com', 'nflxvideo.net', 'spotify.com', 'scdn.co', 'kick.com', 'disneyplus.com',
                  'primevideo.com', 'soundcloud.com'),
    'social': ('discord.com', 'discord.gg', 'discordapp.com', 'discordapp.net', 'facebook.com', 'fbcdn.net',
               'instagram.com', 'tiktok.com', 'tiktokcdn.com', 'twitter.com', 'x.com', 'twimg.com',
               'whatsapp.net', 'whatsapp.com', 'reddit.com', 'redd.it', 'snapchat.com', 'telegram.org',
               'teamspeak.com', 'signal.org'),
    'updates': ('windowsupdate.com', 'nvidia.com', 'amd.com'),
}
CATEGORY_IDS = (*CATEGORIES, 'other')
LABEL_RE = re.compile(r'^[a-z0-9_]([a-z0-9_-]{0,61}[a-z0-9_])?$')

_stats = None


def settings():
    return {'min_clients': config.get_int('DNS_MIN_SEATS', 5, minimum=2),
            'retention_hours': config.get_int('DNS_RETENTION_HOURS', 168, minimum=1),
            'interval': config.get_int('DNS_INTERVAL', 60, minimum=15)}


def site(name):
    """The site a lookup is for, or None for local names and anything that isn't a hostname."""
    name = str(name or '').strip().lower().rstrip('.')
    labels = name.split('.')
    if len(labels) < 2 or len(name) > 253 or not all(LABEL_RE.match(label) for label in labels):
        return None
    if labels[-1].isdigit():
        return None   # an address, not a name
    if any(name == s or name.endswith('.' + s) for s in LOCAL_SUFFIXES):
        return None
    keep = 3 if '.'.join(labels[-2:]) in MULTI_SUFFIXES and len(labels) >= 3 else 2
    return '.'.join(labels[-keep:])


def category(site_name):
    for cat, sites in CATEGORIES.items():
        if site_name in sites:
            return cat
    return 'other'


def _hour(ts):
    return int(ts // 3600 * 3600)


class DnsStats:
    def __init__(self, registry=None, path=None):
        self.registry = registry
        self.path = path
        self._lock = threading.Lock()
        self._key = os.urandom(32)   # never stored: once the process ends, no hash can be matched again
        self._thread = None
        self._stop = threading.Event()
        self.cursors = {}
        self.last_poll = None
        self.last_error = None
        # Closed hours: {hour: {"lookups", "blocked", "sites": {site: [lookups, blocked, clients]}}}.
        self.hours = {}
        self.current = None          # the open hour, with hashed clients
        self._load()

    # ── storage ──────────────────────────────────────────────────────────────
    def _file(self):
        return self.path or os.path.join(os.path.dirname(os.path.abspath(store.DATA_FILE)), FILE)

    def _load(self):
        try:
            raw = store.read_json(self._file(), {}) or {}
        except (OSError, ValueError):
            raw = {}
        hours = raw.get('hours') if isinstance(raw, dict) else None
        for key, h in (hours or {}).items():
            try:
                self.hours[int(key)] = {'lookups': int(h['lookups']), 'blocked': int(h['blocked']),
                                        'sites': {str(s): [int(v[0]), int(v[1]), int(v[2])]
                                                  for s, v in (h.get('sites') or {}).items()}}
            except (KeyError, TypeError, ValueError, IndexError):
                continue

    def _save(self):
        try:
            store.write_json(self._file(), {'version': 1, 'hours': {str(k): v for k, v in self.hours.items()}})
        except OSError as exc:
            print(f'[dns] could not save {self._file()}: {exc}')

    # ── counting ─────────────────────────────────────────────────────────────
    def _open(self, hour):
        self.current = {'hour': hour, 'lookups': 0, 'blocked': 0, 'sites': {}}

    def _close(self):
        """Keep only counts, and only the sites enough clients looked up."""
        cur, self.current = self.current, None
        if not cur:
            return
        floor = settings()['min_clients']
        self.hours[cur['hour']] = {
            'lookups': cur['lookups'], 'blocked': cur['blocked'],
            'sites': {s: [v['lookups'], v['blocked'], len(v['clients'])]
                      for s, v in cur['sites'].items() if len(v['clients']) >= floor},
        }
        keep = settings()['retention_hours'] * 3600
        for h in [h for h in self.hours if h < cur['hour'] - keep]:
            del self.hours[h]
        self._save()

    def _client(self, client):
        return hmac.new(self._key, str(client).encode(), hashlib.sha256).digest()[:12]

    def add(self, entries, now=None):
        """Count lookups. Entries are plugin answers; nothing about a client is kept but a hash."""
        now = time.time() if now is None else now
        with self._lock:
            for e in entries:
                if not isinstance(e, dict):
                    continue
                try:
                    ts = float(e.get('ts') or now)
                except (TypeError, ValueError):
                    continue
                hour = _hour(min(ts, now))
                if self.current is None or hour > self.current['hour']:
                    self._close()
                    self._open(hour)
                blocked = bool(e.get('blocked'))
                if hour < self.current['hour']:
                    # Late, for an hour that closed: it counts, but its clients can't be added any more.
                    closed = self.hours.get(hour)
                    if closed is not None:
                        closed['lookups'] += 1
                        closed['blocked'] += blocked
                    continue
                cur = self.current
                cur['lookups'] += 1
                cur['blocked'] += blocked
                name = site(e.get('domain'))
                if not name or not e.get('client'):
                    continue
                entry = cur['sites'].setdefault(name, {'lookups': 0, 'blocked': 0, 'clients': set()})
                entry['lookups'] += 1
                entry['blocked'] += blocked
                entry['clients'].add(self._client(e['client']))
            # An hour with no lookups still closes when it's over.
            if self.current is not None and _hour(now) > self.current['hour']:
                self._close()

    # ── polling ──────────────────────────────────────────────────────────────
    def poll_once(self, now=None):
        now = time.time() if now is None else now
        errors = []
        for spec in self.registry.feeders('dns') if self.registry else []:
            since = self.cursors.get(spec.id, now - 2 * settings()['interval'])
            try:
                raw = self.registry.call(spec, 'dns_queries', since)
            except PluginError as exc:
                errors.append(f'{spec.name}: {exc}')
                continue
            if not isinstance(raw, list):
                errors.append(f"{spec.name} returned lookups Floorbit can't read (not a list)")
                continue
            fresh = []
            for e in raw[:MAX_PER_POLL]:
                try:
                    if isinstance(e, dict) and float(e.get('ts') or 0) > since:
                        fresh.append(e)
                except (TypeError, ValueError):
                    continue
            if fresh:
                self.cursors[spec.id] = max(float(e['ts']) for e in fresh)
            self.add(fresh, now)
        self.add([], now)   # closes the hour even when no plugin answered
        self.last_poll = now
        self.last_error = '; '.join(errors) or None

    def start(self):
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, name='dns-watch', daemon=True)
            self._thread.start()

    def stop(self):
        self._stop.set()

    def _run(self):
        while not self._stop.is_set():
            if features.on('dns') and dns_plugins(self.registry):
                try:
                    self.poll_once()
                except Exception as exc:  # noqa: BLE001  # keep the thread alive no matter what
                    print(f'[dns] poll failed: {exc}')
            self._stop.wait(settings()['interval'])

    # ── reading ──────────────────────────────────────────────────────────────
    def snapshot(self, hours=24, now=None):
        now = time.time() if now is None else now
        floor = settings()['min_clients']
        start = _hour(now) - (hours - 1) * 3600
        with self._lock:
            closed = dict(self.hours)
            cur = self.current
            if cur:
                closed[cur['hour']] = {
                    'lookups': cur['lookups'], 'blocked': cur['blocked'],
                    'sites': {s: [v['lookups'], v['blocked'], len(v['clients'])] for s, v in cur['sites'].items()},
                }
        series, sites, first_seen = [], {}, {}
        lookups = blocked = named = 0
        for h in sorted(closed):
            v = closed[h]
            shown = {s: c for s, c in v['sites'].items() if c[2] >= floor}
            for s in shown:
                first_seen.setdefault(s, h)
            if h < start:
                continue
            series.append({'t': h, 'lookups': v['lookups'], 'blocked': v['blocked']})
            lookups += v['lookups']
            blocked += v['blocked']
            for s, (n, b, c) in shown.items():
                row = sites.setdefault(s, {'site': s, 'category': category(s), 'lookups': 0, 'blocked': 0,
                                           'clients_max': 0})
                row['lookups'] += n
                row['blocked'] += b
                row['clients_max'] = max(row['clients_max'], c)
                named += n
        by_hour = {p['t']: p for p in series}
        series = [by_hour.get(h, {'t': h, 'lookups': 0, 'blocked': 0}) for h in range(start, _hour(now) + 1, 3600)]
        cats = dict.fromkeys(CATEGORY_IDS, 0)
        for row in sites.values():
            cats[row['category']] += row['lookups']
        history_start = min(closed) if closed else now
        new = [{**sites[s], 'first_seen': h} for s, h in first_seen.items()
               if s in sites and h >= _hour(now) - NEW_WINDOW and h - history_start >= NEW_HISTORY]
        ranked = sorted(sites.values(), key=lambda r: (-r['lookups'], r['site']))
        return {
            'hours': series, 'lookups': lookups, 'blocked': blocked,
            'block_share': round(blocked / lookups, 4) if lookups else None,
            'sites': ranked[:50],
            'categories': [{'id': c, 'lookups': cats[c]} for c in CATEGORY_IDS],
            'unnamed_lookups': max(0, lookups - named),
            'new': sorted(new, key=lambda r: -r['first_seen'])[:20],
            'blocked_sites': sorted((r for r in sites.values() if r['blocked']), key=lambda r: -r['blocked'])[:10],
            'min_clients': floor, 'plugins': len(dns_plugins(self.registry)),
            'last_poll': self.last_poll, 'error': self.last_error,
        }


def dns_plugins(registry):
    return registry.feeders('dns') if registry else []


def init_dns(app, registry, start_background=True):
    global _stats
    stats = _stats = DnsStats(registry)
    app.extensions['floorbit_dns'] = stats
    started = threading.Event()

    @app.before_request
    def start_dns_once():
        # Started on the first request, like the status monitor: the debug reloader imports twice.
        if start_background and not started.is_set():
            started.set()
            stats.start()

    return stats
