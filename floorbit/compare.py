"""Compare views (issue #90): today against yesterday, and this event against the last one.

Both sides are cut to the same length, so the numbers are fair: at 15:00 today is compared with
yesterday until 15:00, and an event in its 20th hour with the last event's first 20 hours. The
whole of yesterday and of the last event are in the hourly series for context.

From what is already kept: the stats' hourly rows (``Stats.event()``), the switch outages, the
incident board and the archived events (floorbit/event_archive.py). Numbers only, no people.
"""
import time

from . import event_archive, incidents

HOUR = 3600
DAY = 24 * HOUR


def _local_midnight(t):
    lt = time.localtime(t)
    return time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1))


def _window(hours, start, end):
    rows = [h for h in hours if start <= h['t'] < end]
    return {
        'peak_bps': max((h.get('peak_bps') or 0 for h in rows), default=None) if rows else None,
        'avg_bps': round(sum(h.get('avg_bps') or 0 for h in rows) / len(rows)) if rows else None,
        'bytes_moved': round(sum((h.get('avg_bps') or 0) * HOUR / 8 for h in rows)),
        'online_max': max((h.get('online_max') or 0 for h in rows), default=0),
        'hours': len(rows),
    }


def _outages(switch_events, start, end):
    return sum(1 for t, _sid, _name, status in switch_events if status == 'offline' and start <= t < end)


def _incidents(items, start, end):
    return sum(1 for i in items if start <= (i.get('created_at') or 0) < end)


def day(stats_event, incident_list=None, now=None):
    """Today so far against yesterday until the same time of day."""
    now = time.time() if now is None else now
    hours = stats_event['hours']
    today = _local_midnight(now)
    yesterday = _local_midnight(today - HOUR)
    so_far = now - today
    items = incidents.list_all() if incident_list is None else incident_list
    events = stats_event.get('switch_events') or []

    def side(start, end):
        return {**_window(hours, start, end), 'incidents': _incidents(items, start, end),
                'outages': _outages(events, start, end), 'start': start, 'end': end}

    series = []
    by_t = {h['t']: h for h in hours}
    for k in range(24):
        t_today = int(today + k * HOUR)
        t_yday = int(yesterday + k * HOUR)
        a, b = by_t.get(t_today), by_t.get(t_yday)
        series.append({'hour': k, 'now_avg_bps': a['avg_bps'] if a else None,
                       'then_avg_bps': b['avg_bps'] if b else None,
                       'now_online': a['online_max'] if a else None, 'then_online': b['online_max'] if b else None})
    return {'now': side(today, now), 'then': side(yesterday, yesterday + so_far), 'series': series,
            'has_then': any(yesterday <= h['t'] < today for h in hours)}


def event(current_report, now=None):
    """The running event so far against the last archived event's first as many hours."""
    now = time.time() if now is None else now
    past = event_archive.archived()
    if not past:
        return None
    try:
        last = event_archive.get(past[0]['id'])
    except event_archive.ArchiveError:
        return None
    report = last.get('report') or {}
    start = current_report.get('start')
    if start is None:
        return None
    elapsed = now - start
    then_start = report.get('start') or last.get('start')
    then_hours = report.get('hours') or []
    items = (report.get('incidents') or {}).get('items') or []

    cur = _window(current_report.get('hours') or [], start, now + 1)
    cur['incidents'] = (current_report.get('incidents') or {}).get('total', 0)
    cur['outages'] = sum(o['times'] for o in current_report.get('outages') or [])
    then = _window(then_hours, then_start, then_start + elapsed)
    then['incidents'] = sum(1 for i in items if (i.get('start') or 0) < then_start + elapsed)
    then['outages'] = None   # the archive keeps outages per switch, not when they were

    def by_index(rows, base):
        return {int((h['t'] - base) // HOUR): h for h in rows}

    a, b = by_index(current_report.get('hours') or [], start), by_index(then_hours, then_start)
    length = max([0, *a, *b]) + 1 if (a or b) else 0
    series = [{'hour': k,
               'now_avg_bps': a[k]['avg_bps'] if k in a else None, 'then_avg_bps': b[k]['avg_bps'] if k in b else None,
               'now_online': a[k]['online_max'] if k in a else None,
               'then_online': b[k]['online_max'] if k in b else None} for k in range(min(length, 21 * 24))]
    return {'name': last.get('name'), 'id': last.get('id'), 'then_start': then_start, 'elapsed_s': round(elapsed),
            'now': cur, 'then': then, 'then_total': last.get('figures'), 'series': series}
