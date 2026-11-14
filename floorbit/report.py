"""The post-event report (issue #22): what happened at the event, in numbers. See docs/report.md.

Built from what the app already keeps: the stats store's event history (hours, switch outages,
problem ports, ``stats.py``), the check-in history and the incident board. Seat numbers, switches,
ports and times only; nicks and IPs are added only when an admin asks (``people=True``).
"""
import time

from . import incidents
from .stats import HOUR

TOP_PORTS = 10
MAX_INCIDENTS = 200   # the PDF lists them; a board bigger than that is cut, the totals still count all


def _checked_in_by_hour(checkins, hours):
    """Most seats checked in during each hour, from [t, seat, 1|0] changes."""
    out = {}
    if not hours:
        return out
    current = set()
    i = 0
    for h in hours:
        end = h + HOUR
        most = len(current)
        while i < len(checkins) and checkins[i][0] < end:
            _t, seat, on = checkins[i]
            (current.add if on else current.discard)(seat)
            if checkins[i][0] >= h:
                most = max(most, len(current))
            i += 1
        out[h] = max(most, len(current))
    return out


def _outages(events, now):
    """Per switch: how often it went down, for how long in all and at most, and whether it still is."""
    per = {}
    for t, sid, name, status in sorted(events, key=lambda e: e[0]):
        row = per.setdefault(sid or name, {'switch': name, 'times': 0, 'down_s': 0.0, 'longest_s': 0.0,
                                           'down_since': None, 'first': t})
        row['switch'] = name or row['switch']
        if status == 'offline' and row['down_since'] is None:
            row['times'] += 1
            row['down_since'] = t
        elif status == 'online' and row['down_since'] is not None:
            took = t - row['down_since']
            row['down_s'] += took
            row['longest_s'] = max(row['longest_s'], took)
            row['down_since'] = None
    out = []
    for row in per.values():
        if not row['times']:
            continue
        still = row['down_since'] is not None
        if still:
            took = now - row['down_since']
            row['down_s'] += took
            row['longest_s'] = max(row['longest_s'], took)
        out.append({'switch': row['switch'], 'times': row['times'], 'down_s': round(row['down_s']),
                    'longest_s': round(row['longest_s']), 'still_down': still})
    return sorted(out, key=lambda r: (-r['down_s'], r['switch']))


def _incidents(since, people):
    items = [i for i in incidents.list_all() if since is None or i['created_at'] >= since]
    items.sort(key=lambda i: i['created_at'])
    fixed = [i for i in items if i.get('fixed_at')]
    took = sorted(i['fixed_at'] - i['created_at'] for i in fixed)
    rows = []
    for i in items[:MAX_INCIDENTS]:
        row = {'title': i['title'], 'seat': i.get('seat'), 'switch': i.get('switch_name'),
               'circuit': i.get('circuit_name'), 'team': i.get('team'), 'source': i.get('source'),
               'reports': i.get('reports') or 1, 'start': i['created_at'], 'end': i.get('fixed_at'),
               'status': i.get('status')}
        if people:
            row['reported_by'] = i.get('reported_by')
            row['assignee'] = i.get('assignee')
        rows.append(row)
    return {
        'total': len(items), 'fixed': len(fixed), 'open': len(items) - len(fixed),
        'from_seats': sum(1 for i in items if i.get('source') == 'helpdesk'),
        'median_fix_s': round(took[len(took) // 2]) if took else None,
        'items': rows,
    }


def build(stats_event, checkins, seats_total, people=False, seat_info=None, event_name='', now=None):
    """The report as a dict, for the page and the PDF.

    ``stats_event`` is ``Stats.event()``, ``checkins`` is [t, seat, 1|0] from the check-in history,
    ``seat_info`` maps a seat to its source row (username, ip_address), used only with ``people``.
    """
    now = time.time() if now is None else now
    hours = stats_event['hours']
    start = stats_event.get('start')
    if start is not None:
        checkins = [c for c in checkins if c[0] >= start - 24 * HOUR]   # who came the day before counts
    hour_keys = [h['t'] for h in hours]
    checked = _checked_in_by_hour(sorted(checkins, key=lambda c: c[0]), hour_keys)
    rows = [dict(h, checked_in=checked.get(h['t'], 0)) for h in hours]
    end = min(hours[-1]['t'] + HOUR, now) if hours else None
    moved = sum(h['avg_bps'] * HOUR / 8 for h in hours)   # bytes, from the hourly average

    ports = sorted(stats_event['problem_ports'], key=lambda p: (-p['count'], -(p.get('last') or 0)))[:TOP_PORTS]
    ports = [{k: p.get(k) for k in ('switch', 'port', 'seat', 'count', 'kinds', 'last')} for p in ports]
    found = _incidents(start, people)
    if people:
        info = seat_info or {}
        for row in ports + found['items']:
            if row.get('seat'):
                entry = info.get(row['seat']) or {}
                row['nick'] = entry.get('username') or None
                row['ip'] = entry.get('ip_address') or None

    return {
        'event_name': event_name or '',
        'start': start,
        'end': end,
        'generated': now,
        'people': bool(people),
        'seats': seats_total,
        'online_max': max((h['online_max'] for h in hours), default=0),
        'checked_in_max': max((r['checked_in'] for r in rows), default=0),
        'peak': stats_event.get('peak'),
        'bytes_moved': round(moved),
        'hours': rows,
        'outages': _outages(stats_event['switch_events'], now),
        'problem_ports': ports,
        'incidents': found,
    }
