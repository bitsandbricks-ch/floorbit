"""Seats whose PC got an address from another block's range (issue #1062).

At an event each seat range is policy-routed to its own firewall (floorbit/firewalls.py). A seat
patched to the wrong port, a port in the wrong VLAN, or a player's own router puts a PC in another
block's range: it works, but on the wrong firewall, and the firewall view and traffic per block are
quietly wrong.

A range says which seat blocks it is for (``blocks``, optional). Only seats of those blocks are
checked: where DHCP hands out addresses without regard to blocks, nobody sets ``blocks`` and nothing
is flagged. A seat of such a block whose IP is in none of its block's ranges is flagged with the
range it is in instead (or none: a router of its own). When several seats behind one switch are off
at once, the cause is the switch or its VLAN, so that is one item, not one per seat.

Seat IPs never leave this module, like in floorbit/firewalls.py: the items name ranges only.
"""
from __future__ import annotations

import ipaddress

from . import firewalls
from .seat_names import block_rows
from .seatmap import _natural

ONE_SWITCH = 3      # this many seats of one switch off at once: one item for the switch
MOST = 0.5          # more than this share of a block's seats off: the plan is wrong, not the seats


def _blocks(data):
    names, where = {}, {}
    for block in data.get('seat_blocks') or []:
        if not isinstance(block, dict) or not block.get('id'):
            continue
        names[block['id']] = block.get('name') or block['id']
        for row in block_rows(block):
            for seat in row:
                where[str(seat).upper()] = block['id']
    return names, where


def misplaced(data, mapping, checked=None):
    """``[{seat, block, switch, port, expected: [cidr], actual: cidr | None, actual_blocks: [name]}]``
    for the seats of blocks with planned ranges whose IP is outside them. ``mapping``: the merged seat
    mapping (integrations/seat_sources.py). ``checked``: a dict to count the seats looked at, by block
    name."""
    nets = firewalls._nets(data)
    expected = {}
    for row, net in nets:
        for block_id in row.get('blocks') or []:
            expected.setdefault(block_id, []).append((row, net))
    if not expected:
        return []
    names, where = _blocks(data)
    out = []
    for seat, entry in (mapping or {}).items():
        entry = entry or {}
        block_id = where.get(str(seat).upper())
        if block_id not in expected:
            continue
        try:
            ip = ipaddress.ip_address(str(entry.get('ip_address') or '').strip())
        except ValueError:
            continue
        if checked is not None:
            checked[names[block_id]] = checked.get(names[block_id], 0) + 1
        if any(ip.version == net.version and ip in net for _row, net in expected[block_id]):
            continue
        actual = firewalls._match(ip, nets)
        out.append({'seat': str(seat).upper(), 'block': names[block_id],
                    'switch': str(entry.get('switch') or ''), 'port': str(entry.get('port') or ''),
                    'expected': [row['cidr'] for row, _net in expected[block_id]],
                    'actual': actual['cidr'] if actual else None,
                    'actual_blocks': [names[b] for b in (actual or {}).get('blocks') or [] if b in names]})
    out.sort(key=lambda m: (m['switch'].lower(), _natural(m['seat'])))
    return out


def items(data, mapping):
    """The flagged seats as problem items ``{id, kind, title, where, seat, switch}``: one per seat, or
    one per switch when ``ONE_SWITCH`` or more of its seats are off. When most of a block is off,
    the block's ranges are wrong (or DHCP doesn't hand out per block): one item for the block."""
    checked = {}
    found = misplaced(data, mapping, checked)
    out = []
    per_block = {}
    for m in found:
        per_block.setdefault(m['block'], []).append(m)
    wrong_plan = {b for b, ms in per_block.items() if len(ms) >= ONE_SWITCH and len(ms) > MOST * checked[b]}
    for block in sorted(wrong_plan, key=_natural):
        n, of = len(per_block[block]), checked[block]
        out.append({'id': f'range:block:{block}', 'kind': 'range', 'seat': None, 'switch': '',
                    'block': block, 'title': f'Block {block}: {n} of {of} seats are outside its ranges',
                    'where': 'Check which ranges the block is for, under Firewalls'})
    found = [m for m in found if m['block'] not in wrong_plan]
    by_switch = {}
    for m in found:
        if m['switch']:
            by_switch.setdefault(m['switch'].lower(), []).append(m)
    grouped = {k for k, ms in by_switch.items() if len(ms) >= ONE_SWITCH}
    for key in sorted(grouped):
        ms = by_switch[key]
        switch = ms[0]['switch']
        out.append({'id': f'range:switch:{key}', 'kind': 'range', 'seat': None, 'switch': switch,
                    'title': f'{len(ms)} seats on {switch} are outside their block\'s range',
                    'where': f"Seats {', '.join(m['seat'] for m in ms)}: check the switch's VLAN"})
    for m in found:
        if m['switch'].lower() in grouped:
            continue
        # A block spread over many small ranges: the first few say enough.
        expected = ', '.join(m['expected'][:3]) + (', …' if len(m['expected']) > 3 else '')
        if m['actual'] is None:
            title = f"Seat {m['seat']} has an address outside every planned range"
        elif m['actual_blocks']:
            title = f"Seat {m['seat']} is in block {', '.join(m['actual_blocks'])}'s range {m['actual']}"
        else:
            title = f"Seat {m['seat']} is in the range {m['actual']}"
        port = ' '.join(x for x in (m['switch'], m['port']) if x)
        where = f"{port}: block {m['block']} uses {expected}" if port else f"Block {m['block']} uses {expected}"
        out.append({'id': f"range:seat:{m['seat']}", 'kind': 'range', 'seat': m['seat'], 'switch': m['switch'],
                    'title': title, 'where': where})
    return out
