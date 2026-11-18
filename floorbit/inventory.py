"""The inventory: every switch, access point and other device Floorbit knows about.

Floorbit owns this list. People edit it by hand (Inventory page, the floor plan), and plugins
such as NetBox feed it (``uses: [inventory]``). The rules, so a sync never undoes someone's work:

- Each device remembers who created it (``origin``: ``manual`` or a plugin id), the ID each
  plugin knows it by (``refs``) and the last values each plugin sent (``fed``).
- A field someone changes by hand while a plugin feeds it is **locked**: syncs leave it alone
  until it is unlocked, which takes the plugin's value again.
- A sync never deletes. A device a plugin stops sending is flagged ``gone`` for that plugin.
  Deleting a fed device by hand hides it instead, so the next sync doesn't bring it back.
- The first time a plugin sends a device with the same name as one already here, the two are
  joined; fields that differed are locked, so the hand-made values stay.

Stored in data.json under ``inventory``; data from before (``switches``, ``cached_devices``,
``positions``) is moved over the first time it's read. See docs/inventory.md.
"""
from __future__ import annotations

import ipaddress
import math
import re
import threading
import time
import uuid

from . import icon_library

# Fields a plugin may feed (and a hand edit then locks). The second row are the specs of servers,
# VMs and firewalls: what runs on it, how big it is, and for a VM the device it runs on.
FIELDS = ('name', 'role', 'model', 'serial', 'mgmt_ip', 'hall', 'status', 'notes',
          'platform', 'os', 'cpu', 'cores', 'memory_mb', 'disk_gb', 'host')
SPECS = ('platform', 'os', 'cpu', 'cores', 'memory_mb', 'disk_gb', 'host')
NUMBERS = ('cores', 'memory_mb', 'disk_gb')
ROLES = ('switch', 'router', 'firewall', 'access-point', 'server', 'vm', 'pdu', 'other')
STATUSES = ('active', 'planned', 'staged', 'offline', 'failed', 'decommissioning', 'inventory', '')
LIMITS = {'name': 80, 'role': 40, 'model': 80, 'serial': 80, 'mgmt_ip': 45, 'hall': 80, 'status': 40,
          'notes': 1000, 'platform': 60, 'os': 80, 'cpu': 80, 'cores': 6, 'memory_mb': 9, 'disk_gb': 9,
          'host': 80}
# The icons a device or group can show (frontend/src/pages/inventory/icons.tsx draws them).
ICONS = ('switch', 'router', 'firewall', 'server', 'vm', 'access-point', 'pdu', 'ups', 'storage', 'camera',
         'printer', 'screen', 'phone', 'cloud', 'cpu', 'antenna', 'cable', 'circuit', 'power-board', 'patch-panel',
         'rack', 'transceiver', 'vlan', 'other')
COLOR_RE = re.compile(r'^#[0-9a-fA-F]{6}$')
LOG_KEEP = 50
MAX_TAGS = 20
MAX_FEED = 5000

_lock = threading.RLock()


class InventoryError(ValueError):
    """Bad input; the message is shown."""


def now():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def _blank(**kw):
    dev = {'id': str(uuid.uuid4()), **dict.fromkeys(FIELDS, ''), 'role': 'switch',
           'x': None, 'y': None, 'origin': 'manual', 'refs': {}, 'fed': {}, 'locked': [],
           'gone': [], 'hidden': False, 'updated_at': now(),
           # Set by hand only, never fed (floorbit/inventory_scope.py has the rules):
           'icon': '', 'color': '', 'group_id': None, 'tags': [], 'properties': {}, 'features': {}, 'fields': {},
           'interfaces': [], 'blocks': []}
    dev.update(kw)
    return dev


# ── Reading, with the move from the old layout ────────────────────────────────────────────

def migrate(data):
    """Build ``inventory`` from the pre-inventory keys, once. Changes ``data`` in place."""
    if isinstance(data.get('inventory'), list):
        return False
    devices = []
    for s in data.get('switches') or []:
        if not isinstance(s, dict) or not s.get('id'):
            continue
        placed = s.get('placed', True) and s.get('x') is not None
        devices.append(_blank(id=str(s['id']), name=str(s.get('name') or 'Switch')[:80],
                              x=s.get('x') if placed else None, y=s.get('y') if placed else None))
    positions = data.get('positions') or {}
    for d in data.get('cached_devices') or []:
        if not isinstance(d, dict) or not d.get('id'):
            continue
        did = str(d['id'])
        pos = positions.get(did) or {}
        status = str(d.get('netbox_status') or '')
        devices.append(_blank(id=did, name=str(d.get('name') or did)[:80], status=status,
                              x=pos.get('x'), y=pos.get('y'), origin='netbox', refs={'netbox': did},
                              fed={'netbox': {'name': d.get('name') or did, 'status': status}}))
    data['inventory'] = devices
    for key in ('switches', 'cached_devices', 'positions'):
        data.pop(key, None)
    return True


def normalize(raw):
    """A stored device (from a backup) checked and filled in, so later code can trust its shape."""
    dev = _blank(id=str(raw['id'])[:80])
    for f in FIELDS:
        if f in raw:
            dev[f] = clean_field(f, raw[f] if f != 'role' else (raw[f] or 'other'))
    for k in ('x', 'y'):
        v = raw.get(k)
        dev[k] = float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None
    dev['origin'] = str(raw.get('origin') or 'manual')[:40]
    refs = raw.get('refs') if isinstance(raw.get('refs'), dict) else {}
    dev['refs'] = {str(k)[:40]: str(v)[:80] for k, v in refs.items()}
    fed = raw.get('fed') if isinstance(raw.get('fed'), dict) else {}
    dev['fed'] = {str(p)[:40]: {f: str(v)[:LIMITS[f]] for f, v in vals.items() if f in FIELDS}
                  for p, vals in fed.items() if isinstance(vals, dict)}
    dev['locked'] = [f for f in raw.get('locked') or [] if f in FIELDS]
    dev['gone'] = [str(p)[:40] for p in raw.get('gone') or []][:20]
    dev['hidden'] = bool(raw.get('hidden'))
    dev['hall_id'] = str(raw['hall_id'])[:40] if raw.get('hall_id') else None
    dev['updated_at'] = str(raw.get('updated_at') or now())[:40]
    for key in ('icon', 'color'):
        try:
            dev[key] = clean_look(key, raw.get(key))
        except InventoryError:
            dev[key] = ''
    dev['group_id'] = str(raw['group_id'])[:40] if raw.get('group_id') else None
    dev['tags'] = [str(t)[:40] for t in raw.get('tags') or [] if t][:MAX_TAGS]
    for key in ('properties', 'features', 'fields'):
        dev[key] = raw[key] if isinstance(raw.get(key), dict) else {}
    from . import inventory_interfaces
    dev['interfaces'] = [inventory_interfaces.normalize(i) for i in raw.get('interfaces') or []
                         if isinstance(i, dict) and i.get('name')][:inventory_interfaces.MAX_PER_DEVICE]
    dev['blocks'] = [b for b in raw.get('blocks') or [] if isinstance(b, dict) and b.get('credential_id')][:20]
    return dev


def devices(data, include_hidden=False):
    migrate(data)
    return [d for d in data['inventory'] if include_hidden or not d.get('hidden')]


def find(data, device_id):
    migrate(data)
    return next((d for d in data['inventory'] if d['id'] == device_id), None)


def public(dev):
    """What the API returns: the device with which fields come from where."""
    out = {k: dev.get(k) for k in ('id', *FIELDS, 'x', 'y', 'hall_id', 'origin', 'hidden', 'updated_at')}
    out['placed'] = dev.get('x') is not None and dev.get('y') is not None
    out['sources'] = sorted(dev.get('refs') or {})
    out['locked'] = sorted(dev.get('locked') or [])
    out['gone'] = sorted(dev.get('gone') or [])
    out['fed'] = dev.get('fed') or {}
    for key in ('icon', 'color'):
        out[key] = dev.get(key) or ''
    out['group_id'] = dev.get('group_id')
    out['tags'] = list(dev.get('tags') or [])
    out['properties'] = dict(dev.get('properties') or {})
    out['features'] = dict(dev.get('features') or {})
    out['fields'] = dict(dev.get('fields') or {})
    out['interface_count'] = len(dev.get('interfaces') or [])
    out['blocked'] = len(dev.get('blocks') or [])
    return out


def as_switch(dev):
    """The shape /api/switches has always had, for the floor plan editor."""
    out = {'id': dev['id'], 'name': dev['name'], 'x': dev.get('x'), 'y': dev.get('y'), 'hall_id': dev.get('hall_id'),
           'placed': dev.get('x') is not None and dev.get('y') is not None,
           'source': 'manual' if dev.get('origin') == 'manual' else dev['origin'], 'status': 'unknown'}
    if dev.get('origin') != 'manual':
        out['netbox_status'] = dev.get('status') or 'unknown'
    return out


# ── Checking input ─────────────────────────────────────────────────────────────────────────

def clean_field(field, value):
    if field not in FIELDS:
        raise InventoryError(f'Unknown field: {field}')
    value = '' if value is None else str(value).strip()
    if '\n' in value and field != 'notes':
        raise InventoryError(f'{field} must be one line')
    value = value[:LIMITS[field]]
    if field == 'name' and not value:
        raise InventoryError('A device needs a name')
    if field == 'role':
        value = value.lower() or 'other'
        if value not in ROLES:
            raise InventoryError(f"role must be one of {', '.join(ROLES)}")
    if field == 'mgmt_ip' and value:
        try:
            value = str(ipaddress.ip_address(value))
        except ValueError:
            raise InventoryError(f'{value} is not an IP address') from None
    if field == 'status':
        value = value.lower()
    if field in NUMBERS and value:
        if not value.isdigit():
            raise InventoryError(f'{field} is a whole number')
        value = str(int(value))
    return value


def clean_look(key, value):
    """A device's or group's icon (one of ICONS or an uploaded one) or colour (#rrggbb); '' for the default."""
    value = '' if value is None else str(value).strip()
    if not value:
        return ''
    if key == 'icon':
        # Uploaded icons (floorbit/icon_library.py) by id; one removed later falls back to the role's.
        if icon_library.ID_RE.match(value):
            return value
        if value not in ICONS:
            raise InventoryError(f"icon must be one of {', '.join(ICONS)}")
        return value
    if not COLOR_RE.match(value):
        raise InventoryError('A colour is written #rrggbb')
    return value.lower()


def clean_feed(items):
    """A plugin's list, checked: [{'ref', field: value}]. Bad entries are skipped and counted."""
    if not isinstance(items, list):
        raise InventoryError('the plugin must return a list of devices')
    out, skipped, seen = [], 0, set()
    for raw in items[:MAX_FEED]:
        if not isinstance(raw, dict):
            skipped += 1
            continue
        ref = str(raw.get('id') or '').strip()[:80]
        if not ref or ref in seen:
            skipped += 1
            continue
        try:
            item = {f: clean_field(f, raw[f]) for f in FIELDS if f in raw and f != 'notes'}
            if 'name' not in item:
                raise InventoryError('no name')
        except InventoryError:
            skipped += 1
            continue
        seen.add(ref)
        item['ref'] = ref
        if isinstance(raw.get('interfaces'), list):
            # Only a plugin that knows interfaces sends the key; without it they're left alone.
            from . import inventory_interfaces
            item['interfaces'] = inventory_interfaces.clean_feed(raw['interfaces'])
        out.append(item)
    return out, skipped + max(0, len(items) - MAX_FEED)


# ── Hand edits ─────────────────────────────────────────────────────────────────────────────

def _position(body):
    if body.get('x') is None and body.get('y') is None:
        return None, None
    try:
        x, y = float(body['x']), float(body['y'])
    except (KeyError, TypeError, ValueError):
        raise InventoryError('Valid numeric x and y coordinates are required') from None
    # float("nan") takes the text "nan": saved, it made /api/plan answer a bare NaN no browser reads.
    if not (math.isfinite(x) and math.isfinite(y)):
        raise InventoryError('Valid numeric x and y coordinates are required')
    return x, y


def create(data, body):
    with _lock:
        migrate(data)
        fields = {f: clean_field(f, body.get(f, 'switch' if f == 'role' else '')) for f in FIELDS}
        x, y = _position(body)
        dev = _blank(**fields, x=x, y=y)
        if body.get('hall_id'):
            dev['hall_id'] = str(body['hall_id'])[:40]
        from . import inventory_scope
        inventory_scope.apply_device(data, dev, body)
        data['inventory'].append(dev)
        return dev


def _fed_value(dev, field):
    """The value a feeding plugin last sent for this field, or None."""
    for plugin in sorted(dev.get('refs') or {}):
        fed = (dev.get('fed') or {}).get(plugin) or {}
        if field in fed:
            return fed[field]
    return None


def update(data, device_id, body):
    """Hand edit: fields, position, ``unlock: [fields]``, ``hidden``. Returns the changed fields."""
    with _lock:
        dev = find(data, device_id)
        if dev is None:
            raise KeyError(device_id)
        changed = []
        for f in FIELDS:
            if f in body:
                value = clean_field(f, body[f])
                if value != dev.get(f):
                    dev[f] = value
                    changed.append(f)
                # Locked even when equal: the person said what it should be.
                if _fed_value(dev, f) is not None and value != _fed_value(dev, f) and f not in dev['locked']:
                    dev['locked'].append(f)
        if 'x' in body or 'y' in body:
            x, y = _position(body)
            if (x, y) != (dev.get('x'), dev.get('y')):
                dev['x'], dev['y'] = x, y
                changed.append('position')
        # The hall is part of where a device is, checked by the caller (floorbit/halls.py).
        if body.get('hall_id') and body['hall_id'] != dev.get('hall_id'):
            dev['hall_id'] = str(body['hall_id'])[:40]
            changed.append('hall')
        for f in body.get('unlock') or []:
            if f in dev['locked']:
                dev['locked'].remove(f)
                fed = _fed_value(dev, f)
                if fed is not None and fed != dev.get(f):
                    dev[f] = fed
                changed.append(f'unlock:{f}')
        if 'hidden' in body:
            hidden = bool(body['hidden'])
            if hidden != bool(dev.get('hidden')):
                dev['hidden'] = hidden
                changed.append('hidden')
        from . import inventory_scope
        changed += inventory_scope.apply_device(data, dev, body)
        if changed:
            dev['updated_at'] = now()
        return dev, changed


def delete(data, device_id):
    """Deletes a hand-made device; hides a fed one (a sync would bring it back). Returns 'deleted'/'hidden'."""
    with _lock:
        dev = find(data, device_id)
        if dev is None:
            raise KeyError(device_id)
        if dev.get('refs'):
            dev['hidden'] = True
            dev['x'] = dev['y'] = None
            dev['updated_at'] = now()
            return 'hidden'
        data['inventory'].remove(dev)
        return 'deleted'


def unplace(data, device_id):
    with _lock:
        dev = find(data, device_id)
        if dev is None:
            raise KeyError(device_id)
        dev['x'] = dev['y'] = None
        dev['updated_at'] = now()
        return dev


# ── Syncs from plugins ─────────────────────────────────────────────────────────────────────

def sync(data, plugin_id, items, skipped=0):
    """Merge one plugin's devices into the inventory. Returns the report (also logged)."""
    with _lock:
        migrate(data)
        inv = data['inventory']
        by_ref = {d['refs'][plugin_id]: d for d in inv if plugin_id in (d.get('refs') or {})}
        by_name = {}
        for d in inv:
            if plugin_id not in (d.get('refs') or {}):
                by_name.setdefault(d['name'].lower(), d)
        report = {'plugin': plugin_id, 'at': now(), 'received': len(items), 'skipped': skipped,
                  'added': 0, 'updated': 0, 'unchanged': 0, 'joined': 0, 'locked': 0, 'gone': 0,
                  'back': 0}
        sent = set()
        for item in items:
            ref = item['ref']
            sent.add(ref)
            values = {f: v for f, v in item.items() if f not in ('ref', 'interfaces')}
            dev = by_ref.get(ref)
            kind = 'existing'
            if dev is None:
                dev = by_name.pop(values['name'].lower(), None)
                if dev is not None:
                    # Joining a device made by hand: what differs stays as the person set it.
                    dev['refs'][plugin_id] = ref
                    for f, v in values.items():
                        if dev.get(f) and dev.get(f) != v and f not in dev['locked']:
                            dev['locked'].append(f)
                    kind = 'joined'
                else:
                    dev = _blank(id=_new_id(inv, plugin_id, ref), origin=plugin_id, refs={plugin_id: ref})
                    inv.append(dev)
                    kind = 'added'
            dev['fed'][plugin_id] = values
            if plugin_id in dev['gone']:
                dev['gone'].remove(plugin_id)
                report['back'] += 1
            changed = False
            for f, v in values.items():
                if f in dev['locked']:
                    report['locked'] += dev.get(f) != v
                elif dev.get(f) != v:
                    dev[f] = v
                    changed = True
            if 'interfaces' in item:
                from . import inventory_interfaces
                counts = inventory_interfaces.merge_feed(dev, plugin_id, item['interfaces'])
                report['interfaces'] = report.get('interfaces', 0) + counts['added'] + counts['updated']
                changed = changed or bool(counts['added'] or counts['updated'])
            if changed:
                dev['updated_at'] = now()
            if kind != 'existing':
                report[kind] += 1
            else:
                report['updated' if changed else 'unchanged'] += 1
        for ref, dev in by_ref.items():
            if ref not in sent and plugin_id not in dev['gone']:
                dev['gone'].append(plugin_id)
                report['gone'] += 1
        record_log(data, report)
        return report


def _new_id(inv, plugin_id, ref):
    wanted = f'{plugin_id}-{ref}'
    taken = {d['id'] for d in inv}
    return wanted if wanted not in taken else str(uuid.uuid4())


def record_log(data, report):
    log = data.setdefault('inventory_log', [])
    log.append(report)
    del log[:-LOG_KEEP]


def sync_log(data, plugin_id=None):
    log = data.get('inventory_log') or []
    return [r for r in reversed(log) if plugin_id is None or r.get('plugin') == plugin_id]
