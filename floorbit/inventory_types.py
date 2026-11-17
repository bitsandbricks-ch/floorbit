"""Inventory types and the entries of every type that isn't a device (Mike, 2026-11-17).

Everything in the inventory has a **type**. Each type has its own **fields** that an admin sets up
(text, number, choice, yes/no, or a link to another inventory entry, each with a default), and
settings every entry of it inherits: properties, an icon, a colour and, for devices, feature
switches. The order is entry > its tags > group > the group's tags > parent group > ... > its type >
all entries (floorbit/inventory_scope.py ``layers``).

Three sorts of type:

- ``device``: the inventory devices (floorbit/inventory.py), as before.
- **linked**: cables, circuits, power boards and patch panels. Their records stay where their pages
  keep them (``cables``, ``power``, ``patch_panels``), so those pages work as before; the inventory
  adds a group, tags, properties, icon, colour, notes and field values, kept in ``inventory_items``
  keyed ``<type>:<id>``. An entry whose record is gone stops being listed. Patch panels have no id,
  so they are keyed by their name in lower case.
- **stored**: racks and locations, transceivers, VLANs and IP ranges, other items, and the types
  admins add. Their entries live in ``inventory_entries``.

Type settings are kept in ``inventory_types``: the built-in types' changes, and the custom types.
"""
import re
import threading
import uuid

from . import inventory, inventory_scope
from .inventory_scope import ScopeError

TYPES = 'inventory_types'
ENTRIES = 'inventory_entries'
ATTACHED = 'inventory_items'

FIELD_KINDS = ('text', 'number', 'choice', 'bool', 'link')
MAX_FIELDS = 30
MAX_CHOICES = 50
MAX_TYPES = 40
MAX_ENTRIES = 5000
NOTES_MAX = 1000
KEY_RE = re.compile(r'^[a-z][a-z0-9_]{0,39}$')
ID_RE = re.compile(r'^[a-z][a-z0-9-]{0,39}$')

_lock = threading.RLock()


def _f(key, label, kind='text', **kw):
    return {'key': key, 'label': label, 'kind': kind, 'choices': kw.get('choices', []),
            'default': kw.get('default', ''), 'link': kw.get('link', '')}


# The types Floorbit knows. Admins add fields to any of them, and types of their own.
BUILTIN = {
    'device': {'name': 'Device', 'sort': 'device', 'icon': 'other', 'fields': []},
    'cable': {'name': 'Cable', 'sort': 'linked', 'icon': 'cable', 'fields': []},
    'circuit': {'name': 'Circuit', 'sort': 'linked', 'icon': 'circuit', 'fields': []},
    'power-board': {'name': 'Power board', 'sort': 'linked', 'icon': 'power-board', 'fields': []},
    'patch-panel': {'name': 'Patch panel', 'sort': 'linked', 'icon': 'patch-panel', 'fields': []},
    'rack': {'name': 'Rack or location', 'sort': 'stored', 'icon': 'rack', 'fields': [
        _f('height_u', 'Height (U)', 'number', default='42'),
        _f('hall', 'Hall or site'),
    ]},
    'transceiver': {'name': 'Transceiver', 'sort': 'stored', 'icon': 'transceiver', 'fields': [
        _f('device', 'Device', 'link', link='device'),
        _f('port', 'Port'),
        _f('form', 'Form factor', 'choice', choices=['SFP', 'SFP+', 'SFP28', 'QSFP+', 'QSFP28', 'DAC', 'AOC']),
        _f('media', 'Media', 'choice', choices=['Copper', 'SR', 'LR', 'ER', 'BiDi']),
        _f('speed', 'Speed', 'choice', choices=['1G', '10G', '25G', '40G', '100G']),
        _f('serial', 'Serial'),
    ]},
    'vlan': {'name': 'VLAN or IP range', 'sort': 'stored', 'icon': 'vlan', 'fields': [
        _f('vlan_id', 'VLAN ID', 'number'),
        _f('prefix', 'Prefix'),
        _f('gateway', 'Gateway'),
        _f('purpose', 'Purpose', 'choice', choices=['Seats', 'Crew', 'Servers', 'Management', 'Wi-Fi', 'Other']),
    ]},
    'item': {'name': 'Item', 'sort': 'stored', 'icon': 'other', 'fields': []},
}
LINKED = tuple(k for k, v in BUILTIN.items() if v['sort'] == 'linked')


# ── Types ──────────────────────────────────────────────────────────────────────

def _stored_types(data):
    return [t for t in data.get(TYPES) or [] if isinstance(t, dict) and t.get('id')]


def types(data):
    """Every type, built-in ones first: {'id', 'name', 'sort', 'builtin', 'icon', 'color', 'fields',
    'properties', 'features'}."""
    saved = {t['id']: t for t in _stored_types(data)}
    out = []
    for tid, base in BUILTIN.items():
        own = saved.get(tid) or {}
        out.append({'id': tid, 'name': base['name'], 'sort': base['sort'], 'builtin': True,
                    'icon': own.get('icon') or '', 'default_icon': base['icon'], 'color': own.get('color') or '',
                    'fields': [*base['fields'], *(own.get('fields') or [])],
                    'own_fields': list(own.get('fields') or []),
                    'properties': dict(own.get('properties') or {}), 'features': dict(own.get('features') or {})})
    for t in _stored_types(data):
        if t['id'] in BUILTIN:
            continue
        out.append({'id': t['id'], 'name': t.get('name') or t['id'], 'sort': 'stored', 'builtin': False,
                    'icon': t.get('icon') or '', 'default_icon': 'other', 'color': t.get('color') or '',
                    'fields': list(t.get('fields') or []), 'own_fields': list(t.get('fields') or []),
                    'properties': dict(t.get('properties') or {}), 'features': {}})
    return out


def type_of(data, type_id):
    return next((t for t in types(data) if t['id'] == type_id), None)


def layer(data, type_id):
    """The type as a layer of inheritance: its properties (with the fields' defaults), icon, colour."""
    t = type_of(data, type_id or 'device')
    if t is None:
        return None
    return {'id': t['id'], 'name': t['name'], 'properties': t['properties'], 'features': t['features'],
            'icon': t['icon'], 'color': t['color'], 'tags': []}


def _clean_field(raw, taken):
    if not isinstance(raw, dict):
        raise ScopeError('A field is a name, a kind and a default.')
    label = ' '.join(str(raw.get('label') or '').split())[:40]
    if not label:
        raise ScopeError('Give every field a name.')
    key = str(raw.get('key') or '').strip().lower() or re.sub(r'[^a-z0-9]+', '_', label.lower()).strip('_')
    if not key or not key[0].isalpha():
        key = f'f_{key}'.rstrip('_')
    key = key[:40]
    if not KEY_RE.match(key):
        raise ScopeError(f'A field key is lower case letters, digits and _: {key}')
    if key in taken:
        raise ScopeError(f'Two fields are called {key}.')
    kind = raw.get('kind') or 'text'
    if kind not in FIELD_KINDS:
        raise ScopeError(f"A field is one of: {', '.join(FIELD_KINDS)}.")
    choices = []
    if kind == 'choice':
        choices = list(dict.fromkeys(' '.join(str(c).split())[:40] for c in raw.get('choices') or [] if str(c).strip()))
        if not choices or len(choices) > MAX_CHOICES:
            raise ScopeError(f'A choice field has 1 to {MAX_CHOICES} choices.')
    link = str(raw.get('link') or '') if kind == 'link' else ''
    field = {'key': key, 'label': label, 'kind': kind, 'choices': choices, 'default': '', 'link': link}
    default = raw.get('default')
    if default not in (None, ''):
        field['default'] = _value(field, default, None)
    return field


def _clean_fields(value, fixed=()):
    if not isinstance(value, list):
        raise ScopeError('fields is a list.')
    if len(value) + len(fixed) > MAX_FIELDS:
        raise ScopeError(f'A type has at most {MAX_FIELDS} fields.')
    taken = {f['key'] for f in fixed}
    out = []
    for raw in value:
        f = _clean_field(raw, taken)
        taken.add(f['key'])
        out.append(f)
    return out


def save_type(data, body, type_id=None, registry=None):
    """Creates a custom type or changes one (a built-in type: its own fields, icon, colour,
    properties and, for devices, features). Returns (type, changed)."""
    with _lock:
        stored = _stored_types(data)
        if type_id is None:
            name = inventory_scope.clean_name(body.get('name'), 'type')
            new_id = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')[:40] or 'type'
            if not ID_RE.match(new_id):
                new_id = f't-{uuid.uuid4().hex[:8]}'
            if type_of(data, new_id) is not None:
                raise ScopeError(f'There is a type called {name} already.', 409)
            if len([t for t in stored if t['id'] not in BUILTIN]) >= MAX_TYPES:
                raise ScopeError(f'At most {MAX_TYPES} types of your own.', 409)
            own = {'id': new_id, 'name': name}
            stored.append(own)
            changed = ['created']
        else:
            if type_of(data, type_id) is None:
                raise ScopeError('No such type.', 404)
            own = next((t for t in stored if t['id'] == type_id), None)
            if own is None:
                own = {'id': type_id}
                stored.append(own)
            changed = []
            if 'name' in body and type_id not in BUILTIN:
                name = inventory_scope.clean_name(body.get('name'), 'type')
                if name != own.get('name'):
                    own['name'] = name
                    changed.append('name')
        fixed = BUILTIN.get(own['id'], {}).get('fields', [])
        if 'fields' in body:
            value = _clean_fields(body['fields'], fixed)
            if value != (own.get('fields') or []):
                own['fields'] = value
                changed.append('fields')
        body = {k: v for k, v in body.items() if k in ('icon', 'color', 'properties', 'features')}
        if own['id'] != 'device':
            body.pop('features', None)
        inventory_scope._common(data, body, own, changed, registry)
        data[TYPES] = stored
        return type_of(data, own['id']), changed


def delete_type(data, type_id):
    with _lock:
        if type_id in BUILTIN:
            raise ScopeError('Built-in types stay; take their fields away instead.', 409)
        if type_of(data, type_id) is None:
            raise ScopeError('No such type.', 404)
        if any(e['type'] == type_id for e in _entries(data)):
            raise ScopeError('Remove its entries first.', 409)
        data[TYPES] = [t for t in _stored_types(data) if t['id'] != type_id]


# ── Field values ───────────────────────────────────────────────────────────────

def _link_names(data, link):
    if link in ('', 'device'):
        return {d['name'].lower(): d['name'] for d in inventory.devices(data, include_hidden=True)}
    return {e['name'].lower(): e['name'] for e in listing(data, link)}


def _value(field, raw, data):
    value = ' '.join(str(raw).split())[:200] if not isinstance(raw, bool) else ('yes' if raw else 'no')
    if value == '':
        return ''
    kind = field['kind']
    if kind == 'number':
        try:
            number = float(value.replace(',', '.'))
        except ValueError:
            raise ScopeError(f"{field['label']} is a number.") from None
        return str(int(number)) if number.is_integer() else str(number)
    if kind == 'choice':
        hit = next((c for c in field['choices'] if c.lower() == value.lower()), None)
        if hit is None:
            raise ScopeError(f"{field['label']} is one of: {', '.join(field['choices'])}.")
        return hit
    if kind == 'bool':
        if value.lower() in ('yes', 'true', '1', 'on'):
            return 'yes'
        if value.lower() in ('no', 'false', '0', 'off'):
            return 'no'
        raise ScopeError(f"{field['label']} is yes or no.")
    if kind == 'link' and data is not None:
        names = _link_names(data, field['link'])
        if value.lower() not in names:
            raise ScopeError(f"Pick {field['label']} from the inventory.")
        return names[value.lower()]
    return value


def clean_values(data, type_id, raw, current=None):
    """An entry's field values, checked against its type; '' takes a value away (the default shows)."""
    if not isinstance(raw, dict):
        raise ScopeError('fields is an object of field: value.')
    t = type_of(data, type_id)
    by_key = {f['key']: f for f in (t['fields'] if t else [])}
    out = dict(current or {})
    for key, value in raw.items():
        field = by_key.get(key)
        if field is None:
            raise ScopeError(f'{key} is not a field of this type.')
        clean = _value(field, value, data)
        if clean == '':
            out.pop(key, None)
        else:
            out[key] = clean
    return out


def resolve_fields(data, type_id, values):
    """Each field of the type with its value: {'key', 'label', 'kind', ..., 'value', 'default': bool}."""
    t = type_of(data, type_id)
    out = []
    for f in t['fields'] if t else []:
        own = (values or {}).get(f['key'])
        out.append({**f, 'value': own if own not in (None, '') else f['default'],
                    'is_default': own in (None, '')})
    return out


# ── Entries ────────────────────────────────────────────────────────────────────

def _entries(data):
    return [e for e in data.get(ENTRIES) or [] if isinstance(e, dict) and e.get('id') and e.get('type')]


def _attached(data):
    raw = data.get(ATTACHED)
    return raw if isinstance(raw, dict) else {}


def _cable(c):
    ends = [f"{c.get('switch') or ''} {c.get('port') or ''}".strip(),
            ' '.join(x for x in (c.get('panel') or '', str(c.get('panel_port') or '')) if x), c.get('seat') or '']
    extra = [c.get('type') or '', f"{c['speed']}G" if c.get('speed') else '',
             f"{c['length_m']} m" if c.get('length_m') else '']
    return {'id': c['id'], 'name': c.get('label') or ends[0],
            'summary': ' → '.join(x for x in ends if x), 'detail': ' · '.join(x for x in extra if x),
            'link': f"/cables?q={c.get('label') or ''}"}


def _records(data, type_id):
    """A linked type's records as the inventory lists them."""
    from . import cable_plan, cables, power
    if type_id == 'cable':
        return [_cable(c) for c in cables.all_cables(data) if c.get('id')]
    if type_id == 'patch-panel':
        return [{'id': p['name'].lower(), 'name': p['name'], 'link': '/cables',
                 'summary': f"{p.get('ports') or cable_plan.PANEL_PORTS} ports", 'detail': ''}
                for p in cable_plan.panels(data)]
    boards, circuits = power._stored(data)
    if type_id == 'power-board':
        return [{'id': b['id'], 'name': b.get('name') or '', 'summary': b.get('location') or '', 'detail': '',
                 'link': '/power'} for b in boards if b.get('id')]
    names = {b.get('id'): b.get('name') or '' for b in boards}
    return [{'id': c['id'], 'name': c.get('name') or '', 'link': '/power', 'detail': '',
             'summary': ' · '.join(x for x in (names.get(c.get('board'), ''), c.get('phase') or '',
                                               f"{c['rating_a']} A" if c.get('rating_a') else '') if x)}
            for c in circuits if c.get('id')]


def _settings(own):
    return {'group_id': own.get('group_id'), 'tags': list(own.get('tags') or []),
            'properties': dict(own.get('properties') or {}), 'icon': own.get('icon') or '',
            'color': own.get('color') or '', 'notes': own.get('notes') or '', 'fields': dict(own.get('fields') or {})}


def listing(data, type_id=None):
    """Entries of one type (or every non-device type): {'id', 'type', 'name', 'summary', 'detail',
    'link', 'group_id', 'tags', 'properties', 'icon', 'color', 'notes', 'fields'}."""
    out = []
    attached = _attached(data)
    for t in types(data):
        if t['sort'] == 'device' or (type_id and t['id'] != type_id):
            continue
        if t['sort'] == 'linked':
            for r in _records(data, t['id']):
                out.append({**r, 'type': t['id'], **_settings(attached.get(f"{t['id']}:{r['id']}") or {})})
        else:
            for e in _entries(data):
                if e['type'] == t['id']:
                    out.append({'id': e['id'], 'type': t['id'], 'name': e.get('name') or '', 'summary': '',
                                'detail': '', 'link': '', **_settings(e), 'sources': sorted(e.get('refs') or {}),
                                'locked': list(e.get('locked') or []), 'gone': list(e.get('gone') or [])})
    return sorted(out, key=lambda e: (e['type'], e['name'].lower()))


def find(data, type_id, entry_id):
    t = type_of(data, type_id)
    if t is None or t['sort'] == 'device':
        raise ScopeError('No such type.', 404)
    entry = next((e for e in listing(data, type_id) if str(e['id']) == str(entry_id)), None)
    if entry is None:
        raise ScopeError('No such entry.', 404)
    return entry


def detail(data, type_id, entry_id):
    entry = find(data, type_id, entry_id)
    resolved = inventory_scope.resolve(data, {**entry, 'kind': 'entry'})
    resolved.pop('credentials', None)
    resolved.pop('features', None)
    return {**entry, 'resolved': resolved, 'field_values': resolve_fields(data, type_id, entry['fields'])}


def _apply(data, entry_type, own, body, changed):
    if 'group_id' in body:
        gid = body['group_id'] or None
        if gid and inventory_scope.group(data, gid) is None:
            raise ScopeError('No such group.')
        if gid != own.get('group_id'):
            own['group_id'] = gid
            changed.append('group')
    if 'notes' in body:
        notes = str(body.get('notes') or '').strip()[:NOTES_MAX]
        if notes != (own.get('notes') or ''):
            own['notes'] = notes
            changed.append('notes')
    if 'fields' in body:
        values = clean_values(data, entry_type, body['fields'], own.get('fields'))
        if values != (own.get('fields') or {}):
            own['fields'] = values
            changed.append('fields')
    inventory_scope._common(data, {k: v for k, v in body.items() if k in ('icon', 'color', 'tags', 'properties')},
                            own, changed)


def create(data, type_id, body):
    with _lock:
        t = type_of(data, type_id)
        if t is None or t['sort'] != 'stored':
            raise ScopeError('Entries of this type are made on their own page.', 409)
        entries = _entries(data)
        if len(entries) >= MAX_ENTRIES:
            raise ScopeError(f'The inventory holds at most {MAX_ENTRIES} entries.', 409)
        name = inventory_scope.clean_name(body.get('name'), 'entry')
        if any(e['type'] == type_id and (e.get('name') or '').lower() == name.lower() for e in entries):
            raise ScopeError(f'There is a {t["name"]} called {name} already.', 409)
        own = {'id': uuid.uuid4().hex[:12], 'type': type_id, 'name': name}
        _apply(data, type_id, own, body, [])
        data[ENTRIES] = [*entries, own]
        return find(data, type_id, own['id'])


def update(data, type_id, entry_id, body):
    """Changes an entry's name (stored types), group, tags, properties, icon, colour, notes or field
    values. Returns (entry, changed)."""
    with _lock:
        entry = find(data, type_id, entry_id)
        changed = []
        t = type_of(data, type_id)
        if t['sort'] == 'stored':
            own = next(e for e in _entries(data) if e['id'] == entry['id'])
            if 'name' in body:
                name = inventory_scope.clean_name(body.get('name'), 'entry')
                if name != own.get('name'):
                    if any(e is not own and e['type'] == type_id and (e.get('name') or '').lower() == name.lower()
                           for e in _entries(data)):
                        raise ScopeError(f'There is a {t["name"]} called {name} already.', 409)
                    own['name'] = name
                    changed.append('name')
            before = dict(own.get('fields') or {})
            _apply(data, type_id, own, body, changed)
            if own.get('refs'):
                # Changed by hand: a sync keeps it from now on.
                locked = own.setdefault('locked', [])
                touched = (['name'] if 'name' in changed else []) + [
                    f'fields.{k}' for k in set(before) | set(own.get('fields') or {})
                    if before.get(k) != (own.get('fields') or {}).get(k)]
                locked += [k for k in touched if k not in locked]
        else:
            attached = _attached(data)
            key = f"{type_id}:{entry['id']}"
            own = dict(attached.get(key) or {})
            _apply(data, type_id, own, body, changed)
            if changed:
                attached[key] = {k: v for k, v in own.items() if v not in (None, '', [], {})}
                data[ATTACHED] = attached
        return find(data, type_id, entry_id), changed


def delete(data, type_id, entry_id):
    with _lock:
        entry = find(data, type_id, entry_id)
        if type_of(data, type_id)['sort'] != 'stored':
            raise ScopeError('Entries of this type are removed on their own page.', 409)
        data[ENTRIES] = [e for e in _entries(data) if e['id'] != entry['id']]
        return entry


def holders(data):
    """Everything with a group and tags besides devices and groups, for when a group or tag goes."""
    return [*_entries(data), *_attached(data).values(), *_stored_types(data)]


def counts(data):
    """{type_id: number of entries}, devices included."""
    out = {'device': len(inventory.devices(data))}
    for e in listing(data):
        out[e['type']] = out.get(e['type'], 0) + 1
    return out


# ── Feeds from plugins (NetBox) ──────────────────────────────────────────────────

MAX_FEED = 20000


def clean_feed(raw):
    """A plugin's ``entries()``: {type: [{'ref', 'name', 'fields'?, ...}]}, checked. Unknown types and
    entries without a ref or name are skipped and counted."""
    if not isinstance(raw, dict):
        raise ScopeError('the plugin must return entries by type')
    out, skipped = {}, 0
    for type_id, items in raw.items():
        if type_id not in BUILTIN or BUILTIN[type_id]['sort'] == 'device' or type_id in ('cable', 'patch-panel') \
                or not isinstance(items, list):
            skipped += len(items) if isinstance(items, list) else 1
            continue
        rows = []
        for item in items[:MAX_FEED]:
            if not isinstance(item, dict) or not item.get('ref') or not str(item.get('name') or '').strip():
                skipped += 1
                continue
            row = {'ref': str(item['ref'])[:80], 'name': ' '.join(str(item['name']).split())[:80]}
            fields = item.get('fields') if isinstance(item.get('fields'), dict) else {}
            row['fields'] = {str(k)[:40]: v for k, v in fields.items() if isinstance(v, (str, int, float, bool))}
            for key in ('location', 'board_ref', 'phase', 'rating_a'):
                if key in item:
                    row[key] = item[key]
            rows.append(row)
        out[type_id] = rows
    return out, skipped


def _fed_fields(data, type_id, values):
    """The values a type has fields for, each checked; one that doesn't fit is left out."""
    t = type_of(data, type_id)
    out = {}
    for f in t['fields'] if t else []:
        if f['key'] in values and values[f['key']] not in (None, ''):
            try:
                value = _value(f, values[f['key']], data)
            except ScopeError:
                continue
            if value:
                out[f['key']] = value
    return out


def _sync_stored(data, plugin_id, type_id, rows, report):
    entries = _entries(data)
    mine = [e for e in entries if e['type'] == type_id]
    by_ref = {e['refs'][plugin_id]: e for e in mine if plugin_id in (e.get('refs') or {})}
    by_name = {(e.get('name') or '').lower(): e for e in mine if plugin_id not in (e.get('refs') or {})}
    sent = set()
    for row in rows:
        sent.add(row['ref'])
        fed = _fed_fields(data, type_id, row['fields'])
        values = {'name': row['name'], **{f'fields.{k}': v for k, v in fed.items()}}
        entry = by_ref.get(row['ref'])
        if entry is None:
            entry = by_name.pop(row['name'].lower(), None)
            if entry is not None:
                entry.setdefault('refs', {})[plugin_id] = row['ref']
                locked = entry.setdefault('locked', [])
                for key, value in values.items():
                    if _get(entry, key) and _get(entry, key) != value and key not in locked:
                        locked.append(key)
                report['joined'] += 1
            elif len(entries) >= MAX_ENTRIES:
                report['skipped'] += 1
                continue
            else:
                entry = {'id': uuid.uuid4().hex[:12], 'type': type_id, 'name': row['name'], 'origin': plugin_id,
                         'refs': {plugin_id: row['ref']}, 'locked': []}
                entries.append(entry)
                report['added'] += 1
        entry.setdefault('fed', {})[plugin_id] = values
        entry['gone'] = [g for g in entry.get('gone') or [] if g != plugin_id]
        changed = False
        for key, value in values.items():
            if key in (entry.get('locked') or []):
                report['locked'] += _get(entry, key) != value
            elif _get(entry, key) != value:
                _set(entry, key, value)
                changed = True
        report['updated'] += int(changed)
    for entry in mine:
        if plugin_id in (entry.get('refs') or {}) and entry['refs'][plugin_id] not in sent \
                and plugin_id not in (entry.get('gone') or []):
            entry['gone'] = [*(entry.get('gone') or []), plugin_id]
            report['gone'] += 1
    data[ENTRIES] = entries


def _get(entry, key):
    if key.startswith('fields.'):
        return (entry.get('fields') or {}).get(key[7:], '')
    return entry.get(key) or ''


def _set(entry, key, value):
    if key.startswith('fields.'):
        entry.setdefault('fields', {})[key[7:]] = value
    else:
        entry[key] = value


def _sync_power(data, plugin_id, boards_feed, circuits_feed, report):
    """Power panels and feeds become boards and circuits on the power page: new ones are added,
    ones already there stay as the crew set them."""
    from . import power
    boards, circuits = power._stored(data)
    by_ref = {b.get('ref'): b for b in boards if b.get('ref')}
    names = {(b.get('name') or '').lower() for b in boards}
    for row in boards_feed:
        ref = f'{plugin_id}:{row["ref"]}'
        if ref in by_ref:
            continue
        if row['name'].lower() in names:     # one the crew made by hand: link it, don't add another
            board = next(b for b in boards if (b.get('name') or '').lower() == row['name'].lower() and not b.get('ref'))
            board['ref'] = ref
            by_ref[ref] = board
            report['joined'] += 1
            continue
        board = {'id': uuid.uuid4().hex[:10], 'name': row['name'][:40], 'location': str(row.get('location') or '')[:80],
                 'x': None, 'y': None, 'ref': ref}
        boards.append(board)
        by_ref[ref] = board
        report['added'] += 1
    have = {c.get('ref') for c in circuits if c.get('ref')}
    for row in circuits_feed:
        ref = f'{plugin_id}:{row["ref"]}'
        board = by_ref.get(f'{plugin_id}:{row.get("board_ref")}')
        if ref in have or board is None:
            continue
        phase = row.get('phase') if row.get('phase') in power.PHASES else 'L1'
        try:
            rating = int(float(row.get('rating_a') or 16))
        except (TypeError, ValueError):
            rating = 16
        circuits.append({'id': uuid.uuid4().hex[:10], 'board': board['id'], 'name': row['name'][:40], 'phase': phase,
                         'rating_a': max(1, min(rating, 400)), 'meter': '', 'blocks': [], 'switches': [],
                         'tripped': None, 'ref': ref})
        report['added'] += 1
    data[power.KEY] = {'boards': boards, 'circuits': circuits}


def sync_entries(data, plugin_id, feed, skipped=0):
    """Merges a plugin's entries. Hand changes win; nothing is deleted (an entry the plugin no longer
    sends is marked gone)."""
    with _lock:
        report = {'plugin': plugin_id, 'added': 0, 'updated': 0, 'joined': 0, 'locked': 0, 'gone': 0,
                  'skipped': skipped}
        for type_id, rows in feed.items():
            if BUILTIN[type_id]['sort'] == 'stored':
                _sync_stored(data, plugin_id, type_id, rows, report)
        if feed.get('power-board') or feed.get('circuit'):
            _sync_power(data, plugin_id, feed.get('power-board') or [], feed.get('circuit') or [], report)
        return report
