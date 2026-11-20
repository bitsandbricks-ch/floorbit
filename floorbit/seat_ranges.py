"""Seats whose PC got an address from another switch stack's range (issue #1062).

At an event each switch stack has its own seat ranges, each policy-routed to its firewall
(floorbit/firewalls.py); stacks come in sets (a colour, a switch type) that are inventory groups. A
seat patched to the wrong port, a port in the wrong VLAN, or a player's own router puts a PC in
another stack's range: it works, but on the wrong firewall, and the firewall view and traffic per
range are quietly wrong.

Nothing needs setting up: a switch's range is the one most PCs behind it are in right now, once at
least ``GUESS_SEATS`` of them are and they make ``GUESS_SHARE`` of its PCs in a range. Where DHCP
hands out addresses regardless of the switch, no range is that clear and nothing is flagged. A
range can also name the switches or switch groups it is for (``switches``); that wins over the
guess, and a seat behind them outside all their ranges is flagged (or a router of its own, outside
every range). When several seats behind one switch are off at once, that is one item for the
switch: its VLAN, not the seats.

Seat IPs never leave this module, like in floorbit/firewalls.py: the items name ranges only.
"""
from __future__ import annotations

import ipaddress

from . import firewalls, inventory, inventory_scope
from .seatmap import _natural

ONE_SWITCH = 3      # this many seats of one switch off at once: one item for the switch
MOST = 0.5          # more than this share of a planned switch's seats off: the plan is wrong, not the seats
GUESS_SEATS = 3     # a switch's range from its seats: at least this many PCs in it
GUESS_SHARE = 0.6   # and this share of the switch's PCs that are in any range


def _planned(data, nets):
    """{switch name (lower): [(row, net)]} for the switches the ranges name, directly or through a
    group they are in, and {range cidr: label} saying what each range is for."""
    groups = {g['id']: g for g in inventory_scope.groups(data)}
    devices = inventory.devices(data)
    names = {d['id']: d['name'] for d in devices}
    out, label = {}, {}
    for row, net in nets:
        wanted = set(row.get('switches') or [])
        if not wanted:
            continue
        label[row['cidr']] = ', '.join(sorted((names.get(i) or (groups.get(i) or {}).get('name') or '?')
                                              for i in wanted))
        for dev in devices:
            chain = {g['id'] for g in inventory_scope.chain(data, dev.get('group_id'))}
            if dev['id'] in wanted or chain & wanted:
                out.setdefault(dev['name'].lower(), []).append((row, net))
    return out, label


def _guessed(seats, nets, planned):
    """{switch (lower): [(row, net)]}: the range most PCs behind a switch no range names are in."""
    counts = {}
    for _seat, entry, ip in seats:
        key = str(entry.get('switch') or '').lower()
        if not key or key in planned:
            continue
        row = firewalls._match(ip, nets)
        if row is not None:
            counts.setdefault(key, {}).setdefault(row['cidr'], 0)
            counts[key][row['cidr']] += 1
    by_cidr = {row['cidr']: (row, net) for row, net in nets}
    out = {}
    for key, per in counts.items():
        best = max(per, key=lambda c: (per[c], c))
        if per[best] >= GUESS_SEATS and per[best] >= GUESS_SHARE * sum(per.values()):
            out[key] = [by_cidr[best]]
    return out


def misplaced(data, mapping, checked=None):
    """``[{seat, switch, port, expected: [cidr], actual: cidr | None, actual_for: str, guessed}]``
    for the seats whose IP is outside their switch's ranges. ``mapping``: the merged seat mapping
    (integrations/seat_sources.py). ``checked``: a dict to count the seats looked at, by switch."""
    nets = firewalls._nets(data)
    if not nets:
        return []
    seats = []
    for seat, entry in (mapping or {}).items():
        entry = entry or {}
        if not entry.get('switch'):
            continue
        try:
            ip = ipaddress.ip_address(str(entry.get('ip_address') or '').strip())
        except ValueError:
            continue
        seats.append((seat, entry, ip))
    planned, label = _planned(data, nets)
    guessed = _guessed(seats, nets, planned)
    expected = {**guessed, **planned}
    out = []
    for seat, entry, ip in seats:
        key = str(entry['switch']).lower()
        if key not in expected:
            continue
        actual = firewalls._match(ip, nets)
        if key in guessed and actual is None:
            continue    # an address no range covers says nothing about a switch whose range is a guess
        if checked is not None:
            checked[key] = checked.get(key, 0) + 1
        if any(ip.version == net.version and ip in net for _row, net in expected[key]):
            continue
        out.append({'seat': str(seat).upper(), 'switch': str(entry['switch']), 'port': str(entry.get('port') or ''),
                    'expected': [row['cidr'] for row, _net in expected[key]],
                    'actual': actual['cidr'] if actual else None,
                    'actual_for': label.get(actual['cidr'], '') if actual else '',
                    'guessed': key in guessed})
    out.sort(key=lambda m: (m['switch'].lower(), _natural(m['seat'])))
    return out


def items(data, mapping):
    """The flagged seats as problem items ``{id, kind, title, where, seat, switch}``: one per seat, or
    one per switch when ``ONE_SWITCH`` or more of its seats are off. When most seats of a switch a
    range names are off, the range is set for the wrong switch: one item saying so."""
    checked = {}
    found = misplaced(data, mapping, checked)
    by_switch = {}
    for m in found:
        by_switch.setdefault(m['switch'].lower(), []).append(m)
    out = []
    for key in sorted(by_switch):
        ms = by_switch[key]
        switch = ms[0]['switch']
        if not ms[0]['guessed'] and len(ms) >= ONE_SWITCH and len(ms) > MOST * checked[key]:
            out.append({'id': f'range:plan:{key}', 'kind': 'range', 'seat': None, 'switch': switch,
                        'title': f'{switch}: {len(ms)} of {checked[key]} seats are outside its ranges',
                        'where': 'Check which ranges the switch is for, under Firewalls'})
        elif len(ms) >= ONE_SWITCH:
            out.append({'id': f'range:switch:{key}', 'kind': 'range', 'seat': None, 'switch': switch,
                        'title': f'{len(ms)} seats on {switch} are outside its range',
                        'where': f"Seats {', '.join(m['seat'] for m in ms)}: check the switch's VLAN"})
        else:
            out += [_seat_item(m) for m in ms]
    return out


def _seat_item(m):
    # A switch spread over many small ranges: the first few say enough.
    expected = ', '.join(m['expected'][:3]) + (', …' if len(m['expected']) > 3 else '')
    if m['actual'] is None:
        title = f"Seat {m['seat']} has an address outside every planned range"
    elif m['actual_for']:
        title = f"Seat {m['seat']} is in the range {m['actual']} of {m['actual_for']}"
    else:
        title = f"Seat {m['seat']} is in the range {m['actual']}"
    uses = f"most of {m['switch']} is in {expected}" if m['guessed'] else f"{m['switch']} uses {expected}"
    where = f"{m['port']}: {uses}" if m['port'] else uses
    return {'id': f"range:seat:{m['seat']}", 'kind': 'range', 'seat': m['seat'], 'switch': m['switch'],
            'title': title, 'where': where}
