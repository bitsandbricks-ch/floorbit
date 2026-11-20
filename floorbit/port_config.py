"""Seat port config check from the config backups (issue #1059).

Most doors-open trouble on access switches is config, not hardware: a seat port without PortFast
takes about 30 s to come up, a missing BPDU guard lets a player's own switch loop a block, no storm
control lets one PC flood the VLAN, and a port in another access VLAN puts a player in the wrong
range. Floorbit has what it needs to check that before doors open, without logging in to a switch:
the latest config copy of each switch (floorbit/config_backup.py) and which ports are seat ports
(the seat mapping).

The rules are data (``RULES``), for Cisco IOS / IOS-XE style configs: a rule passes on a port when
one of its ``port`` patterns matches a line of the port's interface block, or one of its ``global``
patterns matches a line outside any block (``spanning-tree portfast default``). Rules can be turned
off for an event (``data['port_check']['off']``): an event without storm control says so once.
Besides the rules, the seat ports of one switch should share one access VLAN; the odd ones out are
listed with the VLAN most of them use.
"""
from __future__ import annotations

import re
import threading

from . import config_backup

KEY = 'port_check'
RULES = (
    {'id': 'portfast', 'label': 'PortFast', 'fix': 'spanning-tree portfast',
     'port': (r'^spanning-tree portfast\b(?! disable)',),
     'global': (r'^spanning-tree portfast (edge )?default\b',)},
    {'id': 'bpduguard', 'label': 'BPDU guard', 'fix': 'spanning-tree bpduguard enable',
     'port': (r'^spanning-tree bpduguard enable\b',),
     'global': (r'^spanning-tree portfast (edge )?bpduguard default\b',)},
    {'id': 'storm', 'label': 'storm control', 'fix': 'storm-control broadcast level 1.00',
     'port': (r'^storm-control broadcast level\b',), 'global': ()},
    {'id': 'access', 'label': 'access mode', 'fix': 'switchport mode access',
     'port': (r'^switchport mode access\b',), 'global': ()},
)
RULE_IDS = (*(r['id'] for r in RULES), 'vlan')
RANGES_PER_LINE = 5          # IOS takes at most five ranges in one ``interface range``
_compiled = {r['id']: ([re.compile(p) for p in r['port']], [re.compile(p) for p in r['global']]) for r in RULES}
_parsed = {}                 # (switch, copy id) -> parsed config; copies never change
_lock = threading.Lock()


class PortCheckError(ValueError):
    pass


_LONG = re.compile(r'^([A-Za-z-]+)\s*(\d[\d/.:]*)$')


def port_key(name):
    """``GigabitEthernet1/0/3`` and ``Gi1/0/3`` are the same port: the kind's first two letters
    (three for TwentyFiveGigE, which would clash with TwoGigabitEthernet) and the numbers."""
    m = _LONG.match(str(name or '').strip())
    if not m:
        return str(name or '').strip().lower()
    kind = m.group(1).lower()
    short = 'twe' if kind.startswith('twe') else kind[:2]
    return f'{short}{m.group(2)}'


def parse(text):
    """``(interfaces, globals)``: the lines of each ``interface`` block by port key (with the name
    as written), and the lines outside any block."""
    interfaces, globals_ = {}, []
    current = None
    for raw in (text or '').splitlines():
        line = raw.rstrip()
        if not line or line.startswith('!'):
            current = None if line.startswith('!') else current
            continue
        if line.startswith(' ') and current is not None:
            current['lines'].append(line.strip())
        elif line.startswith('interface '):
            name = line.split(None, 1)[1].strip()
            current = {'name': name, 'lines': []}
            interfaces[port_key(name)] = current
        else:
            current = None
            globals_.append(line.strip())
    return interfaces, globals_


def _config(switch):
    copies = config_backup.history(switch)['copies']
    if not copies:
        return None, None
    last = copies[0]
    key = (switch, last['id'])
    with _lock:
        if key not in _parsed:
            if len(_parsed) > 500:
                _parsed.clear()
            _parsed[key] = parse(config_backup.text(switch, last['id']) or '')
        return last, _parsed[key]


def off(data):
    raw = data.get(KEY) if isinstance(data.get(KEY), dict) else {}
    return [r for r in raw.get('off') or [] if r in RULE_IDS]


def set_off(data, rules):
    if not isinstance(rules, list) or any(r not in RULE_IDS for r in rules):
        raise PortCheckError('Pick the rules to turn off from the list.')
    data[KEY] = {**(data.get(KEY) if isinstance(data.get(KEY), dict) else {}), 'off': sorted(set(rules))}
    return off(data)


def _vlan(lines):
    for line in lines:
        m = re.match(r'^switchport access vlan (\d+)$', line)
        if m:
            return int(m.group(1))
    return 1    # IOS: an access port without the line is in VLAN 1


def _ranges(names):
    """``Gi1/0/1 - 4`` for runs of neighbouring ports, in order."""
    def split(name):
        m = re.match(r'^(.*?)(\d+)$', name)
        return (m.group(1), int(m.group(2))) if m else (name, None)
    out, run = [], None
    for name in sorted(names, key=lambda n: (split(n)[0], split(n)[1] or 0)):
        base, n = split(name)
        if run and n is not None and run[0] == base and run[2] == n - 1:
            run[2] = n
            continue
        if run:
            out.append(run)
        run = [base, n, n, name]
    if run:
        out.append(run)
    return [r[3] if r[1] is None or r[1] == r[2] else f'{r[0]}{r[1]} - {r[2]}' for r in out]


def fix_lines(ports, commands):
    """The config to paste: ``interface range`` lines of at most five ranges, then the commands."""
    ranges = _ranges(ports)
    out = []
    for i in range(0, len(ranges), RANGES_PER_LINE):
        out.append('interface range ' + ' , '.join(ranges[i:i + RANGES_PER_LINE]))
        out += [f' {c}' for c in commands]
    return out


def check(data, mapping):
    """Every switch with seat ports: its last copy, the seat ports found in it, and per rule the seat
    ports that break it, with the config that fixes them. Switches with seat ports but no copy yet are
    listed under ``no_copy``."""
    disabled = set(off(data))
    seats = {}
    for seat, entry in (mapping or {}).items():
        entry = entry or {}
        switch, port = str(entry.get('switch') or ''), str(entry.get('port') or '')
        if switch and port:
            seats.setdefault(switch, {})[port_key(port)] = str(seat)
    switches, no_copy = [], []
    for switch in sorted(seats, key=str.lower):
        last, parsed = _config(switch) if config_backup.NAME_RE.match(switch) else (None, None)
        if last is None:
            no_copy.append(switch)
            continue
        interfaces, globals_ = parsed
        found = {k: interfaces[k] for k in seats[switch] if k in interfaces}
        findings = []
        for rule in RULES:
            if rule['id'] in disabled:
                continue
            port_res, global_res = _compiled[rule['id']]
            if any(p.match(g) for p in global_res for g in globals_):
                continue
            bad = [i['name'] for i in found.values() if not any(p.match(ln) for p in port_res for ln in i['lines'])]
            if bad:
                findings.append({'rule': rule['id'], 'label': rule['label'], 'ports': _ranges(bad), 'count': len(bad),
                                 'fix': fix_lines(bad, [rule['fix']])})
        if 'vlan' not in disabled and found:
            vlans = {k: _vlan(i['lines']) for k, i in found.items()}
            counts = {}
            for v in vlans.values():
                counts[v] = counts.get(v, 0) + 1
            usual = max(counts, key=lambda v: (counts[v], -v))
            odd = [found[k]['name'] for k, v in vlans.items() if v != usual]
            if odd and counts[usual] > len(odd):   # no majority, no guess
                findings.append({'rule': 'vlan', 'label': f'VLAN {usual}', 'ports': _ranges(odd), 'count': len(odd),
                                 'vlan': usual, 'fix': fix_lines(odd, [f'switchport access vlan {usual}'])})
        switches.append({'switch': switch, 'copy': {'id': last['id'], 'at': last.get('at')},
                         'seat_ports': len(seats[switch]), 'checked': len(found), 'findings': findings})
    return {'switches': switches, 'no_copy': no_copy, 'off': sorted(disabled),
            'rules': [{'id': r['id'], 'label': r['label'], 'fix': r['fix']} for r in RULES]
            + [{'id': 'vlan', 'label': 'One access VLAN', 'fix': 'switchport access vlan <n>'}]}


def problems(result):
    """``to look at`` items: one per switch and rule, or one for a rule every checked switch breaks
    on every seat port (the event doesn't use it: say it once, or turn the rule off)."""
    checked = [s for s in result['switches'] if s['checked']]
    out = []
    everywhere = set()
    for rule in RULES:
        if len(checked) > 1 and all(any(f['rule'] == rule['id'] and f['count'] == s['checked'] for f in s['findings'])
                                    for s in checked):
            everywhere.add(rule['id'])
            out.append({'id': f"portcheck:all:{rule['id']}", 'switch': None,
                        'title': f"No switch has {rule['label']} on its seat ports",
                        'where': 'Fix it, or turn the rule off under Switch configs'})
    for s in checked:
        for f in s['findings']:
            if f['rule'] in everywhere:
                continue
            ports = 'seat port' if f['count'] == 1 else 'seat ports'
            if f['rule'] == 'vlan':
                title = f"{s['switch']}: {f['count']} {ports} not in VLAN {f['vlan']}"
            else:
                title = f"{s['switch']}: {f['count']} {ports} without {f['label']}"
            out.append({'id': f"portcheck:{s['switch']}:{f['rule']}", 'switch': s['switch'], 'title': title,
                        'where': ', '.join(f['ports'][:4]) + (', …' if len(f['ports']) > 4 else '')})
    return out
