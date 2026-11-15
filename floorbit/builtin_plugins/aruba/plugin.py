"""Aruba AOS-CX as the monitoring source (issue #39).

Every switch is its own REST API (v10.08), listed in the settings as Name=URL. Each read signs in
(``POST /login``), reads, and signs out again: AOS-CX allows only a few sessions per user, and a
poll that left them open would lock the account out.

- reachability: ``GET system?attributes=hostname``
- ports: ``GET system/interfaces?depth=2`` (admin and link state, speed, duplex, description,
  ``rate_statistics`` and ``statistics``)
- where an IP is: ``system/vrfs/default/neighbors`` (ARP) on any listed switch, then the MAC in
  ``system/vlans/<id>/macs/dynamic,<mac>`` on each switch, skipping uplinks (a description matching
  the uplink pattern) so the access port wins.

Attribute names follow the AOS-CX 10.08 REST reference. Answers have the same shapes as the LibreNMS
plugin's.
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from urllib.parse import quote, unquote, urlsplit

from floorbit.builtin_plugins.librenms.ports import summarize_port
from floorbit.builtin_plugins.mikrotik.plugin import parse_switches
from floorbit.plugins.base import Plugin as Base
from floorbit.plugins.base import PluginError
from floorbit.sources import normalise_mac

API = '/rest/v10.08'
PARALLEL = 16


def _num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def port_from_ref(ref):
    """'/rest/v10.08/system/interfaces/1%2F1%2F7' (or a dict of them) -> '1/1/7'."""
    if isinstance(ref, dict):
        ref = next(iter(ref.values()), '') if ref else ''
    return unquote(str(ref or '').rstrip('/').rsplit('/', 1)[-1]) or None


class Plugin(Base):
    def configured(self):
        return bool(self.settings.get('switches') and self.settings.get('username'))

    # the REST API ----------------------------------------------------------------------------
    def _switches(self):
        return parse_switches(self.settings.get('switches'))

    @contextmanager
    def _signed_in(self, switch):
        http = self.ctx.http(switch['url'], timeout=self.settings.get('timeout') or 6)
        resp = http.post(f'{API}/login', data={'username': self.settings.get('username') or '',
                                               'password': self.settings.get('password') or ''})
        if resp.status_code in (401, 403):
            raise PluginError(f"{switch['name']} refused the username or password.")
        if resp.status_code >= 400:
            raise PluginError(f"{switch['name']}: signing in failed ({resp.status_code}).")
        try:
            yield http
        finally:
            try:
                http.post(f'{API}/logout')
            except PluginError:
                self.ctx.log(f"{switch['name']}: signing out failed")

    @staticmethod
    def _get(http, switch, path, **params):
        resp = http.get(f'{API}/{path}', params=params or None)
        if resp.status_code == 404:
            return None
        if resp.status_code >= 400:
            raise PluginError(f"{switch['name']} answered {resp.status_code} for {path}.")
        try:
            return resp.json()
        except ValueError as exc:
            raise PluginError(f"{switch['name']} answered {path} without JSON.") from exc

    def _each(self, fn, switches):
        def safe(switch):
            try:
                with self._signed_in(switch) as http:
                    return fn(http, switch)
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
        answers = self._each(lambda http, s: self._get(http, s, 'system', attributes='hostname,platform_name') or {},
                             switches)
        return [{'hostname': s['name'], 'display': s['name'], 'sysName': (a or {}).get('hostname') or s['name'],
                 'ip': urlsplit(s['url']).hostname, 'status': 1 if a is not None else 0,
                 'model': (a or {}).get('platform_name'), 'source': 'aruba'}
                for s, a in zip(switches, answers, strict=True)]

    def _ports(self, http, switch):
        found = self._get(http, switch, 'system/interfaces', depth=2,
                          attributes='name,type,description,admin_state,link_state,link_speed,duplex,'
                                     'rate_statistics,statistics') or {}
        out = []
        for key, i in sorted(found.items()):
            if not isinstance(i, dict) or i.get('type') not in (None, 'system'):
                continue   # VLAN interfaces, LAGs and loopbacks are not seat ports
            name = i.get('name') or unquote(key)
            rates, stats = i.get('rate_statistics') or {}, i.get('statistics') or {}
            up = i.get('link_state') == 'up'
            raw = {
                'ifName': name, 'ifAlias': i.get('description') or '',
                'ifOperStatus': 'up' if up else 'down',
                'ifAdminStatus': 'down' if i.get('admin_state') == 'down' else 'up',
                'ifHighSpeed': (_num(i.get('link_speed')) or 0) / 1e6 or None,
                # bits per second from the switch's side: rx is what the player sends.
                'ifInOctets_rate': (_num(rates.get('rx_bits_per_second')) or 0) / 8,
                'ifOutOctets_rate': (_num(rates.get('tx_bits_per_second')) or 0) / 8,
                'ifInErrors': _num(stats.get('rx_error')), 'ifOutErrors': _num(stats.get('tx_error')),
            }
            if up and i.get('duplex') in ('full', 'half'):
                raw['ifDuplex'] = f"{i['duplex']}Duplex"
            out.append({'name': name, 'last_change': None, **summarize_port(raw)})
        return out

    def device_ports(self, hostname):
        switch = self._find(hostname)
        if not switch:
            return []
        with self._signed_in(switch) as http:
            return self._ports(http, switch)

    def port_stats(self, hostname, interface):
        want = str(interface or '').strip().lower()
        return next((p for p in self.device_ports(hostname) if p['name'].lower() == want), {})

    def device_details(self, hostname):
        switch = self._find(hostname)
        if not switch:
            return {'status': 'unknown', 'hostname': hostname}
        ip = urlsplit(switch['url']).hostname
        try:
            with self._signed_in(switch) as http:
                ports = self._ports(http, switch)
        except PluginError:
            return {'status': 'offline', 'hostname': hostname, 'ip': ip}
        up = [p for p in ports if p['state'] in ('up', 'errors')]
        traffic = sum((p['download_bps'] or 0) + (p['upload_bps'] or 0) for p in up)
        capacity = sum(p['speed_bps'] or 0 for p in up)
        result = {'status': 'online', 'hostname': hostname, 'ip': ip, 'total_ports': len(ports),
                  'up_ports': len(up), 'total_traffic_bps': round(traffic)}
        if capacity:
            result['traffic_util'] = round(min(1.0, traffic / capacity), 4)
        return result

    def arp(self, query):
        want_mac = normalise_mac(query)

        def neighbors(http, switch):
            return self._get(http, switch, 'system/vrfs/default/neighbors', depth=2,
                             attributes='ip_address,mac') or {}
        seen, out = set(), []
        for answer in self._each(neighbors, self._switches()):
            for n in (answer or {}).values():
                entry = (n.get('ip_address'), normalise_mac(n.get('mac')))
                if not entry[0] or not entry[1] or entry in seen:
                    continue
                if entry[0] == query or (want_mac and entry[1] == want_mac):
                    seen.add(entry)
                    out.append({'ipv4_address': entry[0], 'mac_address': entry[1]})
        return out

    def resolve_ip(self, ip_address, search_device=None):
        from floorbit.stats import _uplink_re
        mac = next((e['mac_address'] for e in self.arp(ip_address) if e['ipv4_address'] == ip_address), None)
        if not mac:
            return None
        uplink = _uplink_re()
        wanted = [str(v).strip() for v in self.settings.get('vlans') or [] if str(v).strip().isdigit()]

        def where(http, switch):
            vlans = wanted or sorted((self._get(http, switch, 'system/vlans') or {}).keys(), key=str)
            for vlan in vlans:
                entry = self._get(http, switch, f"system/vlans/{vlan}/macs/{quote('dynamic,' + mac, safe='')}",
                                  attributes='port')
                port = port_from_ref((entry or {}).get('port'))
                if not port:
                    continue
                iface = self._get(http, switch, f"system/interfaces/{quote(port, safe='')}",
                                  attributes='description') or {}
                if uplink.search(iface.get('description') or ''):
                    continue
                return {'port': port, 'vlan': str(vlan)}
            return None
        switches = self._switches()
        for switch, found in zip(switches, self._each(where, switches), strict=True):
            if found:
                return {'ip': ip_address, 'mac': mac, 'device_name': switch['name'], 'hostname': switch['name'],
                        'port': found['port'], 'vlan': found['vlan'], 'arp_source': 'Aruba',
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
