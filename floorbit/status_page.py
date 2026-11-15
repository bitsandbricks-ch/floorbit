"""Public network status page (issue #101). See docs/status-page.md.

What attendees see at ``/status`` during an outage: the overall state, which areas are hit (halls,
seat blocks and their rows), and updates the crew posts. Never switch names or IPs, unless an admin
turns on ``public.status_switch_names``.

The state works itself out from the status monitor: every placed switch up is ``operational``;
some down is ``degraded``; a router or firewall down, or half the switches or more, is ``outage``;
the monitoring source unreachable is ``unknown`` (better than claiming all is fine). The crew can set
the state by hand (for example ``maintenance``) until they clear it.

Which seats a switch serves comes from the port reads (a port's description names its seat, see
floorbit/attention.py), remembered while the switch is down. A switch with no seats known counts
for the seat block nearest to it on the floor plan.
"""
import math
import threading
import time
import uuid

from . import halls, inventory
from .power import block_rows
from .store import load_data, save_data

KEY = 'status_page'
STATES = ('operational', 'degraded', 'outage', 'maintenance', 'unknown')
SET_BY_HAND = ('operational', 'degraded', 'outage', 'maintenance')
CORE_ROLES = ('router', 'firewall')
MAX_UPDATES = 50
MAX_TEXT = 500
_lock = threading.Lock()
_seats_of = {}   # switch name (lower case) -> seats it served when last read


class StatusError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def _stored(data):
    raw = data.get(KEY)
    raw = raw if isinstance(raw, dict) else {}
    return {'override': raw.get('override'), 'updates': [u for u in raw.get('updates') or [] if isinstance(u, dict)]}


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


def current(data, statuses, monitoring_up, show_names=False):
    """The page: state, why, areas and updates. ``statuses`` is the monitor's {id: {'status'}}."""
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
    since = [s.get('since') for s in statuses.values() if s.get('status') == 'offline' and s.get('since')]
    return {
        'state': override['state'] if override else auto,
        'auto_state': auto,
        'override': override,
        'since': min(since) if since and down else None,
        'areas': affected(data, down, show_names) if down else [],
        'updates': [{k: u.get(k) for k in ('id', 'at', 'text', 'state', 'area')} for u in stored['updates']],
        'checked_at': time.time(),
    }
