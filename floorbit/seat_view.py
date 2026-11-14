"""The floor plan's seats for the React view (issue #55): one state per seat, and one seat's details.

Every seat gets a state and a few flags, so the page can draw it the same way everywhere:

- ``state``: ``online`` (its switch port was up in the latest read), ``offline`` (its port is known
  and down), ``unknown`` (no recent read, or Floorbit doesn't know its port yet);
- ``checked_in``: the player checked in at the seat (with check-in on);
- ``taken``: the seat mapping has a player there;
- ``problems``: open incidents plus current port trouble (needs attention) on the seat;
- ``match``: the match zone the seat is in, if any;
- ``note``: the crew left a note on the seat (its text only in :func:`details`, for the crew).

No nicks, IPs or MACs here: :func:`details` adds those only for accounts with ``seats.view``.
"""
import re
import time

from flask import current_app

from integrations import checkin, config, seat_sources

from . import halls, incidents, inventory, seat_notes, tournament
from .blueprints.screen import CELL, PLAN_H, PLAN_W, plan
from .store import load_data

RECENT = 15 * 60     # "changed lately" on the Seats view (issue #171)
HISTORY = 6 * 3600   # the inspector's link history (issue #167): long enough for "it keeps dropping"


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
    stats = _ext('floorbit_stats')
    changed = stats.changed_since(now - RECENT) if stats else {}
    notes = seat_notes.all_notes(data)
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
            if s in changed:
                row['changed'] = changed[s]
            if s in notes:
                row['note'] = True
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


def details(seat, people, crew=False):
    """One seat for the inspector. ``people``: may this account see nicks, IPs and MACs?
    ``crew``: may it read and write the seat's note?"""
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
        'crew': bool(crew),
    }
    if crew:
        out['note'] = seat_notes.get(seat, data)
    stats = _ext('floorbit_stats')
    if stats:
        out['history'] = {**stats.seat_history(seat, now - HISTORY), 'to': now}
    if people:
        row = (seat_sources.load() or {}).get(seat) or {}
        out['nick'] = row.get('username') or None
        out['ip'] = row.get('ip_address') or None
        out['mac'] = row.get('mac_address') or row.get('mac') or None
    return out


def block(name, now=None):
    """One seat block for the block panel (issue #174): its seats by state, the ones with problems,
    and the switches that serve it. States only, never who sits there."""
    now = time.time() if now is None else now
    data = load_data()
    for hall in halls.halls(data):
        drawing, _ = plan(data, hall_id=hall['id'])
        shape = next((s for s in (drawing or {}).get('shapes', []) if s['name'] == name), None)
        if shape:
            break
    else:
        return None
    seats = view(hall['id'], now=now)['seats']
    cells = [c['seat'] for c in shape['cells']]
    rows = {s: seats.get(s) or {'state': 'unknown'} for s in cells}
    counts = dict.fromkeys(('online', 'offline', 'unknown'), 0)
    for row in rows.values():
        counts[row['state']] += 1
    monitor = (_ext('lal_integrations') or {}).get('monitor')
    status = {str(st.get('name') or '').lower().split('.')[0]: st.get('status') or 'unknown'
              for st in (getattr(monitor, 'statuses', None) or {}).values()}
    ports = _port_of_seat()
    switches = {}
    for s in cells:
        if s not in ports:
            continue
        sw = switches.setdefault(ports[s][0], {'name': ports[s][0], 'seats': 0, 'online': 0,
                                               'status': status.get(ports[s][0].lower().split('.')[0], 'unknown')})
        sw['seats'] += 1
        sw['online'] += rows[s]['state'] == 'online'
    checked = [s for s, r in rows.items() if r.get('checked_in')]
    return {
        'name': name,
        'hall': hall['id'],
        'seats': len(cells),
        **counts,
        'checked_in': len(checked) if _checked_in() is not None else None,
        'bps': sum(int(r.get('bps') or 0) for r in rows.values()),
        'problems': [{'seat': s, 'state': r['state'], 'problems': r['problems']}
                     for s, r in rows.items() if r.get('problems')],
        'switches': sorted(switches.values(), key=lambda w: w['name']),
        'no_port': sum(1 for s in cells if s not in ports),
    }


def switch(name, now=None):
    """One switch for the switch panel (issue #176): its status and the seats it serves, port by
    port. States only, never who sits where."""
    now = time.time() if now is None else now
    short = str(name or '').lower().split('.')[0]
    data = load_data()
    dev = next((d for d in inventory.devices(data, include_hidden=True)
                if short and str(d.get('name') or '').lower().split('.')[0] == short), None)
    ports = [(seat, port) for seat, (sw, port) in _port_of_seat().items() if sw.lower().split('.')[0] == short]
    if dev is None and not ports:
        return None
    monitor = (_ext('lal_integrations') or {}).get('monitor')
    st = next((s for s in (getattr(monitor, 'statuses', None) or {}).values()
               if str(s.get('name') or '').lower().split('.')[0] == short), None) or {}
    seats = {}
    for hall in halls.halls(data):
        seats.update(view(hall['id'], now=now)['seats'])
    rows = [{'seat': seat, 'port': port, 'state': (seats.get(seat) or {}).get('state', 'unknown'),
             'problems': (seats.get(seat) or {}).get('problems', 0)} for seat, port in ports]
    rows.sort(key=lambda r: _port_key(r['port']))
    return {
        'name': (dev or {}).get('name') or name,
        'status': st.get('status') or 'unknown',
        'since': st.get('since'),
        'model': (dev or {}).get('model') or None,
        'seats': rows,
        'online': sum(1 for r in rows if r['state'] == 'online'),
    }


def _port_key(port):
    """Gi1/0/2 before Gi1/0/10."""
    return [int(p) if p.isdigit() else p for p in re.split(r'(\d+)', str(port))]
