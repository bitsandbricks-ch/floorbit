"""The public stats wall (issue #105): fun facts about the event for a big screen and attendees' phones.

Hall-wide and per seat block only: no nicks, IPs, MACs, seat numbers or switch names. A seat block
is only named when it has ``MIN_BLOCK_SEATS`` (5) seats or more, the same five-seat rule the
traffic and DNS statistics use. The games, downloads and sites come from floorbit/games.py, which only
counts sites and services enough seats used.
"""
from itertools import pairwise

from . import recording

MIN_BLOCK_SEATS = 5
TOP_GAMES = 5
HOUR = 3600


def downloaded(frames, hours):
    """Bytes downloaded so far: from the whole-event recording, else from the report's hourly averages."""
    if len(frames) > 1:
        total = 0.0
        for a, b in pairwise(frames):
            # A gap longer than an hour is the app being off: don't make up traffic for it.
            total += (a.get('down') or 0) * min(b['t'] - a['t'], HOUR) / 8
        return round(total)
    return round(sum(h['avg_bps'] * HOUR / 8 for h in hours))   # down and up: the best there is


def loyal_block(frames):
    """The seat block whose seats were online the longest, on average: {name, hours, share} or None."""
    totals = {}
    span = 0.0
    for a, b in pairwise(frames):
        dt = min(b['t'] - a['t'], HOUR)
        span += dt
        for name, row in (a.get('blocks') or {}).items():
            seats, online = row[0], row[1]
            if seats >= MIN_BLOCK_SEATS and name != '?':
                totals[name] = totals.get(name, 0.0) + online / seats * dt
    if not totals or not span:
        return None
    name, secs = max(totals.items(), key=lambda kv: (kv[1], kv[0]))
    return {'name': name, 'hours': round(secs / HOUR, 1), 'share': round(secs / span, 3)}


def busiest_hour(hours):
    best = max(hours, key=lambda h: h['avg_bps'], default=None)
    return {'t': best['t'], 'bps': best['avg_bps']} if best and best['avg_bps'] else None


def _bars(rows):
    """[(name, number, extra)] busiest first, top five, with a 0..1 bar against the first."""
    rows = sorted((r for r in rows if r[1]), key=lambda r: (-r[1], r[0]))[:TOP_GAMES]
    top = rows[0][1] if rows else 0
    return [{'name': n, 'bar': round(w / top, 3), **extra} for n, w, extra in rows]


def _cache_bytes(r):
    return (r.get('cache_hit_bytes') or 0) + (r.get('cache_miss_bytes') or 0)


def top_games(insights):
    """Game titles by the most seats any source saw (applications.seats), names and counts only."""
    rows = []
    for r in (insights or {}).get('titles') or []:
        via = [k for k, v in (('dns', r.get('dns_seats_max')), ('traffic', r.get('traffic_seats')),
                              ('servers', r.get('players'))) if v]
        rows.append((r['name'], r.get('seats') or 0, {'seats': r.get('seats') or 0, 'via': via}))
    return _bars(rows)


def top_downloads(insights):
    """What came through the LAN cache, by title where the Steam depots say so, else by launcher
    (less what its titles already count) or site group such as Windows updates."""
    insights = insights or {}
    titles = insights.get('titles') or []
    rows, of_titles = [], {}
    for r in titles:
        if _cache_bytes(r):
            rows.append((r['name'], _cache_bytes(r), {'bytes': _cache_bytes(r)}))
            if r.get('part_of'):
                of_titles[r['part_of']] = of_titles.get(r['part_of'], 0) + _cache_bytes(r)
    for r in (insights.get('launchers') or []) + (insights.get('sitegroups') or []):
        rest = _cache_bytes(r) - of_titles.get(r['id'], 0)
        if rest > 0:
            rows.append((r['name'], rest, {'bytes': rest}))
    return _bars(rows)


def top_sites(insights):
    """The sites the hall looks up most, five seats or more each (dns.py's rule). Only sites of a
    known application (the open lists or the event's own): a big screen never shows whatever else
    enough seats looked up."""
    rows = [(s['site'], s['seats'], {'seats': s['seats'], 'category': s['category']})
            for s in (insights or {}).get('sites') or [] if s.get('application')]
    return _bars(rows)


def facts(stats_event, online, seats_total, insights=None, frames=None, now=None):
    """Everything the wall shows. ``online`` is the number of seats online now, or None when unknown."""
    frames = recording.frames() if frames is None else frames
    hours = stats_event.get('hours') or []
    start = stats_event.get('start') or (frames[0]['t'] if frames else None) or (hours[0]['t'] if hours else None)
    cache = (insights or {}).get('cache') or {}
    return {
        'online': online,
        'seats': seats_total,
        'online_max': max([h['online_max'] for h in hours] + [f.get('online') or 0 for f in frames], default=0),
        'downloaded': downloaded(frames, hours),
        'peak': stats_event.get('peak'),
        'busiest_hour': busiest_hour(hours),
        'loyal_block': loyal_block(frames),
        'games': top_games(insights),
        'downloads': top_downloads(insights),
        'sites': top_sites(insights),
        'cache_hit_share': round(cache['hit_bytes'] / (cache['hit_bytes'] + cache['miss_bytes']), 3)
        if cache.get('configured') and (cache.get('hit_bytes') or 0) + (cache.get('miss_bytes') or 0) else None,
        'cache_saved': cache.get('hit_bytes') or None if cache.get('configured') else None,
        'start': start,
        'running_hours': round((now - start) / HOUR, 1) if start and now else None,
    }


UNITS = ('B', 'KB', 'MB', 'GB', 'TB', 'PB')
BIT_UNITS = ('bit/s', 'kbit/s', 'Mbit/s', 'Gbit/s', 'Tbit/s')


def _scaled(value, units, lang):
    n, i = float(value or 0), 0
    while n >= 1000 and i < len(units) - 1:
        n, i = n / 1000, i + 1
    text = f'{n:.0f}' if n >= 100 or i == 0 else f'{n:.1f}'
    if lang == 'de':
        text = text.replace('.', ',')   # Swiss German writes 1,5 TB
    return f'{text} {units[i]}'


def size(value, lang='en'):
    return _scaled(value, UNITS, lang)


def rate(value, lang='en'):
    return _scaled(value, BIT_UNITS, lang)
