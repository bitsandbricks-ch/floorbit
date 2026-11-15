"""UniFi Network as the monitoring source (issue #39).

Reads the controller's own API with a View Only account: ``stat/device`` for the switches and their
``port_table``, ``stat/sta`` for the clients (IP, MAC, and the switch MAC and port they are on).
For the Wi-Fi view, ``stat/device``'s access points with their radios' channel, load and client count.
Answers have the same shapes as the LibreNMS plugin's. UniFi names a switch port "Port 7"; a name
someone gave it in the controller ("Seat A1") becomes its description.
"""
import contextlib
import re

from floorbit.builtin_plugins.librenms.ports import summarize_port
from floorbit.plugins.base import Plugin as Base
from floorbit.plugins.base import PluginError
from floorbit.sources import normalise_mac

SITE_RE = re.compile(r'^[a-zA-Z0-9_-]{1,64}$')
SWITCH_TYPES = ('usw',)   # access points and gateways are not on the floor plan's switch layer


def port_name(idx):
    return f'Port {idx}'


class Plugin(Base):
    def configured(self):
        return bool(self.settings.get('url') and self.settings.get('username') and self.settings.get('password'))

    # the controller's API --------------------------------------------------------------------
    def _site(self):
        site = str(self.settings.get('site') or 'default').strip()
        if not SITE_RE.match(site):
            raise PluginError(f'"{site}" is not a site name.')
        return site

    def _session(self):
        if not self.configured():
            raise PluginError('Set the controller URL, username and password under Settings > Plugins first.')
        http = self.ctx.http(self.settings.get('url'), timeout=10)
        unifi_os = self.settings.get('unifi_os', True)
        login = '/api/auth/login' if unifi_os else '/api/login'
        resp = http.post(login, json={'username': self.settings.get('username'),
                                      'password': self.settings.get('password')})
        if resp.status_code in (401, 403):
            raise PluginError('The controller refused the username or password.')
        if resp.status_code >= 400:
            raise PluginError(f'Signing in to the controller failed ({resp.status_code}).')
        csrf = resp.headers.get('x-csrf-token') or resp.headers.get('X-CSRF-Token')
        if csrf:
            http.s.headers['X-CSRF-Token'] = csrf
        return http, ('/proxy/network' if unifi_os else '')

    def _get(self, what):
        http, prefix = self._session()
        try:
            resp = http.get(f'{prefix}/api/s/{self._site()}/{what}')
            if resp.status_code >= 400:
                raise PluginError(f'The controller answered {resp.status_code} for {what}.')
            try:
                return resp.json().get('data') or []
            except ValueError as exc:
                raise PluginError(f'The controller answered {what} without JSON.') from exc
        finally:
            # Sign out again so a poll every minute doesn't pile up sessions on the console.
            http.post(f"{'/api/auth/logout' if prefix else '/api/logout'}")

    def _switches(self):
        return [d for d in self._get('stat/device') if d.get('type') in SWITCH_TYPES and d.get('name')]

    # the monitoring interface ----------------------------------------------------------------
    def devices(self):
        return [{'hostname': d['name'], 'display': d['name'], 'sysName': d['name'], 'ip': d.get('ip'),
                 'mac': normalise_mac(d.get('mac')), 'model': d.get('model'),
                 'status': 1 if d.get('state') == 1 else 0, 'source': 'unifi'} for d in self._switches()]

    def _find(self, hostname, switches=None):
        from integrations.monitor import StatusMonitor
        switches = self._switches() if switches is None else switches
        found = StatusMonitor.match(hostname, [{**d, 'hostname': d['name'], 'display': d['name']} for d in switches])
        return next((d for d in switches if found and d['name'] == found['name']), None)

    @staticmethod
    def _ports(device):
        out = []
        for p in device.get('port_table') or []:
            idx = p.get('port_idx')
            if idx is None:
                continue
            name = port_name(idx)
            given = str(p.get('name') or '').strip()
            raw = {
                'ifName': name,
                'ifAlias': '' if given == name else given,
                'ifOperStatus': 'up' if p.get('up') else 'down',
                'ifAdminStatus': 'down' if p.get('enable') is False else 'up',
                'ifHighSpeed': p.get('speed') or None,
                # The switch's side: rx is what the player sends.
                'ifInOctets_rate': p.get('rx_bytes-r'),
                'ifOutOctets_rate': p.get('tx_bytes-r'),
                'ifInErrors': p.get('rx_errors'),
                'ifOutErrors': p.get('tx_errors'),
            }
            if p.get('up'):
                raw['ifDuplex'] = 'fullDuplex' if p.get('full_duplex', True) else 'halfDuplex'
            out.append({'name': name, 'last_change': None, **summarize_port(raw)})
        return out

    def device_ports(self, hostname):
        device = self._find(hostname)
        return self._ports(device) if device else []

    def port_stats(self, hostname, interface):
        want = str(interface or '').strip().lower()
        for port in self.device_ports(hostname):
            if port['name'].lower() == want or (port['description'] or '').lower() == want:
                return port
        return {}

    def device_details(self, hostname):
        device = self._find(hostname)
        if not device:
            return {'status': 'unknown', 'hostname': hostname}
        result = {'status': 'online' if device.get('state') == 1 else 'offline', 'hostname': hostname,
                  'ip': device.get('ip') or ''}
        stats = device.get('system-stats') or {}
        for key, field in (('cpu', 'cpu_load'), ('mem', 'mem_percent')):
            with contextlib.suppress(KeyError, TypeError, ValueError):   # older firmware leaves them out
                result[field] = round(float(stats[key]))
        if device.get('general_temperature') is not None:
            result['temperature'] = device['general_temperature']
        ports = self._ports(device)
        up = [p for p in ports if p['state'] in ('up', 'errors')]
        traffic = sum((p['download_bps'] or 0) + (p['upload_bps'] or 0) for p in up)
        capacity = sum(p['speed_bps'] or 0 for p in up)
        result.update(total_ports=len(ports), up_ports=len(up), total_traffic_bps=round(traffic))
        if capacity:
            result['traffic_util'] = round(min(1.0, traffic / capacity), 4)
        return result

    def arp(self, query):
        """Clients matching an IP or a MAC, as LibreNMS ARP rows."""
        want_mac = normalise_mac(query)
        out = []
        for c in self._get('stat/sta'):
            mac = normalise_mac(c.get('mac'))
            if c.get('ip') == query or (want_mac and mac == want_mac):
                out.append({'ipv4_address': c.get('ip'), 'mac_address': mac})
        return out

    def resolve_ip(self, ip_address, search_device=None):
        client = next((c for c in self._get('stat/sta') if c.get('ip') == ip_address), None)
        if not client or not client.get('is_wired', True) or not client.get('sw_mac'):
            return None
        switches = self._switches()
        device = next((d for d in switches if normalise_mac(d.get('mac')) == normalise_mac(client['sw_mac'])), None)
        if not device:
            return None
        port = port_name(client.get('sw_port'))
        stats = next((p for p in self._ports(device) if p['name'] == port), None)
        return {'ip': ip_address, 'mac': normalise_mac(client.get('mac')), 'device_name': device['name'],
                'hostname': device['name'], 'port': port, 'vlan': str(client['vlan']) if client.get('vlan') else None,
                'arp_source': 'UniFi', 'stats': stats}

    # the Wi-Fi view (issue #98): counts only, never the client list ------------------------
    def wifi_aps(self):
        out = []
        for d in self._get('stat/device'):
            if d.get('type') != 'uap' or not d.get('name'):
                continue
            widths = {r.get('radio'): r.get('ht') for r in d.get('radio_table') or []}
            radios = [{'band': r.get('radio'), 'channel': r.get('channel'),
                       'width': widths.get(r.get('radio')), 'utilization': r.get('cu_total'),
                       'clients': r.get('num_sta') or 0} for r in d.get('radio_table_stats') or []]
            out.append({'name': d['name'], 'model': d.get('model') or '', 'clients': d.get('num_sta'),
                        'status': 'up' if d.get('state') == 1 else 'down', 'radios': radios})
        return out

    def test(self):
        found = self.devices()
        online = sum(d['status'] == 1 for d in found)
        return f'Connected: {len(found)} UniFi switches on site "{self._site()}", {online} online.'
