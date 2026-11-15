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

from . import halls, incidents, inventory, seat_notes, seat_search, speedtest, tournament
from .blueprints.screen import CELL, PLAN_H, PLAN_W, plan
from .store import load_data

RECENT = 15 * 60     # "changed lately" on the Seats view (issue #171)
HISTORY = 6 * 3600   # the inspector's link history (issue #167): long enough for "it keeps dropping"
SPEEDTESTS = 3       # the inspector's speed tests (issue #182)


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


def _switches_of(seat, data):
    """The inventory devices serving ``seat``: from the last port read, or what the status page
    remembered while a switch went down. Only a known link counts: better say nothing than blame the
    wrong switch."""
    from . import status_page
    short = lambda name: str(name or '').lower().split('.')[0]   # noqa: E731
    names = set()
    port = _port_of_seat().get(seat)
    if port:
        names.add(short(port[0]))
    with status_page._lock:
        names |= {short(sw) for sw, seats in status_page._seats_of.items() if seat in seats}
    if not names:
        return []
    return [d for d in inventory.devices(data if data is not None else load_data()) if short(d.get('name')) in names]


def outage_of(seat, data=None, statuses=None):
    """(switch name, down since) for the down switch serving ``seat``, or None (issues #384, #386)."""
    statuses = monitor_statuses() if statuses is None else statuses
    if not statuses:
        return None
    down = [(d.get('name'), (statuses.get(d['id']) or {}).get('since') or time.time())
            for d in _switches_of(seat, data) if (statuses.get(d['id']) or {}).get('status') == 'offline']
    return min(down, key=lambda x: x[1]) if down else None


def back_up(seat, after, data=None, statuses=None):
    """(switch name, up since) when the seat's switch came back from offline after ``after``, or None
    (issue #390): a report from during the outage may be fixed already."""
    statuses = monitor_statuses() if statuses is None else statuses
    if not statuses:
        return None
    for d in _switches_of(seat, data):
        st = statuses.get(d['id']) or {}
        if st.get('status') == 'online' and st.get('previous') == 'offline' and (st.get('since') or 0) > after:
            return d.get('name'), st['since']
    return None


def monitor_statuses():
    """The status monitor's {device id: status}, or None before its first poll."""
    monitor = (_ext('lal_integrations') or {}).get('monitor')
    if not monitor or not getattr(monitor, 'last_poll', None):
        return None
    return dict(getattr(monitor, 'statuses', None) or {})


def outage_since(seat, data=None):
    """Since when the switch serving ``seat`` is down, or None (issue #384). No names: for attendees."""
    found = outage_of(seat, data)
    return found[1] if found else None


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


def _state(seat, online, ports):
    if online is None:
        return 'unknown'
    if seat in online:
        return 'online'
    return 'offline' if seat in ports else 'unknown'


def _hall_counts(data, hall_id, online, ports, problems):
    """Totals for a hall that isn't on screen, for the hall picker (issue #196)."""
    drawing, _ = plan(data, hall_id=hall_id)
    seats = [c['seat'] for shape in (drawing or {}).get('shapes', []) for c in shape['cells']]
    return {'seats': len(seats), 'online': sum(_state(s, online, ports) == 'online' for s in seats),
            'problems': sum(bool(problems.get(s)) for s in seats)}


def _seat_halls(data):
    """{seat: hall id} over every hall's seat blocks."""
    hall_of = {}
    for hall in halls.halls(data):
        drawing, _ = plan(data, hall_id=hall['id'])
        for shape in (drawing or {}).get('shapes', []):
            for cell in shape['cells']:
                hall_of.setdefault(cell['seat'], hall['id'])
    return hall_of


def hall_for(seat=None, switch=None, data=None):
    """The hall a seat or a placed switch is in, for links that name only the seat (issue #206)."""
    data = load_data() if data is None else data
    if seat:
        return _seat_halls(data).get(seat)
    short = str(switch or '').lower().split('.')[0]
    if short:
        ids = {h['id'] for h in halls.halls(data)}
        dev = next((d for d in inventory.devices(data) if str(d.get('name') or '').lower().split('.')[0] == short
                    and d.get('x') is not None), None)
        return halls.hall_of(dev, data, ids) if dev else None
    return None


def view(hall_id=None, now=None, seat=None, switch=None):
    now = time.time() if now is None else now
    data = load_data()
    all_halls = halls.halls(data)
    if not hall_id and (seat or switch):
        hall_id = hall_for(seat, switch, data)
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
            state = _state(s, online, ports)
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
    here = {k: sum(b[k] for b in blocks) for k in ('seats', 'online', 'problems')}
    return {
        'halls': [{'id': h['id'], 'name': h['name'],
                   **(here if h['id'] == hall['id'] else _hall_counts(data, h['id'], online, ports, problems))}
                  for h in all_halls],
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
    ``crew``: may it read and write the seat's note and see its speed tests?"""
    data = load_data()
    seat = str(seat or '').upper()
    if seat not in incidents.seat_numbers(data):
        return None
    now = time.time()
    online, last = _fresh_online(now)
    port = _port_of_seat().get(seat)
    here = [i for i in incidents.list_all() if i.get('seat') == seat]
    open_items = [{'id': i['id'], 'title': i['title'], 'status': i['status'], 'created_at': i['created_at']}
                  for i in here if i.get('status') != 'fixed']
    # A seat that keeps breaking is a cable or port to swap (issue #330): say what was fixed before.
    fixed = sorted((i for i in here if i.get('status') == 'fixed'), key=lambda i: -(i.get('fixed_at') or 0))
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
        'fixed_before': {'count': len(fixed), 'last': {'title': fixed[0]['title'], 'fixed_at': fixed[0].get('fixed_at')}
                         if fixed else None},
        'attention': attention,
        'match': tournament.zone_of(seat, data),
        'checked_in': None if checked is None else seat in checked,
        'last_read': last,
        'people': bool(people),
        'crew': bool(crew),
    }
    if crew:
        out['note'] = seat_notes.get(seat, data)
        # The player's own tests from the help page (issue #182), newest first.
        out['speedtests'] = speedtest.results(seat, data)[:SPEEDTESTS]
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
        'id': (dev or {}).get('id'),
        'status': st.get('status') or 'unknown',
        'since': st.get('since'),
        'model': (dev or {}).get('model') or None,
        'seats': rows,
        'online': sum(1 for r in rows if r['state'] == 'online'),
    }


def _port_key(port):
    """Gi1/0/2 before Gi1/0/10."""
    return [int(p) if p.isdigit() else p for p in re.split(r'(\d+)', str(port))]


def find_player(query):
    """A player by nick, IP or MAC for the Seats page's search (issue #186), with the hall each seat
    is in so the page can switch to it. Names people: the route needs ``seats.view``."""
    hall_of = _seat_halls(load_data())
    found = seat_search.find(query)
    return {'query': found['query'], 'results': [
        {'seat': r['seat'], 'nick': r.get('username') or '', 'matched': r['matched'], 'hall': hall_of[r['seat']]}
        for r in found['results'] if r.get('seat') in hall_of]}
