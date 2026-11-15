"""Electrics (issue #45): distribution boards, the circuits they feed and the load on each, on the
floor plan. See docs/power.md.

Stored in data.json under ``power``::

    {"boards": [{"id": "b1", "name": "DB-1", "location": "Stage left", "x": 12.5, "y": 30}],
     "circuits": [{"id": "c1", "board": "b1", "name": "A row 1", "phase": "L1", "rating_a": 16,
                   "meter": "db1-1", "blocks": [{"block": "<seat block id>", "rows": [1]}],
                   "switches": ["<inventory id>"], "tripped": null, "reading": {...}}]}

A circuit feeds whole seat blocks or some of their rows (counted from the top as drawn, 1 first),
and switches. The load is a percentage of its rating, from the last reading: typed in by the
Electrics team, or from a plugin with ``uses: [power]`` whose ``power_readings()`` returns
``[{"meter": "db1-1", "amps": 12.4}]`` (or ``"watts"``) for smart PDUs and meters. A circuit at
``POWER_WARN`` % shows amber, at ``POWER_CRIT`` % red; crossing into red, or a reported trip, files
an incident for the Electrics team (``POWER_TEAM``) naming what the circuit feeds, and publishes
``power.alert``. ``POWER_ENABLED`` off hides the page and the layer for installs without it.

Nothing here is personal data: seat numbers and switch names only.
"""
import re
import threading
import time
import uuid

from integrations import config, events

from . import features
from .plugins import PluginError
from .store import load_data, save_data

KEY = 'power'
PHASES = ('L1', 'L2', 'L3', '3P')
STATES = ('ok', 'warn', 'crit', 'tripped', 'unknown')
MAX_BOARDS = 100
MAX_CIRCUITS = 500
MAX_RATING = 400          # amps; a LAN hall circuit is 10 to 63
METER_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9 ._:/-]{0,59}$')

_lock = threading.Lock()


class PowerError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def enabled():
    return config.get_bool('POWER_ENABLED', True)


def thresholds():
    warn = config.get_int('POWER_WARN', 80, minimum=10)
    return warn, max(warn + 1, config.get_int('POWER_CRIT', 95, minimum=11))


def _text(value, limit):
    return '' if value is None else ' '.join(str(value).split())[:limit]


def _stored(data):
    raw = data.get(KEY) if isinstance(data.get(KEY), dict) else {}
    return ([b for b in raw.get('boards') or [] if isinstance(b, dict)],
            [c for c in raw.get('circuits') or [] if isinstance(c, dict)])


def _save(data, boards, circuits):
    data[KEY] = {'boards': boards, 'circuits': circuits}
    save_data(data)


# ── What a circuit feeds ───────────────────────────────────────────────────────
def block_rows(block):
    """The seat numbers of each row of a seat block as drawn, top row first.

    The same numbering as the editor's ``blockSeatNumbers`` (static/js/editor/sidebar.js): the
    rotation and "reverse numbers" change which number sits where.
    """
    cols, rows = int(block.get('cols') or 0), int(block.get('rows') or 0)
    base = list(range(1, cols * rows + 1))
    rotation = int(block.get('rotation') or 0) % 360
    if rotation < 90:
        ordered = base
    elif rotation < 180:
        ordered = [n for r in range(rows) for n in reversed(base[r * cols:(r + 1) * cols])]
    elif rotation < 270:
        ordered = list(reversed(base))
    else:
        ordered = [n for r in reversed(range(rows)) for n in base[r * cols:(r + 1) * cols]]
    if block.get('reverse_numbers'):
        ordered = list(reversed(ordered))
    prefix = f"{str(block['name']).upper()}-" if block.get('name') else ''
    return [[f'{prefix}{n}' for n in ordered[r * cols:(r + 1) * cols]] for r in range(rows)]


def fed_by(circuit, data):
    """{'seats': [...], 'switches': [{id, name}]} that go dark when this circuit does."""
    blocks = {b.get('id'): b for b in data.get('seat_blocks') or []}
    seats = []
    for feed in circuit.get('blocks') or []:
        block = blocks.get(feed.get('block'))
        if not block:
            continue
        rows = block_rows(block)
        wanted = feed.get('rows') or range(1, len(rows) + 1)
        for r in wanted:
            if 1 <= r <= len(rows):
                seats += rows[r - 1]
    from . import inventory
    devices = {d['id']: d for d in inventory.devices(data, include_hidden=True)}
    switches = [{'id': sid, 'name': devices[sid]['name']} for sid in circuit.get('switches') or []
                if sid in devices]
    return {'seats': list(dict.fromkeys(seats)), 'switches': switches}


def _feed_label(feed, blocks):
    block = blocks.get(feed.get('block'))
    name = (block or {}).get('name') or '?'
    rows = feed.get('rows') or []
    return f"block {name}" + (f" row{'s' if len(rows) > 1 else ''} {', '.join(map(str, rows))}" if rows else '')


# ── Cleaning what the browser sends ───────────────────────────────────────────
def _clean_board(body, old=None):
    old = old or {}
    name = _text(body.get('name', old.get('name')), 40)
    if not name:
        raise PowerError('Give the board a name, like DB-1.')
    board = {'id': old.get('id') or uuid.uuid4().hex[:10], 'name': name,
             'location': _text(body.get('location', old.get('location')), 80)}
    for axis in ('x', 'y'):
        value = body.get(axis, old.get(axis))
        if value is None or value == '':
            board[axis] = None
            continue
        try:
            board[axis] = min(100.0, max(0.0, round(float(value), 2)))
        except (TypeError, ValueError):
            raise PowerError('A board position is a percentage of the floor plan.') from None
    return board


def _clean_circuit(body, data, boards, old=None):
    old = old or {}
    get = lambda k: body.get(k, old.get(k))  # noqa: E731
    name = _text(get('name'), 40)
    if not name:
        raise PowerError('Give the circuit a name, like "A row 1".')
    board = get('board')
    if board not in {b['id'] for b in boards}:
        raise PowerError('Pick the board this circuit comes from.')
    phase = get('phase') or 'L1'
    if phase not in PHASES:
        raise PowerError(f"Phase must be one of: {', '.join(PHASES)}.")
    try:
        rating = float(16 if get('rating_a') in (None, '') else get('rating_a'))
    except (TypeError, ValueError):
        raise PowerError('The fuse rating is a number of amps.') from None
    if not 1 <= rating <= MAX_RATING:
        raise PowerError(f'The fuse rating must be between 1 and {MAX_RATING} A.')
    meter = _text(get('meter'), 60)
    if meter and not METER_RE.match(meter):
        raise PowerError('The meter id has characters Floorbit does not accept.')
    blocks = {b.get('id'): b for b in data.get('seat_blocks') or []}
    feeds = []
    for feed in (get('blocks') or [])[:100]:
        if not isinstance(feed, dict) or feed.get('block') not in blocks:
            raise PowerError('One of the seat blocks is not on the floor plan any more.')
        total = int(blocks[feed['block']].get('rows') or 0)
        rows = sorted({int(r) for r in feed.get('rows') or [] if str(r).isdigit() and 1 <= int(r) <= total})
        feeds.append({'block': feed['block'], 'rows': rows})
    from . import inventory
    known = {d['id'] for d in inventory.devices(data, include_hidden=True)}
    switches = list(dict.fromkeys(s for s in (get('switches') or [])[:200] if s in known))
    return {'id': old.get('id') or uuid.uuid4().hex[:10], 'board': board, 'name': name, 'phase': phase,
            'rating_a': rating, 'meter': meter, 'blocks': feeds, 'switches': switches,
            'tripped': old.get('tripped'), 'reading': old.get('reading')}


# ── Boards and circuits ────────────────────────────────────────────────────────
def save_board(body, board_id=None):
    with _lock:
        data = load_data()
        boards, circuits = _stored(data)
        old = next((b for b in boards if b['id'] == board_id), None) if board_id else None
        if board_id and not old:
            raise PowerError('No such board.', 404)
        if not old and len(boards) >= MAX_BOARDS:
            raise PowerError(f'Floorbit keeps up to {MAX_BOARDS} boards.')
        board = _clean_board(body, old)
        boards = [board if b is old else b for b in boards] if old else [*boards, board]
        _save(data, boards, circuits)
        return board


def delete_board(board_id):
    with _lock:
        data = load_data()
        boards, circuits = _stored(data)
        board = next((b for b in boards if b['id'] == board_id), None)
        if not board:
            raise PowerError('No such board.', 404)
        if any(c['board'] == board_id for c in circuits):
            raise PowerError('Move or remove its circuits first.', 409)
        _save(data, [b for b in boards if b is not board], circuits)
        return board


def save_circuit(body, circuit_id=None):
    with _lock:
        data = load_data()
        boards, circuits = _stored(data)
        old = next((c for c in circuits if c['id'] == circuit_id), None) if circuit_id else None
        if circuit_id and not old:
            raise PowerError('No such circuit.', 404)
        if not old and len(circuits) >= MAX_CIRCUITS:
            raise PowerError(f'Floorbit keeps up to {MAX_CIRCUITS} circuits.')
        circuit = _clean_circuit(body, data, boards, old)
        circuits = [circuit if c is old else c for c in circuits] if old else [*circuits, circuit]
        _save(data, boards, circuits)
        return circuit


def delete_circuit(circuit_id):
    with _lock:
        data = load_data()
        boards, circuits = _stored(data)
        circuit = next((c for c in circuits if c['id'] == circuit_id), None)
        if not circuit:
            raise PowerError('No such circuit.', 404)
        _save(data, boards, [c for c in circuits if c is not circuit])
        return circuit


def _amps(raw):
    """Amps from a reading of amps or watts; None when it is neither."""
    for key, factor in (('amps', 1.0), ('watts', 1.0 / config.get_int('POWER_VOLTAGE', 230, minimum=100))):
        value = raw.get(key)
        if isinstance(value, bool) or value is None or value == '':
            continue
        try:
            amps = float(value) * factor
        except (TypeError, ValueError):
            return None
        return round(amps, 2) if 0 <= amps <= 10 * MAX_RATING else None
    return None


def set_reading(circuit_id, body, user):
    amps = _amps(body)
    if amps is None:
        raise PowerError('Type the load in amps (or watts).')
    with _lock:
        data = load_data()
        boards, circuits = _stored(data)
        circuit = next((c for c in circuits if c['id'] == circuit_id), None)
        if not circuit:
            raise PowerError('No such circuit.', 404)
        circuit['reading'] = {'amps': amps, 'at': time.time(), 'by': user, 'source': 'manual'}
        _save(data, boards, circuits)
        return circuit


def set_tripped(circuit_id, tripped, user):
    with _lock:
        data = load_data()
        boards, circuits = _stored(data)
        circuit = next((c for c in circuits if c['id'] == circuit_id), None)
        if not circuit:
            raise PowerError('No such circuit.', 404)
        circuit['tripped'] = {'by': user, 'at': time.time()} if tripped else None
        _save(data, boards, circuits)
        return circuit


# ── Load and state ─────────────────────────────────────────────────────────────
def state_of(circuit, reading):
    if circuit.get('tripped'):
        return 'tripped', None
    if not reading:
        return 'unknown', None
    pct = round(100 * reading['amps'] / circuit['rating_a'], 1)
    warn, crit = thresholds()
    return ('crit' if pct >= crit else 'warn' if pct >= warn else 'ok'), pct


class PowerWatch:
    """Readings from power plugins, polled in the background, and the alerts when a circuit
    turns red or trips."""

    def __init__(self, registry):
        self.registry = registry
        self._lock = threading.Lock()
        self._thread = None
        self._stop = threading.Event()
        self.reset()

    def reset(self):
        self.readings = {}        # meter id -> {amps, at, source, plugin}
        self.states = {}          # circuit id -> the state alerts are about
        self.baseline_done = False
        self.last_poll = None

    def start(self):
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, name='power-watch', daemon=True)
            self._thread.start()

    def stop(self):
        self._stop.set()

    @staticmethod
    def interval():
        return config.get_int('POWER_INTERVAL', 60, minimum=15)

    def _run(self):
        while not self._stop.is_set():
            if enabled() and features.on('power') and self.registry.feeders('power'):
                try:
                    self.poll_once()
                except Exception as exc:  # noqa: BLE001  # keep the thread alive no matter what
                    print(f'[power] poll failed: {exc}')
            self._stop.wait(self.interval())

    def poll_once(self):
        now = time.time()
        found = {}
        for spec in self.registry.feeders('power'):
            try:
                raw = self.registry.call(spec, 'power_readings')
            except PluginError:
                continue   # its meters keep their last reading, which ages on the page
            for item in (raw if isinstance(raw, list) else [])[:MAX_CIRCUITS]:
                if not isinstance(item, dict):
                    continue
                meter, amps = _text(item.get('meter'), 60), _amps(item)
                if meter and amps is not None:
                    found[meter] = {'amps': amps, 'at': now, 'source': 'plugin', 'plugin': spec.name}
        with self._lock:
            self.readings.update(found)
            self.last_poll = now
        return self.evaluate(baseline=not self.baseline_done)

    def reading_for(self, circuit):
        with self._lock:
            return self._reading_for(circuit)

    def _reading_for(self, circuit):
        """The newer of the typed-in reading and the plugin's."""
        manual = circuit.get('reading')
        metered = self.readings.get(circuit.get('meter')) if circuit.get('meter') else None
        if manual and metered:
            return manual if manual['at'] >= metered['at'] else metered
        return manual or metered

    def ensure_baseline(self):
        """Before the first change after a start: what is red already pages nobody again."""
        if not self.baseline_done:
            self.evaluate(baseline=True)

    def evaluate(self, baseline=False, data=None):
        """Compare every circuit's state with the last one; file and announce the ones that turned
        red or tripped. Returns those alerts."""
        data = data if data is not None else load_data()
        boards, circuits = _stored(data)
        names = {b['id']: b['name'] for b in boards}
        alerts = []
        with self._lock:
            seen = {}
            for c in circuits:
                state, pct = state_of(c, self._reading_for(c))
                seen[c['id']] = state
                was = self.states.get(c['id'])
                if baseline or was == state or state not in ('crit', 'tripped'):
                    continue
                if was == 'tripped' and state == 'crit':
                    continue   # reset and still overloaded: the open incident covers it
                alerts.append({'id': c['id'], 'name': c['name'], 'board': names.get(c['board'], ''),
                               'phase': c['phase'], 'state': state, 'pct': pct, 'rating_a': c['rating_a']})
            self.states = seen
            self.baseline_done = True
        for alert in alerts:
            circuit = next(c for c in circuits if c['id'] == alert['id'])
            feeds = fed_by(circuit, data)
            events.publish('power.alert', {**alert, 'seats': len(feeds['seats']),
                                           'switches': [s['name'] for s in feeds['switches']]})
            if config.get_bool('POWER_INCIDENTS', True):
                _file_incident(circuit, alert, feeds)
        if alerts or baseline:
            events.publish('power.changed', {})
        return alerts

    def snapshot(self):
        data = load_data()
        boards, circuits = _stored(data)
        blocks = {b.get('id'): b for b in data.get('seat_blocks') or []}
        out = []
        for c in circuits:
            reading = self.reading_for(c)
            state, pct = state_of(c, reading)
            feeds = fed_by(c, data)
            out.append({**c, 'reading': reading, 'state': state, 'load_pct': pct, 'fed': feeds,
                        'feeds_label': '; '.join(_feed_label(f, blocks) for f in c.get('blocks') or [])})
        order = {s: i for i, s in enumerate(('tripped', 'crit', 'warn', 'unknown', 'ok'))}
        out.sort(key=lambda c: (order[c['state']], c['name'].lower()))
        warn, crit = thresholds()
        counts = {s: sum(c['state'] == s for c in out) for s in STATES}
        return {'enabled': enabled(), 'boards': sorted(boards, key=lambda b: b['name'].lower()),
                'circuits': out, 'counts': counts, 'warn': warn, 'crit': crit, 'last_poll': self.last_poll,
                'plugins': len(self.registry.feeders('power')),
                'blocks': [{'id': b.get('id'), 'name': b.get('name') or '', 'rows': int(b.get('rows') or 0)}
                           for b in data.get('seat_blocks') or []]}

    def markers(self):
        """Per seat and switch, the circuit and its state, and the placed boards: the floor plan layer."""
        snap = self.snapshot()
        seats, switches = {}, {}
        for c in snap['circuits']:
            mark = {'circuit': c['name'], 'state': c['state'], 'pct': c['load_pct']}
            for seat in c['fed']['seats']:
                seats.setdefault(seat, mark)
            for sw in c['fed']['switches']:
                switches.setdefault(sw['id'], mark)
        worst = {}
        for c in snap['circuits']:
            rank = ('ok', 'unknown', 'warn', 'crit', 'tripped').index(c['state'])
            if rank > worst.get(c['board'], -1):
                worst[c['board']] = rank
        boards = [{'id': b['id'], 'name': b['name'], 'x': b['x'], 'y': b['y'],
                   'state': ('ok', 'unknown', 'warn', 'crit', 'tripped')[worst.get(b['id'], 1)]}
                  for b in snap['boards'] if b.get('x') is not None and b.get('y') is not None]
        return {'enabled': snap['enabled'], 'seats': seats, 'switches': switches, 'boards': boards,
                'counts': snap['counts']}


def _file_incident(circuit, alert, feeds):
    """One open incident per circuit for the Electrics team, naming what goes dark."""
    from auth import teams

    from . import incidents
    try:
        if any(i.get('circuit_id') == circuit['id'] and i['status'] != 'fixed' for i in incidents.list_all()):
            return None
        team = config.get('POWER_TEAM', 'electrics') or None
        team = team if team in teams.all_teams() else None
        title = (f"Breaker tripped: {circuit['name']}" if alert['state'] == 'tripped'
                 else f"Circuit {circuit['name']} at {alert['pct']:g} % of {circuit['rating_a']:g} A")
        seats = feeds['seats']
        parts = []
        if seats:
            parts.append(f"{len(seats)} seat{'s' if len(seats) != 1 else ''} ({seats[0]} to {seats[-1]})"
                         if len(seats) > 1 else f'seat {seats[0]}')
        if feeds['switches']:
            parts.append('switches ' + ', '.join(s['name'] for s in feeds['switches']))
        note = (f"Board {alert['board']}, phase {circuit['phase']}. Feeds " + ' and '.join(parts) + '.'
                if parts else f"Board {alert['board']}, phase {circuit['phase']}.")
        incident = incidents.create(None, {'circuit_id': circuit['id'], 'title': title, 'problem': 'power',
                                           'team': team, 'note': note}, source='power')
        events.publish('incident.changed', {'id': incident['id'], 'status': incident['status']})
        return incident
    except Exception as exc:  # noqa: BLE001  # the alert still goes out when the board can't take it
        print(f'[power] could not file the incident for {circuit.get("name")}: {exc}')
        return None


def init_power(app, registry, start_background=True):
    watch = PowerWatch(registry)
    app.extensions['floorbit_power'] = watch
    events.subscribe('power.alert', lambda ev: registry.emit('power.alert', ev.get('data') or {}))
    started = threading.Event()

    @app.before_request
    def start_power_once():
        if start_background and not started.is_set():
            started.set()
            watch.start()

    return watch
