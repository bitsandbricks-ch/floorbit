"""Firewalls and the ranges they serve (issue #470).

The core policy-routes each seat range to its firewall while that one is up, and to the next in
line when it isn't. Floorbit keeps that plan and shows it against the firewalls' health:

- **The firewalls** are the inventory's devices with the role ``firewall``.
- **A range** is a network (``192.0.2.0/27``) with its firewalls in order: the first is the one its
  traffic should take, the rest the failover order. Kept in data.json under ``firewalls``; the crew
  changes them (``floorplan.edit``).
- **Now**: the first firewall in a range's line that the monitoring source doesn't report down. A
  firewall the source can't tell about counts as up (the core would still route to it), but the
  range says so (``unknown``).

A seat's range is the most specific one its IP is in. Seat IPs never leave this module: the seat
panel gets the firewall names only.
"""
import ipaddress
import threading
import time
import uuid

from integrations import seat_sources
from integrations.monitor import StatusMonitor

from . import inventory, sources
from .store import load_data, save_data

KEY = 'firewalls'
MAX_RANGES = 500
MAX_LINE = 10            # firewalls in one range's failover line
READ_EVERY = 15          # seconds the source's device list is kept
_lock = threading.Lock()


class FirewallError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def _ranges(data):
    raw = data.get(KEY)
    raw = raw if isinstance(raw, dict) else {}
    return [r for r in raw.get('ranges') or [] if isinstance(r, dict) and r.get('id') and r.get('cidr')]


def _firewall_names(data):
    return {str(d['name']).lower(): d['name'] for d in inventory.devices(data, include_hidden=True)
            if d.get('role') == 'firewall' and d.get('name')}


def _network(value):
    try:
        return ipaddress.ip_network(str(value or '').strip(), strict=False)
    except ValueError:
        raise FirewallError('Write the range as a network, like 192.0.2.0/27.') from None


def _clean(body, data, current=None):
    current = current or {}
    net = _network(body.get('cidr', current.get('cidr')))
    names = _firewall_names(data)
    line = body.get('firewalls', current.get('firewalls'))
    if not isinstance(line, list) or not line:
        raise FirewallError('Pick at least one firewall for the range.')
    out = []
    for name in line:
        found = names.get(str(name or '').strip().lower())
        if not found:
            raise FirewallError('Pick the firewalls from the inventory (devices with the role firewall).')
        if found not in out:
            out.append(found)
    if len(out) > MAX_LINE:
        raise FirewallError(f'A range has at most {MAX_LINE} firewalls.')
    label = ' '.join(str(body.get('name', current.get('name')) or '').split())[:60]
    return {'cidr': str(net), 'name': label, 'firewalls': out}


def save(body, by, range_id=None):
    with _lock:
        data = load_data()
        stored = data.get(KEY) if isinstance(data.get(KEY), dict) else {}
        rows = stored.setdefault('ranges', [])
        row = next((r for r in rows if r.get('id') == range_id), None) if range_id else None
        if range_id and row is None:
            raise FirewallError('No such range.', 404)
        fields = _clean(body, data, row)
        if any(r is not row and r.get('cidr') == fields['cidr'] for r in rows):
            raise FirewallError(f"{fields['cidr']} is planned already.", 409)
        if row is None:
            if len(rows) >= MAX_RANGES:
                raise FirewallError(f'Floorbit keeps at most {MAX_RANGES} ranges.')
            row = {'id': uuid.uuid4().hex[:12]}
            rows.append(row)
        row.update(fields, updated_at=time.time(), by=by)
        data[KEY] = stored
        save_data(data)
    return dict(row)


def delete(range_id):
    with _lock:
        data = load_data()
        rows = _ranges(data)
        gone = next((r for r in rows if r.get('id') == range_id), None)
        if gone is None:
            return None
        data[KEY] = {**data[KEY], 'ranges': [r for r in rows if r is not gone]}
        save_data(data)
    return gone


# ── health ──────────────────────────────────────────────────────────────────
class Health:
    """The source's device list, kept a few seconds: the seat panel asks on every click."""

    def __init__(self):
        self._lock = threading.Lock()
        self._at = None
        self._devices = None      # None: the source couldn't be read

    def reset(self):
        with self._lock:
            self._at, self._devices = None, None

    def devices(self, now):
        with self._lock:
            if self._at is not None and now - self._at < READ_EVERY:
                return self._devices
        try:
            source = sources.monitoring()
            found = source.devices() if source.enabled() else None
        except Exception:  # noqa: BLE001 - an unreadable source means "unknown", not an error page
            found = None
        with self._lock:
            self._at, self._devices = now, found
        return found

    def status(self, name, now):
        """online, offline or unknown, the way the status monitor reads it."""
        found = self.devices(now)
        if found is None:
            return 'unknown'
        return StatusMonitor.device_status(StatusMonitor.match(name, found))


health = Health()


def _route(line, status):
    """(firewall now, state) for one range: primary, failover, unknown or down."""
    for i, name in enumerate(line):
        if status[name] == 'offline':
            continue
        if status[name] == 'unknown':
            return name, 'unknown'
        return name, 'primary' if i == 0 else 'failover'
    return None, 'down'


def _seat_ips():
    out = {}
    for seat, entry in (seat_sources.load() or {}).items():
        try:
            out[str(seat).upper()] = ipaddress.ip_address(str((entry or {}).get('ip_address') or '').strip())
        except ValueError:
            continue
    return out


def _match(ip, nets):
    """The most specific range ``ip`` is in, like the core's routing table."""
    best = None
    for row, net in nets:
        if ip.version == net.version and ip in net and (best is None or net.prefixlen > best[1].prefixlen):
            best = (row, net)
    return best[0] if best else None


def _nets(data):
    out = []
    for row in _ranges(data):
        try:
            out.append((row, ipaddress.ip_network(row['cidr'], strict=False)))
        except ValueError:
            continue
    return out


def overview(now=None):
    """The firewalls with their health and what they serve, and every range with its route now."""
    now = time.time() if now is None else now
    data = load_data()
    firewalls = [d for d in inventory.devices(data) if d.get('role') == 'firewall' and d.get('name')]
    rows = _ranges(data)
    names = {d['name'] for d in firewalls} | {n for r in rows for n in r.get('firewalls') or []}
    status = {n: health.status(n, now) for n in names}
    nets = _nets(data)
    seats = {}
    for _seat, ip in _seat_ips().items():
        row = _match(ip, nets)
        if row:
            seats[row['id']] = seats.get(row['id'], 0) + 1
    ranges = []
    for row in rows:
        line = [n for n in row.get('firewalls') or [] if n in status]
        now_on, state = _route(line, status)
        ranges.append({'id': row['id'], 'cidr': row['cidr'], 'name': row.get('name') or '', 'firewalls': line,
                       'intended': line[0] if line else None, 'now': now_on, 'state': state,
                       'seats': seats.get(row['id'], 0)})
    ranges.sort(key=lambda r: (ipaddress.ip_network(r['cidr']).version, ipaddress.ip_network(r['cidr'])))
    cards = []
    for d in firewalls:
        name = d['name']
        cards.append({'id': d['id'], 'name': name, 'model': d.get('model') or '', 'hall': d.get('hall') or '',
                      'status': status.get(name, 'unknown'),
                      'serving': [r['cidr'] for r in ranges if r['now'] == name],
                      'planned': [r['cidr'] for r in ranges if r['intended'] == name],
                      'backup_for': [r['cidr'] for r in ranges if name in r['firewalls'][1:]],
                      'seats': sum(r['seats'] for r in ranges if r['now'] == name)})
    cards.sort(key=lambda c: c['name'].lower())
    return {'firewalls': cards, 'ranges': ranges,
            'counts': {'firewalls': len(cards), 'down': sum(c['status'] == 'offline' for c in cards),
                       'failover': sum(r['state'] == 'failover' for r in ranges),
                       'without': sum(r['state'] == 'down' for r in ranges)},
            'unread': health.devices(now) is None}


def configured(data=None):
    """Are there firewalls in the inventory? Cheap: the health wall asks on every poll."""
    data = load_data() if data is None else data
    return any(d.get('role') == 'firewall' for d in inventory.devices(data))


def health_checks(now=None):
    """The firewalls as tiles of the service health wall (floorbit/health.py), so one going down, and
    its ranges failing over, reaches Discord like any other service."""
    if not configured():
        return []
    view = overview(now)
    by_planned = {}
    for r in view['ranges']:
        by_planned.setdefault(r['intended'], []).append(r)
    out = []
    for fw in view['firewalls']:
        status = {'online': 'up', 'offline': 'down'}.get(fw['status'], 'unknown')
        if fw['status'] == 'offline':
            moved = by_planned.get(fw['name'], [])
            lost = [r['cidr'] for r in moved if r['state'] == 'down']
            if lost:
                summary = f"{', '.join(lost)} without a firewall"
            elif moved:
                summary = f"{len(moved)} range{'s' if len(moved) != 1 else ''} failed over"
            else:
                summary = 'Down, serves no range'
        elif fw['serving']:
            n, seats = len(fw['serving']), fw['seats']
            summary = f"Serves {n} range{'s' if n != 1 else ''}, {seats} seat{'s' if seats != 1 else ''}"
        else:
            summary = 'Serves no range now'
        out.append({'id': f"firewall:{fw['id']}", 'name': fw['name'], 'kind': 'firewall', 'status': status,
                    'summary': summary, 'link': '/firewalls',
                    'metrics': [{'label': 'Seats', 'value': fw['seats'], 'unit': '', 'tone': ''}]
                    if status == 'up' else [],
                    'plugin': 'firewalls', 'plugin_name': 'Firewalls'})
    return out


def for_seat(seat, data=None, now=None):
    """Which firewall a seat's traffic should take and which it takes now, or None when no range
    covers its IP. Firewall names only: for the crew's seat panel."""
    now = time.time() if now is None else now
    data = load_data() if data is None else data
    nets = _nets(data)
    if not nets:
        return None
    ip = _seat_ips().get(str(seat or '').upper())
    row = _match(ip, nets) if ip is not None else None
    if row is None:
        return None
    line = list(row.get('firewalls') or [])
    now_on, state = _route(line, {n: health.status(n, now) for n in line})
    return {'intended': line[0] if line else None, 'now': now_on, 'state': state, 'range': row.get('name') or ''}
