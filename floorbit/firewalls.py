"""Firewalls and the ranges they serve (issue #470).

The core policy-routes each seat range to its firewall while that one is up, and to the next in
line when it isn't. Floorbit keeps that plan and shows it against the firewalls' health:

- **The firewalls** are the inventory's devices with the role ``firewall``.
- **A range** is a network (``192.0.2.0/27``) with its firewalls in order: the first is the one its
  traffic should take, the rest the failover order. Kept in data.json under ``firewalls``; the crew
  changes them (``floorplan.edit``), or imports them from NetBox prefixes that have the custom field
  ``floorbit_firewalls`` (``source: import``; each import replaces the last).
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
        if row is not None and row.get('source') == 'import':
            raise FirewallError(f"This range comes from {row.get('plugin') or 'NetBox'}: change it there and import "
                                'again.', 409)
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


MAX_SPLIT = 256          # ranges one split may make


def split(body, by):
    """Cut a network into equal ranges and hand them to the firewalls in turn: range 1 to the first
    firewall with the others as backups in order, range 2 to the second, and so on. This is how a
    core usually spreads seats over a firewall cluster, so a whole hall is planned in one go.
    Ranges planned already are left as they are."""
    net = _network(body.get('cidr'))
    try:
        size = int(body.get('size'))
    except (TypeError, ValueError):
        size = -1
    if not net.prefixlen <= size <= net.max_prefixlen:
        raise FirewallError(f'The range size is a prefix length from /{net.prefixlen} to /{net.max_prefixlen}.')
    if size - net.prefixlen > 8:
        raise FirewallError(f'One split makes at most {MAX_SPLIT} ranges.')
    label = ' '.join(str(body.get('name') or '').split())[:50]
    with _lock:
        data = load_data()
        # Checks the names (and the line length) the same way a single range does.
        line = _clean({'cidr': str(net), 'firewalls': body.get('firewalls')}, data)['firewalls']
        stored = data.get(KEY) if isinstance(data.get(KEY), dict) else {}
        rows = stored.setdefault('ranges', [])
        planned = {r.get('cidr') for r in rows}
        added, skipped = [], 0
        for i, sub in enumerate(net.subnets(new_prefix=size)):
            if str(sub) in planned:
                skipped += 1
                continue
            if len(rows) >= MAX_RANGES:
                raise FirewallError(f'Floorbit keeps at most {MAX_RANGES} ranges.')
            turn = i % len(line)
            row = {'id': uuid.uuid4().hex[:12], 'cidr': str(sub), 'name': f'{label} {i + 1}' if label else '',
                   'firewalls': line[turn:] + line[:turn], 'updated_at': time.time(), 'by': by}
            rows.append(row)
            added.append(row)
        data[KEY] = stored
        save_data(data)
    return {'added': len(added), 'skipped': skipped, 'ranges': [dict(r) for r in added]}


# ── import from NetBox ───────────────────────────────────────────────────────
FIELD = 'floorbit_firewalls'   # the NetBox custom field on a prefix: its firewalls, in order


def import_sources(registry):
    """Inventory plugins that can list firewall ranges (NetBox)."""
    if registry is None:
        return []
    return [spec for spec in registry.feeders('inventory')
            if (cls := spec.plugin_class()) is not None and hasattr(cls, 'firewall_ranges')]


def can_import():
    from . import agent_link
    return agent_link.active() or bool(import_sources(sources.registry))


def import_from(registry, by):
    """Replace the ranges read from plugins with what they list now; the crew's own ranges stay, and
    a network the crew planned already keeps the crew's line. Returns (added, errors)."""
    from . import agent_link
    from .plugins.base import PluginError
    found, errors, answered = [], [], set()
    if agent_link.active():
        # A hosted Floorbit: the local agent asks the event's NetBox.
        try:
            feeds = agent_link.feeds('firewall_feeds')
        except (agent_link.AgentUnavailable, agent_link.AgentError) as exc:
            feeds = []
            errors.append(f'Local agent: {exc}')
        for feed in feeds:
            if 'error' in feed:
                errors.append(f"{feed['name']} (local agent): {feed['error']}")
            else:
                found += [(feed['name'], r) for r in feed['items']]
                answered.update({feed['name'], feed.get('base_name', feed['name'])})
    for spec in import_sources(registry):
        if spec.name in answered:
            continue
        try:
            found += [(spec.name, r) for r in registry.call(spec, 'firewall_ranges') or []]
            answered.add(spec.name)
        except PluginError as exc:
            errors.append(f'{spec.name}: {exc}')
    if errors and not answered:
        raise FirewallError('; '.join(errors), 502)
    with _lock:
        data = load_data()
        stored = data.get(KEY) if isinstance(data.get(KEY), dict) else {}
        # A source that failed this time keeps its last import.
        kept = [r for r in _ranges(data) if r.get('source') != 'import' or r.get('plugin') not in answered]
        planned = {r['cidr'] for r in kept}
        added, unknown, clash = [], 0, 0
        for plugin, raw in found:
            if not isinstance(raw, dict):
                continue
            try:
                fields = _clean({'cidr': raw.get('cidr'), 'name': raw.get('name'), 'firewalls': raw.get('firewalls')},
                                data)
            except FirewallError:
                unknown += 1   # one prefix with a typo in NetBox must not stop the rest
                continue
            if fields['cidr'] in planned:
                clash += 1
                continue
            if len(kept) + len(added) >= MAX_RANGES:
                break
            planned.add(fields['cidr'])
            added.append({'id': uuid.uuid4().hex[:12], **fields, 'source': 'import', 'plugin': plugin,
                          'updated_at': time.time(), 'by': by})
        data[KEY] = {**stored, 'ranges': kept + added}
        save_data(data)
    if unknown:
        errors.append(f'{unknown} prefix(es) skipped: not a network, or a firewall that is not in the inventory.')
    if clash:
        errors.append(f'{clash} prefix(es) skipped: planned in Floorbit already.')
    return len(added), errors


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
        if StatusMonitor.latest['polled'] is not None:
            # The status monitor is polling: use its list rather than ask a source that may be
            # hanging (the page waited for its timeout). None, "unknown", when its last poll failed.
            latest = StatusMonitor.latest
            found = latest['devices'] if latest['at'] is not None and latest['at'] >= latest['polled'] else None
            with self._lock:
                self._at, self._devices = now, found
            return found
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
                       'seats': seats.get(row['id'], 0), 'source': row.get('source') or 'floorbit',
                       'plugin': row.get('plugin') or ''})
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
            'monitoring': _monitored(),
            'unread': _monitored() and health.devices(now) is None, 'can_import': can_import()}


def _monitored():
    # Without a monitoring source the ranges can only show their plan: that is setup, not trouble.
    try:
        return bool(sources.monitoring().enabled())
    except Exception:  # noqa: BLE001 - a source that can't even say is "set up but unreadable"
        return True


def seat_routes(now=None):
    """The seats whose traffic isn't on its planned firewall, for the plan's firewall layer: by seat,
    the firewall now (None: none left) and the planned one. Names only, never the IPs."""
    now = time.time() if now is None else now
    data = load_data()
    nets = _nets(data)
    if not nets:
        return {'enabled': False, 'seats': {}}
    status = {n: health.status(n, now) for _row, _net in nets for n in _row.get('firewalls') or []}
    routes = {}
    seats = {}
    for seat, ip in _seat_ips().items():
        row = _match(ip, nets)
        if row is None:
            continue
        if row['id'] not in routes:
            line = list(row.get('firewalls') or [])
            routes[row['id']] = (*_route(line, status), line[0] if line else None)
        now_on, state, intended = routes[row['id']]
        if state in ('failover', 'down'):
            seats[seat] = {'now': now_on, 'intended': intended, 'state': state}
    return {'enabled': True, 'seats': seats}


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
