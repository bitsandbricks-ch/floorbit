"""The devices telemetry is collected from, and how (docs/telemetry.md): the inventory's devices
with the Telemetry feature on. Their logins are the inventory's stored credentials; only the
ingest token is kept here, in data.json under ``telemetry``, sealed with floorbit/vault.py.

A target is one device: its name, its address, and the drivers that collect from it:

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
import re
import secrets
import threading

from .. import vault
from ..store import load_data, save_data
from .telegraf import PORT_KINDS

KEY = 'telemetry'
DRIVERS = ('snmp', 'traps', 'gnmi', 'mdt', 'nxapi', 'restconf', 'opnsense', 'push')
KINDS = ('switch', 'router', 'firewall')
PLATFORMS = ('nxos', 'iosxe', 'ios', 'opnsense', 'pfsense', 'other')
FDB_MODES = ('qbridge', 'cisco_vlans', 'bridge', 'off')
AGENT_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z')
SECRETS = ('community', 'auth_password', 'priv_password', 'password', 'api_secret')
_lock = threading.Lock()


def _section(data=None):
    data = load_data() if data is None else data
    return data.get(KEY) or {}


def _int(value, low, high, default):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, number))


def _ports(value):
    value = value if isinstance(value, dict) else {}
    out = {k: _int(value.get(k), 1, 65535, 0) for k in PORT_KINDS}
    return {k: v for k, v in out.items() if v}


def _agent(value):
    value = str(value or '').strip()
    return value if AGENT_RE.match(value) else ''


# ── devices from the inventory ─────────────────────────────────────────────────────────────────
# A device in the inventory with the Telemetry feature on (on itself, a tag, its group or type) is
# collected from like one set up here, with the logins stored in the inventory: SNMP v3 or v2c for
# polling and traps, an API login for NX-API, RESTCONF or OPNsense. Its properties can say more:
# telemetry_drivers, telemetry_fdb, telemetry_vlans, telemetry_port_snmp, telemetry_port_gnmi,
# telemetry_port_api, telemetry_agent (the agent that collects), telemetry_address, telemetry_url, telemetry_mdt_node,
# telemetry_verify_tls. Like every property they come from the device, its tags, group or type.
# A device that sends by itself (push, mdt, traps in telemetry_drivers) needs no login.

FEATURE = 'telemetry'
API_DRIVER = {'nxos': 'nxapi', 'iosxe': 'restconf', 'opnsense': 'opnsense'}
# What a device does on its own: these need no stored login.
SENDING = ('push', 'mdt', 'traps')


def _platform(text):
    t = str(text or '').lower().replace(' ', '').replace('_', '-')
    for needle, platform in (('nx', 'nxos'), ('ios-xe', 'iosxe'), ('iosxe', 'iosxe'), ('ios', 'ios'),
                             ('opnsense', 'opnsense'), ('pfsense', 'pfsense')):
        if needle in t:
            return platform
    return 'other'


def auto(platform, has_snmp, has_api):
    """What telemetry does for a device that leaves it open, from its software and its logins:
    SNMP polling and traps with an SNMP login, the platform's API with an API login, MAC tables per
    VLAN on Cisco IOS and IOS-XE. MDT, gNMI and a firewall's own Telegraf need setting up on the
    device first, so they are never on by themselves."""
    drivers = ['snmp', 'traps'] if has_snmp else []
    if has_api and platform in API_DRIVER:
        drivers.append(API_DRIVER[platform])
    return {'drivers': drivers, 'fdb': 'cisco_vlans' if platform in ('ios', 'iosxe') else 'qbridge'}


def iface_vlans(dev):
    """The VLANs on a device's interfaces: where a Cisco switch keeps a MAC table each."""
    return sorted({int(i['vlan']) for i in dev.get('interfaces') or []
                   if not i.get('hidden') and str(i.get('vlan') or '').isdigit() and 1 <= int(i['vlan']) <= 4094})


def _words(value):
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return [w for w in re.split(r'[,\s]+', str(value or '')) if w]


def _from_device(dev, snmp, api):
    """One telemetry target (secrets open) from an inventory device and its opened logins. What its
    properties leave open comes from auto() and, for the VLANs, from its interfaces."""
    props = dev.get('properties') or {}
    platform = _platform(dev.get('platform'))
    kind = dev.get('role') if dev.get('role') in KINDS else 'switch'
    given = auto(platform, bool(snmp), bool(api))
    drivers = [d for d in _words(props.get('telemetry_drivers')) if d in DRIVERS]
    if not snmp and not api:
        drivers = [d for d in drivers if d in SENDING]
    drivers = drivers or given['drivers']
    # telemetry_address: where the agent reaches it, when not its management address (a NAT, a lab).
    address = str(props.get('telemetry_address') or '').strip()[:253] or dev['address']
    vlans = {int(v) for v in _words(props.get('telemetry_vlans')) if v.isdigit() and 1 <= int(v) <= 4094}
    t = {'id': f"inv-{dev['id']}", 'name': dev['name'], 'address': address, 'kind': kind,
         'platform': platform, 'drivers': drivers, 'source': 'inventory', 'inventory_id': dev['id'],
         'fdb': props.get('telemetry_fdb') if props.get('telemetry_fdb') in FDB_MODES else given['fdb'],
         'vlans': sorted(vlans) or list(dev.get('iface_vlans') or []),
         'ports': _ports({k: props.get(f'telemetry_port_{k}') for k in PORT_KINDS}),
         'agent': _agent(props.get('telemetry_agent')),
         'url': str(props.get('telemetry_url') or '').strip() or None,
         # Cisco names the stream after the switch unless it is set up otherwise.
         'mdt_node': str(props.get('telemetry_mdt_node') or '').strip() or (dev['name'] if 'mdt' in drivers else None),
         'verify_tls': str(props.get('telemetry_verify_tls', 'true')).lower() not in ('false', '0', 'no', 'off'),
         'tables': True, 'snmp_version': '2c', 'logins': {}}
    if t['url'] and not t['url'].startswith('https://'):
        t['url'] = None
    if snmp:
        c = snmp
        # The inventory's block (device id, credential id, revision) is what a refused login stops.
        t['logins']['snmp'] = {'device': dev['id'], 'credential': c['id'], 'rev': c.get('rev') or ''}
        if c['kind'] == 'snmp_v3':
            t.update(snmp_version='3', sec_name=c.get('username') or '',
                     auth_protocol=c.get('auth_protocol') or 'SHA', priv_protocol=c.get('priv_protocol') or 'AES',
                     auth_password=c.get('secret') or '', priv_password=c.get('priv_secret') or '')
        else:
            t['community'] = c.get('secret') or ''
    if api:
        c = api
        t['logins']['api'] = {'device': dev['id'], 'credential': c['id'], 'rev': c.get('rev') or ''}
        t['username'] = c.get('username') or ''
        t['password' if platform != 'opnsense' else 'api_secret'] = c.get('secret') or ''
    return t if t['drivers'] else None


def from_inventory(data=None):
    """Telemetry targets for the inventory devices with the Telemetry feature on, logins opened.
    Only for the collector (its config, or the agent over its link)."""
    from .. import inventory, inventory_scope
    data = load_data() if data is None else data
    try:
        snmp = {d['id']: d for d in inventory_scope.plugin_targets(FEATURE, ['snmp_v3', 'snmp_v2c'], data)}
        api = {d['id']: d for d in inventory_scope.plugin_targets(FEATURE, ['api', 'http'], data)}
        # The ones without a login that send by themselves (a firewall's own Telegraf, MDT dial-out).
        bare = {}
        for dev in inventory.devices(data):
            if dev['id'] in snmp or dev['id'] in api or not inventory_scope.feature_on(data, dev, FEATURE):
                continue
            stack = inventory_scope.layers(data, dev)
            bare[dev['id']] = {'id': dev['id'], 'name': dev['name'], 'address': dev.get('mgmt_ip') or dev['name'],
                               'role': dev.get('role') or '', 'platform': dev.get('platform') or '',
                               'properties': inventory_scope._properties(stack)}
    except Exception as exc:  # noqa: BLE001  # no inventory devices is better than no telemetry
        print(f'[telemetry] inventory devices: {exc}')
        return []
    found = {**bare, **api, **snmp}
    out = []
    for dev_id in sorted(found, key=lambda i: found[i]['name'].lower()):
        found[dev_id]['iface_vlans'] = iface_vlans(inventory.find(data, dev_id) or {})
        t = _from_device(found[dev_id], (snmp.get(dev_id) or {}).get('credential'),
                         (api.get(dev_id) or {}).get('credential'))
        if t:
            out.append(t)
    return out


def for_device(device_id, data=None):
    """One inventory device's telemetry as its page shows it, without opening a login: whether the
    feature is on, which logins it has, what is automatic, and what the collector would do."""
    from .. import inventory, inventory_scope
    data = load_data() if data is None else data
    dev = inventory.find(data, device_id)
    if dev is None:
        return None
    on = inventory_scope.feature_on(data, dev, FEATURE)
    stack = inventory_scope.layers(data, dev)
    logins = {}
    for name, kinds in (('snmp', ('snmp_v3', 'snmp_v2c')), ('api', ('api', 'http'))):
        for kind in kinds:
            cred = inventory_scope._credential_for(data, dev, kind, stack)[0]
            if cred is not None and inventory_scope._block(dev, cred) is None:
                logins[name] = {'id': cred['id'], 'kind': kind, 'rev': cred.get('rev') or '', 'username': ''}
                break
    platform = _platform(dev.get('platform'))
    flat = {'id': dev['id'], 'name': dev['name'], 'address': dev.get('mgmt_ip') or dev['name'],
            'role': dev.get('role') or '', 'platform': dev.get('platform') or '',
            'properties': inventory_scope._properties(stack), 'iface_vlans': iface_vlans(dev)}
    target = _from_device(flat, logins.get('snmp'), logins.get('api')) if on else None
    if target:
        target = {k: v for k, v in target.items() if k not in SECRETS and k != 'logins'}
    return {'on': on, 'platform': platform, 'logins': {k: v['kind'] for k, v in logins.items()},
            'auto': {**auto(platform, 'snmp' in logins, 'api' in logins), 'vlans': flat['iface_vlans'],
                     'mdt_node': dev['name'], 'address': flat['address']},
            'target': target}


def any_device(data=None):
    """Is the Telemetry feature on for any inventory device? Cheap: opens no logins."""
    from .. import inventory, inventory_scope
    data = load_data() if data is None else data
    return any(inventory_scope.feature_on(data, dev, FEATURE) for dev in inventory.devices(data))


def all_opened(data=None):
    """Every device to collect from with its secrets open."""
    return from_inventory(data)


def listing(data=None):
    """The devices as the Telemetry page shows them: no secrets (only which ones are set)."""
    return [{k: v for k, v in t.items() if k not in SECRETS and k != 'logins'}
            | {'secrets': sorted(k for k in SECRETS if t.get(k))} for t in from_inventory(data)]


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


# ── which agent collects ──────────────────────────────────────────────────────────────────────
# A device with an agent (telemetry_agent) is collected by that agent alone, even when it stands by
# for another (VRRP): "mine" tells it to. While that agent is away, the device goes back to the
# rest like one without an agent, so it isn't left unheard. Without an agent, every agent gets it
# and the primary one polls (the agent's own rule).

def for_agent(every, agent_id, connected):
    """The targets ``agent_id`` gets, ``mine`` set on those only it collects. ``connected``: the
    agent ids connected now. ``agent_id`` None (an agent that doesn't say who it is): every target,
    as before."""
    if agent_id is None:
        return [dict(t) for t in every]
    out = []
    for t in every:
        owner = t.get('agent') or ''
        if owner and owner in connected:
            if owner == agent_id:
                out.append({**t, 'mine': True})
        else:
            out.append(dict(t))
    return out


def pinned(data=None):
    """{device name, lower case: agent id} for the devices with an agent: where calls about them go."""
    from .. import inventory, inventory_scope
    data = load_data() if data is None else data
    out = {}
    for dev in inventory.devices(data, include_hidden=True):
        name = str(dev.get('name') or '').lower()
        if not name or name in out:
            continue
        stack = inventory_scope.layers(data, dev)
        agent = _agent(next((h['properties']['telemetry_agent'] for _k, h in stack
                             if (h.get('properties') or {}).get('telemetry_agent')), ''))
        if agent:
            out[name] = agent
    return out
