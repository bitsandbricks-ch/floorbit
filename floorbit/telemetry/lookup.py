"""One PC's switch port, asked on the local agent with single SNMP GETs (issue #947, docs/segments.md).

The hosted Floorbit names the core with the VLAN interface and the switches to ask, in order (the
seat's section, then its block, then the rest on the VLAN). The agent has the logins (its telemetry
targets), so they never travel with the request.

The answer is the first switch that learned the MAC on a port that isn't an uplink: a trunk, an
LLDP or CDP neighbour, or a port with more than ``UPLINK_MACS`` MACs in the telemetry picture. Each
switch along the path learns the MAC on its uplink first, so uplinks are skipped, not answers.
"""
import time

from . import snmpget

UPLINK_MACS = 4
MAX_SWITCHES = 64        # a lookup asks at most this many switches: never the whole hall at once


def _uplinks(dev):
    """ifIndex keys of ``dev``'s ports that lead to other switches, from what the picture knows."""
    if dev is None:
        return set()
    from .clients import uplinks
    ups, _counts = uplinks(dev, UPLINK_MACS)
    ups = {str(u) for u in ups}
    ups |= {str(i) for i, facts in dev.if_facts.items() if facts.get('mode') == 'trunk'}
    return ups


def find(req, targets, state=None, get=snmpget.get, log=None):
    """``req``: {ip, vlan, if_index, core, switches: [names], mac?}. Returns {mac, switch, port,
    if_index, asked, skipped, errors, took_ms}; ``switch`` is None when no switch knew the MAC."""
    started = time.monotonic()
    by_name = {str(t.get('name')): t for t in targets or [] if t.get('name')}
    vlan = int(req['vlan'])
    from ..sources import normalise_mac
    out = {'mac': normalise_mac(req.get('mac')) or None, 'switch': None, 'port': None,
           'if_index': None, 'asked': [], 'skipped': [], 'errors': []}

    def ask(fn, name, *args):
        target = by_name.get(name)
        if target is None:
            out['errors'].append({'switch': name, 'error': 'not among the devices this agent collects from'})
            return None
        try:
            return fn({**target, 'name': name}, *args, get=get)
        except snmpget.SnmpError as exc:
            out['errors'].append({'switch': name, 'error': str(exc)[:200]})
            return None

    if not out['mac']:
        core = str(req.get('core') or '')
        out['mac'] = ask(snmpget.mac_of_ip, core, req.get('if_index'), req.get('ip')) if core else None
        if out['mac'] is None:
            out['took_ms'] = int((time.monotonic() - started) * 1000)
            return out
    for name in list(dict.fromkeys(str(n) for n in req.get('switches') or []))[:MAX_SWITCHES]:
        if name not in by_name:
            continue                     # another agent's: it answers for its own
        out['asked'].append(name)
        if_index = ask(snmpget.port_of_mac, name, out['mac'], vlan)
        if if_index is None:
            continue
        dev = state.find(name) if state is not None else None
        if str(if_index) in _uplinks(dev):
            out['skipped'].append({'switch': name, 'if_index': if_index})
            continue
        named = (dev.port_name(if_index) or (dev.if_facts.get(str(if_index)) or {}).get('name')) if dev else None
        out.update(switch=name, if_index=if_index, port=named or None)
        break
    out['took_ms'] = int((time.monotonic() - started) * 1000)
    if log:
        where = f'{out["switch"]} {out["port"] or out["if_index"]}' if out['switch'] else 'not found'
        log(f'lookup {req.get("ip") or out["mac"]} in VLAN {vlan}: {where}, asked {len(out["asked"])} switches'
            + (f', skipped {len(out["skipped"])} uplinks' if out['skipped'] else '') + f' in {out["took_ms"]} ms')
    return out
