"""The floor plan's seats for the React view (issue #55): one state per seat, and one seat's details.

Every seat gets a state and a few flags, so the page can draw it the same way everywhere:

- ``state``: ``online`` (its switch port was up in the latest read), ``offline`` (its port is known
  and down), ``unknown`` (no recent read, or Floorbit doesn't know its port yet);
- ``checked_in``: the player checked in at the seat (with check-in on);
- ``taken``: the seat mapping has a player there;
- ``problems``: open incidents plus current port trouble (needs attention) on the seat;
- ``match``: the match zone the seat is in, if any.

No nicks, IPs or MACs here: :func:`details` adds those only for accounts with ``seats.view``.
"""
import time

from flask import current_app

from integrations import checkin, config, seat_sources

from . import halls, incidents, inventory, tournament
from .blueprints.screen import CELL, PLAN_H, PLAN_W, plan
from .store import load_data


def _ext(name):
    return current_app.extensions.get(name)


def _fresh_online(now):
    """Online seats from the latest port read, or None when the read is too old to trust."""
    from .attention import AttentionWatch
    stats = _ext('floorbit_stats')
    if stats is None:
        return None, None
    seats = stats.seats()
    last = seats.get('last_poll')
    if not last or now - last > 3 * AttentionWatch.interval():
        return None, last
    return dict(seats.get('seats') or {}), last


def _port_of_seat():
    """{seat: (switch name, port)} from the port watch's last read (port descriptions name seats)."""
    watch = _ext('floorbit_attention')
    out = {}
    for (switch, port), seat in (getattr(watch, 'port_seats', None) or {}).items():
        out.setdefault(seat, (switch, port))
    return out


def _problems():
    """{seat: count} of open incidents and port trouble from the needs-attention list.

    "Online without a check-in" doesn't count: the missing check-in mark already says so, and at a
    big event it would put a "!" on half the hall.
    """
    out = {}
    for i in incidents.list_all():
        if i.get('status') != 'fixed' and i.get('seat'):
            out[i['seat']] = out.get(i['seat'], 0) + 1
    watch = _ext('floorbit_attention')
    for item in (watch.snapshot()['items'] if watch else []):
        if item.get('seat') and item.get('kind') != 'checkin':
            out[item['seat']] = out.get(item['seat'], 0) + 1
    return out


def _checked_in():
    if not config.get_bool('CHECKIN_ENABLED', False):
        return None
    return set(checkin.load_all())


def _taken():
    rows = seat_sources.load() or {}
    return {s for s, v in rows.items() if any((v or {}).get(k) for k in ('username', 'ip_address'))}


def _switches(data, hall_id, box):
    monitor = (_ext('lal_integrations') or {}).get('monitor')
    statuses = getattr(monitor, 'statuses', None) or {}
    ids = {h['id'] for h in halls.halls(data)}
    out = []
    for dev in inventory.devices(data):
        if dev.get('x') is None or dev.get('y') is None or halls.hall_of(dev, data, ids) != hall_id:
            continue
        status = (statuses.get(dev['id']) or {}).get('status') or 'unknown'
        out.append({'id': dev['id'], 'name': dev.get('name') or '', 'status': status,
                    'x': float(dev['x']) / 100 * PLAN_W, 'y': float(dev['y']) / 100 * PLAN_H})
    return out


def view(hall_id=None, now=None):
    now = time.time() if now is None else now
    data = load_data()
    all_halls = halls.halls(data)
    hall = halls.find(data, hall_id or '') or all_halls[0]
    drawing, _ = plan(data, hall_id=hall['id'])
    online, last = _fresh_online(now)
    ports = _port_of_seat()
    problems = _problems()
    checked = _checked_in()
    taken = _taken()
    match = tournament.match_seats(data)
    seats, blocks = {}, []
    for shape in (drawing or {}).get('shapes', []):
        counts = {'seats': 0, 'online': 0, 'problems': 0}
        for cell in shape['cells']:
            s = cell['seat']
            if online is None:
                state = 'unknown'
            elif s in online:
                state = 'online'
            else:
                state = 'offline' if s in ports else 'unknown'
            row = {'state': state}
            if checked is not None and s in checked:
                row['checked_in'] = True
            if s in taken:
                row['taken'] = True
            if problems.get(s):
                row['problems'] = problems[s]
            if s in match:
                row['match'] = match[s]
            if online and s in online:
                row['bps'] = int(online[s] or 0)
            seats[s] = row
            counts['seats'] += 1
            counts['online'] += state == 'online'
            counts['problems'] += bool(problems.get(s))
        blocks.append({'name': shape['name'], **counts})
    bg = hall.get('background')
    return {
        'halls': [{'id': h['id'], 'name': h['name']} for h in all_halls],
        'hall': hall['id'],
        'drawing': drawing,
        'size': {'w': PLAN_W, 'h': PLAN_H, 'cell': CELL},
        'background': f"/api/halls/{hall['id']}/background?v={bg['version']}" if bg else None,
        'switches': _switches(data, hall['id'], drawing and drawing['box']),
        'seats': seats,
        'blocks': blocks,
        'monitoring': online is not None,
        'checkin': checked is not None,
        'last_read': last,
    }


def details(seat, people):
    """One seat for the inspector. ``people``: may this account see nicks, IPs and MACs?"""
    data = load_data()
    seat = str(seat or '').upper()
    if seat not in incidents.seat_numbers(data):
        return None
    now = time.time()
    online, last = _fresh_online(now)
    port = _port_of_seat().get(seat)
    open_items = [{'id': i['id'], 'title': i['title'], 'status': i['status'], 'created_at': i['created_at']}
                  for i in incidents.list_all() if i.get('seat') == seat and i.get('status') != 'fixed']
    watch = _ext('floorbit_attention')
    attention = [{'kind': a['kind'], 'title': a['title'], 'since': a['since']}
                 for a in (watch.snapshot()['items'] if watch else []) if a.get('seat') == seat]
    checked = _checked_in()
    out = {
        'seat': seat,
        'block': seat.rsplit('-', 1)[0] if '-' in seat else '',
        'state': 'unknown' if online is None else 'online' if seat in online else 'offline' if port else 'unknown',
        'bps': int(online[seat] or 0) if online and seat in online else None,
        'switch': port[0] if port else None,
        'port': port[1] if port else None,
        'incidents': open_items,
        'attention': attention,
        'match': tournament.zone_of(seat, data),
        'checked_in': None if checked is None else seat in checked,
        'last_read': last,
        'people': bool(people),
    }
    if people:
        row = (seat_sources.load() or {}).get(seat) or {}
        out['nick'] = row.get('username') or None
        out['ip'] = row.get('ip_address') or None
        out['mac'] = row.get('mac_address') or row.get('mac') or None
    return out
