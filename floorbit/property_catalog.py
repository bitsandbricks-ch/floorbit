"""Which inventory properties Floorbit knows, and what kind of value each takes (issue #879).

Properties stay free key/value pairs on devices, groups, tags, types and the defaults
(floorbit/inventory_scope.py), but a **known** property has a type, so the editor shows the fitting
input and a wrong value is refused when it is saved:

- **Built in**: the ones Floorbit itself reads (the ``telemetry.*`` set, floorbit/telemetry/targets.py).
- **Custom**: ones admins define (``settings.manage``) with a name, a type, a unit, allowed values
  and the device roles they are for, kept in data.json under ``property_catalog``.

A key in neither list is "custom, untyped": kept as typed, as before, until someone defines it.
Types: text, number, bool (stored as ``true``/``false``), ip, url, choice (one of ``choices``) and
list (any of ``choices``, comma separated). Secrets don't go here: logins are inventory credentials.
"""
import ipaddress
import re

from . import inventory
from .inventory_scope import PROP_KEY_RE, ScopeError

KEY = 'property_catalog'
TYPES = ('text', 'number', 'bool', 'ip', 'url', 'choice', 'list')
MAX_CUSTOM = 100
MAX_CHOICES = 50
TRUE = ('true', 'yes', 'on', '1')
FALSE = ('false', 'no', 'off', '0')


def _def(key, label, kind='text', unit='', choices=(), roles=(), hint=''):
    return {'key': key, 'label': label, 'type': kind, 'unit': unit, 'choices': list(choices),
            'roles': list(roles), 'hint': hint, 'builtin': True}


def _builtin():
    from .telemetry import targets
    routed = ('switch', 'router', 'firewall')
    return [
        _def('telemetry.drivers', 'Telemetry drivers', 'list', choices=targets.DRIVERS,
             hint='What the agent collects with; empty: what fits the platform.'),
        _def('telemetry.agent', 'Collected by agent', hint='The local agent that collects; empty: any.'),
        _def('telemetry.address', 'Telemetry address',
             hint='Where the agent reaches it, when not the management address.'),
        _def('telemetry.verify_tls', 'Check the TLS certificate', 'bool'),
        _def('telemetry.snmp.fdb', 'MAC table over SNMP', 'choice', choices=targets.FDB_MODES, roles=routed),
        _def('telemetry.snmp.vlans', 'VLANs to read over SNMP', roles=routed,
             hint='VLAN IDs, comma separated; empty: the ones on its interfaces.'),
        _def('telemetry.snmp.port', 'SNMP port', 'number'),
        _def('telemetry.gnmi.port', 'gNMI port', 'number'),
        _def('telemetry.api.port', 'API port', 'number'),
        _def('telemetry.api.url', 'API address', 'url'),
        _def('telemetry.mdt.node', 'MDT node name', hint="Cisco's model-driven telemetry; empty: the device name."),
    ]


def _custom(data):
    raw = data.get(KEY)
    return [d for d in raw if isinstance(d, dict) and d.get('key')] if isinstance(raw, list) else []


def catalog(data):
    """Every known property, built-in ones first, then the custom ones by key."""
    builtin = _builtin()
    taken = {d['key'] for d in builtin}
    own = sorted((d for d in _custom(data) if d['key'] not in taken), key=lambda d: d['key'])
    return [*builtin, *({**d, 'builtin': False} for d in own)]


def known(data):
    return {d['key']: d for d in catalog(data)}


def check(definition, value):
    """A property's value as it is stored, or ScopeError when it doesn't fit its type. '' stays ''."""
    value = '' if value is None else str(value).strip()
    if value == '':
        return ''
    kind, label = definition['type'], definition['label']
    if kind == 'number':
        try:
            number = float(value.replace(',', '.'))
        except ValueError:
            raise ScopeError(f'{label} is a number.') from None
        return str(int(number)) if number.is_integer() else str(number)
    if kind == 'bool':
        if value.lower() in TRUE:
            return 'true'
        if value.lower() in FALSE:
            return 'false'
        raise ScopeError(f'{label} is yes or no.')
    if kind == 'ip':
        try:
            return str(ipaddress.ip_address(value))
        except ValueError:
            raise ScopeError(f'{label} is an IP address.') from None
    if kind == 'url':
        if not re.match(r'^https?://[^\s/]+', value):
            raise ScopeError(f'{label} is an address starting with http:// or https://.')
        return value
    if kind == 'choice':
        hit = next((c for c in definition['choices'] if c.lower() == value.lower()), None)
        if hit is None:
            raise ScopeError(f"{label} is one of: {', '.join(definition['choices'])}.")
        return hit
    if kind == 'list':
        out = []
        for word in (w for w in re.split(r'[,\s]+', value) if w):
            hit = next((c for c in definition['choices'] if c.lower() == word.lower()), None)
            if hit is None:
                raise ScopeError(f"{label} takes: {', '.join(definition['choices'])}.")
            if hit not in out:
                out.append(hit)
        return ', '.join(out)
    return value


def check_all(data, properties):
    """Checks the known ones among ``properties`` (already cleaned names); unknown keys pass."""
    defs = known(data)
    return {k: check(defs[k], v) if k in defs else v for k, v in properties.items()}


# ── custom properties ──────────────────────────────────────────────────────────────────────────

def _clean(body, current=None):
    current = current or {}
    key = str(body.get('key', current.get('key')) or '').strip().lower()
    if not PROP_KEY_RE.match(key):
        raise ScopeError(f'{key or "(empty)"} is not a property name (a-z, 0-9, dot, dash, underscore).')
    if key.startswith(('system.', 'auto.', 'telemetry.')):
        raise ScopeError(f"{key}: names starting with system., auto. or telemetry. are Floorbit's own.")
    label = ' '.join(str(body.get('label', current.get('label')) or '').split())[:60] or key
    kind = body.get('type', current.get('type')) or 'text'
    if kind not in TYPES:
        raise ScopeError(f"A property's type is one of: {', '.join(TYPES)}.")
    unit = ' '.join(str(body.get('unit', current.get('unit')) or '').split())[:16]
    choices = body.get('choices', current.get('choices')) or []
    if not isinstance(choices, list):
        raise ScopeError('Send the allowed values as a list.')
    choices = list(dict.fromkeys(' '.join(str(c).split())[:40] for c in choices if str(c).strip()))
    if kind in ('choice', 'list') and not 1 <= len(choices) <= MAX_CHOICES:
        raise ScopeError(f'A choice has 1 to {MAX_CHOICES} allowed values.')
    if kind not in ('choice', 'list'):
        choices = []
    roles = body.get('roles', current.get('roles')) or []
    if not isinstance(roles, list) or any(r not in inventory.ROLES for r in roles):
        raise ScopeError(f"Roles are some of: {', '.join(inventory.ROLES)}.")
    hint = ' '.join(str(body.get('hint', current.get('hint')) or '').split())[:200]
    return {'key': key, 'label': label, 'type': kind, 'unit': unit, 'choices': choices,
            'roles': list(dict.fromkeys(roles)), 'hint': hint}


def save(data, body, key=None):
    """Defines a custom property, or changes one (``key``). Returns the definition."""
    own = _custom(data)
    current = next((d for d in own if d['key'] == key), None) if key else None
    if key and current is None:
        raise ScopeError('No such property.', 404)
    clean = _clean(body, current)
    if any(d is not current and d['key'] == clean['key'] for d in own):
        raise ScopeError(f"{clean['key']} is defined already.", 409)
    if current is None:
        if len(own) >= MAX_CUSTOM:
            raise ScopeError(f'At most {MAX_CUSTOM} properties of your own.', 409)
        own.append(clean)
    else:
        current.clear()
        current.update(clean)
    data[KEY] = own
    return {**clean, 'builtin': False}


def delete(data, key):
    """Forgets a custom property's type; values set with it stay, untyped."""
    own = _custom(data)
    if not any(d['key'] == key for d in own):
        raise ScopeError('No such property.', 404)
    data[KEY] = [d for d in own if d['key'] != key]
