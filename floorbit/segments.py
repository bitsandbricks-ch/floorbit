"""Network segments: a VLAN and its IP range (issue #946, docs/segments.md).

A segment says which VLAN an IP is on, so a check-in can ask the switches for that one PC in that
one VLAN (issue #947) instead of walking every table. Lookups are opt-in per segment and every
segment starts with them **off** (Mike, 2026-11-19): nothing gets asked of the switches by surprise.

Segments are the inventory's "VLAN or IP range" entries (issue #1029, floorbit/inventory_types.py)
that have both a VLAN and a prefix; their ``lookups`` field turns lookups on. Discovery gives a
network on a switch's or router's VLAN interface (``svis`` in floorbit/telemetry/state.py) its VLAN
(floorbit/inventory_discovery.py), so those become segments by themselves; a field someone changed
by hand stays as they set it (the inventory's sync rules).
"""
import ipaddress
import re

FEED = 'discovery'          # discovery's inventory feed (inventory_discovery.PLUGIN)
TYPE = 'vlan'               # the inventory type (inventory_types.BUILTIN)


class SegmentError(ValueError):
    status = 400


def _network(value):
    try:
        net = ipaddress.ip_network(str(value or '').strip(), strict=False)
    except ValueError:
        raise SegmentError('Give the IP range as an address with its prefix, e.g. 10.10.0.0/22.') from None
    if net.version != 4 or net.prefixlen < 8 or net.prefixlen > 30:
        raise SegmentError('The IP range must be IPv4, between /8 and /30.')
    return str(net)


def _vlan(value):
    try:
        vlan = int(value)
    except (TypeError, ValueError):
        raise SegmentError('The VLAN must be a number from 1 to 4094.') from None
    if not 1 <= vlan <= 4094:
        raise SegmentError('The VLAN must be a number from 1 to 4094.')
    return vlan


def _name(value):
    return ' '.join(str(value or '').split())[:64]


def _segment(entry):
    """An inventory entry as a segment, or None when it has no usable VLAN and prefix."""
    fields = entry.get('fields') or {}
    try:
        vlan, network = _vlan(fields.get('vlan_id')), _network(fields.get('prefix'))
    except SegmentError:
        return None
    return {'id': entry['id'], 'vlan': vlan, 'network': network, 'name': entry.get('name') or '',
            'lookups': fields.get('lookups') == 'yes',
            'source': FEED if FEED in (entry.get('sources') or []) else 'manual'}


def all_segments(data=None):
    """Every segment, VLAN order."""
    from . import inventory_types
    if data is None:
        from .store import load_data
        data = load_data()
    found = [s for s in map(_segment, inventory_types.listing(data, TYPE)) if s]
    return sorted(found, key=lambda s: (s['vlan'], s['network']))


def lookups_on():
    """Whether any segment lets check-ins ask the switches."""
    return any(s['lookups'] for s in all_segments())


def for_ip(ip, segments=None):
    """The segment an IP is in (the narrowest range), or None."""
    try:
        address = ipaddress.ip_address(str(ip))
    except ValueError:
        return None
    best = None
    for seg in all_segments() if segments is None else segments:
        try:
            net = ipaddress.ip_network(seg['network'])
        except (KeyError, ValueError):
            continue
        if address in net and (best is None or net.prefixlen > ipaddress.ip_network(best['network']).prefixlen):
            best = seg
    return best


# ── from discovery ────────────────────────────────────────────────────────────────────────────

SVI = re.compile(r'^(?:vlan|vl|vlanif|vlan-interface|irb\.|bvi)\s*(\d{1,4})$', re.IGNORECASE)


def vlan_of_interface(name):
    """The VLAN of a VLAN interface's name (Vlan110, Vl110, irb.110, Vlanif110), or None."""
    found = SVI.match(str(name or '').strip())
    vlan = int(found.group(1)) if found else None
    return vlan if vlan and 1 <= vlan <= 4094 else None


def proposals(data=None):
    """What discovery found: one {vlan, network, name, device, if_index} per VLAN interface with an
    address, from each device's last discovery (data['inventory_discovered'][*]['svis'])."""
    from . import inventory
    if data is None:
        from .store import load_data
        data = load_data()
    found = data.get('inventory_discovered') if isinstance(data.get('inventory_discovered'), dict) else {}
    out = {}
    for dev_id, n in sorted(found.items()):
        if not isinstance(n, dict):
            continue
        dev = inventory.find(data, dev_id)
        names = {v.get('id'): v.get('name') for v in n.get('vlans') or [] if isinstance(v, dict)}
        for svi in n.get('svis') or []:
            try:
                vlan, network = _vlan(svi.get('vlan')), _network(svi.get('network'))
            except SegmentError:
                continue
            # The same range on two devices (a core pair): the first one names it.
            out.setdefault(network, {'vlan': vlan, 'network': network, 'name': _name(names.get(vlan)),
                                     'device': dev['name'] if dev else '', 'if_index': svi.get('if_index')})
    return list(out.values())
