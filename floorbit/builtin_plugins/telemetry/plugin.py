"""Telemetry as the monitoring source (docs/telemetry.md).

Answers from floorbit/telemetry/state.py, the latest picture the hall's devices sent, in the same
shapes as the LibreNMS plugin, so the core doesn't know which one it asked. ARP lives on the core
(Nexus) and MAC tables on the access switches: an IP becomes a MAC by ARP, and the MAC a seat's
port by the access switch that learned it on a port that isn't an uplink.
"""
from floorbit.builtin_plugins.librenms.ports import summarize_port
from floorbit.plugins.base import Plugin as Base
from floorbit.plugins.base import PluginError
from floorbit.sources import normalise_mac
from floorbit.telemetry.state import state


class Plugin(Base):
    def configured(self):
        from floorbit.telemetry import targets
        return bool(state.devices) or targets.any_device()

    def _device(self, hostname):
        return state.find(hostname)

    # the local agent (agent.py there) -----------------------------------------------------------
    def agent_settings(self, settings, agent_id=None):
        """What the agent part gets: the devices it collects from (an agent named on a device takes
        it alone, targets.for_agent), secrets opened, sent over the agent's link only. The plugin's
        own settings (uplink limit, ignored ports) too."""
        from floorbit import agent_link
        from floorbit.telemetry import targets
        connected = agent_link.tunnel.connected_agents() if agent_id is not None else set()
        return {**settings, 'targets': targets.for_agent(targets.all_opened(), agent_id, connected)}

    def agent_series(self, agent, payload):
        """The agent's per-port and per-device numbers, for the history here."""

        from floorbit.telemetry import storage
        values = payload.get('values') if isinstance(payload, dict) else None
        clean = {k: float(v) for k, v in list((values or {}).items())[:200_000]
                 if isinstance(k, str) and k.count('|') == 2 and len(k) <= 300
                 and isinstance(v, (int, float)) and not isinstance(v, bool)}
        at = _when(payload)
        if clean:
            storage.storage().sample(clean, at)
        return {'taken': len(clean)}

    def agent_endpoints(self, agent, payload):
        """Where the agent saw each machine: into the IP/MAC history (floorbit/endpoints.py)."""
        from floorbit import endpoints
        rows = payload.get('rows') if isinstance(payload, dict) else None
        rows = [r for r in (rows or [])[:50_000] if isinstance(r, dict)]
        # A batch the agent kept while the link was down (or from before a failover) keeps its time.
        return {'taken': endpoints.history().record(rows, _when(payload))}

    # the dashboard -----------------------------------------------------------------------------
    def widget_devices(self):
        """Which devices report: up when heard within the last minutes."""
        from floorbit import agent_link, sources
        # On a hosted Floorbit the picture lives on the agent, asked through its link.
        found = sources.monitoring().devices() if agent_link.active() else self.devices()
        if not found:
            return {'type': 'status', 'items': [], 'sub': 'No devices set up yet.', 'link': '/telemetry'}
        items = [{'label': d.get('display') or d.get('hostname'), 'state': 'up' if d.get('status') else 'down',
                  'detail': d.get('driver') or ''} for d in found]
        up = sum(i['state'] == 'up' for i in items)
        return {'type': 'status', 'items': items, 'link': '/telemetry',
                'sub': f'{up} of {len(items)} up' if up == len(items)
                else f'{up} of {len(items)} up: {len(items) - up} down'}

    # the monitoring interface -----------------------------------------------------------------
    def devices(self):
        if not state.collecting:     # a standby agent: the primary one answers
            return []
        with state._lock:
            found = list(state.devices.values())
            facts = {d.name: d.summary() for d in found}
        problems = _problems()
        # facts: what the device said it is, for discovery (floorbit/inventory_discovery.py).
        out = [{'hostname': d.name, 'display': d.name, 'sysName': d.sys_name or d.name, 'ip': d.address,
                'status': 1 if d.online() else 0, 'source': 'telemetry', 'driver': d.driver, 'kind': d.kind,
                'seen': d.seen or None, 'problems': problems.pop(d.name, []), 'facts': facts[d.name], **_counts(d)}
               for d in sorted(found, key=lambda d: d.name)]
        # A device that never sent anything has no picture yet, but may well have a problem.
        out += [{'hostname': name, 'display': name, 'sysName': name, 'ip': rows[0].get('address') or '',
                 'status': 0, 'source': 'telemetry', 'driver': rows[0]['driver'], 'kind': '', 'seen': None,
                 'problems': rows} for name, rows in sorted(problems.items()) if name]
        return out

    def device_ports(self, hostname):
        if not state.collecting:
            return []
        dev = self._device(hostname)
        if dev is None:
            return []
        with state._lock:
            rows = [i for i in dev.interfaces.values() if i.name]
            return [{'name': i.name, 'last_change': i.last_change, **summarize_port(i.librenms_row())}
                    for i in sorted(rows, key=lambda i: _natural(i.name))]

    def port_stats(self, hostname, interface):
        if not state.collecting:
            return {}
        want = str(interface or '').lower()
        for port in self.device_ports(hostname):
            if str(port['name']).lower() == want:
                return port
        return {}

    def device_details(self, hostname):
        if not state.collecting:
            return {}
        dev = self._device(hostname)
        if dev is None:
            return {'status': 'unknown', 'hostname': hostname, 'problems': _problems().get(hostname, [])}
        result = {'status': 'online' if dev.online() else 'offline', 'hostname': hostname, 'ip': dev.address,
                  'source': 'telemetry', 'driver': dev.driver, 'problems': _problems().get(dev.name, [])}
        for key, value in (('cpu_load', dev.cpu), ('mem_percent', dev.mem), ('uptime', dev.uptime),
                           ('states', dev.states)):
            if value is not None:
                result[key] = round(value) if key in ('cpu_load', 'mem_percent') else value
        if dev.gateways:
            result['gateways'] = [{'name': n, **{k: v for k, v in g.items() if k != 'seen'}}
                                  for n, g in sorted(dev.gateways.items())]
        ports = self.device_ports(hostname)
        up = [p for p in ports if p['state'] in ('up', 'errors')]
        traffic = sum((p['download_bps'] or 0) + (p['upload_bps'] or 0) for p in up)
        capacity = sum(p['speed_bps'] or 0 for p in up)
        result.update(total_ports=len(ports), up_ports=len(up), total_traffic_bps=round(traffic))
        if capacity:
            result['traffic_util'] = round(min(1.0, traffic / capacity), 4)
        return result

    def arp(self, query):
        """ARP rows matching an IP or a MAC, LibreNMS-shaped."""
        if not state.collecting:
            return []
        q = str(query or '').strip()
        mac = normalise_mac(q)
        out = []
        with state._lock:
            for dev in state.devices.values():
                for ip, (row_mac, port, _seen) in dev.arp.items():
                    if ip == q or (mac and row_mac == mac):
                        out.append({'ipv4_address': ip, 'mac_address': row_mac, 'hostname': dev.name,
                                    'ifName': dev.port_name(port)})
        return out

    def port_clients(self, hostname):
        if not state.collecting:
            return []
        dev = self._device(hostname)
        if dev is None:
            raise PluginError(f'No telemetry from {hostname} yet.')
        with state._lock:
            return [{'port': dev.port_name(port), 'mac': mac, 'vlan': vlan or None}
                    for (mac, vlan), (port, _seen) in sorted(dev.fdb.items()) if dev.port_name(port)]

    def neighbours(self, hostname):
        if not state.collecting:
            return []
        dev = self._device(hostname)
        if dev is None:
            return []
        out = []
        with state._lock:
            for row, _seen in dev.lldp.values():
                port = dev.lldp_local.get(row['local']) or dev.port_name(row['local'])
                if port and row.get('remote') and row.get('remote_port'):
                    out.append({'port': port, 'remote': row['remote'], 'remote_port': row['remote_port'],
                                'protocol': 'lldp'})
            for row, _seen in dev.cdp.values():
                port = dev.port_name(row['local'])
                if port and row.get('remote') and row.get('remote_port'):
                    out.append({'port': port, 'remote': row['remote'], 'remote_port': row['remote_port'],
                                'protocol': 'cdp'})
        return out

    def _uplinks(self, dev):
        """Port keys that lead to other switches, and the MAC count per port."""
        from floorbit.telemetry.clients import uplinks
        return uplinks(dev, int(self.settings.get('uplink_macs') or 8))

    def find_mac(self, mac):
        """(device, port name, vlan, MACs on that port) of the access port a MAC is on, or None."""
        if not state.collecting:
            return None
        mac = normalise_mac(mac)
        if not mac:
            return None
        excludes = [str(x).strip().lower() for x in (self.settings.get('exclude') or []) if str(x).strip()]
        candidates = []
        with state._lock:
            for dev in state.devices.values():
                hits = [(port, vlan) for (m, vlan), (port, _seen) in dev.fdb.items() if m == mac]
                if not hits:
                    continue
                ups, counts = self._uplinks(dev)
                for port, vlan in hits:
                    name = dev.port_name(port)
                    if not name or any(x in name.lower() for x in excludes):
                        continue
                    candidates.append((port in ups, counts.get(port, 0), dev.name, name, vlan))
        if not candidates:
            return None
        candidates.sort()
        _up, count, device, port, vlan = candidates[0]
        return device, port, vlan, count

    def resolve_ip(self, ip_address, search_device=None):
        if not state.collecting:
            return None
        rows = [r for r in self.arp(ip_address) if r['ipv4_address'] == ip_address
                and (not search_device or r['hostname'] == search_device)]
        if not rows:
            return None
        mac = rows[0]['mac_address']
        result = {'ip': ip_address, 'mac': mac, 'device_name': None, 'hostname': None, 'port': None,
                  'vlan': None, 'arp_source': rows[0]['hostname']}
        found = self.find_mac(mac)
        if found:
            device, port, vlan, count = found
            result.update(device_name=device, hostname=device, port=port, vlan=vlan, macs_on_port=count,
                          stats=self.port_stats(device, port))
        return result

    def test(self):
        found = self.devices()
        if not found:
            raise PluginError('No telemetry has come in yet. Turn on Telemetry for devices in the inventory and start '
                              'Telegraf (docs/telemetry.md).')
        online = sum(d['status'] == 1 for d in found)
        return f'Receiving: {len(found)} devices, {online} sent something in the last {_minutes()} minutes.'


REPLAY = 6 * 3600     # an agent's spool may bring batches this old


def _counts(dev):
    """What came in, for the Telemetry page on a Floorbit whose agent collects."""
    with state._lock:
        return {'ports': len(dev.interfaces), 'macs': len(dev.fdb), 'arp': len(dev.arp),
                'neighbours': len(dev.lldp) + len(dev.cdp)}


def _problems():
    """{device: [problem]} from the collector here (floorbit/telemetry/problems.py), with the
    hint in words; the hosted page translates by ``kind``."""
    from floorbit.telemetry import problems as problems_mod
    out = {}
    for p in state.problems.current() if state.problems is not None else []:
        row = {k: p.get(k) for k in ('driver', 'kind', 'address', 'detail', 'since', 'at', 'count')}
        out.setdefault(p['device'], []).append({**row, 'hint': problems_mod.hint(p)})
    return out


def _when(payload):
    """When the agent saw it: its ``at``, unless that is in the future or older than its spool can
    be (then this clock's now: an agent with a wrong clock is not trusted)."""
    import time
    now = time.time()
    at = payload.get('at') if isinstance(payload, dict) else None
    if isinstance(at, bool) or not isinstance(at, (int, float)) or not now - REPLAY <= at <= now + 60:
        return now
    return min(at, now)


def _minutes():
    from floorbit.telemetry.state import STALE
    return STALE // 60


def _natural(name):
    import re
    return [int(p) if p.isdigit() else p.lower() for p in re.split(r'(\d+)', str(name))]
