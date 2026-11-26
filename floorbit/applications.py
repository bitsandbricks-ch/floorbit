"""Applications (issue #1481): the games, launchers and site groups Floorbit recognises in DNS,
NetFlow and the LAN cache. See docs/applications.md.

- **Built in:** ``applications_lists.json`` (launchers and games from uklans/cache-domains, site
  groups from v2fly/domain-list-community, both MIT, written by ``scripts/applications_import.py``)
  plus ``STARTER`` below: launcher ports and game titles no open list has.
- **Rule sources** (floorbit/application_sources.py, #1503): files fetched on a schedule, on top of
  the built-in ones; the higher a source in its list, the more it wins.
- **The event's own** live in data.json (``applications``): new applications, and for a built-in one
  the domains, ports, addresses and depots added to it, or that it is hidden.
- **Matching:** DNS by site (``dns.site``), traffic by the name of the flow service (the agent's
  classifier gets every application with ports or addresses as a rule), the LAN cache by cache id
  and Steam depot, and game servers by their game.

Every count stays hall-wide: names only show where DNS and traffic already name them (5+ seats).
"""
import ipaddress
import json
import pathlib
import re
import threading

from . import dns
from .store import load_data, save_data

KEY = 'applications'
KINDS = ('game', 'launcher', 'sitegroup')
CATEGORIES = ('gaming', 'streaming', 'social', 'downloads', 'updates', 'web', 'other')
MAX_OWN = 300
MAX_ITEMS = 200
ID_RE = re.compile(r'^[a-z0-9][a-z0-9-]{0,39}\Z')
PORT_RE = re.compile(r'^(tcp|udp)/(\d{1,5})(?:-(\d{1,5}))?\Z')
LISTS = pathlib.Path(__file__).with_name('applications_lists.json')
_lock = threading.Lock()

# What no open list has: the ports the vendors publish (the same as the traffic's built-in rules,
# floorbit/flows/classify.py) and game titles. Merged into the lists by id.
STARTER = (
    {'id': 'steam', 'sites': ['steampowered.com', 'steamstatic.com', 'steamserver.net', 'steamcommunity.com',
                              'valvesoftware.com'],
     'ports': ['udp/27015-27030', 'udp/27036', 'tcp/27036']},
    {'id': 'blizzard', 'ports': ['tcp/1119', 'udp/1119']},
    {'id': 'riot', 'sites': ['leagueoflegends.com'], 'ports': ['udp/5000-5500']},
    {'id': 'origin', 'sites': ['origin.com']},
    {'id': 'uplay', 'sites': ['ubisoft.com']},
    {'id': 'epicgames', 'sites': ['epicgames.dev']},
    {'id': 'minecraft', 'name': 'Minecraft', 'kind': 'game', 'category': 'gaming',
     'sites': ['minecraft.net', 'mojang.com'], 'ports': ['tcp/25565']},
    {'id': 'cs2', 'name': 'Counter-Strike 2', 'kind': 'game', 'category': 'gaming', 'part_of': 'steam',
     'sites': ['counter-strike.net']},
    {'id': 'dota2', 'name': 'Dota 2', 'kind': 'game', 'category': 'gaming', 'part_of': 'steam',
     'sites': ['dota2.com']},
    {'id': 'valorant', 'name': 'Valorant', 'kind': 'game', 'category': 'gaming', 'part_of': 'riot',
     'sites': ['playvalorant.com']},
    {'id': 'fortnite', 'name': 'Fortnite', 'kind': 'game', 'category': 'gaming', 'part_of': 'epicgames',
     'sites': ['fortnite.com']},
    {'id': 'rocketleague', 'name': 'Rocket League', 'kind': 'game', 'category': 'gaming', 'part_of': 'epicgames',
     'sites': ['rocketleague.com']},
)
# The flow services that are a launcher under another name (classify.BUILTIN's names).
SERVICE_NAMES = {'blizzard': 'Battle.net'}


class ApplicationError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        # The text is ours (a validation message), never a stack trace.
        self.message = message
        self.status = status


_builtin_cache = None


def builtin():
    """{id: application} shipped with Floorbit, lists and starter merged."""
    global _builtin_cache
    if _builtin_cache is None:
        doc = json.loads(LISTS.read_text())
        apps = {a['id']: {**_blank(), **a} for a in doc['applications']}
        for extra in STARTER:
            app = apps.setdefault(extra['id'], {**_blank(), 'id': extra['id'], 'source': 'floorbit'})
            for k, v in extra.items():
                if isinstance(v, list):
                    app[k] = sorted(set(app.get(k) or []) | set(v))
                elif k != 'id':
                    app[k] = v
        _builtin_cache = {'apps': apps, 'sources': doc['sources']}
    return _builtin_cache


def base(data=None):
    """{id: application} before the event's own changes: what Floorbit ships, with the rule
    sources on top (a source's entry replaces one with the same id, keeping its LAN cache ids)."""
    from . import application_sources
    apps = dict(builtin()['apps'])
    for source, entries in application_sources.overlay(data):
        for entry in entries:
            old = apps.get(entry['id']) or {}
            apps[entry['id']] = {**_blank(), **old, **entry, 'source': f'source:{source["id"]}',
                                 'source_name': source['name']}
    return apps


def _blank():
    return {'name': '', 'kind': 'sitegroup', 'category': 'other', 'part_of': None, 'sites': [], 'ports': [],
            'cidr': [], 'caches': [], 'depots': [], 'source': 'own'}


def _own(data=None):
    data = load_data() if data is None else data
    return {e['id']: e for e in data.get(KEY) or [] if isinstance(e, dict) and e.get('id')}


def listing(data=None):
    """Every application, built-in and own, with the event's changes applied. Hidden ones too."""
    data = load_data() if data is None else data
    shipped = base(data)
    own = _own(data)
    out = []
    for aid, app in shipped.items():
        change = own.get(aid) or {}
        merged = {**app, 'builtin': True, 'hidden': bool(change.get('hidden')), 'edited': bool(change),
                  'added': {k: change.get(k) or [] for k in ('sites', 'ports', 'cidr', 'depots')}}
        for k in ('sites', 'ports', 'cidr', 'depots'):
            merged[k] = sorted(set(app.get(k) or []) | set(change.get(k) or []), key=str)
        out.append(merged)
    for aid, entry in own.items():
        if aid in shipped:
            continue
        out.append({**_blank(), **entry, 'builtin': False, 'hidden': bool(entry.get('hidden')), 'edited': False,
                    'added': {k: entry.get(k) or [] for k in ('sites', 'ports', 'cidr', 'depots')}})
    out.sort(key=lambda a: (KINDS.index(a['kind']) if a['kind'] in KINDS else 9, a['name'].lower()))
    return out


def active(data=None):
    return [a for a in listing(data) if not a['hidden']]


# ── checking what is saved ──────────────────────────────────────────────────

def _strings(body, key, limit=MAX_ITEMS):
    raw = body.get(key)
    if raw is None:
        return []
    if not isinstance(raw, list) or len(raw) > limit:
        raise ApplicationError(f'{key} is a list of up to {limit} entries.')
    return [' '.join(str(v).split()).lower() for v in raw if str(v).strip()]


def _sites(body):
    out = []
    for name in _strings(body, 'sites'):
        got = dns.site(name.lstrip('*.'))
        if not got:
            raise ApplicationError(f'"{name}" is not a domain Floorbit can count.')
        out.append(got)
    return sorted(set(out))


def _ports(body):
    out = []
    for spec in _strings(body, 'ports'):
        m = PORT_RE.match(spec)
        lo, hi = (int(m[2]), int(m[3] or m[2])) if m else (0, 0)
        if not m or not 1 <= lo <= hi <= 65535:
            raise ApplicationError(f'Port "{spec}" should look like udp/27015 or tcp/6881-6889.')
        out.append(spec)
    return sorted(set(out))


def _cidr(body):
    out = []
    for spec in _strings(body, 'cidr'):
        try:
            out.append(str(ipaddress.ip_network(spec, strict=False)))
        except ValueError as exc:
            raise ApplicationError(f'"{spec}" is not an address or network.') from exc
    return sorted(set(out))


def _depots(body):
    out = []
    for spec in _strings(body, 'depots'):
        if not spec.isdigit() or len(spec) > 10:
            raise ApplicationError(f'"{spec}" is not a Steam depot id (a number).')
        out.append(spec)
    return sorted(set(out), key=int)


def _matches(body):
    return {'sites': _sites(body), 'ports': _ports(body), 'cidr': _cidr(body), 'depots': _depots(body)}


def save(body, app_id=None, new_id=None):
    """Adds an application (no id) or changes one. For a built-in one only what is added to it and
    whether it is hidden are kept: its own matches stay. ``new_id`` keeps an imported one's id when
    it is free."""
    if not isinstance(body, dict):
        raise ApplicationError('Send the application as a JSON object.')
    with _lock:
        data = load_data()
        shipped = base(data)
        own = _own(data)
        if app_id is not None and app_id not in shipped and app_id not in own:
            raise ApplicationError('No such application.', 404)
        hidden = body['hidden'] if 'hidden' in body else (own.get(app_id) or {}).get('hidden', False)
        entry = {'id': app_id, **_matches(body), 'hidden': bool(hidden)}
        if app_id is None or app_id not in shipped:
            name = ' '.join(str(body.get('name') or '').split())
            if not 1 <= len(name) <= 60:
                raise ApplicationError('Give the application a name (up to 60 characters).')
            kind = body.get('kind') or 'game'
            if kind not in KINDS:
                raise ApplicationError('The kind is game, launcher or sitegroup.')
            category = body.get('category') or ('gaming' if kind != 'sitegroup' else 'other')
            if category not in CATEGORIES:
                raise ApplicationError(f'The category is one of {", ".join(CATEGORIES)}.')
            part_of = body.get('part_of') or None
            launchers = {a['id'] for a in listing(data) if a['kind'] == 'launcher'}
            if part_of is not None and (kind != 'game' or part_of not in launchers):
                raise ApplicationError('Only a game is part of something, and that is a launcher.')
            names = {a['name'].lower(): a['id'] for a in listing(data)}
            if names.get(name.lower(), app_id) != app_id:
                raise ApplicationError(f'There is already an application called {name}.')
            if app_id is None:
                if len([a for a in own if a not in shipped]) >= MAX_OWN:
                    raise ApplicationError(f'Floorbit keeps at most {MAX_OWN} own applications.')
                taken = set(shipped) | set(own)
                app_id = new_id if new_id and ID_RE.match(new_id) and new_id not in taken else _new_id(name, taken)
            entry.update({'id': app_id, 'name': name, 'kind': kind, 'category': category, 'part_of': part_of})
        rest = [e for e in data.get(KEY) or [] if isinstance(e, dict) and e.get('id') != app_id]
        data[KEY] = [*rest, entry]
        save_data(data)
    return next(a for a in listing() if a['id'] == app_id)


def import_entries(entries):
    """Takes applications from another Floorbit's export (a rules file, already checked): a new one
    is added with its id, an own one replaced, and a built-in one gets what the file has beyond what
    shipped, on top of what the event added. Stops at the first one that doesn't fit and says which;
    the ones before it stay. {"added": n, "changed": n}."""
    out = {'added': 0, 'changed': 0}
    keys = ('sites', 'ports', 'cidr', 'depots')
    for entry in entries:
        aid = entry['id']
        shipped, own = base(), _own()
        try:
            if aid in shipped:
                added = own.get(aid) or {}
                save({k: sorted(set(added.get(k) or []) | (set(entry.get(k) or []) - set(shipped[aid].get(k) or [])))
                      for k in keys}, aid)
            else:
                body = {k: entry.get(k) for k in ('name', 'kind', 'category', 'part_of', *keys)}
                save(body, aid if aid in own else None, new_id=aid)
        except ApplicationError as exc:
            raise ApplicationError(f'{entry.get("name") or aid}: {exc.message} '
                                   f'({out["added"] + out["changed"]} taken before it.)') from exc
        out['changed' if aid in shipped or aid in own else 'added'] += 1
    return out


def _new_id(name, taken):
    stem = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')[:32] or 'app'
    aid, n = stem, 2
    while aid in taken:
        aid, n = f'{stem}-{n}', n + 1
    return aid


def remove(app_id):
    """Removes an own application, or puts a built-in one back as it shipped. The removed entry, or None."""
    with _lock:
        data = load_data()
        own = _own(data)
        if app_id not in own:
            return None
        data[KEY] = [e for e in data.get(KEY) or [] if isinstance(e, dict) and e.get('id') != app_id]
        save_data(data)
    return own[app_id]


# ── what the agent's classifier gets ────────────────────────────────────────

def flow_rules(data=None, servers=None):
    """Traffic rules from the applications with ports or addresses, and from the game servers, as
    ``FLOWS_SERVICES`` entries (floorbit/flows/classify.py). Games first: a game wins over its launcher."""
    apps = active(data)
    rules = []
    for app in sorted(apps, key=lambda a: a['kind'] != 'game'):
        if app['ports'] or app['cidr']:
            rules.append({'name': service_name(app), 'category': _flow_category(app['category']),
                          'ports': app['ports'], 'cidr': app['cidr']})
    for server in servers or []:
        net = _host_net(server.get('host'))
        if net and server.get('game'):
            rules.insert(0, {'name': _game_name(server['game'], apps), 'category': 'gaming', 'cidr': [net]})
    return rules


def service_name(app):
    return SERVICE_NAMES.get(app['id'], app['name'])


def _flow_category(category):
    from .flows.classify import CATEGORIES as FLOW
    return category if category in FLOW else 'web' if category == 'social' else 'other'


def _host_net(host):
    try:
        addr = ipaddress.ip_address(str(host or ''))
    except ValueError:
        return None   # a host name: the agent can't match it to flows without asking DNS
    return f'{addr}/{addr.max_prefixlen}'


def _game_name(game, apps):
    """A game server's game as the application it is, matched by name or id, else its own text."""
    wanted = str(game).strip().lower()
    for app in apps:
        if app['kind'] == 'game' and wanted in (app['name'].lower(), app['id']):
            return app['name']
    return str(game).strip()[:60]


# ── numbers ─────────────────────────────────────────────────────────────────

def usage(apps, sites=None, services=None, caches=None, downloads=None, servers=None):
    """Per application id: what each source saw. ``sites`` {site: [lookups, most clients in an hour]}
    (dns.site_lookups), ``services`` {name: {"bytes", "seats"}} (traffic, 24 hours), ``caches``
    {cache: {"hit_bytes", "miss_bytes"}}, ``downloads`` [{"cache", "item", "hit_bytes", "miss_bytes"}],
    ``servers`` the game servers with their last answer."""
    sites, services, caches = sites or {}, services or {}, caches or {}
    by_depot = {}
    for d in downloads or []:
        item = str(d.get('item') or '')
        if d.get('cache') == 'steam' and item.startswith('depot '):
            by_depot[item[6:]] = d
    players = {}
    for s in servers or []:
        if s.get('status') == 'up' and s.get('game'):
            name = _game_name(s['game'], apps).lower()
            players[name] = players.get(name, 0) + ((s.get('info') or {}).get('players') or 0)
    out = {}
    for app in apps:
        dns_rows = [sites[s] for s in app['sites'] if s in sites]
        flow = services.get(service_name(app))
        cache_rows = [caches[c] for c in app['caches'] if c in caches]
        cache_rows += [by_depot[d] for d in app['depots'] if d in by_depot]
        out[app['id']] = {
            'lookups': sum(r[0] for r in dns_rows) if dns_rows else None,
            'dns_seats_max': max(r[1] for r in dns_rows) if dns_rows else None,
            'traffic_bytes': flow['bytes'] if flow else None,
            'traffic_seats': flow['seats'] if flow else None,
            'cache_hit_bytes': sum(r['hit_bytes'] for r in cache_rows) if cache_rows else None,
            'cache_miss_bytes': sum(r['miss_bytes'] for r in cache_rows) if cache_rows else None,
            'players': players.get(app['name'].lower()) if app['kind'] == 'game' else None,
        }
    return out


def seats(row):
    """The most seats any source saw for an application (players on the event's servers count too)."""
    return max([v for v in (row['dns_seats_max'], row['traffic_seats'], row['players']) if v] or [0])
