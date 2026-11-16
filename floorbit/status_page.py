"""Public network status page (issue #101). See docs/status-page.md.

What attendees see at ``/status`` during an outage: the overall state, which areas are hit (halls,
seat blocks and their rows), and updates the crew posts. Never switch names or IPs, unless an admin
turns on ``public.status_switch_names``.

The state works itself out from the status monitor: every placed switch up is ``operational``;
some down is ``degraded``; a router or firewall down, or half the switches or more, is ``outage``;
the monitoring source unreachable is ``unknown`` (better than claiming all is fine). The crew can set
the state by hand (for example ``maintenance``) until they clear it.

Planned maintenance (issue #422) is announced ahead with a start and an end: attendees see it coming,
and while it runs the state is ``maintenance`` by itself, unless the crew set one by hand.

Which seats a switch serves comes from the port reads (a port's description names its seat, see
floorbit/attention.py), remembered while the switch is down. A switch with no seats known counts
for the seat block nearest to it on the floor plan.
"""
import math
import threading
import time
import uuid
from xml.sax.saxutils import escape as _x

from . import halls, inventory
from .seat_names import block_rows
from .store import load_data, save_data

KEY = 'status_page'
STATES = ('operational', 'degraded', 'outage', 'maintenance', 'unknown')
SET_BY_HAND = ('operational', 'degraded', 'outage', 'maintenance')
CORE_ROLES = ('router', 'firewall')
MAX_UPDATES = 50
RECOVERED_FOR = 30 * 60   # how long an area stays under "Back up recently"
MAX_TEXT = 500
MAX_PLANNED = 20
MAX_PLANNED_AHEAD = 14 * 24 * 3600   # a typo in the date shouldn't announce something for next year
_lock = threading.Lock()
_seats_of = {}   # switch name (lower case) -> seats it served when last read


class StatusError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def _stored(data):
    raw = data.get(KEY)
    raw = raw if isinstance(raw, dict) else {}
    return {'override': raw.get('override'), 'updates': [u for u in raw.get('updates') or [] if isinstance(u, dict)],
            'planned': [m for m in raw.get('planned') or [] if isinstance(m, dict)]}


def _text(value, limit):
    return ' '.join(str(value or '').split())[:limit]


# ── What the crew sets ────────────────────────────────────────────────────────────────────
def post_update(body, by):
    text = _text(body.get('text'), MAX_TEXT)
    if not text:
        raise StatusError('Write what attendees should know.')
    state = body.get('state') or None
    if state is not None and state not in SET_BY_HAND:
        raise StatusError(f"The state is one of: {', '.join(SET_BY_HAND)}.")
    update = {'id': uuid.uuid4().hex[:10], 'at': time.time(), 'text': text, 'state': state,
              'area': _text(body.get('area'), 80), 'by': by}
    with _lock:
        data = load_data()
        stored = _stored(data)
        stored['updates'] = [update, *stored['updates']][:MAX_UPDATES]
        data[KEY] = stored
        save_data(data)
    return update


def delete_update(update_id):
    with _lock:
        data = load_data()
        stored = _stored(data)
        kept = [u for u in stored['updates'] if u.get('id') != update_id]
        if len(kept) == len(stored['updates']):
            raise StatusError('No such update.', 404)
        stored['updates'] = kept
        data[KEY] = stored
        save_data(data)


def _when(value, name):
    try:
        return float(value)
    except (TypeError, ValueError):
        raise StatusError(f'Give the {name} as a time.') from None


def plan_maintenance(body, by, now=None):
    """``{"start", "end", "text", "area"}`` (Unix times): announce maintenance attendees see coming."""
    now = time.time() if now is None else now
    start, end = _when(body.get('start'), 'start'), _when(body.get('end'), 'end')
    text = _text(body.get('text'), MAX_TEXT)
    if not text:
        raise StatusError('Write what attendees should know.')
    if end <= start:
        raise StatusError('The end has to be after the start.')
    if end <= now:
        raise StatusError('That time is already over.')
    if start > now + MAX_PLANNED_AHEAD:
        raise StatusError('Plan at most two weeks ahead.')
    item = {'id': uuid.uuid4().hex[:10], 'start': start, 'end': end, 'text': text,
            'area': _text(body.get('area'), 80), 'by': by, 'at': now}
    with _lock:
        data = load_data()
        stored = _stored(data)
        planned = [m for m in stored['planned'] if (m.get('end') or 0) > now]   # what is over goes
        if len(planned) >= MAX_PLANNED:
            raise StatusError(f'At most {MAX_PLANNED} planned at a time.')
        stored['planned'] = sorted([*planned, item], key=lambda m: m['start'])
        data[KEY] = stored
        save_data(data)
    return item


def cancel_maintenance(item_id):
    with _lock:
        data = load_data()
        stored = _stored(data)
        kept = [m for m in stored['planned'] if m.get('id') != item_id]
        if len(kept) == len(stored['planned']):
            raise StatusError('No such maintenance.', 404)
        stored['planned'] = kept
        data[KEY] = stored
        save_data(data)


def set_override(body, by):
    """``{"state": "maintenance", "note": "..."}`` sets the state by hand; ``{"state": null}`` clears it."""
    state = body.get('state') or None
    if state is not None and state not in SET_BY_HAND:
        raise StatusError(f"The state is one of: {', '.join(SET_BY_HAND)}.")
    with _lock:
        data = load_data()
        stored = _stored(data)
        stored['override'] = {'state': state, 'note': _text(body.get('note'), 200), 'by': by,
                              'at': time.time()} if state else None
        data[KEY] = stored
        save_data(data)
    return stored['override']


# ── Working out the state ─────────────────────────────────────────────────────────────────
def learn_seats(port_seats):
    """Remember which seats each switch served, from the latest port read ({(switch, port): seat})."""
    found = {}
    for (switch, _port), seat in (port_seats or {}).items():
        found.setdefault(str(switch).lower(), set()).add(seat)
    with _lock:
        _seats_of.update(found)


def _blocks(data):
    """[(block, hall id, {seat: row number})] for the placed seat blocks."""
    ids = {h['id'] for h in halls.halls(data)}
    out = []
    for b in data.get('seat_blocks') or []:
        if b.get('x') is None:
            continue
        rows = {seat: r + 1 for r, row in enumerate(block_rows(b)) for seat in row}
        out.append((b, halls.hall_of(b, data, ids), rows))
    return out


def _nearest(dev, blocks, hall_id):
    from .blueprints.screen import PLAN_H, PLAN_W
    tall = PLAN_H / PLAN_W
    same = [b for b in blocks if b[1] == hall_id]
    if not same or dev.get('x') is None:
        return None
    return min(same, key=lambda b: math.hypot(float(b[0]['x']) - dev['x'], (float(b[0]['y']) - dev['y']) * tall))


def _rows_text(rows):
    rows = sorted(rows)
    if not rows:
        return ''
    runs, start, prev = [], rows[0], rows[0]
    for r in [*rows[1:], None]:
        if r is not None and r == prev + 1:
            prev = r
            continue
        runs.append(f'{start}' if start == prev else f'{start}-{prev}')
        if r is not None:
            start = prev = r
    return ', '.join(runs)


def affected(data, down, show_names=False):
    """The areas the down switches hit: [{hall, block, rows, seats, switches?}], biggest first."""
    all_halls = {h['id']: h['name'] for h in halls.halls(data)}
    default = halls.default_id(data)
    blocks = _blocks(data)
    areas = {}
    for dev in down:
        hall_id = dev.get('hall_id') or default
        with _lock:
            seats = set(_seats_of.get(str(dev.get('name') or '').lower()) or ())
        hit = []
        for block, block_hall, rows in blocks:
            mine = seats & set(rows)
            if mine:
                hit.append((block, block_hall, {rows[s] for s in mine}, len(mine)))
        if not hit:
            near = _nearest(dev, blocks, hall_id)
            if near:
                hit.append((near[0], near[1], set(), None))
            else:
                hit.append((None, hall_id, set(), None))
        for block, block_hall, rows, count in hit:
            key = (block_hall, block['id'] if block else None)
            area = areas.setdefault(key, {'hall': all_halls.get(block_hall, ''),
                                          'block': (block or {}).get('name') or '',
                                          'rows': set(), 'seats': 0, 'switches': []})
            area['rows'] |= rows
            area['seats'] += count or 0
            area['switches'].append(dev.get('name') or '')
    out = []
    for area in areas.values():
        row = {'hall': area['hall'] if len(all_halls) > 1 else '', 'block': area['block'],
               'rows': _rows_text(area['rows']), 'seats': area['seats'] or None}
        if show_names:
            row['switches'] = sorted(set(area['switches']))
        out.append(row)
    return sorted(out, key=lambda a: (-(a['seats'] or 0), a['hall'], a['block']))


def current(data, statuses, monitoring_up, show_names=False, now=None):
    """The page: state, why, areas and updates. ``statuses`` is the monitor's {id: {'status'}}."""
    now = time.time() if now is None else now
    stored = _stored(data)
    placed = [d for d in inventory.devices(data) if d.get('x') is not None]
    down = [d for d in placed if (statuses.get(d['id']) or {}).get('status') == 'offline']
    if not monitoring_up:
        auto = 'unknown'
    elif not down:
        auto = 'operational'
    elif any(d.get('role') in CORE_ROLES for d in down) or len(down) * 2 >= len(placed):
        auto = 'outage'
    else:
        auto = 'degraded'
    override = stored['override']
    planned = sorted((m for m in stored['planned'] if (m.get('end') or 0) > now), key=lambda m: m['start'])
    running = next((m for m in planned if m['start'] <= now), None)
    since = [s.get('since') for s in statuses.values() if s.get('status') == 'offline' and s.get('since')]
    # Back from offline in the last half hour (issue #394): attendees who saw the outage see it is over.
    back = [d for d in placed if (statuses.get(d['id']) or {}).get('status') == 'online'
            and statuses[d['id']].get('previous') == 'offline'
            and (statuses[d['id']].get('since') or 0) >= now - RECOVERED_FOR]
    return {
        'state': override['state'] if override else 'maintenance' if running else auto,
        'auto_state': auto,
        'override': override,
        'since': min(since) if since and down else None,
        'areas': affected(data, down, show_names) if down else [],
        'updates': [{k: u.get(k) for k in ('id', 'at', 'text', 'state', 'area')} for u in stored['updates']],
        'recovered': affected(data, back, show_names) if back and monitoring_up else [],
        'recovered_at': max(statuses[d['id']]['since'] for d in back) if back and monitoring_up else None,
        'planned': [{k: m.get(k) for k in ('id', 'start', 'end', 'text', 'area')} for m in planned],
        'maintenance_now': {k: running.get(k) for k in ('id', 'start', 'end', 'text', 'area')} if running else None,
        'checked_at': now,
    }


def atom_feed(updates, base_url, title, state_names, now=None):
    """The crew's updates as an Atom feed, so attendees and the event website can follow them.

    Same fields as /status.json (time, area, state, text): never who posted.
    """
    base = base_url.rstrip('/')
    # A tag: URI names a domain, so no port.
    host = base.split('://', 1)[-1].split('/', 1)[0].rsplit(':', 1)[0] or 'floorbit'

    def stamp(at):
        return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(at))

    # A feed with no entries still needs <updated>: the newest update, else now.
    newest = max((u.get('at') or 0 for u in updates), default=0) or (now or time.time())
    out = ['<?xml version="1.0" encoding="utf-8"?>',
           '<feed xmlns="http://www.w3.org/2005/Atom">',
           f'<id>tag:{_x(host)},2026:floorbit-status</id>',
           f'<title>{_x(title)}</title>',
           f'<link rel="alternate" type="text/html" href="{_x(base)}/status"/>',
           f'<link rel="self" type="application/atom+xml" href="{_x(base)}/status.atom"/>',
           f'<updated>{stamp(newest)}</updated>',
           '<author><name>Floorbit</name></author>']
    for u in updates:
        label = state_names.get(u.get('state')) if u.get('state') else None
        head = ' · '.join(p for p in (label, u.get('area')) if p)
        text = u.get('text') or ''
        line = text if len(text) <= 80 else text[:79].rstrip() + '…'
        out += ['<entry>',
                f'<id>tag:{_x(host)},2026:floorbit-status:{_x(str(u.get("id")))}</id>',
                f'<title>{_x((head + ": " if head else "") + line)}</title>',
                f'<link rel="alternate" type="text/html" href="{_x(base)}/status"/>',
                f'<updated>{stamp(u.get("at") or newest)}</updated>',
                f'<content type="text">{_x(text)}</content>',
                '</entry>']
    out.append('</feed>')
    return '\n'.join(out) + '\n'
