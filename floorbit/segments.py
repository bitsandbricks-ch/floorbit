"""Network segments: a VLAN and its IP range (issue #946, docs/segments.md).

A segment says which VLAN an IP is on, so a check-in can ask the switches for that one PC in that
one VLAN (issue #947) instead of walking every table. Lookups are opt-in per segment and every
segment starts with them **off** (Mike, 2026-11-19): nothing gets asked of the switches by surprise.

Segments come from discovery (a switch's or router's VLAN interface with an address, see
``svis`` in floorbit/telemetry/state.py) or are added by hand. A proposal from discovery never
overwrites a segment someone changed by hand.

Stored in the event's data as ``segments``: a list of
``{id, vlan, network, name, lookups, source ('discovery' | 'manual'), device, if_index, edited}``.
"""
import ipaddress
import re
import secrets

KEY = 'segments'
MAX = 512


class SegmentError(ValueError):
    status = 400


class NotFound(SegmentError):
    status = 404


def _load():
    from .store import load_data
    data = load_data()
    found = data.get(KEY)
    return data, [s for s in found if isinstance(s, dict)] if isinstance(found, list) else []


def _save(data, segments):
    from .store import save_data
    data[KEY] = segments[:MAX]
    save_data(data)


def _lock():
    from .blueprints.inventory import data_lock
    return data_lock


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


def all_segments():
    """Every segment, VLAN order."""
    return sorted(_load()[1], key=lambda s: (s.get('vlan') or 0, s.get('network') or ''))


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


def create(body):
    body = body if isinstance(body, dict) else {}
    seg = {'id': 'seg-' + secrets.token_hex(4), 'vlan': _vlan(body.get('vlan')),
           'network': _network(body.get('network')), 'name': _name(body.get('name')),
           'lookups': bool(body.get('lookups', False)), 'source': 'manual', 'edited': True}
    with _lock():
        data, segments = _load()
        if len(segments) >= MAX:
            raise SegmentError(f'At most {MAX} segments.')
        if any(s.get('network') == seg['network'] for s in segments):
            raise SegmentError('There is already a segment for this IP range.')
        segments.append(seg)
        _save(data, segments)
    return seg


def update(seg_id, body):
    body = body if isinstance(body, dict) else {}
    with _lock():
        data, segments = _load()
        seg = next((s for s in segments if s.get('id') == seg_id), None)
        if seg is None:
            raise NotFound('No such segment.')
        changed = {}
        if 'vlan' in body:
            changed['vlan'] = _vlan(body['vlan'])
        if 'network' in body:
            changed['network'] = _network(body['network'])
            if any(s is not seg and s.get('network') == changed['network'] for s in segments):
                raise SegmentError('There is already a segment for this IP range.')
        if 'name' in body:
            changed['name'] = _name(body['name'])
        if 'lookups' in body:
            changed['lookups'] = bool(body['lookups'])
        # Turning lookups on or off is not an edit of the facts: discovery may still correct those.
        if set(changed) - {'lookups'}:
            changed['edited'] = True
        seg.update(changed)
        _save(data, segments)
    return seg


def delete(seg_id):
    with _lock():
        data, segments = _load()
        kept = [s for s in segments if s.get('id') != seg_id]
        if len(kept) == len(segments):
            raise NotFound('No such segment.')
        _save(data, kept)
    return {'deleted': seg_id}


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


def take_proposals(data=None):
    """Add what discovery found, and correct discovery's own segments; a segment changed by hand
    stays as it is, and lookups stay as they were (new ones start off). Returns {added, updated}."""
    found = proposals(data)
    added = updated = 0
    with _lock():
        stored, segments = _load()
        by_network = {s.get('network'): s for s in segments}
        for p in found:
            seg = by_network.get(p['network'])
            if seg is None:
                if len(segments) >= MAX:
                    break
                seg = {'id': 'seg-' + secrets.token_hex(4), **p, 'lookups': False, 'source': 'discovery',
                       'edited': False}
                segments.append(seg)
                by_network[p['network']] = seg
                added += 1
            elif not seg.get('edited'):
                before = dict(seg)
                seg.update({k: p[k] for k in ('vlan', 'name', 'device', 'if_index') if p.get(k) not in (None, '')})
                updated += seg != before
        if added or updated:
            _save(stored, segments)
    return {'added': added, 'updated': updated, 'found': len(found)}
