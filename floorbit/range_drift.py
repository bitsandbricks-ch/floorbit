"""Seats whose machine is in another block's range (issue #1062, docs/firewalls.md).

At an event where each seat range is policy-routed to its own firewall, a seat patched to the wrong
port, a port in the wrong VLAN, or a player's own switch puts the PC into another block's range: it
works, but on the wrong firewall, and the firewall view and traffic per block are quietly wrong.

Nothing to set up: a block's range is the firewall range most of its seats are in right now (at
least ``MIN_SEATS`` of them and ``SHARE`` of those with a range). A seat of that block whose machine
is in another range is flagged; several seats of one block in the same other range are one problem.
The machines' addresses come from the IP and MAC history (floorbit/endpoints.py) and never leave this
module: problems name seats, blocks and ranges only.
"""
import ipaddress
import threading
import time

from .store import load_data

MIN_SEATS = 3
SHARE = 0.6
EVERY = 30               # seconds a result is kept: Problems asks on every refresh
_lock = threading.Lock()
_cache = {'at': 0.0, 'found': None}


def _blocks(data):
    """{SEAT: (block id, block label)} from the floor plan's seat blocks."""
    from . import seat_names
    out = {}
    for i, block in enumerate(data.get('seat_blocks') or []):
        seats = seat_names.seats(block)
        if not seats:
            continue
        label = block.get('name') or (f'{seats[0]} to {seats[-1]}' if len(seats) > 1 else seats[0])
        for seat in seats:
            out[str(seat).upper()] = (str(block.get('id') or i), str(label))
    return out


def _range_label(row):
    return f"{row['cidr']} ({row['name']})" if row.get('name') else row['cidr']


def find(data=None, seat_ips=None):
    """``[{block, expected, found, seats}]``: per block, the seats in another range than the block's.
    ``seat_ips``: {seat: ip}; read from the IP and MAC history when None."""
    from . import firewalls
    data = load_data() if data is None else data
    nets = firewalls._nets(data)
    if not nets:
        return []
    if seat_ips is None:
        from . import endpoints
        seat_ips = endpoints.history().at_seats_now()
    blocks = _blocks(data)
    per_block = {}
    for seat, ip in seat_ips.items():
        place = blocks.get(str(seat).upper())
        try:
            addr = ipaddress.ip_address(str(ip).strip())
        except ValueError:
            continue
        row = firewalls._match(addr, nets)
        if place is None or row is None:
            continue             # a seat not on the plan, or an address no range covers: nothing to compare
        per_block.setdefault(place, []).append((str(seat).upper(), row))
    out = []
    for (_block_id, label), seats in per_block.items():
        counts = {}
        for _seat, row in seats:
            counts[row['id']] = counts.get(row['id'], 0) + 1
        best = max(counts, key=lambda k: counts[k])
        if counts[best] < MIN_SEATS or counts[best] / len(seats) < SHARE:
            continue             # no clear range for this block yet (few PCs, or a mixed block)
        expected = next(row for _s, row in seats if row['id'] == best)
        wrong = {}
        for seat, row in seats:
            if row['id'] != best:
                wrong.setdefault(row['id'], (row, []))[1].append(seat)
        from .page_index import _seat_key
        for row, names in wrong.values():
            out.append({'block': label, 'expected': _range_label(expected), 'found': _range_label(row),
                        'seats': sorted(names, key=_seat_key)})
    out.sort(key=lambda f: (f['block'], f['found']))
    return out


def cached(now=None):
    now = time.time() if now is None else now
    with _lock:
        if _cache['found'] is not None and now - _cache['at'] < EVERY:
            return _cache['found']
    try:
        found = find()
    except Exception as exc:  # noqa: BLE001  # the history's database away: no check, Problems still answers
        print(f'[range-drift] {exc}')
        found = []
    with _lock:
        _cache.update(at=now, found=found)
    return found


def reset():
    with _lock:
        _cache.update(at=0.0, found=None)


def problems():
    """The Problems page's items: one per block and range it shouldn't be in."""
    from urllib.parse import quote
    out = []
    for f in cached():
        seats = f['seats']
        if len(seats) == 1:
            title = f"Seat {seats[0]} is in {f['found']}, not its block's {f['expected']}"
        else:
            title = f"{len(seats)} seats of block {f['block']} are in {f['found']}, not {f['expected']}"
        out.append({'id': f"range:{f['block']}:{f['found']}", 'kind': 'range', 'level': 'warn', 'title': title,
                    'where': ', '.join(seats[:12]) + (' …' if len(seats) > 12 else ''), 'since': None,
                    'link': f'/plan?seat={quote(seats[0])}', 'seats': seats})
    return out
