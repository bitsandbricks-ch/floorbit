"""Prometheus as the monitoring source (issue #39).

Reads what the SNMP exporter's ``if_mib`` module publishes: ``up`` for whether a switch answers,
and ``ifOperStatus``, ``ifAdminStatus``, ``ifHCInOctets``, ``ifHCOutOctets``, ``ifHighSpeed`` and
the error counters per port, labelled with ``ifIndex``, ``ifName``, ``ifDescr`` and ``ifAlias``.
Answers have the same shape as the LibreNMS plugin's, so the core doesn't know which one it asked.
"""
import re

from floorbit.builtin_plugins.librenms.ports import summarize_port
from floorbit.plugins.base import Plugin as Base
from floorbit.plugins.base import PluginError

NAME_RE = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')
JOB_RE = re.compile(r'^[\w.:/-]{1,100}$')
WINDOW_RE = re.compile(r'^\d{1,4}[smh]$')
# IF-MIB ifOperStatus / ifAdminStatus values as numbers, as the exporter sends them.
OPER = {1: 'up', 2: 'down', 3: 'testing', 4: 'unknown', 5: 'dormant', 6: 'notPresent', 7: 'lowerLayerDown'}


def quote(value):
    """A PromQL string literal: the name comes from the floor plan, so nothing in it can break out."""
    return '"' + str(value).replace('\\', '\\\\').replace('"', '\\"').replace('\n', ' ') + '"'


class Plugin(Base):
    # settings ------------------------------------------------------------------------------
    def _job(self):
        job = str(self.settings.get('job') or 'snmp').strip()
        if not JOB_RE.match(job):
            raise PluginError(f'"{job}" is not a job name.')
        return job

    def _label(self):
        label = str(self.settings.get('device_label') or 'instance').strip()
        if not NAME_RE.match(label):
            raise PluginError(f'"{label}" is not a label name.')
        return label

    def _window(self):
        window = str(self.settings.get('rate_window') or '2m').strip()
        return window if WINDOW_RE.match(window) else '2m'

    def configured(self):
        return bool(self.settings.get('url'))

    # the query API -------------------------------------------------------------------------
    def _query(self, promql):
        if not self.configured():
            raise PluginError('Set the Prometheus URL under Settings > Plugins first.')
        token = self.settings.get('token')
        http = self.ctx.http(self.settings.get('url'), timeout=10,
                             headers={'Authorization': f'Bearer {token}'} if token else None)
        resp = http.get('/api/v1/query', params={'query': promql})
        try:
            body = resp.json()
        except ValueError as exc:
            raise PluginError(f'Prometheus answered {resp.status_code} without JSON') from exc
        if resp.status_code >= 400 or body.get('status') != 'success':
            raise PluginError(f"Prometheus: {body.get('error') or resp.status_code}")
        return (body.get('data') or {}).get('result') or []

    def _series(self, metric, device=None, fn=None):
        """[(labels, value)] for one metric of the job, optionally one switch, optionally wrapped."""
        matchers = [f'job={quote(self._job())}']
        if device is not None:
            matchers.append(f'{self._label()}={quote(device)}')
        selector = f'{metric}{{{",".join(matchers)}}}'
        if fn == 'rate':
            selector = f'rate({selector}[{self._window()}])'
        out = []
        for row in self._query(selector):
            try:
                out.append((row.get('metric') or {}, float(row['value'][1])))
            except (KeyError, IndexError, TypeError, ValueError):
                continue
        return out

    # the monitoring interface --------------------------------------------------------------
    def devices(self):
        """Every switch the job scrapes, shaped like LibreNMS's devices for the status monitor."""
        label = self._label()
        out = []
        for labels, value in self._series('up'):
            name = labels.get(label)
            if not name:
                continue
            out.append({'hostname': name, 'display': name, 'sysName': labels.get('sysName') or name,
                        'status': 1 if value == 1 else 0, 'source': 'prometheus'})
        return out

    def _match(self, hostname):
        from integrations.monitor import StatusMonitor
        return StatusMonitor.match(hostname, self.devices())

    def _ports(self, name):
        rows = {}

        def put(metric, key, fn=None, convert=lambda v: v):
            for labels, value in self._series(metric, name, fn):
                index = labels.get('ifIndex') or labels.get('ifName')
                if not index:
                    continue
                row = rows.setdefault(index, {'ifName': labels.get('ifName') or labels.get('ifDescr'),
                                              'ifAlias': labels.get('ifAlias') or ''})
                row[key] = convert(value)

        put('ifOperStatus', 'ifOperStatus', convert=lambda v: OPER.get(int(v), 'unknown'))
        put('ifAdminStatus', 'ifAdminStatus', convert=lambda v: OPER.get(int(v), 'unknown'))
        put('ifHighSpeed', 'ifHighSpeed')
        put('ifHCInOctets', 'ifInOctets_rate', fn='rate')
        put('ifHCOutOctets', 'ifOutOctets_rate', fn='rate')
        put('ifInErrors', 'ifInErrors_rate', fn='rate')
        put('ifOutErrors', 'ifOutErrors_rate', fn='rate')
        put('ifInErrors', 'ifInErrors')
        put('ifOutErrors', 'ifOutErrors')
        return [r for r in rows.values() if r.get('ifName')]

    def device_ports(self, hostname):
        device = self._match(hostname)
        if not device:
            return []
        return [{'name': r['ifName'], 'last_change': None, **summarize_port(r)}
                for r in self._ports(device['hostname'])]

    def port_stats(self, hostname, interface):
        want = str(interface or '').lower()
        for port in self.device_ports(hostname):
            if str(port['name']).lower() == want:
                return port
        return {}

    def device_details(self, hostname):
        device = self._match(hostname)
        if not device:
            return {'status': 'unknown', 'hostname': hostname}
        result = {'status': 'online' if device['status'] == 1 else 'offline', 'hostname': hostname,
                  'ip': device['hostname']}
        if device['status'] != 1:
            return result
        ports = self.device_ports(hostname)
        up = [p for p in ports if p['state'] in ('up', 'errors')]
        traffic = sum((p['download_bps'] or 0) + (p['upload_bps'] or 0) for p in up)
        capacity = sum(p['speed_bps'] or 0 for p in up)
        result.update(total_ports=len(ports), up_ports=len(up), total_traffic_bps=round(traffic))
        if capacity:
            result['traffic_util'] = round(min(1.0, traffic / capacity), 4)
        return result

    def resolve_ip(self, ip_address, search_device=None):
        return None   # Prometheus keeps no ARP or MAC tables

    def arp(self, query):
        return []

    def test(self):
        found = self.devices()
        if not found:
            raise PluginError(f'Prometheus answers, but has no "up" series for job "{self._job()}".')
        online = sum(d['status'] == 1 for d in found)
        return f'Connected: {len(found)} switches in job "{self._job()}", {online} answering.'
