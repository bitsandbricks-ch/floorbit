"""Needs attention (issue #15): port trouble an ops person should look at. See docs/alerts.md.

Every ``ATTENTION_INTERVAL`` seconds the watch reads all ports of the placed switches that are
online, from the monitoring source (``device_ports``), and keeps what it sees between polls:

- **flapping:** the link went up or down ``ATTENTION_FLAPS`` times (3) within ten minutes;
- **errors rising:** the error counters grew by ``ATTENTION_ERRORS`` (10) or more since the last poll;
- **half duplex:** an up port at half duplex (a bad cable or a forced setting);
- **no check-in:** with check-in on, a seat port that is up while nobody checked in at that seat.
  A port belongs to a seat when its description (ifAlias) names the seat, e.g. "Seat A-12".

Entries clear on their own once the port behaves. They hold switch, port and seat, never who sits
there, so everyone who sees the floor plan may see them.
"""
import re
import threading
import time
from collections import deque

from integrations import checkin, config, events

from . import inventory, sources
from .power import block_rows
from .store import load_data

FLAP_WINDOW = 600
KINDS = ('flapping', 'errors', 'duplex', 'checkin')


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
        self.last_poll = None

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
            if sources.monitoring().enabled():
                try:
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
        checked_in = set(checkin.load_all()) if config.get_bool('CHECKIN_ENABLED', False) else None
        flaps = config.get_int('ATTENTION_FLAPS', 3, minimum=2)
        error_step = config.get_int('ATTENTION_ERRORS', 10, minimum=1)
        statuses = getattr((_app_ext().get('lal_integrations') or {}).get('monitor'), 'statuses', {}) or {}
        found = {}
        reads = []   # every port read, for the stats dashboard (stats.py)
        devices = inventory.devices(data)
        for dev in devices:
            if dev.get('x') is None or (statuses.get(dev['id']) or {}).get('status') == 'offline':
                continue
            for port in monitor.device_ports(dev['name']) or []:
                name = port.get('name')
                if not name:
                    continue
                reads.append((dev, port, seat_of(port.get('description'), names)))
                for entry in self._judge(dev, name, port, now, flaps, error_step, names, checked_in):
                    found[entry['id']] = entry
        new = []
        with self._lock:
            for key, entry in found.items():
                old = self.items.get(key)
                entry['since'] = old['since'] if old else now
                if not old:
                    new.append(entry)
            changed = bool(new) or found.keys() != self.items.keys()
            self.items = found
            self.last_poll = now
        if changed:
            events.publish('attention.changed', {'count': len(found)})
        stats = (_app_ext() or {}).get('floorbit_stats')
        if stats is not None:
            stats.record(reads, [d.get('name') or '' for d in devices], now=now)
            events.publish('stats.changed', {})
        return new

    def _judge(self, dev, name, port, now, flaps, error_step, names, checked_in):
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

        seat = seat_of(port.get('description'), names)
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

    def snapshot(self):
        with self._lock:
            items = sorted(self.items.values(), key=lambda i: -i['since'])
            return {'items': items, 'last_poll': self.last_poll, 'interval': self.interval()}


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
