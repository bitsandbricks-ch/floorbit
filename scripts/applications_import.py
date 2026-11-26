"""Writes floorbit/applications_lists.json from two open lists, at the commits named below.

- uklans/cache-domains (MIT): the CDNs a lancache.net cache serves, one list per launcher or game.
  The same list lancache-dns answers for, so Games and the LAN cache split the hall the same way.
- v2fly/domain-list-community (MIT): per-service domain lists, for the site groups.

Run it by hand to move to newer lists (change the commits first), then check the diff:

    python scripts/applications_import.py

These bundled lists are the fallback: they work in a hall with no internet. Lists that should stay
current are rule sources on the Applications page (floorbit/application_sources.py, #1503), which
Floorbit fetches on a schedule and can freeze for the event.
"""
import json
import pathlib
import sys
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from floorbit.dns import site  # noqa: E402

CACHE_DOMAINS = ('uklans/cache-domains', 'f7d6206f4769d6bf0274b5ad79e6bebda7753b17')
V2FLY = ('v2fly/domain-list-community', '96d9c68b7ef43f71118d0be17a9f2edb464825e6')
OUT = ROOT / 'floorbit' / 'applications_lists.json'

# DNS counts per site, so a CDN that many vendors share would count for all of them. Sites in
# more than one list are left out too.
SHARED_CDNS = {'akamaihd.net', 'akamaized.net', 'akadns.net', 'cloudfront.net', 'comcast.net', 'edgekey.net',
               'edgesuite.net', 'fastly-edge.com', 'gcdn.co', 'llnwd.net', 'microsoft.com', 'google.com',
               'googleapis.com', 'gstatic.com', 'l.google.com', 'fastlylb.net'}
# Second levels Floorbit's site cut doesn't know (youtube.co.ae would count as co.ae): left out.
SECOND_LEVELS = {'co', 'com', 'net', 'org', 'ac', 'gov', 'edu', 'or', 'ne', 'go', 'gob', 'gv', 'nic'}

# cache-domains id -> (name, kind, category). Not listed: left out ('test').
CACHES = {
    'arenanet': ('Guild Wars 2', 'game', 'gaming'),
    'blizzard': ('Battle.net', 'launcher', 'gaming'),
    'blur': ('Blur LAN CE', 'game', 'gaming'),
    'bsg': ('Escape from Tarkov', 'game', 'gaming'),
    'cityofheroes': ('City of Heroes', 'game', 'gaming'),
    'cod': ('Call of Duty', 'game', 'gaming'),
    'daybreak': ('Daybreak Games', 'launcher', 'gaming'),
    'epicgames': ('Epic Games', 'launcher', 'gaming'),
    'frontier': ('Frontier Games', 'launcher', 'gaming'),
    'neverwinter': ('Neverwinter', 'game', 'gaming'),
    'nexusmods': ('Nexus Mods', 'sitegroup', 'downloads'),
    'nintendo': ('Nintendo', 'launcher', 'gaming'),
    'origin': ('EA app', 'launcher', 'gaming'),
    'pathofexile': ('Path of Exile', 'game', 'gaming'),
    'renegadex': ('Renegade X', 'game', 'gaming'),
    'riot': ('Riot Games', 'launcher', 'gaming'),
    'rockstar': ('Rockstar Games', 'launcher', 'gaming'),
    'sony': ('PlayStation Network', 'launcher', 'gaming'),
    'square': ('Final Fantasy XIV', 'game', 'gaming'),
    'steam': ('Steam', 'launcher', 'gaming'),
    'teso': ('The Elder Scrolls Online', 'game', 'gaming'),
    'uplay': ('Ubisoft Connect', 'launcher', 'gaming'),
    'warframe': ('Warframe', 'game', 'gaming'),
    'wargaming': ('Wargaming', 'launcher', 'gaming'),
    'wsus': ('Windows updates', 'sitegroup', 'updates'),
    'xboxlive': ('Xbox', 'launcher', 'gaming'),
}

# Site groups: id -> (name, category, v2fly lists).
GROUPS = {
    'streaming': ('Streaming', 'streaming', ('twitch', 'youtube', 'kick', 'netflix')),
    'music': ('Music', 'streaming', ('spotify',)),
    'voice': ('Voice and chat', 'social', ('discord', 'teamspeak', 'telegram', 'whatsapp')),
    'social': ('Social media', 'social', ('facebook', 'instagram', 'tiktok', 'twitter', 'reddit')),
    'faceit': ('FACEIT', 'gaming', ('faceit',)),
}


def fetch(repo, commit, path):
    url = f'https://raw.githubusercontent.com/{repo}/{commit}/{path}'
    with urllib.request.urlopen(url, timeout=30) as resp:   # a fixed https URL
        return resp.read().decode()


def sites_of(names):
    out = set()
    for name in names:
        got = site(name.strip().lstrip('*.'))
        if got and got.split('.')[0] not in SECOND_LEVELS:
            out.add(got)
    return out


def cache_domains():
    repo, commit = CACHE_DOMAINS
    index = json.loads(fetch(repo, commit, 'cache_domains.json'))
    out = {}
    for entry in index['cache_domains']:
        if entry['name'] not in CACHES:
            continue
        lines = []
        for f in entry['domain_files']:
            lines += [ln for ln in fetch(repo, commit, f).splitlines() if ln.strip() and not ln.startswith('#')]
        out[entry['name']] = sites_of(lines)
    return out


def v2fly_list(name, seen=None):
    """A v2fly list's plain and full domains, following include: lines."""
    repo, commit = V2FLY
    seen = set() if seen is None else seen
    if name in seen:
        return []
    seen.add(name)
    out = []
    for line in fetch(repo, commit, f'data/{name}').splitlines():
        line = line.split('#', 1)[0].strip()
        if not line:
            continue
        value = line.split()[0]
        if value.startswith('include:'):
            out += v2fly_list(value[len('include:'):].split('@')[0], seen)
        elif value.startswith(('regexp:', 'keyword:')):
            continue
        else:
            out.append(value.split(':', 1)[1] if value.startswith(('full:', 'domain:')) else value)
    return out


def main():
    caches = cache_domains()
    groups = {gid: sites_of(n for lst in lists for n in v2fly_list(lst)) for gid, (_n, _c, lists) in GROUPS.items()}
    owners = {}
    for sites in list(caches.values()) + list(groups.values()):
        for s in sites:
            owners[s] = owners.get(s, 0) + 1
    keep = lambda sites: sorted(s for s in sites if s not in SHARED_CDNS and owners[s] == 1)  # noqa: E731
    apps = []
    for cid, sites in sorted(caches.items()):
        name, kind, category = CACHES[cid]
        apps.append({'id': cid, 'name': name, 'kind': kind, 'category': category, 'sites': keep(sites),
                     'caches': [cid], 'source': 'cache-domains'})
    for gid, sites in sorted(groups.items()):
        name, category, _lists = GROUPS[gid]
        apps.append({'id': gid, 'name': name, 'kind': 'sitegroup', 'category': category, 'sites': keep(sites),
                     'caches': [], 'source': 'v2fly'})
    doc = {
        'sources': [
            {'id': 'cache-domains', 'repo': CACHE_DOMAINS[0], 'commit': CACHE_DOMAINS[1], 'license': 'MIT',
             'copyright': 'Copyright (c) 2017 UK LAN Techs'},
            {'id': 'v2fly', 'repo': V2FLY[0], 'commit': V2FLY[1], 'license': 'MIT',
             'copyright': 'Copyright (c) 2018-2019 V2Ray'},
        ],
        'applications': apps,
    }
    OUT.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + '\n')
    print(f'wrote {OUT.relative_to(ROOT)}: {len(apps)} applications')


if __name__ == '__main__':
    main()
