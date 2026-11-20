"""Telemetry for the demo hall: what Telegraf would send for the demo's switches and firewalls, so
the Telemetry page, the stored series and the endpoints search have something to show
(docs/telemetry.md). Built from the same made-up hall the demo's monitoring answers from.

The devices are set up with drivers Telegraf would run (SNMP, traps, gNMI, the firewalls' own
Telegraf): nothing here polls an API, and no Telegraf runs, so nothing is sent out.
"""
import secrets
import threading
import time

from floorbit.telemetry.lineproto import Point

from .plugin import DOMAIN, DOWN_FIREWALL, FIREWALLS, Plugin, _down, _switches, _wave

FEED_EVERY = 30
VLAN = 100
_counters = {}                 # (device, ifIndex, direction) -> (octets, at): counters only grow
_lock = threading.Lock()


def setup():
    """How the demo's devices are set up for telemetry in the inventory: groups with the feature on,
    an SNMP v3 login (made up on the spot) and the properties each kind of device needs."""
    login = {'kind': 'snmp_v3', 'username': 'floorbit', 'auth_protocol': 'SHA', 'priv_protocol': 'AES',
             'secret': secrets.token_urlsafe(16), 'priv_secret': secrets.token_urlsafe(16)}
    switches = {name: ({'telemetry.drivers': 'snmp traps gnmi'} if _role_of(name) == 'core'
                       else {'telemetry.snmp.vlans': str(VLAN)}) for name, _role, _i in _switches()}
    return [
        # The firewalls run Telegraf themselves and push: no login.
        {'name': 'Network', 'properties': {}, 'login': login, 'devices': switches},
        {'name': 'Firewalls', 'properties': {'telemetry.drivers': 'push'}, 'login': None,
         'devices': {name: {} for name in FIREWALLS}},
    ]


def _role_of(name):
    return 'core' if name == 'core-01' else 'dist' if name.startswith('dist-') else 'access'


def _counter(device, index, direction, bps, now):
    """A 64-bit octet counter that grows by ``bps`` since the last read."""
    with _lock:
        octets, at = _counters.get((device, index, direction), ((hash((device, index, direction)) % 10**9), now))
        octets += max(0.0, bps) / 8 * max(0.0, now - at)
        _counters[(device, index, direction)] = (octets, now)
    return int(octets)


def _mac_index(mac):
    return '.'.join(str(int(part, 16)) for part in mac.split(':'))


def points(plugin, now=None):
    """One poll of every demo device, as line protocol points."""
    now = time.time() if now is None else now
    out = []
    for name, _role, i in _switches():
        role = _role_of(name)
        if _down(name):                                # as the plugin answers right now
            continue                                   # a switch that is down answers nothing
        host = f'{name}.{DOMAIN}'
        tags = {'device': name, 'driver': 'snmp'}
        details = plugin.device_details(host)
        out.append(Point('fb_system', dict(tags), {
            'sysName': name, 'sysUpTime': int((now % 864000) * 100) + i * 1000,
            'cpu': float(details.get('cpu_load') or 0), 'mem': float(details.get('mem_percent') or 0)}, now))
        index_of = {}
        for idx, port in enumerate(plugin.device_ports(host), 1):
            index_of[port['name']] = idx
            up = port.get('state') == 'up'
            fields = {'ifName': port['name'], 'ifOperStatus': 1 if up else 2, 'ifAdminStatus': 1,
                      'ifHighSpeed': int((port.get('speed_bps') or 0) / 1e6),
                      'ifHCInOctets': _counter(name, idx, 'in', (port.get('upload_bps') or 0) if up else 0, now),
                      'ifHCOutOctets': _counter(name, idx, 'out', (port.get('download_bps') or 0) if up else 0, now),
                      'ifInErrors': int(port.get('errors_in') or 0), 'ifOutErrors': int(port.get('errors_out') or 0),
                      'ifAlias': port.get('description') or ''}
            if port.get('duplex') in ('half', 'full'):
                fields['dot3StatsDuplexStatus'] = 2 if port['duplex'] == 'half' else 3
            out.append(Point('fb_if', {**tags, 'index': str(idx)}, fields, now))
        for n, row in enumerate(plugin.neighbours(host), 1):
            if row['port'] in index_of:
                out.append(Point('fb_lldp', {**tags, 'index': f"0.{index_of[row['port']]}.{n}"},
                                 {'lldpRemSysName': row['remote'], 'lldpRemPortId': row['remote_port']}, now))
        if role == 'access':
            for row in plugin.port_clients(host):
                if row['port'] in index_of:
                    out.append(Point('fb_qfdb', {**tags, 'index': f"{row['vlan']}.{_mac_index(row['mac'])}"},
                                     {'dot1qTpFdbPort': index_of[row['port']], 'dot1qTpFdbStatus': 3}, now))
        if role == 'core':
            for row in plugin.arp('0.0.0.0/0'):
                out.append(Point('fb_arp', {**tags, 'ip': row['ipv4_address'], 'port': f'Vlan{VLAN}'},
                                 {'mac': row['mac_address']}, now))
    for n, name in enumerate(FIREWALLS, 1):
        if name == DOWN_FIREWALL:
            continue
        tags = {'device': name, 'driver': 'push', 'kind': 'firewall'}
        out += [
            Point('cpu', {**tags, 'cpu': 'cpu-total'}, {'usage_idle': round(92 - 30 * _wave(300 + n, now), 1)}, now),
            Point('mem', dict(tags), {'used_percent': round(30 + 10 * _wave(310 + n, now, period=900), 1)}, now),
            Point('pf', dict(tags), {'entries': int(2000 + 6000 * _wave(320 + n, now))}, now),
            Point('system', dict(tags), {'uptime': int(now % 864000) + n * 3600}, now),
            *(Point('net', {**tags, 'interface': iface}, {
                'bytes_recv': _counter(name, iface, 'in', bps * (0.6 + 0.4 * _wave(340 + n, now)), now),
                'bytes_sent': _counter(name, iface, 'out', bps * 0.15 * (0.6 + 0.4 * _wave(350 + n, now)), now),
                'err_in': 0, 'err_out': 0}, now) for iface, bps in (('ix0', 400e6), ('ix1', 420e6))),
            Point('fb_gateway', {**tags, 'gateway': 'WAN_GW'},
                  {'status': 'online', 'delay_ms': round(4 + 3 * _wave(330 + n, now), 1), 'loss_pct': 0.0}, now),
        ]
    return out


def feed(context, now=None):
    """Hand one poll to the collector, the way /api/telemetry/write does, and note where each machine
    is in the endpoint history (the collector does that only while the Telemetry plugin is on, and
    the demo keeps its own plugin as the monitoring source)."""
    from floorbit import endpoints, telemetry
    from floorbit.telemetry import clients, lineproto
    from floorbit.telemetry import state as state_mod
    text = '\n'.join(lineproto.format_point(p) for p in points(Plugin(context), now))
    taken = telemetry.ingest(text, now)
    endpoints.history().record(clients.sightings(state_mod.state), now)
    return taken
