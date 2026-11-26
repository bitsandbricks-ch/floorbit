"""Needs attention (issue #15): port trouble an ops person should look at. See docs/alerts.md.

Every ``ATTENTION_INTERVAL`` seconds the watch reads all ports of the placed switches that are
online, from the monitoring source (``device_ports``), and keeps what it sees between polls:

- **flapping:** the link went up or down ``ATTENTION_FLAPS`` times (3) within ten minutes;
- **errors rising:** the error counters grew by ``ATTENTION_ERRORS`` (10) or more since the last poll;
- **half duplex:** an up port at half duplex (a bad cable or a forced setting);
- **no check-in:** with check-in on, a seat port that is up while nobody checked in at that seat.
  A port belongs to a seat when a cable goes from it to the seat (cables.py), or else when its
  description (ifAlias) names the seat, e.g. "Seat A-12".

Entries clear on their own once the port behaves. They hold switch, port and seat, never who sits
there, so everyone who sees the floor plan may see them.
"""
import re
import threading
import time
from collections import deque

from integrations import checkin, config, events

from . import cables, inventory, recording, sources, status_page
from .seat_names import block_rows
from .store import load_data

FLAP_WINDOW = 600
KINDS = ('flapping', 'errors', 'duplex', 'checkin', 'mapping')


def _seat_names(data):
    names = {}
    for block in data.get('seat_blocks') or []:
        for row in block_rows(block):
            for seat in row:
                names[seat.lower()] = seat
    return names


def seat_of(description, names):
    """The seat a port description names ("Seat A-12", "A-12 desk"), or None."""
    for token in re.findall(r'[A-Za-z0-9]+-[0-9]+', str(description or '')):
        if token.lower() in names:
            return names[token.lower()]
    return None


def _record_frame(sample, seat_bps, data):
    """A frame for the whole-event replay (floorbit/recording.py), every five minutes."""
    from . import cluster, incidents
    if not cluster.leading():
        return               # every pod watches the ports; one records the replay
    try:
        open_seats = {i.get('seat') for i in incidents.list_all() if i.get('status') != 'fixed' and i.get('seat')}
        recording.capture(sample, seat_bps, open_seats, data)
    except Exception as exc:  # noqa: BLE001  # the recording must never stop the port watch
        print(f'[attention] could not record a replay frame: {exc}')


# When each open item was first seen, so a restart doesn't make them all start "now".
SINCE_FILE = 'attention_since.json'


class AttentionWatch:
    def __init__(self):
        self._lock = threading.Lock()
        self._thread = None
        self._stop = threading.Event()
        self.app = None
        self.reset()

    def reset(self):
        self.ports = {}       # (switch_id, port) -> {'oper', 'last_change', 'errors', 'changes': deque}
        self.items = {}       # id -> entry
        self.port_seats = {}  # (switch name, port) -> seat, from the last read, for the syslog (floorbit/syslog.py)
        self.port_reads = {}  # (switch lowercase, canonical port) -> what the last read said, for patch_check.py
        self.read_switches = set()   # switches (lowercase) read in the last poll
        self.last_poll = None
        self._kept = None     # {item id: since} kept across restarts, read on the first poll (#1415)

    # ── lifecycle ─────────────────────────────────────────────────────────────
    def start(self):
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, name='attention-watch', daemon=True)
            self._thread.start()

    def stop(self):
        self._stop.set()

    @staticmethod
    def interval():
        return config.get_int('ATTENTION_INTERVAL', 120, minimum=30)

    def _run(self):
        while not self._stop.is_set():
            try:
                if sources.monitoring().enabled():
                    # In an app context: the switch statuses live in the app's extensions.
                    with self.app.app_context():
                        self.poll_once()
            except Exception as exc:  # noqa: BLE001  # keep the thread alive no matter what
                print(f'[attention] poll failed: {exc}')
            self._stop.wait(self.interval())

    # ── polling ───────────────────────────────────────────────────────────────
    def poll_once(self, now=None):
        now = time.time() if now is None else now
        monitor = sources.monitoring()
        if not monitor.enabled():
            return []
        data = load_data()
        names = _seat_names(data)
        from .plugins.helpers import uplink_pattern
        uplink = uplink_pattern()       # the admin's uplink and trunk ports: never "up with no cable"
        checked_in = set(checkin.load_all()) if config.get_bool('CHECKIN_ENABLED', False) else None
        flaps = config.get_int('ATTENTION_FLAPS', 3, minimum=2)
        error_step = config.get_int('ATTENTION_ERRORS', 10, minimum=1)
        statuses = getattr((_app_ext().get('floorbit_integrations') or {}).get('monitor'), 'statuses', {}) or {}
        found = {}
        reads = []   # every port read, for the stats dashboard (stats.py)
        port_seats = {}
        port_reads, read_switches = {}, set()
        # A cable to a seat (cables.py, the block patch plan) wins over the port's description:
        # it is what the crew patched, the description is what someone typed on the switch.
        from .syslog import canonical_port  # syslog reads this module's seats: imported late
        cabled = cables.port_seats(data)
        devices = inventory.devices(data)
        for dev in devices:
            if dev.get('x') is None or (statuses.get(dev['id']) or {}).get('status') == 'offline':
                continue
            read_switches.add(str(dev['name']).lower())
            for port in monitor.device_ports(dev['name']) or []:
                name = port.get('name')
                if not name:
                    continue
                port_reads[(str(dev['name']).lower(), canonical_port(name))] = {
                    'switch': dev['name'], 'port': name, 'state': port.get('state'),
                    'utilization': port.get('utilization'),
                    'described_seat': seat_of(port.get('description'), names),
                    'uplink': bool(uplink.search(f"{name} {port.get('description') or ''}"))}
                seat = (cabled.get((str(dev['name']).lower(), canonical_port(name)))
                        or seat_of(port.get('description'), names))
                reads.append((dev, port, seat))
                if seat:
                    port_seats[(str(dev['name']).lower(), name)] = seat
                for entry in self._judge(dev, name, port, now, flaps, error_step, seat, checked_in):
                    found[entry['id']] = entry
        for entry in mapping_items(data, devices):
            found[entry['id']] = entry
        new = []
        kept = self._read_kept()
        with self._lock:
            for key, entry in found.items():
                old = self.items.get(key)
                # After a restart an item that was already there keeps when it started, instead of
                # every row saying "now" (issue #1415).
                entry['since'] = old['since'] if old else kept.get(key) or now
                if not old and key not in kept:
                    new.append(entry)
            changed = found.keys() != self.items.keys()
            self.items = found
            self.port_seats = port_seats
            self.port_reads, self.read_switches = port_reads, read_switches
            self.last_poll = now
        status_page.learn_seats(port_seats)
        if changed:
            self._write_kept({k: e['since'] for k, e in found.items()})
            events.publish('attention.changed', {'count': len(found)})
        stats = (_app_ext() or {}).get('floorbit_stats')
        if stats is not None:
            from .stats import link_ports
            sample = stats.record(reads, [d.get('name') or '' for d in devices], now=now, links=link_ports(data))
            stats.count_problems(new, now=now)
            _record_frame(sample, stats.seats()['seats'], data)
            events.publish('stats.changed', {})
            changes = stats.changes_at(now)
            if changes:
                # Seat numbers and up/down only, for "watch this seat" in the browser (issue #178).
                events.publish('seats.changed', {'seats': changes})
        return new

    def _judge(self, dev, name, port, now, flaps, error_step, seat, checked_in):
        key = (dev['id'], name)
        oper = 'up' if port.get('state') in ('up', 'errors') else port.get('state')
        errors = sum(v or 0 for v in (port.get('errors_in'), port.get('errors_out')))
        seen = self.ports.get(key)
        if seen is None:
            seen = self.ports[key] = {'oper': oper, 'last_change': port.get('last_change'), 'errors': errors,
                                      'changes': deque(maxlen=20)}
        else:
            changed = oper != seen['oper'] or (port.get('last_change') not in (None, seen['last_change']))
            if changed:
                seen['changes'].append(now)
            grew = errors - seen['errors']
            seen.update(oper=oper, last_change=port.get('last_change'), errors=errors, grew=grew)
        while seen['changes'] and now - seen['changes'][0] > FLAP_WINDOW:
            seen['changes'].popleft()

        where = f"{dev['name']} {name}" + (f' (seat {seat})' if seat else '')
        base = {'switch_id': dev['id'], 'switch': dev['name'], 'port': name, 'seat': seat, 'where': where}
        out = []
        if len(seen['changes']) >= flaps:
            out.append({**base, 'kind': 'flapping',
                        'title': f"Port flapping: {len(seen['changes'])} link changes in 10 minutes"})
        if seen.get('grew', 0) >= error_step:
            out.append({**base, 'kind': 'errors', 'title': f"Interface errors rising (+{seen['grew']})"})
        if oper == 'up' and port.get('duplex') == 'half':
            out.append({**base, 'kind': 'duplex', 'title': 'Running at half duplex'})
        if checked_in is not None and seat and oper == 'up' and seat not in checked_in:
            out.append({**base, 'kind': 'checkin', 'title': f'Seat {seat} is online without a check-in'})
        for item in out:
            item['id'] = f"{item['kind']}:{dev['id']}:{name}"
        return out

    def _read_kept(self):
        if self._kept is None:
            from . import database, store
            try:
                saved = store.read_json(store.event_path(SINCE_FILE), {})
            except (OSError, ValueError, database.DatabaseError):
                saved = {}
            self._kept = {str(k): float(v) for k, v in (saved or {}).items()
                          if isinstance(v, (int, float))} if isinstance(saved, dict) else {}
        return self._kept

    def _write_kept(self, since):
        from . import database, store
        self._kept = since
        try:
            store.write_json(store.event_path(SINCE_FILE), since)
        except (OSError, database.DatabaseError) as exc:
            print(f'[attention] could not keep the start times: {exc}')

    def snapshot(self):
        with self._lock:
            items = sorted(self.items.values(), key=lambda i: -i['since'])
            return {'items': items, 'last_poll': self.last_poll, 'interval': self.interval()}


MAPPING_TITLES = {
    'shared': 'Seats {} and {} checked in on the same port',
    'plan': 'Seat {} checked in on the port the patch plan gives to seat {}',
    'taken': 'Seat {} was taken over by another nick',
    'area': 'Seat {} checked in on a port meant for seats {}',
}


def mapping_items(data, devices):
    """Seat check-ins that disagree about ports (integrations/checkin.py, ``port_conflicts``)."""
    try:
        conflicts = checkin.port_conflicts(data)
    except Exception as exc:  # noqa: BLE001  # the port checks above still count
        print(f'[attention] could not read the seat check-in ports: {exc}')
        return []
    ids = {str(d.get('name') or '').lower(): d['id'] for d in devices}
    out = []
    for c in conflicts:
        title = MAPPING_TITLES[c['kind']].format(c['seat'], *(c['other'] or ['']))
        if c['kind'] == 'shared' and len(c['other']) > 1:
            title = MAPPING_TITLES['shared'].format(c['seat'], ', '.join(c['other']))
        out.append({'switch_id': ids.get(str(c['switch']).lower()), 'switch': c['switch'], 'port': c['port'],
                    'seat': c['seat'], 'where': f"{c['switch']} {c['port']} (seat {c['seat']})",
                    'kind': 'mapping', 'title': title,
                    'id': f"mapping:{c['kind']}:{c['seat']}:{c['switch']}:{c['port']}"})
    return out


def _app_ext():
    from flask import current_app, has_app_context
    return current_app.extensions if has_app_context() else {}


def init_attention(app, start_background=True):
    watch = AttentionWatch()
    watch.app = app
    app.extensions['floorbit_attention'] = watch
    started = threading.Event()

    @app.before_request
    def start_attention_once():
        if start_background and not started.is_set():
            started.set()
            watch.start()

    return watch
