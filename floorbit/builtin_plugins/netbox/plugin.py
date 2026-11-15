"""NetBox as an inventory source: GET /api/dcim/devices/ for the configured roles, and
GET /api/dcim/cables/ for the cables page (issue #97)."""
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


class Plugin(Plugin):
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

    def inventory(self):
        params = {'limit': PAGE}
        roles = self.settings.get('device_roles') or []
        if roles:
            params['role'] = roles
        return [device(d) for d in self._all('/api/dcim/devices/', params, 'device') if d.get('name')]

    def cables(self):
        """NetBox cables that end on a switch interface, as Floorbit cables."""
        return [c for c in (cable(raw) for raw in self._all('/api/dcim/cables/', {'limit': PAGE}, 'cable')) if c]

    def test(self):
        r = self._client().get('/api/status/')
        if r.status_code != 200:
            raise PluginError(f'NetBox answered {r.status_code}')
        return f"Connected to NetBox {r.json().get('netbox-version', '')}".strip()
