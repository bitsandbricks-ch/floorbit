"""Rough port areas: which seats a range of switch ports goes to, before anyone knows the exact port.

The crew usually knows the layout in batches: a 40-port access switch serves its row in four
batches of 10, ports 1-10 to seats A-1..A-10, 11-20 to A-11..A-20, and so on. That is not enough
to name a seat's port, but it is enough to:

- say the likely area for a port, an IP or a MAC (walking the row, unexplained clients);
- catch a check-in that learned a port far from its seat (a wrong PIN, a swapped card): the
  ``area`` kind in ``integrations.checkin.port_conflicts``;
- narrow what the crew looks at when a port comes up.

An exact mapping (a cable, or a port learned from a PIN check-in) always wins; an area only fills
in where neither says anything. Areas live in ``data.json`` with the plan (``port_areas``), so a
backup carries them.
"""
import re
import threading
import time
import uuid

from .store import load_data, save_data

KEY = 'port_areas'
MAX_AREAS = 2000
MAX_PORTS = 128      # one switch's ports in one quick entry
_lock = threading.Lock()


class AreaError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def port_number(port):
    """The port's number on its switch: the last number in its name. 'Gi1/0/14' -> 14."""
    found = re.findall(r'\d+', str(port or ''))
    return int(found[-1]) if found else None


def split_seat(seat):
    """'A-12' -> ('A-', 12); '17' -> ('', 17); None when the seat has no number at the end."""
    m = re.match(r'^(.*?)(\d+)$', str(seat or '').strip().upper())
    return (m.group(1), int(m.group(2))) if m else None


def seat_range(start, count):
    """``count`` seats from ``start`` on: 'A-11', 3 -> ['A-11', 'A-12', 'A-13']."""
    parts = split_seat(start)
    if not parts:
        raise AreaError(f'"{start}" is not a seat number like A-11.')
    prefix, first = parts
    return [f'{prefix}{n}' for n in range(first, first + count)]


def all_areas(data=None):
    data = load_data() if data is None else data
    return list(data.get(KEY) or [])


def _label(area):
    seats = area['seats']
    return f'{seats[0]}..{seats[-1]}' if len(seats) > 1 else (seats[0] if seats else '')


def quick_entry(switch, starts, size=10, first_port=1, count=None, known=None):
    """Areas for one switch, one per batch of ``size`` ports from ``first_port``: batch i goes to
    ``count`` seats (default ``size``) from ``starts[i]``. An empty start skips that batch (uplinks,
    APs). ``known``: the plan's seat numbers, to refuse a typo."""
    switch = str(switch or '').strip()
    if not switch:
        raise AreaError('Name the switch.')
    try:
        size, first_port = int(size), int(first_port)
        count = size if count in (None, '') else int(count)
    except (TypeError, ValueError):
        raise AreaError('Batch size, first port and seats per batch are numbers.') from None
    if not 1 <= size <= MAX_PORTS or not 1 <= count <= MAX_PORTS or first_port < 0:
        raise AreaError(f'A batch is 1 to {MAX_PORTS} ports.')
    starts = [str(s or '').strip().upper() for s in (starts or [])]
    if len(starts) * size > MAX_PORTS:
        raise AreaError(f'One switch has at most {MAX_PORTS} ports here.')
    out = []
    for i, start in enumerate(starts):
        if not start:
            continue
        seats = seat_range(start, count)
        if known is not None:
            missing = [s for s in seats if s not in known]
            if missing:
                if len(missing) == 1:
                    raise AreaError(f'{missing[0]} is not on the plan.')
                raise AreaError(f'{", ".join(missing[:3])} are not on the plan.')
        lo = first_port + i * size
        out.append({'switch': switch, 'first': lo, 'last': lo + size - 1, 'seats': seats})
    if not out:
        raise AreaError('Give a first seat for at least one batch.')
    return out


def replace_switch(switch, areas, by=None):
    """Put ``areas`` in place of everything known for ``switch``."""
    with _lock:
        data = load_data()
        kept = [a for a in data.get(KEY) or [] if a['switch'].lower() != switch.lower()]
        if len(kept) + len(areas) > MAX_AREAS:
            raise AreaError(f'Floorbit keeps at most {MAX_AREAS} port areas.')
        now = time.time()
        made = [{'id': uuid.uuid4().hex[:12], **a, 'label': _label(a), 'updated_at': now, 'by': by} for a in areas]
        data[KEY] = kept + made
        save_data(data)
    return made


def delete(area_id=None, switch=None):
    with _lock:
        data = load_data()
        rows = data.get(KEY) or []
        left = [a for a in rows if not ((area_id and a['id'] == area_id)
                                       or (switch and a['switch'].lower() == switch.lower()))]
        if len(left) == len(rows):
            return 0
        data[KEY] = left
        save_data(data)
    return len(rows) - len(left)


def area_for(switch, port, areas=None):
    """The area ``port`` of ``switch`` falls in, or None."""
    n = port_number(port)
    if n is None or not switch:
        return None
    sw = str(switch).lower().split('.')[0]
    for area in all_areas() if areas is None else areas:
        if area['switch'].lower().split('.')[0] == sw and area['first'] <= n <= area['last']:
            return area
    return None


def hint(switch, port, areas=None):
    """What the crew sees next to a port: ``{"label", "seats"}`` or None."""
    area = area_for(switch, port, areas)
    return {'label': area['label'], 'seats': area['seats']} if area else None

