"""Game and launcher insights (issues #88, #1481): what the hall plays and downloads, and what the
LAN cache saved. Hall-wide only. See docs/games.md.

The games and launchers are applications (floorbit/applications.py), so an event can add domains,
ports, server addresses and Steam depots to them. Four sources, each optional:

- DNS analytics (floorbit/dns.py): lookups of each application's sites, named under the five-seat rule.
- Traffic (floorbit/flows): bytes and seats per flow service named after an application.
- The LAN cache (floorbit/lancache.py or the lancache plugin): bytes per cache and per Steam depot.
- The event's game servers (floorbit/game_servers.py): players right now, per game.
"""
from . import applications, dns


def _flow_services(flows):
    """{service: {"bytes", "seats", "category"}} from the traffic summary (24 hours)."""
    return {s['name']: s for s in (flows or {}).get('services') or []}


def _row(app, seen):
    return {'id': app['id'], 'name': app['name'], 'kind': app['kind'], 'part_of': app.get('part_of'),
            'category': app['category'], **seen, 'seats': applications.seats(seen)}


def _weight(r):
    return ((r['cache_hit_bytes'] or 0) + (r['cache_miss_bytes'] or 0), r['traffic_bytes'] or 0, r['lookups'] or 0)


def insights(dns_stats=None, flows=None, lancache=None, hours=24, now=None, servers=None, data=None):
    sites = dns_stats.site_lookups(hours, now) if dns_stats is not None else {}
    services = _flow_services(flows)
    cache = lancache.snapshot(hours, now) if lancache is not None else None
    by_cache = {c['cache']: c for c in (cache or {}).get('caches') or []}
    apps = applications.active(data)
    seen = applications.usage(apps, sites, services, by_cache, (cache or {}).get('downloads'), servers)
    rows = {'launcher': [], 'game': [], 'sitegroup': []}
    for app in apps:
        s = seen[app['id']]
        if any(v for v in s.values()):
            rows[app['kind']].append(_row(app, s))
    for kind in rows:
        rows[kind].sort(key=lambda r: (*(-w for w in _weight(r)), r['name']))
    titles = sorted(rows['game'], key=lambda r: (-r['seats'], *(-w for w in _weight(r)), r['name']))
    # Gaming services the event named itself (FLOWS_SERVICES: tournament servers, a game's ports).
    named = {applications.service_name(a) for a in apps}
    games = sorted(({'name': s['name'], 'bytes': s['bytes'], 'seats': s['seats']} for s in services.values()
                    if s.get('category') == 'gaming' and s['name'] not in named),
                   key=lambda s: -s['bytes'])
    used_caches = {c for a in apps for c in a['caches']}
    other_caches = sorted((c for name, c in by_cache.items() if name not in used_caches),
                          key=lambda c: -(c['hit_bytes'] + c['miss_bytes']))
    return {
        'launchers': rows['launcher'], 'titles': titles, 'sitegroups': rows['sitegroup'],
        'games': games, 'other_caches': other_caches,
        'cache': cache,
        'sources': {'dns': dns_stats is not None and bool(sites), 'traffic': bool(services),
                    'cache': bool(cache and cache['configured']),
                    'servers': any(s.get('status') == 'up' for s in servers or [])},
        'min_seats': {'dns': dns.settings()['min_clients'], 'traffic': (flows or {}).get('min_seats')},
    }
