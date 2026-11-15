"""Zabbix as the monitoring source (issue #39).

Reads hosts of one host group with ``host.get`` (availability of their SNMP interface) and their
network interface items with ``item.get``. The items are the ones Zabbix's SNMP templates create
for every discovered port: ``net.if.status``, ``net.if.in``, ``net.if.out`` (bits per second),
``net.if.speed`` (bits per second), ``net.if.in.errors`` and ``net.if.out.errors``, named
"Interface Gi1/0/1(Seat A1): ...". Answers have the same shapes as the LibreNMS plugin's.
"""
import re

from floorbit.builtin_plugins.librenms.ports import summarize_port
from floorbit.plugins.base import Plugin as Base
from floorbit.plugins.base import PluginError

ITEM_NAME_RE = re.compile(r'^Interface\s+(?P<name>[^():]+?)\s*(?:\((?P<alias>[^)]*)\))?\s*:')
KEY_RE = re.compile(r'^net\.if\.(?P<what>status|in|out|speed|in\.errors|out\.errors)\[')
OPER = {'1': 'up', '2': 'down', '3': 'testing', '5': 'dormant', '6': 'notPresent', '7': 'lowerLayerDown'}


class Plugin(Base):
    def configured(self):
        return bool(self.settings.get('url') and self.settings.get('token'))

    # the JSON-RPC API ----------------------------------------------------------------------
    def _call(self, method, params):
        if not self.configured():
            raise PluginError('Set the Zabbix URL and API token under Settings > Plugins first.')
        http = self.ctx.http(self.settings.get('url'), timeout=10,
                             headers={'Authorization': f"Bearer {self.settings.get('token')}"})
        resp = http.post('/api_jsonrpc.php', json={'jsonrpc': '2.0', 'method': method, 'params': params, 'id': 1})
        try:
            body = resp.json()
        except ValueError as exc:
            raise PluginError(f'Zabbix answered {resp.status_code} without JSON') from exc
        if 'error' in body:
            err = body['error'] or {}
            raise PluginError(f"Zabbix: {err.get('data') or err.get('message') or 'error'}"[:300])
        return body.get('result') or []

    def _hosts(self):
        group = str(self.settings.get('group') or 'Switches').strip()
        groups = self._call('hostgroup.get', {'output': ['groupid'], 'filter': {'name': [group]}})
        if not groups:
            raise PluginError(f'Zabbix has no host group "{group}" (or the token may not read it).')
        return self._call('host.get', {'output': ['hostid', 'host', 'name', 'status'],
                                       'groupids': [g['groupid'] for g in groups],
                                       'selectInterfaces': ['ip', 'available', 'type']})

    @staticmethod
    def _available(host):
        """1 when Zabbix reaches the host's SNMP (or any) interface, 0 when not, None when unknown."""
        if str(host.get('status')) != '0':
            return None   # not monitored in Zabbix
        ifaces = host.get('interfaces') or []
        snmp = [i for i in ifaces if str(i.get('type')) == '2'] or ifaces
        states = {str(i.get('available')) for i in snmp}
        if '1' in states:
            return 1
        return 0 if '2' in states else None

    # the monitoring interface --------------------------------------------------------------
    def devices(self):
        out = []
        for h in self._hosts():
            available = self._available(h)
            out.append({'hostname': h['host'], 'display': h.get('name') or h['host'], 'sysName': h['host'],
                        'ip': next((i.get('ip') for i in h.get('interfaces') or [] if i.get('ip')), None),
                        'status': 1 if available == 1 else 0, 'ignore': 1 if available is None else 0,
                        'hostid': h['hostid'], 'source': 'zabbix'})
        return out

    def _find(self, hostname):
        from integrations.monitor import StatusMonitor
        return StatusMonitor.match(hostname, self.devices())

    def _ports(self, hostid):
        items = self._call('item.get', {'hostids': [hostid], 'output': ['key_', 'name', 'lastvalue'],
                                        'search': {'key_': 'net.if.'}, 'startSearch': True})
        rows = {}
        for item in items:
            key, name = KEY_RE.match(item.get('key_') or ''), ITEM_NAME_RE.match(item.get('name') or '')
            if not key or not name:
                continue
            row = rows.setdefault(name['name'], {'ifName': name['name'], 'ifAlias': (name['alias'] or '').strip()})
            value = item.get('lastvalue')
            what = key['what']
            try:
                if what == 'status':
                    row['ifOperStatus'] = OPER.get(str(value), 'unknown')
                elif what == 'speed':
                    row['ifHighSpeed'] = float(value) / 1e6
                elif what in ('in', 'out'):   # bits per second
                    row['ifInOctets_rate' if what == 'in' else 'ifOutOctets_rate'] = float(value) / 8
                else:
                    row['ifInErrors' if what == 'in.errors' else 'ifOutErrors'] = float(value)
            except (TypeError, ValueError):
                continue
        return [{'name': r['ifName'], 'last_change': None, **summarize_port({'ifAdminStatus': 'up', **r})}
                for r in rows.values() if 'ifOperStatus' in r]

    def device_ports(self, hostname):
        device = self._find(hostname)
        return self._ports(device['hostid']) if device else []

    def port_stats(self, hostname, interface):
        want = str(interface or '').strip().lower()
        return next((p for p in self.device_ports(hostname) if p['name'].lower() == want), {})

    def device_details(self, hostname):
        device = self._find(hostname)
        if not device or device['ignore']:
            return {'status': 'unknown', 'hostname': hostname}
        result = {'status': 'online' if device['status'] == 1 else 'offline', 'hostname': hostname,
                  'ip': device.get('ip') or ''}
        if device['status'] != 1:
            return result
        ports = self._ports(device['hostid'])
        up = [p for p in ports if p['state'] in ('up', 'errors')]
        traffic = sum((p['download_bps'] or 0) + (p['upload_bps'] or 0) for p in up)
        capacity = sum(p['speed_bps'] or 0 for p in up)
        result.update(total_ports=len(ports), up_ports=len(up), total_traffic_bps=round(traffic))
        if capacity:
            result['traffic_util'] = round(min(1.0, traffic / capacity), 4)
        return result

    def resolve_ip(self, ip_address, search_device=None):
        return None   # Zabbix keeps no ARP or MAC tables

    def arp(self, query):
        return []

    def test(self):
        found = self.devices()
        online = sum(d['status'] == 1 for d in found)
        return f"Connected: {len(found)} hosts in \"{self.settings.get('group') or 'Switches'}\", {online} reachable."
