"""Groups, tags, properties, credentials and features for inventory devices, and what each device
ends up with once they are inherited. See docs/inventory.md#groups-and-tags.

- **Groups** nest (``parent_id``). A device is in at most one group. A group carries properties,
  tags, feature switches, credentials, an icon and a colour, and everything in it inherits them.
- **Tags** (labels) carry the same things. A device or a group can have several.
- **Defaults** are the top level ("All devices"): properties and feature switches for every device.
- **Credentials** (SSH, SNMP v2c/v3, API token, HTTP login) can be set on a device, a tag, a group
  or the defaults, sealed with floorbit/vault.py. Write-only: the API says which are set and by
  whom, never the secret. A secret is opened only when it is used (``login_for``) or handed to an
  agent plugin (``plugin_targets``); both are audit-logged.

What a device ends up with is looked up from the most specific place to the least:

    the device > its own tags (in their order) > its group > that group's tags > the parent group
    > its tags > ... > the defaults

A feature switch or credential takes the first place that sets it; properties are merged, the
most specific value winning. (The older Settings > Switch logins, by name pattern, became
credentials here: floorbit/upgrades.py.)

**Features** are Floorbit's per-device features (port actions, switch commands, the terminal,
config backups; on unless switched off) and plugins (off unless switched on somewhere): an agent
plugin works on a device only where it is on and a credential resolves.

**Blocks.** When a stored credential fails to log in (an agent plugin or a port action here), the
device is blocked for that credential: nothing tries it again until a tech clears the block, or
the credential is set again (a new ``rev``). That keeps a wrong password from locking the account
on the device. Blocks are kept on the device (``blocks``).
"""
from __future__ import annotations

import hashlib
import re
import time
import uuid

from . import inventory, vault

GROUPS = 'inventory_groups'
TAGS = 'inventory_tags'
DEFAULTS = 'inventory_defaults'
CREDS = 'inventory_credentials'
MAX_GROUPS = 500
MAX_TAGS = 200
MAX_CREDS = 2000
MAX_DEPTH = 8
MAX_PROPERTIES = 50
PROP_KEY_RE = re.compile(r'^[a-z][a-z0-9_.-]{0,39}\Z')
NAME_RE = re.compile(r'^[^\x00-\x1f]{1,60}\Z')
USER_RE = re.compile(r'^[^\s\x00-\x1f]{1,64}\Z')

# Floorbit's own per-device features: on unless switched off. Anything else named is a plugin id,
# off unless switched on.
CORE_FEATURES = ('ports', 'commands', 'terminal', 'configs')
# The kinds of device each core feature is about: a device's page lists only these, the rest
# under "Other features" (#878). Port actions are seat ports; the others need a CLI over SSH.
CORE_FEATURE_ROLES = {'ports': ('switch',), 'commands': ('switch', 'router', 'firewall'),
                      'terminal': ('switch', 'router', 'firewall'), 'configs': ('switch', 'router', 'firewall')}

# Credential kinds: the plain fields each one has, and its secrets. Every kind has "secret"; SNMP v3
# has its privacy passphrase as "priv_secret".
KINDS = {
    'ssh': {'fields': ('username',), 'secrets': ('secret',), 'needs_user': True},
    'snmp_v2c': {'fields': (), 'secrets': ('secret',), 'needs_user': False},
    'snmp_v3': {'fields': ('username', 'auth_protocol', 'priv_protocol'), 'secrets': ('secret', 'priv_secret'),
                'needs_user': True},
    # The SNMPv3 user devices send traps as (telemetry): both passphrases optional, for authNoPriv
    # and noAuthNoPriv users. Each distinct one gets its own trap listener (telemetry/targets.py).
    'snmp_trap': {'fields': ('username', 'auth_protocol', 'priv_protocol'), 'secrets': ('secret', 'priv_secret'),
                  'needs_user': True, 'optional': ('secret', 'priv_secret')},
    'api': {'fields': ('username',), 'secrets': ('secret',), 'needs_user': False},
    'http': {'fields': ('username',), 'secrets': ('secret',), 'needs_user': True},
}
AUTH_PROTOCOLS = ('MD5', 'SHA', 'SHA224', 'SHA256', 'SHA384', 'SHA512')
PRIV_PROTOCOLS = ('DES', 'AES', 'AES192', 'AES256', 'AES192C', 'AES256C')
OWNER_TYPES = ('device', 'tag', 'group', 'defaults')

_lock = inventory._lock      # one lock for everything in data.json's inventory parts
_handed = {}                 # plugin id -> fingerprint of the logins last handed out (audit once)


class ScopeError(ValueError):
    """Bad input; the message is shown."""

    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def _now():
    return time.time()


def reload_agents():
    """Tell the agents their plugins' settings changed (floorbit/agent_plugins.py), when it exists."""
    try:
        from . import agent_plugins
    except ImportError:
        return
    fn = getattr(agent_plugins, 'reload_agents', None)
    if callable(fn):
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 - an agent away must not fail the save that changed things
            print(f'[inventory] reload_agents failed: {exc}')


# ── Checking input ─────────────────────────────────────────────────────────────────────────

def clean_name(value, what='name'):
    value = str(value or '').strip()
    if not NAME_RE.match(value):
        raise ScopeError(f'Give it a {what} (one line, up to 60 characters).')
    return value


def clean_properties(value, data=None):
    """Property names and values, checked; with ``data``, known properties are checked against their
    type too (floorbit/property_catalog.py)."""
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ScopeError('Properties are pairs of a name and a value.')
    if len(value) > MAX_PROPERTIES:
        raise ScopeError(f'At most {MAX_PROPERTIES} properties.')
    out = {}
    for k, v in value.items():
        k = str(k).strip().lower()
        if not PROP_KEY_RE.match(k):
            raise ScopeError(f'{k or "(empty)"} is not a property name (a-z, 0-9, dot, dash, underscore).')
        if k.startswith(('system.', 'auto.')):
            # Floorbit's own levels (inventory_properties.py): a custom one would hide the real value.
            raise ScopeError(f'{k}: names starting with system. or auto. are Floorbit\'s own. Pick another name.')
        v = '' if v is None else str(v).strip()
        if '\n' in v or len(v) > 200:
            raise ScopeError(f'The value of {k} must be one line, up to 200 characters.')
        out[k] = v
    if data is not None:
        from . import property_catalog
        out = property_catalog.check_all(data, out)
    return out


def known_features(registry=None):
    """Every feature id a switch can be about: the core ones and the plugins installed here."""
    ids = list(CORE_FEATURES)
    registry = registry or _registry()
    for pid in sorted(getattr(registry, 'specs', {}) or {}):
        if pid not in ids:
            ids.append(pid)
    return ids


def feature_scope(spec):
    """``(per_device, roles)`` for a plugin: whether switching it on for a device does anything
    (it works on inventory devices, ``agent.targets``), and for which roles (None: any)."""
    if getattr(spec, 'id', None) == 'telemetry':
        # Built in, so it has no agent.targets: it polls what has an address to poll.
        return True, ['switch', 'router', 'firewall', 'access-point', 'server', 'pdu']
    block = getattr(spec, 'agent', None) or {}
    targets = block.get('targets') if isinstance(block, dict) else None
    if not targets:
        return False, None
    roles = targets.get('roles') if isinstance(targets, dict) else None
    return True, list(roles) if roles else None


def clean_features(value, registry=None):
    """``{feature: true | false}``; ``null`` (or leaving it out) means inherit."""
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ScopeError('Features are {"feature": true or false}.')
    known = set(known_features(registry))
    out = {}
    for k, v in value.items():
        if v is None:
            continue
        if k not in known:
            raise ScopeError(f'Unknown feature or plugin: {k}')
        if not isinstance(v, bool):
            raise ScopeError(f'{k} is true (on), false (off) or null (inherit).')
        out[k] = v
    return out


def _registry():
    try:
        from . import sources
        return sources.registry
    except (ImportError, AttributeError):
        return None


# ── Groups, tags and defaults ─────────────────────────────────────────────────────────────────

def groups(data):
    return [g for g in data.get(GROUPS) or [] if isinstance(g, dict) and g.get('id')]


def tags(data):
    return [t for t in data.get(TAGS) or [] if isinstance(t, dict) and t.get('id')]


def defaults(data):
    raw = data.get(DEFAULTS) if isinstance(data.get(DEFAULTS), dict) else {}
    return {'properties': dict(raw.get('properties') or {}), 'features': dict(raw.get('features') or {})}


def group(data, group_id):
    return next((g for g in groups(data) if g['id'] == group_id), None)


def tag(data, tag_id):
    return next((t for t in tags(data) if t['id'] == tag_id), None)


def chain(data, group_id):
    """The group and its parents, nearest first (stops at a loop or MAX_DEPTH)."""
    out, seen = [], set()
    by_id = {g['id']: g for g in groups(data)}
    while group_id and group_id in by_id and group_id not in seen and len(out) <= MAX_DEPTH:
        seen.add(group_id)
        out.append(by_id[group_id])
        group_id = by_id[group_id].get('parent_id')
    return out


def _check_tags(data, value):
    if value is None:
        return []
    if not isinstance(value, list):
        raise ScopeError('Tags are a list.')
    known = {t['id'] for t in tags(data)}
    out = []
    for tid in value:
        if tid not in known:
            raise ScopeError('No such tag.')
        if tid not in out:
            out.append(tid)
    return out[:inventory.MAX_TAGS]


def _look(body, target, changed):
    for key in ('icon', 'color'):
        if key in body:
            try:
                value = inventory.clean_look(key, body[key])
            except inventory.InventoryError as exc:
                raise ScopeError(str(exc)) from None
            if value != (target.get(key) or ''):
                target[key] = value
                changed.append(key)


def _common(data, body, target, changed, registry=None):
    """Icon, colour, tags, properties and features: the same on devices, groups and tags."""
    _look(body, target, changed)
    if 'tags' in body:
        value = _check_tags(data, body['tags'])
        if value != (target.get('tags') or []):
            target['tags'] = value
            changed.append('tags')
    if 'properties' in body:
        value = clean_properties(body['properties'], data)
        if value != (target.get('properties') or {}):
            target['properties'] = value
            changed.append('properties')
    if 'features' in body:
        value = clean_features(body['features'], registry)
        if value != (target.get('features') or {}):
            target['features'] = value
            changed.append('features')


def apply_device(data, dev, body, registry=None):
    """The hand-only parts of a device edit (inventory.update/create). Returns what changed."""
    changed = []
    if 'group_id' in body:
        gid = body['group_id'] or None
        if gid and group(data, gid) is None:
            raise inventory.InventoryError('No such group.')
        if gid != dev.get('group_id'):
            dev['group_id'] = gid
            changed.append('group')
    try:
        _common(data, body, dev, changed, registry)
        if 'fields' in body:
            from . import inventory_types
            values = inventory_types.clean_values(data, 'device', body['fields'], dev.get('fields'))
            if values != (dev.get('fields') or {}):
                dev['fields'] = values
                changed.append('fields')
    except ScopeError as exc:
        raise inventory.InventoryError(str(exc)) from None
    return changed


def save_group(data, body, group_id=None, registry=None):
    """Create (no id) or change a group. Returns (group, changed)."""
    with _lock:
        rows = data.setdefault(GROUPS, [])
        if group_id is None:
            if len(rows) >= MAX_GROUPS:
                raise ScopeError(f'At most {MAX_GROUPS} groups.')
            g = {'id': uuid.uuid4().hex[:12], 'name': '', 'parent_id': None, 'icon': '', 'color': '', 'tags': [],
                 'properties': {}, 'features': {}, 'notes': ''}
        else:
            g = group(data, group_id)
            if g is None:
                raise KeyError(group_id)
        changed = []
        if 'name' in body or group_id is None:
            name = clean_name(body.get('name'))
            if any(o['name'].lower() == name.lower() and o['id'] != g['id'] and
                   o.get('parent_id') == body.get('parent_id', g.get('parent_id')) for o in groups(data)):
                raise ScopeError(f'There already is a group called {name} there.')
            if name != g['name']:
                g['name'] = name
                changed.append('name')
        if 'parent_id' in body:
            parent = body['parent_id'] or None
            if parent:
                if group(data, parent) is None:
                    raise ScopeError('No such parent group.')
                if parent == g['id'] or any(p['id'] == g['id'] for p in chain(data, parent)):
                    raise ScopeError('A group cannot be inside itself.')
                if len(chain(data, parent)) >= MAX_DEPTH:
                    raise ScopeError(f'Groups nest at most {MAX_DEPTH} deep.')
            if parent != g.get('parent_id'):
                g['parent_id'] = parent
                changed.append('parent')
        if 'notes' in body:
            notes = str(body['notes'] or '').strip()[:1000]
            if notes != g.get('notes'):
                g['notes'] = notes
                changed.append('notes')
        _common(data, body, g, changed, registry)
        if group_id is None:
            rows.append(g)
        return g, changed


def delete_group(data, group_id):
    """Removes a group. Its devices and child groups move up to its parent."""
    with _lock:
        g = group(data, group_id)
        if g is None:
            raise KeyError(group_id)
        parent = g.get('parent_id')
        for other in groups(data):
            if other.get('parent_id') == group_id:
                other['parent_id'] = parent
        moved = 0
        from . import inventory_types
        for dev in [*inventory.devices(data, include_hidden=True), *inventory_types.holders(data)]:
            if dev.get('group_id') == group_id:
                dev['group_id'] = parent
                moved += 1
        data[GROUPS] = [o for o in groups(data) if o['id'] != group_id]
        _drop_creds(data, 'group', group_id)
        return g, moved


def save_tag(data, body, tag_id=None, registry=None):
    with _lock:
        rows = data.setdefault(TAGS, [])
        if tag_id is None:
            if len(rows) >= MAX_TAGS:
                raise ScopeError(f'At most {MAX_TAGS} tags.')
            t = {'id': uuid.uuid4().hex[:12], 'name': '', 'icon': '', 'color': '', 'properties': {}, 'features': {},
                 'description': ''}
        else:
            t = tag(data, tag_id)
            if t is None:
                raise KeyError(tag_id)
        changed = []
        if 'name' in body or tag_id is None:
            name = clean_name(body.get('name'))
            if any(o['name'].lower() == name.lower() and o['id'] != t['id'] for o in tags(data)):
                raise ScopeError(f'There already is a tag called {name}.')
            if name != t['name']:
                t['name'] = name
                changed.append('name')
        if 'description' in body:
            text = str(body['description'] or '').strip()[:300]
            if text != t.get('description'):
                t['description'] = text
                changed.append('description')
        body = {k: v for k, v in body.items() if k != 'tags'}    # a tag has no tags of its own
        _common(data, body, t, changed, registry)
        if tag_id is None:
            rows.append(t)
        return t, changed


def delete_tag(data, tag_id):
    with _lock:
        t = tag(data, tag_id)
        if t is None:
            raise KeyError(tag_id)
        from . import inventory_types
        for holder in [*inventory.devices(data, include_hidden=True), *groups(data), *inventory_types.holders(data)]:
            if tag_id in (holder.get('tags') or []):
                holder['tags'] = [x for x in holder['tags'] if x != tag_id]
        data[TAGS] = [o for o in tags(data) if o['id'] != tag_id]
        _drop_creds(data, 'tag', tag_id)
        return t


def save_defaults(data, body, registry=None):
    with _lock:
        current = defaults(data)
        changed = []
        if 'properties' in body:
            value = clean_properties(body['properties'], data)
            if value != current['properties']:
                current['properties'] = value
                changed.append('properties')
        if 'features' in body:
            value = clean_features(body['features'], registry)
            if value != current['features']:
                current['features'] = value
                changed.append('features')
        data[DEFAULTS] = current
        return current, changed


# ── Resolving: what a device ends up with ─────────────────────────────────────────────────────

def layers(data, dev):
    """Where a device's settings come from, most specific first: [(kind, holder)]."""
    out = [('device', dev)]
    seen = set()
    for tid in dev.get('tags') or []:
        t = tag(data, tid)
        if t is not None and tid not in seen:
            seen.add(tid)
            out.append(('tag', t))
    for g in chain(data, dev.get('group_id')):
        out.append(('group', g))
        for tid in g.get('tags') or []:
            t = tag(data, tid)
            if t is not None and tid not in seen:
                seen.add(tid)
                out.append(('tag', t))
    from . import inventory_types
    kind = inventory_types.layer(data, dev.get('type') if dev.get('kind') == 'entry' else 'device')
    if kind is not None:
        out.append(('type', kind))
    out.append(('defaults', {'id': 'defaults', 'name': 'All devices', **defaults(data)}))
    return out


def _origin(kind, holder):
    return {'type': kind, 'id': holder.get('id'), 'name': holder.get('name') or ''}


def resolve(data, dev, registry=None):
    """Everything a device ends up with, each value with where it comes from."""
    stack = layers(data, dev)
    props = {}
    for kind, holder in reversed(stack):         # least specific first, so the specific one wins
        for k, v in (holder.get('properties') or {}).items():
            props[k] = {'value': v, 'from': _origin(kind, holder)}
    features = {}
    for fid in known_features(registry):
        hit = next(((kind, h) for kind, h in stack if fid in (h.get('features') or {})), None)
        if hit:
            features[fid] = {'on': bool(hit[1]['features'][fid]), 'from': _origin(*hit)}
        else:
            features[fid] = {'on': fid in CORE_FEATURES, 'from': None}
    all_tags = [{'id': h['id'], 'name': h['name'], 'color': h.get('color') or '', 'icon': h.get('icon') or '',
                 'own': any(h['id'] == t for t in dev.get('tags') or [])}
                for kind, h in stack if kind == 'tag']
    look = {}
    for key in ('icon', 'color'):
        hit = next(((kind, h) for kind, h in stack if kind != 'defaults' and h.get(key)), None)
        look[key] = {'value': hit[1][key], 'from': _origin(*hit)} if hit else {'value': '', 'from': None}
    creds = {}
    for kind_id in KINDS if dev.get('kind') != 'entry' else ():
        cred, origin = _credential_for(data, dev, kind_id, stack)
        if cred is not None:
            creds[kind_id] = {**_cred_public(cred), 'from': origin, 'blocked': _block(dev, cred) is not None}
    group_path = [{'id': g['id'], 'name': g['name']} for g in reversed(chain(data, dev.get('group_id')))]
    return {'properties': props, 'features': features, 'tags': all_tags, 'look': look, 'credentials': creds,
            'group_path': group_path}


def feature_on(data, dev, feature, registry=None):
    for _kind, holder in layers(data, dev):
        value = (holder.get('features') or {}).get(feature)
        if isinstance(value, bool):
            return value
    return feature in CORE_FEATURES


def require(dev, feature, data=None):
    """Raise ScopeError when a core feature is switched off for this device (port actions,
    commands, terminal, config backups check it before they connect)."""
    if dev is None:
        return
    if data is None:
        from .store import load_data
        data = load_data()
    if not feature_on(data, dev, feature):
        words = {'ports': 'Port actions', 'commands': 'Switch commands', 'terminal': 'The terminal',
                 'configs': 'Config backups'}
        raise ScopeError(f"{words.get(feature, feature)} are switched off for {dev['name']} in the inventory.", 403)


# ── Credentials ────────────────────────────────────────────────────────────────────────────

def _creds(data):
    return [c for c in data.get(CREDS) or [] if isinstance(c, dict) and c.get('id')]


def _slot(cred, name):
    return f"inventory:{cred['id']}:{name}"


def _cred_public(cred):
    return {'id': cred['id'], 'kind': cred['kind'], 'owner_type': cred['owner_type'], 'owner_id': cred['owner_id'],
            'username': cred.get('username') or '', 'auth_protocol': cred.get('auth_protocol') or '',
            'priv_protocol': cred.get('priv_protocol') or '', 'rev': cred.get('rev'),
            'set_at': cred.get('set_at'), 'set_by': cred.get('set_by'),
            'secrets': sorted((cred.get('secrets') or {}).keys())}


def credentials_of(data, owner_type, owner_id):
    return [_cred_public(c) for c in _creds(data) if c['owner_type'] == owner_type and c['owner_id'] == owner_id]


def credential_listing(data):
    """Every stored credential, without secrets, with the name of what it is set on."""
    names = {('device', d['id']): d['name'] for d in inventory.devices(data, include_hidden=True)}
    names.update({('group', g['id']): g['name'] for g in groups(data)})
    names.update({('tag', t['id']): t['name'] for t in tags(data)})
    names[('defaults', 'defaults')] = 'All devices'
    return [{**_cred_public(c), 'owner_name': names.get((c['owner_type'], c['owner_id']), '?')} for c in _creds(data)]


def _owner_exists(data, owner_type, owner_id):
    if owner_type == 'device':
        return inventory.find(data, owner_id) is not None
    if owner_type == 'group':
        return group(data, owner_id) is not None
    if owner_type == 'tag':
        return tag(data, owner_id) is not None
    return owner_id == 'defaults'


def set_credential(data, body, by=None):
    """Set or replace the credential of one kind on a device, tag, group or the defaults.
    Secrets left out keep their stored value when the kind stays the same. Returns it (public)."""
    owner_type = body.get('owner_type')
    owner_id = 'defaults' if owner_type == 'defaults' else str(body.get('owner_id') or '')
    kind = body.get('kind')
    if owner_type not in OWNER_TYPES or not _owner_exists(data, owner_type, owner_id):
        raise ScopeError('Pick the device, tag or group the credential is for.')
    if kind not in KINDS:
        raise ScopeError(f"The kind is one of {', '.join(KINDS)}.")
    spec = KINDS[kind]
    with _lock:
        rows = data.setdefault(CREDS, [])
        cred = next((c for c in _creds(data) if c['owner_type'] == owner_type and c['owner_id'] == owner_id
                     and c['kind'] == kind), None)
        if cred is None and len(rows) >= MAX_CREDS:
            raise ScopeError(f'At most {MAX_CREDS} credentials.')
        fresh = {'id': cred['id'] if cred else uuid.uuid4().hex[:12], 'kind': kind, 'owner_type': owner_type,
                 'owner_id': owner_id}
        if 'username' in spec['fields']:
            user = body.get('username')
            if user in (None, '') and not spec['needs_user']:
                fresh['username'] = ''
            elif not isinstance(user, str) or not USER_RE.match(user):
                raise ScopeError('Type the username (one word, up to 64 characters).')
            else:
                fresh['username'] = user
        if kind in ('snmp_v3', 'snmp_trap'):
            auth, priv = body.get('auth_protocol') or 'SHA', body.get('priv_protocol') or 'AES'
            if auth not in AUTH_PROTOCOLS or priv not in PRIV_PROTOCOLS:
                raise ScopeError('Pick the SNMP v3 authentication and privacy protocols.')
            fresh.update(auth_protocol=auth, priv_protocol=priv)
        secrets = dict(cred.get('secrets') or {}) if cred else {}
        for name in spec['secrets']:
            value = body.get(name)
            if value in (None, ''):
                if name not in secrets and name not in spec.get('optional', ()):
                    raise ScopeError('Type the password, community or token.' if name == 'secret'
                                     else 'Type the SNMP v3 privacy passphrase.')
                continue
            if not isinstance(value, str) or len(value) > 512 or '\n' in value:
                raise ScopeError('A secret is one line, up to 512 characters.')
            secrets[name] = vault.seal(_slot(fresh, name), value)
        if secrets.get('priv_secret') and not secrets.get('secret'):
            raise ScopeError('A privacy passphrase needs an authentication passphrase too.')
        fresh['secrets'] = secrets
        fresh.update(rev=uuid.uuid4().hex[:10], set_at=_now(), set_by=by)
        if cred is None:
            rows.append(fresh)
        else:
            cred.clear()
            cred.update(fresh)
        # A new rev clears the blocks the old secret caused.
        for dev in inventory.devices(data, include_hidden=True):
            dev['blocks'] = [b for b in dev.get('blocks') or [] if b.get('credential_id') != fresh['id']]
        return _cred_public(fresh)


def delete_credential(data, cred_id):
    with _lock:
        cred = next((c for c in _creds(data) if c['id'] == cred_id), None)
        if cred is None:
            raise KeyError(cred_id)
        data[CREDS] = [c for c in _creds(data) if c['id'] != cred_id]
        for dev in inventory.devices(data, include_hidden=True):
            dev['blocks'] = [b for b in dev.get('blocks') or [] if b.get('credential_id') != cred_id]
        return _cred_public(cred)


def rotate():
    """Seal every stored credential again with the current key. Returns how many secrets."""
    from .store import load_data, save_data
    with _lock:
        data = load_data()
        done = 0
        for cred in _creds(data):
            for name, sealed in (cred.get('secrets') or {}).items():
                if vault.needs_rotation(sealed):
                    cred['secrets'][name] = vault.seal(_slot(cred, name), vault.open_(_slot(cred, name), sealed))
                    done += 1
        if done:
            save_data(data)
    return done


def _drop_creds(data, owner_type, owner_id):
    data[CREDS] = [c for c in _creds(data) if not (c['owner_type'] == owner_type and c['owner_id'] == owner_id)]


def _credential_for(data, dev, kind, stack=None):
    """(credential, where it comes from) for one kind, or (None, None)."""
    rows = _creds(data)
    for layer_kind, holder in stack or layers(data, dev):
        owner_id = 'defaults' if layer_kind == 'defaults' else holder.get('id')
        cred = next((c for c in rows if c['kind'] == kind and c['owner_type'] == layer_kind
                     and c['owner_id'] == owner_id), None)
        if cred is not None:
            return cred, _origin(layer_kind, holder)
    return None, None


def _open(cred):
    """The credential with its secrets opened, as plugins get it."""
    out = {'id': cred['id'], 'rev': cred.get('rev') or '', 'kind': cred['kind'], 'username': cred.get('username') or ''}
    for key in ('auth_protocol', 'priv_protocol'):
        if cred.get(key):
            out[key] = cred[key]
    for name, sealed in (cred.get('secrets') or {}).items():
        out[name] = vault.open_(_slot(cred, name), sealed)
    return out


def _block(dev, cred):
    return next((b for b in dev.get('blocks') or [] if b.get('credential_id') == cred['id']
                 and b.get('rev') == (cred.get('rev') or '')), None)


def login_for(data, dev, kind='ssh', user=None, purpose=''):
    """The opened credential of ``kind`` for this device, for one use here, or None. Raises
    ScopeError (409) while it is blocked. Each use is in the audit log."""
    from . import audit
    cred, origin = _credential_for(data, dev, kind)
    if cred is None:
        return None
    block = _block(dev, cred)
    if block is not None:
        why = block.get('message') or 'login refused'
        raise ScopeError(f"The stored login for {dev['name']} failed before ({why}). "
                         'A tech clears it on the device in the inventory once it is fixed.', 409)
    try:
        opened = _open(cred)
    except vault.VaultError as exc:
        audit.record('credentials', f"Stored {kind} login for {dev['name']} did not open", user=user,
                     target=dev['name'], ok=False)
        raise ScopeError(str(exc), 500) from None
    what = f"Used the stored {kind} login set on {origin['type']} {origin['name']}"
    audit.record('credentials', what + (f' ({purpose})' if purpose else ''), user=user, target=dev['name'])
    return opened


# ── Blocks after a failed login ───────────────────────────────────────────────────────────────

def _device(data, device_id):
    dev = inventory.find(data, device_id)
    if dev is None:
        dev = next((d for d in inventory.devices(data, include_hidden=True)
                    if d['name'].lower() == str(device_id or '').lower()), None)
    return dev


def block(data, device_id, credential_id, rev, plugin, message, agent=None):
    """Record a failed login with a stored credential. Returns the block, or None when the device
    is unknown or the credential was set again since (a new rev: nothing to block)."""
    with _lock:
        dev = _device(data, device_id)
        if dev is None:
            return None
        cred = next((c for c in _creds(data) if c['id'] == credential_id), None)
        if cred is None or str(rev or '') != str(cred.get('rev') or ''):
            return None
        entry = {'credential_id': credential_id, 'rev': str(rev or ''), 'kind': cred['kind'],
                 'plugin': str(plugin or '')[:40], 'message': str(message or 'login refused')[:300],
                 'agent': (str(agent)[:80] if agent else None), 'at': _now()}
        dev['blocks'] = [b for b in dev.get('blocks') or [] if b.get('credential_id') != credential_id] + [entry]
        return {**entry, 'device_id': dev['id'], 'device': dev['name']}


def clear(data, device_id, credential_id=None):
    """Clear a device's blocks (one credential's, or all). Returns how many."""
    with _lock:
        dev = _device(data, device_id)
        if dev is None:
            raise KeyError(device_id)
        before = dev.get('blocks') or []
        dev['blocks'] = [b for b in before if credential_id and b.get('credential_id') != credential_id]
        return dev, len(before) - len(dev['blocks'])


def blocks(data, device_id=None):
    out = []
    for dev in inventory.devices(data, include_hidden=True):
        if device_id and dev['id'] != device_id:
            continue
        for b in dev.get('blocks') or []:
            out.append({**b, 'device_id': dev['id'], 'device': dev['name']})
    return sorted(out, key=lambda b: -(b.get('at') or 0))


# ── For plugins: the devices a plugin works on ───────────────────────────────────────────────

def targets(data, plugin_id, kinds=None, registry=None):
    """The devices where ``plugin_id`` is on (after inheritance) and a credential of one of
    ``kinds`` (in that order; None: any) resolves and isn't blocked. Secrets stay sealed here."""
    kinds = [k for k in (kinds or KINDS) if k in KINDS]
    out = []
    for dev in inventory.devices(data):
        stack = layers(data, dev)
        on = next(((h.get('features') or {})[plugin_id] for _k, h in stack
                   if isinstance((h.get('features') or {}).get(plugin_id), bool)), False)
        if not on:
            continue
        for kind in kinds:
            cred = _credential_for(data, dev, kind, stack)[0]
            if cred is not None and _block(dev, cred) is None:
                out.append((dev, cred, stack))
                break
    return out


def _properties(stack):
    props = {}
    for _kind, holder in reversed(stack):
        props.update(holder.get('properties') or {})
    return props


def plugin_targets(plugin_id, kinds=None, data=None, registry=None):
    """For agent plugins (floorbit/agent_plugins.py): each device the plugin works on, with its
    credential opened. Audit-logged when the set handed out changes."""
    from . import audit
    from .store import load_data
    data = load_data() if data is None else data
    out, opened = [], []
    for dev, cred, stack in targets(data, plugin_id, kinds, registry):
        try:
            secret = _open(cred)
        except vault.VaultError as exc:
            print(f'[inventory] credential {cred["id"]} for {dev["name"]} did not open: {exc}')
            continue
        opened.append(f"{dev['id']}:{cred['id']}:{cred.get('rev')}")
        out.append({'id': dev['id'], 'name': dev['name'], 'address': dev.get('mgmt_ip') or dev['name'],
                    'role': dev.get('role') or '', 'platform': dev.get('platform') or '',
                    'model': dev.get('model') or '', 'properties': _properties(stack), 'credential': secret})
    fingerprint = hashlib.sha256('|'.join(sorted(opened)).encode()).hexdigest()
    # Per plugin and kinds: a plugin asking once for SNMP and once for API logins logs each once.
    key = f"{plugin_id}:{','.join(kinds or ())}"
    if opened and _handed.get(key) != fingerprint:
        audit.record('credentials', f'Handed stored logins for {len(opened)} devices to the {plugin_id} plugin',
                     user='agent', target=plugin_id)
    _handed[key] = fingerprint
    return out


def auth_failed(device_id, credential_id, rev, plugin_id, message, agent=None):
    """An agent plugin (or a port action here) says a stored credential failed to log in."""
    from . import audit
    from .store import load_data, save_data
    with _lock:
        data = load_data()
        entry = block(data, device_id, credential_id, rev, plugin_id, message, agent)
        if entry is None:
            return None
        save_data(data)
    audit.record('credentials', f"Stored {entry['kind']} login failed; blocked until a tech clears it",
                 user=agent or plugin_id, target=entry['device'], ok=False)
    _publish()
    reload_agents()
    return entry


def clear_block(device_id, credential_id=None, user=None):
    from . import audit
    from .store import load_data, save_data
    with _lock:
        data = load_data()
        dev, cleared = clear(data, device_id, credential_id)
        if cleared:
            save_data(data)
    if cleared:
        audit.record('credentials', 'Cleared a blocked login', user=user, target=dev['name'])
        _publish()
        reload_agents()
    return cleared


def auth_blocks(device_id=None):
    from .store import load_data
    return blocks(load_data(), device_id)


def _publish():
    try:
        from integrations import events
        events.publish('inventory.changed', {})
    except Exception:  # noqa: BLE001 - live updates are best effort
        pass
