"""Game and launcher insights (issue #88): what the hall plays and downloads, and what the LAN
cache saved. Hall-wide only. See docs/games.md.

Three sources, each optional:

- DNS analytics (floorbit/dns.py): lookups of each launcher's sites, named under the five-seat rule.
- Traffic (floorbit/flows): bytes and seats per service, for the services whose category is gaming.
- The LAN cache's log (floorbit/lancache.py): bytes served from disk and from the internet, per cache.
"""
from . import dns

# Launchers: the sites they look up, the flow services they show as, and the lancache.net cache
# identifiers (cache-domains) that carry their downloads.
LAUNCHERS = (
    {'id': 'steam', 'name': 'Steam',
     'sites': ('steampowered.com', 'steamcontent.com', 'steamstatic.com', 'steamserver.net', 'steamcommunity.com',
               'valvesoftware.com'),
     'services': ('Steam',), 'caches': ('steam',)},
    {'id': 'battlenet', 'name': 'Battle.net', 'sites': ('battle.net', 'blizzard.com'),
     'services': ('Battle.net',), 'caches': ('blizzard',)},
    {'id': 'riot', 'name': 'Riot Games', 'sites': ('riotgames.com', 'leagueoflegends.com'),
     'services': ('Riot Games',), 'caches': ('riot',)},
    {'id': 'epic', 'name': 'Epic Games', 'sites': ('epicgames.com', 'epicgames.dev', 'unrealengine.com'),
     'services': (), 'caches': ('epicgames',)},
    {'id': 'ea', 'name': 'EA app', 'sites': ('ea.com', 'origin.com'), 'services': (), 'caches': ('origin',)},
    {'id': 'ubisoft', 'name': 'Ubisoft Connect', 'sites': ('ubi.com', 'ubisoft.com'), 'services': (),
     'caches': ('uplay',)},
    {'id': 'xbox', 'name': 'Xbox / Microsoft Store', 'sites': ('xboxlive.com',), 'services': (),
     'caches': ('xboxlive',)},
    {'id': 'minecraft', 'name': 'Minecraft', 'sites': ('minecraft.net', 'mojang.com'),
     'services': ('Minecraft',), 'caches': ()},
)


def _flow_services(flows):
    """{service: {"bytes", "seats", "category"}} from the traffic summary (24 hours)."""
    return {s['name']: s for s in (flows or {}).get('services') or []}


def insights(dns_stats=None, flows=None, lancache=None, hours=24, now=None):
    sites = dns_stats.site_lookups(hours, now) if dns_stats is not None else {}
    services = _flow_services(flows)
    cache = lancache.snapshot(hours, now) if lancache is not None else None
    by_cache = {c['cache']: c for c in (cache or {}).get('caches') or []}
    used_services, used_caches = set(), set()
    rows = []
    for launcher in LAUNCHERS:
        lookups = sum(sites.get(s, [0])[0] for s in launcher['sites'])
        seats = max([sites.get(s, [0, 0])[1] for s in launcher['sites']] or [0])
        flow = [services[n] for n in launcher['services'] if n in services]
        used_services.update(launcher['services'])
        caches = [by_cache[c] for c in launcher['caches'] if c in by_cache]
        used_caches.update(launcher['caches'])
        hit = sum(c['hit_bytes'] for c in caches)
        miss = sum(c['miss_bytes'] for c in caches)
        row = {
            'id': launcher['id'], 'name': launcher['name'],
            'lookups': lookups if launcher['sites'] else None, 'dns_seats_max': seats,
            'traffic_bytes': sum(s['bytes'] for s in flow) if flow else None,
            'traffic_seats': max(s['seats'] for s in flow) if flow else None,
            'cache_hit_bytes': hit if caches else None, 'cache_miss_bytes': miss if caches else None,
        }
        if lookups or flow or caches:
            rows.append(row)
    rows.sort(key=lambda r: (-((r['cache_hit_bytes'] or 0) + (r['cache_miss_bytes'] or 0)),
                             -(r['traffic_bytes'] or 0), -(r['lookups'] or 0), r['name']))
    # Gaming services the event named itself (FLOWS_SERVICES: tournament servers, a game's ports).
    games = sorted(({'name': s['name'], 'bytes': s['bytes'], 'seats': s['seats']} for s in services.values()
                    if s.get('category') == 'gaming' and s['name'] not in used_services),
                   key=lambda s: -s['bytes'])
    other_caches = sorted((c for name, c in by_cache.items() if name not in used_caches),
                          key=lambda c: -(c['hit_bytes'] + c['miss_bytes']))
    return {
        'launchers': rows, 'games': games, 'other_caches': other_caches,
        'cache': cache,
        'sources': {'dns': dns_stats is not None and bool(sites), 'traffic': bool(services),
                    'cache': bool(cache and cache['configured'])},
        'min_seats': {'dns': dns.settings()['min_clients'], 'traffic': (flows or {}).get('min_seats')},
    }
