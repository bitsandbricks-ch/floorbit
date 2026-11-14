"""NetBox as an inventory source: GET /api/dcim/devices/ for the configured roles."""
from urllib.parse import urlsplit

from floorbit.plugins.base import Plugin, PluginError

PAGE = 500
MAX_PAGES = 40   # 20,000 devices: far more than a LAN party has; stops a loop on a bad "next"


ROLE_WORDS = ((('switch', 'sw'), 'switch'), (('router', 'rtr'), 'router'), (('firewall', 'fw'), 'firewall'),
              (('ap', 'wifi', 'wlan', 'wireless', 'access'), 'access-point'), (('server', 'srv'), 'server'))


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


class Plugin(Plugin):
    def _client(self):
        s = self.settings
        if not s.get('url') or not s.get('token'):
            raise PluginError('Set the NetBox URL and API token under Settings > NetBox first.')
        return self.ctx.http(s['url'], headers={'Authorization': f"Token {s['token']}", 'Accept': 'application/json'},
                             timeout=15)

    def inventory(self):
        http = self._client()
        base = urlsplit(http.base)
        params = {'limit': PAGE}
        roles = self.settings.get('device_roles') or []
        if roles:
            params['role'] = roles
        url, out = '/api/dcim/devices/', []
        for _ in range(MAX_PAGES):
            r = http.get(url, params=params)
            if r.status_code != 200:
                raise PluginError(f'NetBox answered {r.status_code} for the device list')
            payload = r.json()
            out += [device(d) for d in payload.get('results') or [] if d.get('name')]
            url, params = payload.get('next'), None   # "next" already has the query
            if not url:
                return out
            nxt = urlsplit(url)
            # Only follow "next" to the NetBox we were told to use.
            if (nxt.scheme, nxt.netloc) != (base.scheme, base.netloc):
                raise PluginError('NetBox sent a "next" page on another host; stopped')
        raise PluginError(f'NetBox has more than {PAGE * MAX_PAGES} devices with these roles; stopped')

    def test(self):
        r = self._client().get('/api/status/')
        if r.status_code != 200:
            raise PluginError(f'NetBox answered {r.status_code}')
        return f"Connected to NetBox {r.json().get('netbox-version', '')}".strip()
