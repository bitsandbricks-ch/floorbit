"""Tournament awareness (issue #31): protected match seats. See docs/tournament.md.

Match zones are named groups of seats ("Main stage", "CS2 finals"): whole seat blocks and single
seats. A seat in a zone is a match seat:

- its needs-attention items and incidents go to the top of their lists, marked with the zone;
- port actions on it need a second confirmation (``confirm_match``);
- the tournament page lists the switch ports behind the match seats, for QoS on those switches.

Kept in data.json under ``tournament``: ``{"zones": [{"id", "name", "blocks", "seats", "note"}]}``.
"""
import re
import threading
import uuid

from .store import load_data, save_data

KEY = 'tournament'
MAX_ZONES = 50
MAX_NAME = 60
MAX_NOTE = 300
_RANGE = re.compile(r'^([A-Z0-9]+)-(\d+)(?:\.\.|-)(?:\1-)?(\d+)$')

_lock = threading.Lock()


class TournamentError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def zones(data=None):
    data = data if data is not None else load_data()
    raw = (data.get(KEY) or {}).get('zones') if isinstance(data.get(KEY), dict) else None
    return [z for z in raw or [] if isinstance(z, dict) and z.get('id')]


def _block_names(data):
    return {str(b.get('name')).upper() for b in data.get('seat_blocks') or [] if b.get('name')}


def parse_seats(text, data):
    """``"A-1..A-16, B, C-3"`` into (blocks, seats). Unknown seats or blocks are an error."""
    from .incidents import seat_numbers
    known = seat_numbers(data)
    blocks, seats, unknown = [], [], []
    text = re.sub(r'\s*(\.\.|\u2013)\s*', '..', str(text or '').upper())
    for part in re.split(r'[,;\s]+', text):
        part = part.strip()
        if not part:
            continue
        found = _RANGE.match(part)
        if found:
            prefix, a, b = found.group(1), int(found.group(2)), int(found.group(3))
            lo, hi = min(a, b), max(a, b)
            if hi - lo > 2000:
                raise TournamentError(f'{part} is too long a range.')
            for n in range(lo, hi + 1):
                seat = f'{prefix}-{n}'
                (seats if seat in known else unknown).append(seat)
        elif part in _block_names(data):
            blocks.append(part)
        elif part in known:
            seats.append(part)
        else:
            unknown.append(part)
    if unknown:
        shown = ', '.join(unknown[:5]) + (' …' if len(unknown) > 5 else '')
        raise TournamentError(f'Not on the floor plan: {shown}')
    if not blocks and not seats:
        raise TournamentError('Name the seats: blocks like "B", seats like "A-3" or ranges like "A-1..A-16".')
    return sorted(set(blocks)), sorted(set(seats), key=_natural)


def _natural(seat):
    head, _, tail = seat.rpartition('-')
    return (head, int(tail)) if tail.isdigit() else (seat, 0)


def match_seats(data=None):
    """{seat: zone name} for every match seat."""
    data = data if data is not None else load_data()
    from .incidents import seat_numbers
    all_seats = seat_numbers(data)
    out = {}
    for zone in zones(data):
        for block in zone.get('blocks') or []:
            for seat in all_seats:
                if seat.startswith(f'{block}-'):
                    out.setdefault(seat, zone['name'])
        for seat in zone.get('seats') or []:
            out.setdefault(seat, zone['name'])
    return out


def zone_of(seat, data=None):
    return match_seats(data).get(str(seat or '').upper()) if seat else None


def _clean(body, data):
    name = str(body.get('name') or '').strip()[:MAX_NAME]
    if not name:
        raise TournamentError('Give the zone a name.')
    blocks, seats = parse_seats(body.get('seats'), data)
    return {'name': name, 'blocks': blocks, 'seats': seats, 'note': str(body.get('note') or '').strip()[:MAX_NOTE]}


def _save(data, items):
    data[KEY] = {'zones': items}
    save_data(data)


def create(body):
    with _lock:
        data = load_data()
        items = zones(data)
        if len(items) >= MAX_ZONES:
            raise TournamentError(f'At most {MAX_ZONES} match zones.')
        zone = {'id': uuid.uuid4().hex[:12], **_clean(body, data)}
        items.append(zone)
        _save(data, items)
        return zone


def update(zone_id, body):
    with _lock:
        data = load_data()
        items = zones(data)
        zone = next((z for z in items if z['id'] == zone_id), None)
        if not zone:
            raise TournamentError('No such match zone.', 404)
        zone.update(_clean({**zone, 'seats': ', '.join(zone['blocks'] + zone['seats']), **body}, data))
        _save(data, items)
        return zone


def delete(zone_id):
    with _lock:
        data = load_data()
        items = zones(data)
        zone = next((z for z in items if z['id'] == zone_id), None)
        if not zone:
            raise TournamentError('No such match zone.', 404)
        _save(data, [z for z in items if z['id'] != zone_id])
        return zone


def qos_hints(data=None):
    """The switch ports behind the match seats, per switch, and each switch's uplinks.

    Asks the monitoring source for each placed switch's ports, like the needs-attention watch does,
    and finds the seat in the port description.
    """
    from . import inventory, sources
    from .attention import _seat_names, seat_of
    from .stats import _uplink_re
    data = data if data is not None else load_data()
    seats = match_seats(data)
    monitor = sources.monitoring()
    if not seats or not monitor.enabled():
        return {'available': monitor.enabled(), 'switches': [], 'missing': sorted(seats, key=_natural)}
    names = _seat_names(data)
    uplink = _uplink_re()
    found, out = set(), []
    for dev in inventory.devices(data):
        if dev.get('x') is None:
            continue
        ports, uplinks = [], []
        for port in monitor.device_ports(dev['name']) or []:
            seat = seat_of(port.get('description'), names)
            if seat in seats:
                ports.append({'port': port.get('name'), 'seat': seat, 'zone': seats[seat]})
                found.add(seat)
            elif not seat and uplink.search(str(port.get('description') or '')):
                uplinks.append(port.get('name'))
        if ports:
            ports.sort(key=lambda p: _natural(p['seat']))
            out.append({'switch': dev['name'], 'switch_id': dev['id'], 'ports': ports, 'uplinks': uplinks})
    return {'available': True, 'switches': out, 'missing': sorted(set(seats) - found, key=_natural)}
