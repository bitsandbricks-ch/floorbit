"""MikroTik (RouterOS 7 REST API) as the monitoring source (issue #39).

Every switch is its own API, listed in the settings as Name=URL. Reads only:

- reachability and load: ``/rest/system/resource``
- ports: ``/rest/interface`` (state, comment, counters), ``interface/monitor-traffic`` (rates),
  ``interface/ethernet/monitor`` (link speed and duplex)
- where an IP is: ``/rest/ip/arp`` on any listed device, then ``/rest/interface/bridge/host`` for
  the MAC on each switch, skipping uplinks (a comment matching the uplink pattern) so the access
  port wins over the core's port towards it.

Answers have the same shapes as the LibreNMS plugin's.
"""
import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit

from floorbit.builtin_plugins.librenms.ports import summarize_port
from floorbit.plugins.base import Plugin as Base
from floorbit.plugins.base import PluginError
from floorbit.sources import normalise_mac

RATE_RE = re.compile(r'^([\d.]+)\s*([KMG]?)bps$', re.IGNORECASE)
UNITS = {'': 1, 'K': 1e3, 'M': 1e6, 'G': 1e9}
PARALLEL = 16


def parse_switches(raw):
    out = []
    for item in raw or []:
        name, sep, url = str(item).partition('=')
        parts = urlsplit(url.strip())
        if not sep or not name.strip() or parts.scheme not in ('http', 'https') or not parts.netloc:
            raise PluginError(f'"{item}" is not Name=https://address')
        out.append({'name': name.strip(), 'url': f'{parts.scheme}://{parts.netloc}'})
    return out


def link_speed(rate):
    """'1Gbps' -> 1000 (Mbps), or None."""
    m = RATE_RE.match(str(rate or '').strip())
    return float(m.group(1)) * UNITS[m.group(2).upper()] / 1e6 if m else None


def truthy(value):
    return value is True or str(value).lower() == 'true'


class Plugin(Base):
    def configured(self):
        return bool(self.settings.get('switches') and self.settings.get('username'))

    # the REST API ----------------------------------------------------------------------------
    def _switches(self):
        return parse_switches(self.settings.get('switches'))

    def _http(self, switch):
        return self.ctx.http(switch['url'], timeout=self.settings.get('timeout') or 4,
                             auth=(self.settings.get('username') or '', self.settings.get('password') or ''))

    def _rest(self, switch, method, path, **kw):
        resp = self._http(switch).request(method, f'/rest/{path}', **kw)
        if resp.status_code == 401:
            raise PluginError(f"{switch['name']} refused the username or password.")
        if resp.status_code >= 400:
            raise PluginError(f"{switch['name']} answered {resp.status_code} for {path}.")
        try:
            return resp.json()
        except ValueError as exc:
            raise PluginError(f"{switch['name']} answered {path} without JSON.") from exc

    def _each(self, fn, switches):
        """fn(switch) for every switch at once; a switch that fails gives None, the rest still count."""
        def safe(switch):
            try:
                return fn(switch)
            except PluginError as exc:
                self.ctx.log(str(exc))
                return None
        with ThreadPoolExecutor(max_workers=min(PARALLEL, max(1, len(switches)))) as pool:
            return list(pool.map(safe, switches))

    def _find(self, hostname):
        from integrations.monitor import StatusMonitor
        switches = self._switches()
        found = StatusMonitor.match(hostname, [{'hostname': s['name'], 'display': s['name']} for s in switches])
        return next((s for s in switches if found and s['name'] == found['hostname']), None)

    # the monitoring interface ----------------------------------------------------------------
    def devices(self):
        switches = self._switches()
        answers = self._each(lambda s: self._rest(s, 'GET', 'system/resource'), switches)
        return [{'hostname': s['name'], 'display': s['name'], 'sysName': s['name'],
                 'ip': urlsplit(s['url']).hostname, 'status': 1 if a else 0,
                 'model': (a or {}).get('board-name'), 'source': 'mikrotik'}
                for s, a in zip(switches, answers, strict=True)]

    def _ports(self, switch):
        ifaces = [i for i in self._rest(switch, 'GET', 'interface') if i.get('type') == 'ether']
        if not ifaces:
            return []
        names = ','.join(i['name'] for i in ifaces)
        traffic = {t.get('name'): t for t in self._rest(switch, 'POST', 'interface/monitor-traffic',
                                                         json={'interface': names, 'once': ''})}
        links = {e.get('name'): e for e in self._rest(switch, 'POST', 'interface/ethernet/monitor',
                                                       json={'numbers': names, 'once': ''})}
        out = []
        for i in ifaces:
            t, e = traffic.get(i['name']) or {}, links.get(i['name']) or {}
            up = truthy(i.get('running'))
            raw = {
                'ifName': i['name'], 'ifAlias': i.get('comment') or '',
                'ifOperStatus': 'up' if up else 'down',
                'ifAdminStatus': 'down' if truthy(i.get('disabled')) else 'up',
                'ifHighSpeed': link_speed(e.get('rate')),
                # bits per second from the switch's side: rx is what the player sends.
                'ifInOctets_rate': float(t.get('rx-bits-per-second') or 0) / 8,
                'ifOutOctets_rate': float(t.get('tx-bits-per-second') or 0) / 8,
                'ifInErrors': int(i.get('rx-error') or 0), 'ifOutErrors': int(i.get('tx-error') or 0),
            }
            if up and 'full-duplex' in e:
                raw['ifDuplex'] = 'fullDuplex' if truthy(e['full-duplex']) else 'halfDuplex'
            out.append({'name': i['name'], 'last_change': i.get('last-link-up-time'), **summarize_port(raw)})
        return out

    def device_ports(self, hostname):
        switch = self._find(hostname)
        return self._ports(switch) if switch else []

    def port_stats(self, hostname, interface):
        want = str(interface or '').strip().lower()
        return next((p for p in self.device_ports(hostname) if p['name'].lower() == want), {})

    def device_details(self, hostname):
        switch = self._find(hostname)
        if not switch:
            return {'status': 'unknown', 'hostname': hostname}
        try:
            res = self._rest(switch, 'GET', 'system/resource')
        except PluginError:
            return {'status': 'offline', 'hostname': hostname, 'ip': urlsplit(switch['url']).hostname}
        result = {'status': 'online', 'hostname': hostname, 'ip': urlsplit(switch['url']).hostname}
        try:
            result['cpu_load'] = round(float(res.get('cpu-load')))
            total, free = float(res['total-memory']), float(res['free-memory'])
            result['mem_percent'] = round((total - free) / total * 100) if total else None
        except (KeyError, TypeError, ValueError):
            pass
        ports = self._ports(switch)
        up = [p for p in ports if p['state'] in ('up', 'errors')]
        traffic = sum((p['download_bps'] or 0) + (p['upload_bps'] or 0) for p in up)
        capacity = sum(p['speed_bps'] or 0 for p in up)
        result.update(total_ports=len(ports), up_ports=len(up), total_traffic_bps=round(traffic))
        if capacity:
            result['traffic_util'] = round(min(1.0, traffic / capacity), 4)
        return result

    def arp(self, query):
        mac = normalise_mac(query)
        params = {'mac-address': mac.upper()} if mac else {'address': str(query)}
        rows = self._each(lambda s: self._rest(s, 'GET', 'ip/arp', params=params), self._switches())
        seen, out = set(), []
        for row in (r for answer in rows if answer for r in answer):
            entry = (row.get('address'), normalise_mac(row.get('mac-address')))
            if entry[0] and entry[1] and entry not in seen:
                seen.add(entry)
                out.append({'ipv4_address': entry[0], 'mac_address': entry[1]})
        return out

    def resolve_ip(self, ip_address, search_device=None):
        from floorbit.stats import _uplink_re
        mac = next((e['mac_address'] for e in self.arp(ip_address) if e['ipv4_address'] == ip_address), None)
        if not mac:
            return None
        uplink = _uplink_re()
        switches = self._switches()

        def where(switch):
            hosts = self._rest(switch, 'GET', 'interface/bridge/host', params={'mac-address': mac.upper()})
            ports = {i['name']: i for i in self._rest(switch, 'GET', 'interface')}
            for h in hosts:
                port = h.get('on-interface') or h.get('interface')
                iface = ports.get(port) or {}
                if truthy(h.get('local')) or iface.get('type') != 'ether' or uplink.search(iface.get('comment') or ''):
                    continue
                return {'port': port, 'vlan': str(h['vid']) if h.get('vid') else None}
            return None
        for switch, found in zip(switches, self._each(where, switches), strict=True):
            if found:
                return {'ip': ip_address, 'mac': mac, 'device_name': switch['name'], 'hostname': switch['name'],
                        'port': found['port'], 'vlan': found['vlan'], 'arp_source': 'MikroTik',
                        'stats': self.port_stats(switch['name'], found['port'])}
        return None

    def test(self):
        found = self.devices()
        if not found:
            raise PluginError('Add at least one switch as Name=URL under Settings > Plugins.')
        missing = [d['hostname'] for d in found if d['status'] != 1]
        message = f'{len(found) - len(missing)} of {len(found)} switches answering.'
        if missing:
            message += f" Not answering: {', '.join(missing[:5])}{' and more' if len(missing) > 5 else ''}" \
                       '. The log says why.'
        return message
