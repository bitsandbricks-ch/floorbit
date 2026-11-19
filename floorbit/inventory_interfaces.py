"""The interfaces (ports) of an inventory device: switch ports, a server's NICs, a firewall's
interfaces, a VM's virtual NICs. See docs/inventory.md#interfaces.

They follow the inventory's rules (floorbit/inventory.py), per interface instead of per device:

- People add, change and remove them by hand (one, or a range like ``Gi1/0/1-48``).
- Plugins feed them: an inventory plugin sends ``interfaces`` with each device (NetBox), and the
  monitoring source's port list can be taken over for every device it knows (LibreNMS, telemetry).
  Each plugin's last values are kept in ``fed``; a field changed by hand while a plugin feeds it is
  locked until it is unlocked.
- A sync never deletes. An interface a plugin stops sending is flagged ``gone`` for that plugin;
  removing a fed one by hand hides it, so the next sync doesn't bring it back.

Stored on the device, under ``interfaces``, matched by name (case and spacing don't count).
"""
from __future__ import annotations

import contextlib
import ipaddress
import re
import uuid

FIELDS = ('type', 'speed_mbps', 'mac', 'ips', 'vlan', 'mode', 'description', 'enabled', 'mgmt', 'lag')
TYPES = ('copper', 'fiber', 'dac', 'virtual', 'lag', 'wireless', 'mgmt', 'other', '')
MODES = ('access', 'trunk', 'routed', '')
MAX_PER_DEVICE = 1024
MAX_RANGE = 512
MAX_IPS = 16
NAME_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9/._:@+-]{0,63}\Z')
MAC_RE = re.compile(r'^[0-9a-f]{12}\Z')
# "Gi1/0/1-48", "eth0-3", "1-24": a prefix and the number range at the end.
RANGE_RE = re.compile(r'^(?P<prefix>.*?)(?P<first>\d+)\s*-\s*(?P<last>\d+)$')


class InterfaceError(ValueError):
    """Bad input; the message is shown."""


def key(name):
    return re.sub(r'\s+', '', str(name or '')).lower()


def blank(name):
    return {'id': uuid.uuid4().hex[:12], 'name': name, 'type': '', 'speed_mbps': None, 'mac': '', 'ips': [],
            'vlan': None, 'mode': '', 'description': '', 'enabled': True, 'mgmt': False, 'lag': '',
            'origin': 'manual', 'refs': {}, 'fed': {}, 'locked': [], 'gone': [], 'hidden': False}


def clean_name(value):
    name = str(value or '').strip()
    if not NAME_RE.match(name):
        raise InterfaceError(f'{name or "(empty)"} is not an interface name (letters, digits and / . _ : - only)')
    return name


def _mac(value):
    raw = re.sub(r'[^0-9a-fA-F]', '', str(value or '')).lower()
    if not raw:
        return ''
    if not MAC_RE.match(raw):
        raise InterfaceError(f'{value} is not a MAC address')
    return ':'.join(raw[i:i + 2] for i in range(0, 12, 2))


def _ips(value):
    items = value if isinstance(value, list) else re.split(r'[,\s]+', str(value or ''))
    out = []
    for raw in items:
        raw = str(raw).strip()
        if not raw:
            continue
        try:
            out.append(str(ipaddress.ip_interface(raw)) if '/' in raw else str(ipaddress.ip_address(raw)))
        except ValueError:
            raise InterfaceError(f'{raw} is not an IP address') from None
    if len(out) > MAX_IPS:
        raise InterfaceError(f'At most {MAX_IPS} addresses per interface')
    return out


def _int(value, field, low, high):
    if value in (None, ''):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise InterfaceError(f'{field} is a whole number') from None
    if not low <= number <= high:
        raise InterfaceError(f'{field} must be between {low} and {high}')
    return number


def clean_field(field, value):
    if field == 'type':
        value = str(value or '').strip().lower()
        if value not in TYPES:
            raise InterfaceError(f"type must be one of {', '.join(t for t in TYPES if t)}")
        return value
    if field == 'mode':
        value = str(value or '').strip().lower()
        if value not in MODES:
            raise InterfaceError(f"mode must be one of {', '.join(m for m in MODES if m)}")
        return value
    if field == 'speed_mbps':
        return _int(value, 'speed_mbps', 1, 1_600_000)
    if field == 'vlan':
        return _int(value, 'vlan', 1, 4094)
    if field == 'mac':
        return _mac(value)
    if field == 'ips':
        return _ips(value)
    if field in ('enabled', 'mgmt'):
        if not isinstance(value, bool):
            raise InterfaceError(f'{field} is true or false')
        return value
    if field == 'description':
        value = str(value or '').strip()
        if '\n' in value:
            raise InterfaceError('description must be one line')
        return value[:200]
    if field == 'lag':
        value = str(value or '').strip()
        return clean_name(value) if value else ''
    raise InterfaceError(f'Unknown interface field: {field}')


def normalize(raw):
    """A stored interface (from a backup) checked and filled in."""
    out = blank(str(raw.get('name'))[:64])
    out['id'] = str(raw.get('id') or out['id'])[:40]
    for f in FIELDS:
        if f in raw:
            with contextlib.suppress(InterfaceError):
                out[f] = clean_field(f, raw[f])
    out['origin'] = str(raw.get('origin') or 'manual')[:40]
    refs = raw.get('refs') if isinstance(raw.get('refs'), dict) else {}
    out['refs'] = {str(k)[:40]: str(v)[:80] for k, v in refs.items()}
    fed = raw.get('fed') if isinstance(raw.get('fed'), dict) else {}
    out['fed'] = {str(p)[:40]: {f: v for f, v in vals.items() if f in FIELDS}
                  for p, vals in fed.items() if isinstance(vals, dict)}
    out['locked'] = [f for f in raw.get('locked') or [] if f in FIELDS]
    out['gone'] = [str(p)[:40] for p in raw.get('gone') or []][:20]
    out['hidden'] = bool(raw.get('hidden'))
    return out


def public(iface):
    out = {k: iface.get(k) for k in ('id', 'name', *FIELDS, 'origin', 'hidden')}
    out['sources'] = sorted(iface.get('refs') or {})
    out['locked'] = sorted(iface.get('locked') or [])
    out['gone'] = sorted(iface.get('gone') or [])
    out['fed'] = iface.get('fed') or {}
    return out


def listing(dev, include_hidden=False):
    from .blueprints.options import _natural
    items = [i for i in dev.get('interfaces') or [] if include_hidden or not i.get('hidden')]
    return sorted(items, key=lambda i: _natural(i['name']))


def find(dev, iface_id):
    return next((i for i in dev.get('interfaces') or [] if i['id'] == iface_id), None)


def by_name(dev, name):
    k = key(name)
    return next((i for i in dev.get('interfaces') or [] if key(i['name']) == k), None)


def expand(names):
    """``Gi1/0/1-48`` -> Gi1/0/1 ... Gi1/0/48. Several, split by commas or new lines."""
    out = []
    for part in re.split(r'[,\n]+', str(names or '')):
        part = part.strip()
        if not part:
            continue
        m = RANGE_RE.match(part)
        if m and m.group('prefix') and not m.group('prefix')[-1].isdigit():
            first, last = int(m.group('first')), int(m.group('last'))
            if last < first:
                raise InterfaceError(f'{part}: the range runs backwards')
            if last - first + 1 > MAX_RANGE:
                raise InterfaceError(f'{part}: at most {MAX_RANGE} interfaces at a time')
            out += [clean_name(f"{m.group('prefix')}{n}") for n in range(first, last + 1)]
        else:
            out.append(clean_name(part))
    if not out:
        raise InterfaceError('Name at least one interface')
    return list(dict.fromkeys(out))


# ── Hand edits ─────────────────────────────────────────────────────────────────────────────

def _values(body):
    return {f: clean_field(f, body[f]) for f in FIELDS if f in body}


def add(dev, body):
    """Add one or more interfaces by hand: ``{"names": "Gi1/0/1-48", <fields>}``. Returns the new
    ones; names the device already has are skipped (shown again if they were hidden)."""
    names = expand(body.get('names') or body.get('name'))
    values = _values(body)
    ifaces = dev.setdefault('interfaces', [])
    added = []
    for name in names:
        have = by_name(dev, name)
        if have is not None:
            if have.get('hidden'):
                have['hidden'] = False
                added.append(have)
            continue
        if len(ifaces) >= MAX_PER_DEVICE:
            raise InterfaceError(f'A device has at most {MAX_PER_DEVICE} interfaces')
        iface = {**blank(name), **values}
        ifaces.append(iface)
        added.append(iface)
    return added


def _fed_value(iface, field):
    for plugin in sorted(iface.get('refs') or {}):
        fed = (iface.get('fed') or {}).get(plugin) or {}
        if field in fed:
            return fed[field]
    return None


def update(dev, iface_id, body):
    """Hand edit of one interface: fields, ``name`` (hand-made only), ``unlock``. Returns changes."""
    iface = find(dev, iface_id)
    if iface is None:
        raise KeyError(iface_id)
    changed = []
    if 'name' in body and body['name'] != iface['name']:
        if iface.get('refs'):
            raise InterfaceError('A plugin feeds this interface by its name; rename it there')
        name = clean_name(body['name'])
        other = by_name(dev, name)
        if other is not None and other is not iface:
            raise InterfaceError(f'{dev["name"]} already has {name}')
        iface['name'] = name
        changed.append('name')
    for f, value in _values(body).items():
        if value != iface.get(f):
            iface[f] = value
            changed.append(f)
        fed = _fed_value(iface, f)
        if fed is not None and value != fed and f not in iface['locked']:
            iface['locked'].append(f)
    unlock = body.get('unlock') or []
    if not isinstance(unlock, list):
        raise InterfaceError('unlock is a list of field names')
    for f in unlock:
        if f in iface['locked']:
            iface['locked'].remove(f)
            fed = _fed_value(iface, f)
            if fed is not None:
                iface[f] = fed
            changed.append(f'unlock:{f}')
    if 'hidden' in body and bool(body['hidden']) != bool(iface.get('hidden')):
        iface['hidden'] = bool(body['hidden'])
        changed.append('hidden')
    return iface, changed


def remove(dev, iface_id):
    """Removes a hand-made interface; hides a fed one. Returns 'deleted' or 'hidden'."""
    iface = find(dev, iface_id)
    if iface is None:
        raise KeyError(iface_id)
    if iface.get('refs'):
        iface['hidden'] = True
        return 'hidden'
    dev['interfaces'].remove(iface)
    return 'deleted'


# ── Feeds ──────────────────────────────────────────────────────────────────────────────────

def clean_feed(items):
    """A plugin's interfaces for one device: [{'name', field: value}]. Bad entries are skipped."""
    out, seen = [], set()
    for raw in (items or [])[:MAX_PER_DEVICE]:
        if not isinstance(raw, dict):
            continue
        try:
            name = clean_name(raw.get('name'))
        except InterfaceError:
            continue
        if key(name) in seen:
            continue
        values = {}
        for f in FIELDS:
            if f in raw and raw[f] is not None:
                with contextlib.suppress(InterfaceError):
                    values[f] = clean_field(f, raw[f])
        seen.add(key(name))
        out.append({'name': name, **values})
    return out


def merge_feed(dev, plugin_id, items):
    """Merge one plugin's interfaces into a device. Returns counts."""
    counts = {'added': 0, 'updated': 0, 'unchanged': 0, 'gone': 0}
    ifaces = dev.setdefault('interfaces', [])
    sent = set()
    for item in items:
        name = item['name']
        sent.add(key(name))
        values = {f: v for f, v in item.items() if f != 'name'}
        iface = by_name(dev, name)
        if iface is None:
            if len(ifaces) >= MAX_PER_DEVICE:
                continue
            iface = {**blank(name), 'origin': plugin_id}
            ifaces.append(iface)
            counts['added'] += 1
            new = True
        else:
            new = False
            if plugin_id not in iface['refs']:
                # A hand-made interface the plugin now knows too: what differs stays as set by hand.
                for f, v in values.items():
                    if iface['origin'] == 'manual' and iface.get(f) not in (None, '', [], v) \
                            and f not in iface['locked']:
                        iface['locked'].append(f)
        iface['refs'][plugin_id] = name
        iface['fed'][plugin_id] = values
        if plugin_id in iface['gone']:
            iface['gone'].remove(plugin_id)
        changed = False
        for f, v in values.items():
            if f not in iface['locked'] and iface.get(f) != v:
                iface[f] = v
                changed = True
        if not new:
            counts['updated' if changed else 'unchanged'] += 1
    for iface in ifaces:
        if plugin_id in iface['refs'] and key(iface['name']) not in sent and plugin_id not in iface['gone']:
            iface['gone'].append(plugin_id)
            counts['gone'] += 1
    return counts


def from_monitoring(port):
    """One port from the monitoring source (``device_ports``) as a fed interface."""
    out = {'name': port.get('name')}
    bps = port.get('speed_bps')
    if isinstance(bps, (int, float)) and bps > 0:
        out['speed_mbps'] = int(bps // 1_000_000) or None
    if port.get('description'):
        out['description'] = str(port['description'])[:200]
    if port.get('state'):
        out['enabled'] = port['state'] != 'disabled'
    for k in ('mac', 'vlan', 'type', 'mode'):
        if port.get(k) not in (None, ''):
            out[k] = port[k]
    return out
