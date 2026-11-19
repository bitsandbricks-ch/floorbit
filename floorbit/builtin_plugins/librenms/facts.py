"""What a device is, from LibreNMS, in the shape of telemetry's ``Device.summary()`` (issue #966), so
discovery fills VLANs, networks and optics when Floorbit's own telemetry is off.

LibreNMS's API has no routes and no PoE budget, so those stay telemetry's. Every answer here is
optional: a LibreNMS that refuses an endpoint (older versions have no ``/transceivers``) just leaves
that part out.
"""
import ipaddress
import re

import requests

from floorbit.runtime import rt

from . import breaker
from .memo import Memo

MAX_OPTICS = 500
# What the ENTITY-MIB fallback takes as an optic, as telemetry does (floorbit/telemetry/state.py).
OPTIC = re.compile(r'SFP|GBIC|XFP|CFP|TRANSCEIVER|GLC-|BASE-?[A-Z]{1,3}\d?\b|TWINAX', re.I)
IPS_TTL = 300            # a port's addresses don't change during an event
_ips = Memo(2000)        # device -> [address rows]


def reset_caches():
    _ips.clear()


def _headers():
    return {'X-Auth-Token': rt.librenms_token, 'Accept': 'application/json'}


def _get(device_id, what, key):
    """The rows LibreNMS lists under ``key``, or None when it can't say (an old version, a 404
    for "none", down)."""
    try:
        resp = breaker.get(f'{rt.librenms_url}/api/v0/{what.format(device=device_id)}', headers=_headers(),
                           timeout=15, verify=rt.librenms_verify_ssl)
    except requests.RequestException:
        return None
    if not resp.ok:
        return None
    try:
        rows = resp.json().get(key)
    except ValueError:
        return None
    return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else None


def _text(value, limit):
    return ' '.join(str(value or '').split())[:limit]


def addresses(device_id):
    """The device's IPv4 addresses: [{ip, prefix, port_id}], kept a few minutes ([] when none)."""
    def load():
        out = []
        for row in _get(device_id, 'devices/{device}/ip', 'addresses') or []:
            try:
                ip = ipaddress.IPv4Address(str(row.get('ipv4_address') or '').strip())
                prefix = int(row.get('ipv4_prefixlen'))
            except (ValueError, TypeError):
                continue                       # IPv6 rows: discovery's networks are IPv4
            if 0 < prefix <= 32:
                out.append({'ip': str(ip), 'prefix': prefix, 'port_id': row.get('port_id')})
        return out
    return _ips.load((rt.librenms_url, str(device_id)), load, IPS_TTL)


def port_facts(row, ips_by_port):
    """mac, ips ['a.b.c.d/nn'], vlan, mode of one LibreNMS port row, as telemetry's port_facts()."""
    from floorbit.sources import normalise_mac
    out = {}
    mac = normalise_mac(row.get('ifPhysAddress'))
    if mac and mac != '00:00:00:00:00:00':
        out['mac'] = mac
    try:
        vlan = int(row.get('ifVlan') or 0)
    except (TypeError, ValueError):
        vlan = 0
    if row.get('ifTrunk'):                     # dot1Q, isl: LibreNMS leaves it empty on access ports
        out['mode'] = 'trunk'
    elif 1 <= vlan <= 4094:
        out['mode'] = 'access'
    if 1 <= vlan <= 4094:
        out['vlan'] = vlan
    ips = ips_by_port.get(row.get('port_id'))
    if ips:
        out['ips'] = sorted(ips)
    return out


def ips_by_port(device_id):
    out = {}
    for a in addresses(device_id):
        out.setdefault(a['port_id'], []).append(f"{a['ip']}/{a['prefix']}")
    return out


def _vlans(device_id):
    out = {}
    for row in _get(device_id, 'devices/{device}/vlans', 'vlans') or []:
        try:
            vid = int(row.get('vlan_vlan'))
        except (TypeError, ValueError):
            continue
        if 1 <= vid <= 4094:
            out[str(vid)] = _text(row.get('vlan_name'), 64)
    return {k: out[k] for k in sorted(out, key=int)}


def _networks(device_id):
    return sorted({str(ipaddress.ip_network(f"{a['ip']}/{a['prefix']}", strict=False))
                   for a in addresses(device_id) if a['prefix'] < 32})


def _optics(device_id, names, by_index):
    """The transceivers LibreNMS lists (its transceivers module), else the optics in its ENTITY-MIB
    inventory, as [{port, model, descr, serial}]."""
    rows = _get(device_id, 'devices/{device}/transceivers', 'transceivers')
    out = []
    if rows is not None:
        for t in rows:
            serial = _text(t.get('serial'), 64)
            if not serial:
                continue
            descr = ' '.join(_text(t.get(k), 40) for k in ('vendor', 'type', 'cable', 'connector') if t.get(k))
            out.append({'port': names.get(t.get('port_id'), ''), 'model': _text(t.get('model'), 80),
                        'descr': descr[:120], 'serial': serial})
        return out[:MAX_OPTICS]
    for row in _get(device_id, 'inventory/{device}/all', 'inventory') or []:
        if str(row.get('entPhysicalClass') or '').lower() not in ('module', 'port', '9', '10'):
            continue
        serial = _text(row.get('entPhysicalSerialNum'), 64)
        model, descr = _text(row.get('entPhysicalModelName'), 80), _text(row.get('entPhysicalDescr'), 120)
        name = _text(row.get('entPhysicalName'), 64)
        if not serial or not OPTIC.search(f'{model} {descr} {name}'):
            continue
        out.append({'port': by_index.get(str(row.get('ifIndex'))) or name, 'model': model, 'descr': descr,
                    'serial': serial})
        if len(out) >= MAX_OPTICS:
            break
    return out


def summary(device_id, ports):
    """The facts of one LibreNMS device (``ports``: its port rows with port_id, ifIndex and ifName):
    vlans, networks, transceivers. Only what LibreNMS said."""
    names = {p.get('port_id'): p.get('ifName') for p in ports if p.get('ifName')}
    by_index = {str(p.get('ifIndex')): p.get('ifName') for p in ports if p.get('ifName')}
    out = {}
    vlans = _vlans(device_id)
    if vlans:
        out['vlans'] = vlans
    networks = _networks(device_id)
    if networks:
        out['networks'] = networks
    optics = _optics(device_id, names, by_index)
    if optics:
        out['transceivers'] = optics
    return out
