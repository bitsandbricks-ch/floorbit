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
        return bool(state.devices) or bool(targets.listing())

    def _device(self, hostname):
        return state.find(hostname)

    # the local agent (agent.py there) -----------------------------------------------------------
    def agent_settings(self, settings):
        """What the agent part gets: the devices from Settings > Telemetry, secrets opened, sent
        over the agent's link only. The plugin's own settings (uplink limit, ignored ports) too."""
        from floorbit.telemetry import targets
        return {**settings, 'targets': [targets.opened(t) for t in targets.raw_targets()]}

    def agent_series(self, agent, payload):
        """The agent's per-port and per-device numbers, for the history here."""
        import time

        from floorbit.telemetry import storage
        values = payload.get('values') if isinstance(payload, dict) else None
        clean = {k: float(v) for k, v in list((values or {}).items())[:200_000]
                 if isinstance(k, str) and k.count('|') == 2 and len(k) <= 300
                 and isinstance(v, (int, float)) and not isinstance(v, bool)}
        at = payload.get('at') if isinstance(payload.get('at'), (int, float)) else time.time()
        # This clock decides: an agent whose clock is off by more than a minute is not trusted.
        if abs(at - time.time()) > 60:
            at = time.time()
        if clean:
            storage.storage().sample(clean, at)
        return {'taken': len(clean)}

    def agent_endpoints(self, agent, payload):
        """Where the agent saw each machine: into the IP/MAC history (floorbit/endpoints.py)."""
        from floorbit import endpoints
        rows = payload.get('rows') if isinstance(payload, dict) else None
        rows = [r for r in (rows or [])[:50_000] if isinstance(r, dict)]
        return {'taken': endpoints.history().record(rows)}

    # the monitoring interface -----------------------------------------------------------------
    def devices(self):
        with state._lock:
            found = list(state.devices.values())
        return [{'hostname': d.name, 'display': d.name, 'sysName': d.sys_name or d.name, 'ip': d.address,
                 'status': 1 if d.online() else 0, 'source': 'telemetry', 'driver': d.driver, 'kind': d.kind}
                for d in sorted(found, key=lambda d: d.name)]

    def device_ports(self, hostname):
        dev = self._device(hostname)
        if dev is None:
            return []
        with state._lock:
            rows = [i for i in dev.interfaces.values() if i.name]
            return [{'name': i.name, 'last_change': i.last_change, **summarize_port(i.librenms_row())}
                    for i in sorted(rows, key=lambda i: _natural(i.name))]

    def port_stats(self, hostname, interface):
        want = str(interface or '').lower()
        for port in self.device_ports(hostname):
            if str(port['name']).lower() == want:
                return port
        return {}

    def device_details(self, hostname):
        dev = self._device(hostname)
        if dev is None:
            return {'status': 'unknown', 'hostname': hostname}
        result = {'status': 'online' if dev.online() else 'offline', 'hostname': hostname, 'ip': dev.address,
                  'source': 'telemetry', 'driver': dev.driver}
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
        dev = self._device(hostname)
        if dev is None:
            raise PluginError(f'No telemetry from {hostname} yet.')
        with state._lock:
            return [{'port': dev.port_name(port), 'mac': mac, 'vlan': vlan or None}
                    for (mac, vlan), (port, _seen) in sorted(dev.fdb.items()) if dev.port_name(port)]

    def neighbours(self, hostname):
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
            raise PluginError('No telemetry has come in yet. Add devices under Settings > Telemetry and start '
                              'Telegraf (docs/telemetry.md).')
        online = sum(d['status'] == 1 for d in found)
        return f'Receiving: {len(found)} devices, {online} sent something in the last {_minutes()} minutes.'


def _minutes():
    from floorbit.telemetry.state import STALE
    return STALE // 60


def _natural(name):
    import re
    return [int(p) if p.isdigit() else p.lower() for p in re.split(r'(\d+)', str(name))]
