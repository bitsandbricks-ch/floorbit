"""The public stats wall (issue #105): fun facts about the event for a big screen and attendees' phones.

Hall-wide and per seat block only: no nicks, IPs, MACs, seat numbers or switch names. A seat block
is only named when it has ``MIN_BLOCK_SEATS`` (5) seats or more, the same five-seat rule the
traffic and DNS statistics use. The games come from floorbit/games.py, which only counts sites and
services enough seats used.
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


def top_games(insights):
    """Launcher and game names, busiest first, with a 0..1 bar against the first. Names only."""
    rows = []
    for r in (insights or {}).get('launchers') or []:
        weight = (r['cache_hit_bytes'] or 0) + (r['cache_miss_bytes'] or 0) or r['traffic_bytes'] or r['lookups'] or 0
        rows.append((r['name'], weight))
    for g in (insights or {}).get('games') or []:
        rows.append((g['name'], g['bytes']))
    rows = sorted((r for r in rows if r[1]), key=lambda r: -r[1])[:TOP_GAMES]
    top = rows[0][1] if rows else 0
    return [{'name': n, 'bar': round(w / top, 3)} for n, w in rows]


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
