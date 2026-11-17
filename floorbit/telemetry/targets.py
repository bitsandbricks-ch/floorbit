"""The devices telemetry is collected from, and how (docs/telemetry.md). Kept in data.json under
``telemetry``; secrets (SNMP communities, v3 passphrases, gNMI, NX-API, RESTCONF and OPNsense
logins) are sealed with floorbit/vault.py and are write-only, like stored switch logins.

A target is one device: its floor plan name, its address, and the drivers that collect from it:

- ``snmp``: polling (IF-MIB, BRIDGE/Q-BRIDGE MAC tables, IP-MIB ARP, LLDP, CDP), v2c or v3.
- ``traps``: SNMP traps to the collector (linkUp/linkDown change a port at once).
- ``gnmi``: gNMI subscriptions (NX-OS 9.3+, IOS-XE 16.12+), OpenConfig interfaces.
- ``mdt``: Cisco model-driven telemetry dial-out (the device connects to the collector's gRPC port).
- ``nxapi``: NX-API on a Nexus (ARP and interfaces over HTTPS JSON-RPC).
- ``restconf``: RESTCONF on IOS-XE 16+ (ARP and interfaces, the same YANG models MDT streams).
- ``opnsense``: the OPNsense API (gateways, ARP, interfaces).
- ``push``: the device runs Telegraf itself and sends to the collector (OPNsense os-telegraf, the
  pfSense Telegraf package); nothing to poll.
"""
import ipaddress
import re
import secrets
import threading
import time
import uuid

from .. import vault
from ..store import load_data, save_data

KEY = 'telemetry'
MAX = 500
DRIVERS = ('snmp', 'traps', 'gnmi', 'mdt', 'nxapi', 'restconf', 'opnsense', 'push')
KINDS = ('switch', 'router', 'firewall')
PLATFORMS = ('nxos', 'iosxe', 'ios', 'opnsense', 'pfsense', 'other')
FDB_MODES = ('qbridge', 'cisco_vlans', 'bridge', 'off')
SECRETS = ('community', 'auth_password', 'priv_password', 'password', 'api_secret')
NAME_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$')
HOST_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9.:-]{0,252}$')
USER_RE = re.compile(r'^[^\s\x00-\x1f]{1,64}$')
_lock = threading.Lock()


class TargetError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def _section(data=None):
    data = load_data() if data is None else data
    return data.get(KEY) or {}


def _slot(target_id, name):
    return f'telemetry:{target_id}:{name}'


def _public(t):
    out = {k: v for k, v in t.items() if k not in SECRETS}
    out['secrets'] = sorted(k for k in SECRETS if t.get(k))
    return out


def listing(data=None):
    """Every target, secrets left out (only which ones are set)."""
    return [_public(t) for t in sorted(_section(data).get('targets') or [], key=lambda t: t['name'].lower())]


def raw_targets(data=None):
    return list(_section(data).get('targets') or [])


def _int(value, low, high, default):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, number))


def _clean(body, existing=None):
    existing = existing or {}
    name = str(body.get('name', existing.get('name')) or '').strip()
    if not NAME_RE.match(name):
        raise TargetError('Name it as on the floor plan (letters, digits, dot, dash, underscore).')
    address = str(body.get('address', existing.get('address')) or '').strip()
    if not HOST_RE.match(address):
        raise TargetError('Give the device address, an IP or a host name.')
    drivers = body.get('drivers', existing.get('drivers') or [])
    if not isinstance(drivers, list) or not drivers or any(d not in DRIVERS for d in drivers):
        raise TargetError(f'Pick at least one way to collect: {", ".join(DRIVERS)}.')
    out = {'name': name, 'address': address, 'drivers': sorted(set(drivers), key=DRIVERS.index)}
    kind = body.get('kind', existing.get('kind') or 'switch')
    platform = body.get('platform', existing.get('platform') or 'other')
    if kind not in KINDS or platform not in PLATFORMS:
        raise TargetError('Unknown device kind or platform.')
    out.update(kind=kind, platform=platform)
    snmp = body.get('snmp_version', existing.get('snmp_version') or '2c')
    if snmp not in ('2c', '3'):
        raise TargetError('SNMP version is 2c or 3.')
    out['snmp_version'] = snmp
    for key in ('username', 'sec_name'):
        value = body.get(key, existing.get(key))
        if value not in (None, ''):
            if not isinstance(value, str) or not USER_RE.match(value):
                raise TargetError('A username is one word, at most 64 characters.')
            out[key] = value
    for key, allowed in (('auth_protocol', ('', 'MD5', 'SHA', 'SHA224', 'SHA256', 'SHA384', 'SHA512')),
                         ('priv_protocol', ('', 'DES', 'AES', 'AES192', 'AES256', 'AES192C', 'AES256C')),
                         ('fdb', FDB_MODES)):
        value = body.get(key, existing.get(key) or ('qbridge' if key == 'fdb' else ''))
        if value not in allowed:
            raise TargetError(f'{key} must be one of {", ".join(a for a in allowed if a)}.')
        out[key] = value
    if snmp == '3':
        out['auth_protocol'] = out['auth_protocol'] or 'SHA'
        out['priv_protocol'] = out['priv_protocol'] or 'AES'
    if out['platform'] in ('ios', 'iosxe') and 'fdb' not in body and not existing:
        out['fdb'] = 'cisco_vlans'       # Catalyst IOS answers MAC tables per VLAN only
    vlans = body.get('vlans', existing.get('vlans') or [])
    if isinstance(vlans, str):
        vlans = [v for v in re.split(r'[,\s]+', vlans) if v]
    try:
        vlans = sorted({int(v) for v in vlans})
    except (TypeError, ValueError):
        raise TargetError('VLANs are numbers, like 10, 20, 30.') from None
    if any(not 1 <= v <= 4094 for v in vlans) or len(vlans) > 64:
        raise TargetError('At most 64 VLANs, each 1 to 4094.')
    out['vlans'] = vlans
    out['port'] = _int(body.get('port', existing.get('port')), 1, 65535, 0) or None
    out['verify_tls'] = bool(body.get('verify_tls', existing.get('verify_tls', True)))
    out['tables'] = bool(body.get('tables', existing.get('tables', True)))
    out['mdt_node'] = str(body.get('mdt_node', existing.get('mdt_node')) or '').strip()[:80] or None
    out['url'] = str(body.get('url', existing.get('url')) or '').strip()[:300] or None
    if out['url'] and not out['url'].startswith('https://'):
        raise TargetError('API addresses must start with https://.')
    return out


def save(body, by, target_id=None):
    """Add or change a target. Secrets in ``body`` replace the stored ones; an empty string removes
    one; a missing key keeps it. Returns the public entry."""
    if not isinstance(body, dict):
        raise TargetError('Send the device as JSON.')
    with _lock:
        data = load_data()
        section = data.setdefault(KEY, {})
        rows = section.setdefault('targets', [])
        entry = next((t for t in rows if t['id'] == target_id), None) if target_id else None
        if target_id and entry is None:
            raise TargetError('That device is gone.', 404)
        clean = _clean(body, entry)
        if any(t['name'].lower() == clean['name'].lower() and t is not entry for t in rows):
            raise TargetError(f'{clean["name"]} is already in the list.', 409)
        if entry is None:
            if len(rows) >= MAX:
                raise TargetError(f'Floorbit collects from at most {MAX} devices.')
            entry = {'id': uuid.uuid4().hex[:12]}
            rows.append(entry)
        entry.update(clean, set_at=time.time(), set_by=by)
        for key in SECRETS:
            if key not in body:
                continue
            value = body.get(key)
            if value in (None, ''):
                entry.pop(key, None)
            elif not isinstance(value, str) or len(value) > 256 or '\n' in value:
                raise TargetError('Secrets are one line, at most 256 characters.')
            else:
                entry[key] = vault.seal(_slot(entry['id'], key), value)
        save_data(data)
    return _public(entry)


def delete(target_id):
    with _lock:
        data = load_data()
        rows = (data.get(KEY) or {}).get('targets') or []
        gone = next((t for t in rows if t['id'] == target_id), None)
        if gone is None:
            return None
        data[KEY]['targets'] = [t for t in rows if t is not gone]
        save_data(data)
    return _public(gone)


def opened(target):
    """The target with its secrets opened, for the collector's config. Only ever handed to the
    collector (the sidecar's config file, or the agent over its TLS link), never to a browser."""
    out = dict(target)
    for key in SECRETS:
        if target.get(key):
            out[key] = vault.open_(_slot(target['id'], key), target[key])
    return out


# ── the ingest token: what Telegraf (and a firewall's own Telegraf) shows to send ──────────────

def ingest_token(create=True):
    """The token senders use. Made on first use and kept sealed; admins can see it again (it only
    lets someone write telemetry, and every firewall's Telegraf needs it typed in)."""
    data = load_data()
    sealed = _section(data).get('ingest_token')
    if sealed:
        return vault.open_('telemetry:ingest', sealed)
    if not create:
        return None
    with _lock:
        data = load_data()
        section = data.setdefault(KEY, {})
        if not section.get('ingest_token'):
            section['ingest_token'] = vault.seal('telemetry:ingest', 'fbt_' + secrets.token_urlsafe(24))
            save_data(data)
        return vault.open_('telemetry:ingest', section['ingest_token'])


def new_ingest_token():
    with _lock:
        data = load_data()
        data.setdefault(KEY, {})['ingest_token'] = vault.seal('telemetry:ingest', 'fbt_' + secrets.token_urlsafe(24))
        save_data(data)
    return ingest_token()


def token_ok(given):
    if not given:
        return False
    want = ingest_token(create=False)
    return bool(want) and secrets.compare_digest(str(given), want)


def is_address(text):
    try:
        ipaddress.ip_address(str(text))
        return True
    except ValueError:
        return False
