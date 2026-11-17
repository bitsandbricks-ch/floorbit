"""Cables drawn on the floor plan: LAN and fiber from switch ports to seats, uplinks between
switches, and power from distribution boards to seat blocks and switches. See docs/cables.md.

The cables themselves live where they always did: seat cables in ``cables`` (floorbit/cables.py),
uplinks in ``links`` (floorbit/links.py), power feeds on the circuits (floorbit/power.py). This
module only works out where to draw them and keeps what the crew changed about the drawing, in
data.json under ``cable_routes``::

    {"lan:sw-a-01|gi1/0/3": {"points": [[41.5, 20], [41.5, 33]], "corners": "round"}}

A cable is drawn from one end to the other through its bend points. Without points of its own it is
routed automatically: along the side of its seat block and into each row, so the cables of one
block run together. Points the crew dragged pin the route: it keeps them when the seat behind a
port changes. An entry without points (``points: null``) marks a cable drawn with the Cable tool,
which shows even when automatic cabling is off.

Automatic cabling (Settings > Cabling, ``CABLE_AUTO``, on by default) draws every seat whose switch
port is known: from the cables typed in or imported, and from the port descriptions the port watch
read. Venues that patch through panels can turn it off and draw the cables they want; a cable that
names a patch panel placed on the plan runs through the panel.

Patch panels are kept under ``patch_panels``: ``{"name", "x", "y", "hall_id", "ports"}``. ``ports``
is how many the panel has (1 to 96, 24 unless said); a cable's panel port is then one of 1 to that,
and one cable per panel port (floorbit/cables.py checks).
"""
import math
import re
import time

from . import halls, inventory, links, power, seat_gaps
from .seat_names import block_rows
from .store import load_data, save_data

KEY = 'cable_routes'
PANELS_KEY = 'patch_panels'
CORNERS = ('square', 'round')
MAX_POINTS = 50
MAX_ROUTES = 20000
MAX_PANELS = 500
PANEL_PORTS = 24                        # a new panel's ports unless said
MAX_PANEL_PORTS = 96
PITCH_X, PITCH_Y = 2.0, 3.2           # one seat in % of the plan (16:10, 50 seats across)
TRUNK = 1.0                            # how far beside a block its cables run, in seats
KEY_RE = re.compile(r'^(lan|link|power):[^\s]{1,200}$')
PANEL_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9 ._/#-]{0,39}$')


def _lock():
    # The editor's own lock: seat blocks, marks and these are saved into the same data.json.
    from .blueprints.inventory import data_lock
    return data_lock


class RouteError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def _canon(port):
    from .syslog import canonical_port  # syslog imports the seat data: late
    return canonical_port(port)


def lan_key(switch, port):
    return f'lan:{str(switch).lower()}|{_canon(port)}'


# ── Where things are ───────────────────────────────────────────────────────────
def _turn(dx, dy, rotation):
    """A point relative to a block's centre, turned like the block (clockwise, y down)."""
    a = math.radians(rotation)
    return dx * math.cos(a) - dy * math.sin(a), dx * math.sin(a) + dy * math.cos(a)


def geometry(data, hall_id):
    """Seat centres ``{seat: (x, y)}`` and block boxes ``{block id: {l, t, r, b, cx, cy, sideways}}``
    of one hall, in % of the plan. Works in seat units so a turned block keeps its shape."""
    ids = {h['id'] for h in halls.halls(data)}
    seats, boxes = {}, {}
    for block in data.get('seat_blocks') or []:
        if halls.hall_of(block, data, ids) != hall_id or block.get('x') is None:
            continue
        rows = block_rows(block)
        if not rows:
            continue
        xs, width, ys, height = seat_gaps.layout(block, len(rows[0]), len(rows))
        rotation = int(block.get('rotation') or 0) % 360
        cx, cy = float(block['x']), float(block['y'])
        corners = []
        for dx, dy in ((-width / 2, -height / 2), (width / 2, -height / 2), (width / 2, height / 2),
                       (-width / 2, height / 2)):
            tx, ty = _turn(dx, dy, rotation)
            corners.append((cx + tx * PITCH_X, cy + ty * PITCH_Y))
        for r, row in enumerate(rows):
            for c, seat in enumerate(row):
                tx, ty = _turn(xs[c] + 0.5 - width / 2, ys[r] + 0.5 - height / 2, rotation)
                seats.setdefault(seat, (round(cx + tx * PITCH_X, 3), round(cy + ty * PITCH_Y, 3), block['id']))
        boxes[block['id']] = {'l': min(p[0] for p in corners), 'r': max(p[0] for p in corners),
                              't': min(p[1] for p in corners), 'b': max(p[1] for p in corners),
                              'cx': cx, 'cy': cy, 'sideways': round(rotation / 90) % 2 == 1}
    return seats, boxes


def _switches(data, hall_id):
    ids = {h['id'] for h in halls.halls(data)}
    out = {}
    for dev in inventory.devices(data):
        if dev.get('x') is None or dev.get('y') is None or halls.hall_of(dev, data, ids) != hall_id:
            continue
        point = (float(dev['x']), float(dev['y']))
        out[str(dev['name']).lower()] = (point, dev)
        out[dev['id']] = (point, dev)
    return out


def panels(data, hall_id=None):
    rows = [p for p in data.get(PANELS_KEY) or [] if isinstance(p, dict) and p.get('name')]
    if hall_id is None:
        return rows
    ids = {h['id'] for h in halls.halls(data)}
    return [p for p in rows if halls.hall_of(p, data, ids) == hall_id]


# ── Automatic routes ───────────────────────────────────────────────────────────
def _elbow(a, b):
    """Across, then up or down: one bend."""
    return [] if a[0] == b[0] or a[1] == b[1] else [(b[0], a[1])]


def _to_seat(start, seat, box):
    """From a switch (or panel) to a seat: to the side of the seat's block that faces the start,
    along it, then into the seat's row. The cables of one block share that run."""
    if box is None:
        return _elbow(start, seat)
    sx, sy = start
    if box['sideways'] or box['l'] <= sx <= box['r']:
        # Above or below the block (or its rows run up and down): the run is along the top or bottom.
        y = box['t'] - TRUNK * PITCH_Y / 2 if sy < box['cy'] else box['b'] + TRUNK * PITCH_Y / 2
        return [(sx, y), (seat[0], y)]
    x = box['l'] - TRUNK * PITCH_X / 2 if sx < box['cx'] else box['r'] + TRUNK * PITCH_X / 2
    return [(x, sy), (x, seat[1])]


def _tidy(points):
    """Drop repeated points and bends that are not bends (three in a line)."""
    out = []
    for p in points:
        p = (round(p[0], 2), round(p[1], 2))
        if out and out[-1] == p:
            continue
        if len(out) >= 2:
            (ax, ay), (bx, by) = out[-2], out[-1]
            if (ax == bx == p[0]) or (ay == by == p[1]):
                out[-1] = p
                continue
        out.append(p)
    return out


# ── What is drawn ──────────────────────────────────────────────────────────────
def auto_on():
    from flask import current_app, has_app_context
    if has_app_context() and current_app.extensions.get('floorbit_settings') is not None:
        return bool(current_app.extensions['floorbit_settings'].get('cabling.auto'))
    from integrations import config
    return config.get_bool('CABLE_AUTO', True)


def _live_port_seats():
    """(switch name, port) -> seat from the port watch's last read (port descriptions)."""
    from flask import current_app, has_app_context
    if not has_app_context():
        return {}
    watch = current_app.extensions.get('floorbit_attention')
    return dict(getattr(watch, 'port_seats', None) or {})


def _speed_of(media, speed):
    return {'media': media or '', 'speed': speed}


def _drawn(key, kind, a, b, via, auto_points, routes, **extra):
    entry = routes.get(key)
    manual = bool(entry and entry.get('points'))
    bends = [tuple(p) for p in entry['points']] if manual else auto_points
    corners = (entry or {}).get('corners') or 'square'
    path = _tidy([a, *bends, b])
    return {'key': key, 'kind': kind, 'layer': 'electrical' if kind == 'power' else 'network',
            'points': [list(p) for p in path], 'manual': manual, 'drawn': entry is not None,
            'corners': corners, 'via': via, **extra}


def plan(data=None, hall_id=None, live=None, auto=None):
    """Every cable to draw in one hall: ``{"cables": [...], "panels": [...], "auto": bool}``.

    Each cable has ``points`` (both ends and the bends between, in % of the plan), ``manual`` (the
    crew placed the bends), ``layer`` (network or electrical) and what it is (``ref``)."""
    data = load_data() if data is None else data
    hall_id = hall_id or halls.default_id(data)
    auto = auto_on() if auto is None else auto
    live = _live_port_seats() if live is None else live
    routes = data.get(KEY) if isinstance(data.get(KEY), dict) else {}
    seats, boxes = geometry(data, hall_id)
    switches = _switches(data, hall_id)
    placed_panels = {p['name'].lower(): p for p in panels(data, hall_id)
                     if p.get('x') is not None and p.get('y') is not None}
    out = []

    # Seat cables: the typed-in and imported ones, then (automatic cabling) the ports the watch read.
    seen = set()
    from .cables import all_cables
    from .links import MEDIA
    rows = [(c['switch'], c['port'], (c.get('seat') or '').upper(), c) for c in all_cables(data) if c.get('seat')]
    if auto:
        rows += [(sw, port, str(seat).upper(), None) for (sw, port), seat in live.items()]
    for switch, port, seat, cable in rows:
        key = lan_key(switch, port)
        if key in seen:
            continue
        seen.add(key)
        if not auto and key not in routes:
            continue
        sw, at = switches.get(str(switch).lower()), seats.get(seat)
        if sw is None or at is None:
            continue
        start = sw[0]
        via = None
        panel = placed_panels.get(str((cable or {}).get('panel') or '').lower())
        bends = []
        if panel:
            via = panel['name']
            p = (float(panel['x']), float(panel['y']))
            bends = [*_elbow(start, p), p]
            start = p
        bends += _to_seat(start, at[:2], boxes.get(at[2]))
        out.append(_drawn(key, 'lan', sw[0], at[:2], via, bends, routes, label=(cable or {}).get('label') or '',
                          ref={'cable': (cable or {}).get('id'), 'source': (cable or {}).get('source') or 'watch',
                               'switch': sw[1]['name'], 'port': port, 'seat': seat},
                          **_speed_of(MEDIA.get((cable or {}).get('type')), (cable or {}).get('speed'))))

    # Uplinks between switches on this plan.
    for link in links.all_links(data):
        a, b = switches.get(link['a'].lower()), switches.get(link['b'].lower())
        if a is None or b is None:
            continue
        out.append(_drawn(f"link:{link['id']}", 'uplink', a[0], b[0], None, _elbow(a[0], b[0]), routes,
                          label=f"{link['a']} {link['a_port']} to {link['b']} {link['b_port']}",
                          ref={'link': link['id']}, **_speed_of(MEDIA.get(link.get('type')), link.get('speed'))))

    # Power: each circuit from its board to the blocks and switches it feeds.
    boards, circuits = power._stored(data)
    by_board = {b['id']: b for b in boards if b.get('x') is not None and b.get('y') is not None}
    for c in circuits:
        board = by_board.get(c.get('board'))
        if board is None:
            continue
        start = (float(board['x']), float(board['y']))
        for feed in c.get('blocks') or []:
            box = boxes.get(feed.get('block'))
            if box is None:
                continue
            end = (min(max(start[0], box['l']), box['r']), min(max(start[1], box['t']), box['b']))
            out.append(_drawn(f"power:{c['id']}:block:{feed['block']}", 'power', start, end, None,
                              _elbow(start, end), routes, label=c.get('name') or '',
                              ref={'circuit': c['id'], 'block': feed['block']}, media='power', speed=None))
        for sw_id in c.get('switches') or []:
            sw = switches.get(sw_id)
            if sw is None:
                continue
            out.append(_drawn(f"power:{c['id']}:switch:{sw_id}", 'power', start, sw[0], None,
                              _elbow(start, sw[0]), routes, label=c.get('name') or '',
                              ref={'circuit': c['id'], 'switch': sw_id}, media='power', speed=None))
    return {'cables': out, 'auto': auto,
            'panels': [{'name': p['name'], 'x': p.get('x'), 'y': p.get('y'), 'ports': p.get('ports') or PANEL_PORTS}
                       for p in panels(data, hall_id)]}


# ── Changing the drawing ───────────────────────────────────────────────────────
def _clean_points(raw):
    if raw is None:
        return None
    if not isinstance(raw, list) or len(raw) > MAX_POINTS:
        raise RouteError(f'A cable has at most {MAX_POINTS} bends.')
    out = []
    for p in raw:
        try:
            x, y = (round(float(v), 2) for v in p)
        except (TypeError, ValueError):
            raise RouteError('A bend is a point on the plan: [x, y] in percent.') from None
        if not (-1000 <= x <= 1000 and -1000 <= y <= 1000) or math.isnan(x) or math.isnan(y):
            raise RouteError('A bend is a point on the plan: [x, y] in percent.')
        out.append([x, y])
    return out or None


def set_routes(changes, by=None):
    """``{key: {"points": [...] | null, "corners": "square" | "round"} | null}``: null forgets the
    cable's drawing (back to automatic, and not drawn when automatic cabling is off)."""
    if not isinstance(changes, dict) or not changes:
        raise RouteError('Say which cables to change.')
    cleaned = {}
    for key, value in list(changes.items())[:2000]:
        if not isinstance(key, str) or not KEY_RE.match(key):
            raise RouteError('That is not a cable on the plan.')
        if key.startswith('lan:') and '|' in key:
            key = lan_key(*key[4:].split('|', 1))   # Gi1/0/1 and GigabitEthernet1/0/1 are one port
        if value is None:
            cleaned[key] = None
            continue
        if not isinstance(value, dict):
            raise RouteError('That is not a cable on the plan.')
        corners = value.get('corners') or 'square'
        if corners not in CORNERS:
            raise RouteError('Corners are square or round.')
        cleaned[key] = {'points': _clean_points(value.get('points')), 'corners': corners}
    with _lock():
        data = load_data()
        routes = data.get(KEY) if isinstance(data.get(KEY), dict) else {}
        for key, value in cleaned.items():
            if value is None:
                routes.pop(key, None)
            else:
                routes[key] = {**value, 'by': by, 'at': time.time()}
        if len(routes) > MAX_ROUTES:
            raise RouteError(f'Floorbit keeps the drawing of at most {MAX_ROUTES} cables.')
        data[KEY] = routes
        save_data(data)
    return {k: routes.get(k) for k in cleaned}


def _panel_ports(value):
    try:
        n = int(value)
    except (TypeError, ValueError):
        n = 0
    if not 1 <= n <= MAX_PANEL_PORTS:
        raise RouteError(f'A patch panel has 1 to {MAX_PANEL_PORTS} ports.')
    return n


def find_panel(data, name):
    name = str(name or '').strip().lower()
    rows = [p for p in data.get(PANELS_KEY) or [] if isinstance(p, dict)]
    return next((p for p in rows if str(p.get('name', '')).lower() == name), None)


def place_panel(name, body, create=False):
    """Put a patch panel on the plan or change it: ``x``, ``y``, ``hall_id`` and ``ports``. A panel
    already there keeps what the body leaves out; ``create`` refuses one that exists (409)."""
    name = ' '.join(str(name or '').split())
    if not PANEL_RE.match(name):
        raise RouteError('A patch panel name is up to 40 letters, digits, spaces, . _ / # or -.')
    with _lock():
        data = load_data()
        rows = [p for p in data.get(PANELS_KEY) or [] if isinstance(p, dict)]
        panel = next((p for p in rows if str(p.get('name', '')).lower() == name.lower()), None)
        if panel is not None and create:
            raise RouteError(f'There is a patch panel called {panel["name"]} already.', 409)
        has_xy = body.get('x') is not None or body.get('y') is not None
        if panel is None or panel.get('x') is None or has_xy:
            try:
                x, y = round(float(body.get('x')), 2), round(float(body.get('y')), 2)
            except (TypeError, ValueError):
                raise RouteError('A patch panel position is a point on the plan in percent.') from None
        else:
            x, y = panel['x'], panel['y']
        hall = halls.check_id(data, body['hall_id']) if body.get('hall_id') else (
            panel.get('hall_id') if panel and panel.get('hall_id') else halls.check_id(data, None))
        ports = _panel_ports(body['ports']) if body.get('ports') is not None else (
            (panel or {}).get('ports') or PANEL_PORTS)
        if panel is not None and body.get('ports') is not None:
            from .cables import all_cables
            mine = [c for c in all_cables(data) if str(c.get('panel') or '').lower() == name.lower()]
            top = max((int(c['panel_port']) for c in mine if str(c.get('panel_port') or '').isdigit()), default=0)
            if top > ports:
                raise RouteError(f'Port {top} of {panel["name"]} has a cable: the panel needs at least {top} ports.',
                                 409)
        if panel is None:
            if len(rows) >= MAX_PANELS:
                raise RouteError(f'Floorbit keeps at most {MAX_PANELS} patch panels on the plan.')
            panel = {'name': name}
            rows.append(panel)
        panel.update(x=x, y=y, hall_id=hall, ports=ports)
        data[PANELS_KEY] = rows
        save_data(data)
    return {**panel, 'id': panel['name']}


def panel_ports(data, name):
    """The ports of one patch panel (1 to its count), with the seat or cable on each one."""
    from .cables import all_cables
    panel = find_panel(data, name)
    held = {}
    for c in all_cables(data):
        if str(c.get('panel') or '').lower() == str(name).strip().lower() and c.get('panel_port'):
            held[str(c['panel_port'])] = c.get('seat') or c.get('label')
    count = int((panel or {}).get('ports') or 0)
    names = [str(n) for n in range(1, count + 1)]
    names += sorted((p for p in held if p not in names), key=lambda p: (len(p), p))
    return [{'value': n, 'label': n, 'used': held.get(n)} for n in names]


def remove_panel(name):
    with _lock():
        data = load_data()
        rows = [p for p in data.get(PANELS_KEY) or [] if isinstance(p, dict)]
        kept = [p for p in rows if str(p.get('name', '')).lower() != str(name).lower()]
        if len(kept) == len(rows):
            return False
        data[PANELS_KEY] = kept
        save_data(data)
    return True
