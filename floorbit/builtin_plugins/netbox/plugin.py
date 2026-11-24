"""NetBox as an inventory source: GET /api/dcim/devices/ for the configured roles with their
interfaces (/api/dcim/interfaces/, addresses from /api/ipam/ip-addresses/) and the virtual machines
(/api/virtualization/virtual-machines/ and their interfaces),
GET /api/dcim/cables/ for the cables page (issue #97), and GET /api/ipam/prefixes/ for the firewall
ranges (issue #470)."""
import contextlib
import re
from urllib.parse import urlsplit

from floorbit.plugins.base import Plugin, PluginError

PAGE = 500
MAX_PAGES = 40   # 20,000 devices: far more than a LAN party has; stops a loop on a bad "next"


ROLE_WORDS = ((('switch', 'sw'), 'switch'), (('router', 'rtr'), 'router'), (('firewall', 'fw'), 'firewall'),
              (('ap', 'wifi', 'wlan', 'wireless', 'access'), 'access-point'), (('server', 'srv'), 'server'))


SEAT_RE = re.compile(r'\bseat[:\s]+([A-Za-z0-9-]{1,16})', re.I)
UNITS = {'m': 1.0, 'cm': 0.01, 'km': 1000.0, 'ft': 0.3048, 'in': 0.0254}
# NetBox stores cable colours as hex; name the usual patch cable ones.
COLORS = {'0000ff': 'blue', '2196f3': 'blue', 'ff0000': 'red', 'f44336': 'red', '00ff00': 'green',
          '4caf50': 'green', 'ffff00': 'yellow', 'ffeb3b': 'yellow', 'ffffff': 'white', '000000': 'black',
          '9e9e9e': 'grey', '111111': 'black', 'ff9800': 'orange', 'ffa500': 'orange', '9c27b0': 'purple'}


def _role(slug):
    """NetBox role slugs are free text ("access-switch", "core-router"); map them to ours."""
    words = set((slug or '').lower().replace('_', '-').split('-'))
    return next((role for keys, role in ROLE_WORDS if words & set(keys)), 'other')


def _name(obj, *keys):
    for k in keys:
        if isinstance(obj, dict):
            obj = obj.get(k)
    return str(obj) if obj not in (None, '') else ''


def device(d):
    """One NetBox device as an inventory entry (works with NetBox 3.x and 4.x)."""
    role = d.get('role') or d.get('device_role') or {}
    ip = _name(d, 'primary_ip', 'address').split('/')[0]
    return {
        'id': str(d['id']),
        'name': d.get('name') or '',
        'role': _role(role.get('slug') if isinstance(role, dict) else ''),
        'model': _name(d, 'device_type', 'model'),
        'serial': d.get('serial') or '',
        'mgmt_ip': ip,
        'hall': _name(d, 'location', 'name') or _name(d, 'site', 'name'),
        'status': _name(d, 'status', 'value'),
        'platform': _name(d, 'platform', 'name'),
    }


# NetBox interface types ("1000base-t", "10gbase-x-sfpp", "virtual", "lag", "ieee802.11ax") as ours.
def _iface_type(value):
    value = str(value or '').lower()
    if not value:
        return ''
    if value in ('virtual', 'bridge'):
        return 'virtual'
    if value == 'lag':
        return 'lag'
    if value.startswith('ieee802.11') or 'wireless' in value or value.startswith('other-wireless'):
        return 'wireless'
    if 'dac' in value or 'cx4' in value:
        return 'dac'
    if 'base-t' in value or value.endswith('-t') or 'baset' in value:
        return 'copper'
    if any(k in value for k in ('sfp', 'qsfp', 'xfp', 'cfp', 'osfp', 'base-x', 'base-sr', 'base-lr', 'gbic')):
        return 'fiber'
    return 'other'


def _mac(raw):
    # NetBox 4.2 moved the MAC to its own object.
    return raw.get('mac_address') or _name(raw, 'primary_mac_address', 'mac_address')


def interface(raw, ips=()):
    """One NetBox interface (device or VM) as a Floorbit interface."""
    mode = _name(raw, 'mode', 'value')
    kind = _iface_type(_name(raw, 'type', 'value')) if raw.get('type') else 'virtual'   # VM interfaces have no type
    out = {'name': raw.get('name') or '', 'type': kind, 'description': (raw.get('description') or '')[:200],
           'enabled': raw.get('enabled', True) is not False, 'mgmt': bool(raw.get('mgmt_only')),
           'mode': 'access' if mode == 'access' else 'trunk' if mode else '',
           'lag': _name(raw, 'lag', 'name'), 'ips': list(ips)}
    if isinstance(raw.get('speed'), int) and raw['speed'] > 0:
        out['speed_mbps'] = max(1, raw['speed'] // 1000)        # NetBox counts kbps
    if _mac(raw):
        out['mac'] = _mac(raw)
    vid = (raw.get('untagged_vlan') or {}).get('vid') if isinstance(raw.get('untagged_vlan'), dict) else None
    if vid:
        out['vlan'] = vid
    return out


def _number(value):
    try:
        return str(int(float(value)))
    except (TypeError, ValueError):
        return ''


def vm(raw, disk_in_mb):
    """One NetBox virtual machine as an inventory entry (role "vm")."""
    disk = raw.get('disk')
    if isinstance(disk, (int, float)) and disk_in_mb:
        disk = disk / 1000          # NetBox 4.1 and later keep the disk in MB
    return {
        'id': f"vm-{raw['id']}",
        'name': raw.get('name') or '',
        'role': 'vm',
        'mgmt_ip': _name(raw, 'primary_ip', 'address').split('/')[0],
        'hall': _name(raw, 'site', 'name'),
        'status': _name(raw, 'status', 'value'),
        'platform': _name(raw, 'platform', 'name'),
        'cores': _number(raw.get('vcpus')),
        'memory_mb': _number(raw.get('memory')),
        'disk_gb': _number(disk),
        'host': _name(raw, 'device', 'name') or _name(raw, 'cluster', 'name'),
    }


def _ends(raw, side):
    """The terminations of one side of a NetBox cable (4.x: a_terminations, 3.x: termination_a)."""
    ends = raw.get(f'{side}_terminations')
    if ends is None and raw.get(f'termination_{side}'):
        ends = [{'object_type': raw.get(f'termination_{side}_type'), 'object': raw[f'termination_{side}']}]
    return ends or []


def _end(raw, side):
    for t in _ends(raw, side):
        kind = str(t.get('object_type') or t.get('termination_type') or '')
        obj = t.get('object') or t.get('termination') or {}
        if not isinstance(obj, dict):
            continue
        dev = _name(obj, 'device', 'name') or _name(obj, 'device', 'display')
        if kind.endswith('interface'):
            return 'interface', dev, obj.get('name') or ''
        if kind.endswith('frontport') or kind.endswith('rearport'):
            return 'panel', dev, obj.get('name') or ''
    return None, '', ''


def cable(raw):
    """One NetBox cable as a Floorbit cable, or None when neither end is an interface.

    A seat isn't a NetBox object, so a seat comes from the cable's description (``seat: A-12``)
    or, failing that, from the far interface's device name when it isn't the switch.
    """
    a, b = _end(raw, 'a'), _end(raw, 'b')
    if a[0] != 'interface':
        a, b = b, a
    if a[0] != 'interface' or not a[1] or not a[2]:
        return None
    out = {'label': raw.get('label') or f"NB-{raw.get('id')}", 'switch': a[1], 'port': a[2],
           'panel': b[1] if b[0] == 'panel' else '', 'panel_port': b[2] if b[0] == 'panel' else '',
           'seat': '', 'color': '', 'length_m': None, 'note': raw.get('description') or ''}
    m = SEAT_RE.search(out['note'])
    if m:
        out['seat'] = m.group(1)
    color = (raw.get('color') or '').lower()
    out['color'] = COLORS.get(color, f'#{color}' if color else '')
    if raw.get('length') not in (None, ''):
        unit = _name(raw, 'length_unit', 'value') or 'm'
        with contextlib.suppress(TypeError, ValueError):
            out['length_m'] = round(float(raw['length']) * UNITS.get(unit, 1.0), 1) or None
    return out


FIREWALL_FIELD = 'floorbit_firewalls'


def _firewall_line(value):
    """A prefix's firewalls in order, from the custom field: text ("fw-1, fw-2") or a multi-object
    field of devices (each with a name)."""
    if isinstance(value, str):
        items = value.replace(';', ',').split(',')
    elif isinstance(value, list):
        items = [v.get('name') or v.get('display') if isinstance(v, dict) else v for v in value]
    else:
        return []
    return [str(v).strip() for v in items if v and str(v).strip()]


def firewall_range(raw):
    """A NetBox prefix as a Floorbit firewall range, or None when it names no firewall."""
    line = _firewall_line((raw.get('custom_fields') or {}).get(FIREWALL_FIELD))
    if not raw.get('prefix') or not line:
        return None
    return {'cidr': raw['prefix'], 'name': (raw.get('description') or '')[:60], 'firewalls': line}



# ── Other inventory types (floorbit/inventory_types.py) ───────────────────────────

TRANSCEIVER_WORDS = ('sfp', 'qsfp', 'xfp', 'transceiver', 'optic', 'gbic', 'dac')


def _custom(raw):
    """NetBox custom fields with a plain value: they fill type fields with the same key."""
    return {k: v for k, v in (raw.get('custom_fields') or {}).items() if isinstance(v, (str, int, float, bool))}


def rack(raw):
    site = _name(raw, 'location', 'name') or _name(raw, 'site', 'name')
    return {'ref': f"rack-{raw['id']}", 'name': raw.get('name') or '',
            'fields': {**_custom(raw), 'height_u': raw.get('u_height') or '', 'hall': site}}


def location(raw):
    return {'ref': f"location-{raw['id']}", 'name': raw.get('name') or '',
            'fields': {**_custom(raw), 'hall': _name(raw, 'site', 'name')}}


def vlan(raw):
    return {'ref': f"vlan-{raw['id']}", 'name': raw.get('name') or f"VLAN {raw.get('vid')}",
            'fields': {**_custom(raw), 'vlan_id': raw.get('vid') or ''}}


def prefix(raw):
    return {'ref': f"prefix-{raw['id']}", 'name': raw.get('description') or raw.get('prefix') or '',
            'fields': {**_custom(raw), 'prefix': raw.get('prefix') or '', 'vlan_id': _name(raw, 'vlan', 'vid')}}


def _speed_word(text):
    for speed in ('100G', '40G', '25G', '10G', '1G'):
        if speed.lower() in text.lower().replace(' ', ''):
            return speed
    return ''


def transceiver(raw, kind):
    """A NetBox module (in a module bay) or inventory item that looks like an optic, or None."""
    if kind == 'module':
        model = _name(raw, 'module_type', 'model')
        port, name = _name(raw, 'module_bay', 'name'), model
    else:
        model = raw.get('part_id') or _name(raw, 'manufacturer', 'name')
        port, name = _name(raw, 'component', 'name'), raw.get('name') or ''
        words = ' '.join([name, model, _name(raw, 'role', 'slug'), _name(raw, 'role', 'name')]).lower()
        if not any(w in words for w in TRANSCEIVER_WORDS):
            return None
    device_name = _name(raw, 'device', 'name')
    label = ' '.join(x for x in (device_name, port) if x) or name
    return {'ref': f"{kind}-{raw['id']}", 'name': label or f"{kind} {raw['id']}",
            'fields': {**_custom(raw), 'device': device_name, 'port': port, 'serial': raw.get('serial') or '',
                       'speed': _speed_word(f'{model} {name}')}}


def power_panel(raw):
    return {'ref': f"panel-{raw['id']}", 'name': raw.get('name') or '',
            'location': _name(raw, 'location', 'name') or _name(raw, 'site', 'name')}


def power_feed(raw):
    phase = _name(raw, 'phase', 'value')
    return {'ref': f"feed-{raw['id']}", 'name': raw.get('name') or '',
            'board_ref': f"panel-{_name(raw, 'power_panel', 'id')}",
            'phase': '3P' if phase == 'three-phase' else 'L1', 'rating_a': raw.get('amperage') or 16}

class Plugin(Plugin):
    def configured(self):
        return bool(self.settings.get('url') and self.settings.get('token'))

    def _client(self):
        s = self.settings
        if not s.get('url') or not s.get('token'):
            raise PluginError('Set the NetBox URL and API token under Settings > NetBox first.')
        return self.ctx.http(s['url'], headers={'Authorization': f"Token {s['token']}", 'Accept': 'application/json'},
                             timeout=15)

    def _all(self, url, params, what):
        http = self._client()
        base = urlsplit(http.base)
        out = []
        for _ in range(MAX_PAGES):
            r = http.get(url, params=params)
            if r.status_code != 200:
                raise PluginError(f'NetBox answered {r.status_code} for the {what} list')
            payload = r.json()
            out += payload.get('results') or []
            url, params = payload.get('next'), None   # "next" already has the query
            if not url:
                return out
            nxt = urlsplit(url)
            # Only follow "next" to the NetBox we were told to use.
            if (nxt.scheme, nxt.netloc) != (base.scheme, base.netloc):
                raise PluginError('NetBox sent a "next" page on another host; stopped')
        raise PluginError(f'NetBox has more than {PAGE * MAX_PAGES} {what}s; stopped')

    def _optional(self, url, params, what):
        """A list this NetBox may not give (an older one, or a token without the right): [] then."""
        try:
            return self._all(url, params, what)
        except PluginError as exc:
            self.ctx.log(f'skipped the {what}s: {exc}')
            return []

    def _ips(self):
        """(object type, object id) -> its addresses, for interfaces of devices and VMs."""
        out = {}
        for ip in self._optional('/api/ipam/ip-addresses/', {'limit': PAGE}, 'IP address'):
            kind, oid = ip.get('assigned_object_type'), ip.get('assigned_object_id')
            if kind and oid is not None and ip.get('address'):
                out.setdefault((kind, oid), []).append(ip['address'])
        return out

    def _disk_in_mb(self):
        try:
            version = str(self._client().get('/api/status/').json().get('netbox-version') or '')
            major, minor = (int(x) for x in re.findall(r'\d+', version)[:2])
        except (ValueError, TypeError, AttributeError, KeyError, PluginError):
            return True
        return (major, minor) >= (4, 1)

    def inventory(self):
        """Devices with the configured roles and their interfaces, then virtual machines with theirs."""
        params = {'limit': PAGE}
        roles = self.settings.get('device_roles') or []
        if roles:
            params['role'] = roles
        raw_devices = [d for d in self._all('/api/dcim/devices/', params, 'device') if d.get('name')]
        out = [device(d) for d in raw_devices]
        if not out:
            return out
        ips = self._ips()
        by_device = {}
        for raw in self._optional('/api/dcim/interfaces/', {'limit': PAGE}, 'interface'):
            dev_id = (raw.get('device') or {}).get('id') if isinstance(raw.get('device'), dict) else None
            if dev_id is not None and raw.get('name'):
                addresses = ips.get(('dcim.interface', raw.get('id')), ())
                by_device.setdefault(str(dev_id), []).append(interface(raw, addresses))
        if by_device:
            for item in out:
                item['interfaces'] = by_device.get(item['id'], [])
        vms = [v for v in self._optional('/api/virtualization/virtual-machines/', dict(params), 'virtual machine')
               if v.get('name') and v.get('id') is not None]
        if vms:
            disk_in_mb = self._disk_in_mb()
            by_vm = {}
            for raw in self._optional('/api/virtualization/interfaces/', {'limit': PAGE}, 'VM interface'):
                owner = raw.get('virtual_machine') if isinstance(raw.get('virtual_machine'), dict) else {}
                if owner.get('id') is not None and raw.get('name'):
                    addresses = ips.get(('virtualization.vminterface', raw.get('id')), ())
                    by_vm.setdefault(owner['id'], []).append(interface(raw, addresses))
            for raw in vms:
                item = vm(raw, disk_in_mb)
                item['interfaces'] = by_vm.get(raw['id'], [])
                out.append(item)
        return out

    def cables(self):
        """NetBox cables that end on a switch interface, as Floorbit cables."""
        return [c for c in (cable(raw) for raw in self._all('/api/dcim/cables/', {'limit': PAGE}, 'cable')) if c]

    def entries(self):
        """Racks and locations, VLANs and prefixes, optics, power panels and feeds, for the inventory's
        other types. Lists this NetBox doesn't give (or the token can't read) are left out."""
        page = {'limit': PAGE}
        optics = [transceiver(m, 'module') for m in self._optional('/api/dcim/modules/', dict(page), 'module')]
        optics += [transceiver(i, 'item')
                   for i in self._optional('/api/dcim/inventory-items/', dict(page), 'inventory item')]
        panels = self._optional('/api/dcim/power-panels/', dict(page), 'power panel')
        feeds = self._optional('/api/dcim/power-feeds/', dict(page), 'power feed')
        return {
            'rack': [rack(r) for r in self._optional('/api/dcim/racks/', dict(page), 'rack')]
            + [location(x) for x in self._optional('/api/dcim/locations/', dict(page), 'location')],
            'vlan': [vlan(v) for v in self._optional('/api/ipam/vlans/', dict(page), 'VLAN')],
            'prefix': [prefix(p) for p in self._optional('/api/ipam/prefixes/', dict(page), 'prefix')],
            'transceiver': [o for o in optics if o],
            'power-board': [power_panel(p) for p in panels],
            'circuit': [power_feed(f) for f in feeds],
        }

    def firewall_ranges(self):
        """Prefixes whose custom field ``floorbit_firewalls`` names their firewalls, in order."""
        params = {'limit': PAGE, f'cf_{FIREWALL_FIELD}__empty': 'false'}
        return [r for r in (firewall_range(raw) for raw in self._all('/api/ipam/prefixes/', params, 'prefix')) if r]

    def test(self):
        r = self._client().get('/api/status/')
        if r.status_code != 200:
            raise PluginError(f'NetBox answered {r.status_code}')
        return f"Connected to NetBox {r.json().get('netbox-version', '')}".strip()
