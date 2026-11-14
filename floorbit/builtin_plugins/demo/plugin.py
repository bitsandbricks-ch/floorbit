"""Made-up data for every data area: inventory, seat mapping, monitoring, the health wall and port actions.

Everything is computed from the seat and switch numbers plus the clock, so it needs no state,
moves a little on every poll and looks the same on every instance. Names are generic, IPs come
from the documentation ranges (RFC 5737) and MACs are locally administered (02:...).
"""
import math
import time

from floorbit.builtin_plugins.librenms.ports import summarize_port
from floorbit.plugins.base import Plugin, PluginError

DOMAIN = 'example.com'
BLOCKS = ('A', 'B', 'C', 'D')
COLS, ROWS = 12, 2
SEATS_PER_SWITCH = 8
SWITCHES_PER_BLOCK = COLS * ROWS // SEATS_PER_SWITCH   # 3
FLAPPING = 'sw-c-02'          # goes down for a minute every four
HALF_DUPLEX = ('B', 5)        # one seat with a bad cable
ERRORS = ('D', 17)
BOUNCE_SECONDS = 10          # a demo bounce keeps the port down this long
_bounced = {}                 # (switch, port) -> time the port comes back
DHCP_POOL = 100               # small enough that the player scope shows amber

# Where things go on an empty floor plan (percent of the plan), used by floorbit/blueprints/demo.py.
# Blocks in a 2 x 2 grid (12 seats of 3.5 % each are 42 % wide), their switches just above them.
_CENTRES = {'A': (27, 42), 'B': (73, 42), 'C': (27, 78), 'D': (73, 78)}
LAYOUT = {
    'devices': {'core-01': (50, 8), 'dist-01': (27, 20), 'dist-02': (73, 20),
                **{f'sw-{b.lower()}-{n:02d}': (x + (n - 2) * 13, y - 12)
                   for b, (x, y) in _CENTRES.items() for n in range(1, SWITCHES_PER_BLOCK + 1)}},
    'blocks': [{'name': b, 'x': x, 'y': y, 'cols': COLS, 'rows': ROWS} for b, (x, y) in _CENTRES.items()],
}


def _seats():
    """[(seat, block, number, global index)] for every seat in the demo hall."""
    out = []
    for b in BLOCKS:
        for n in range(1, COLS * ROWS + 1):
            out.append((f'{b}-{n}', b, n, len(out)))
    return out


def _taken(index):
    return index % 7 != 3          # a few empty seats, like any LAN


def _ip(index):
    return f'192.0.2.{10 + index}'


def _mac(index):
    return f'02:00:00:00:{index // 256:02x}:{index % 256:02x}'


def _switch_for(block, number):
    n = (number - 1) // SEATS_PER_SWITCH + 1
    return f'sw-{block.lower()}-{n:02d}', f'Gi1/0/{(number - 1) % SEATS_PER_SWITCH + 1}'


def _switches():
    """[(name, role, mgmt index)] for the core, distribution and access switches."""
    out = [('core-01', 'router', 1), ('dist-01', 'switch', 2), ('dist-02', 'switch', 3)]
    for b in BLOCKS:
        for n in range(1, SWITCHES_PER_BLOCK + 1):
            out.append((f'sw-{b.lower()}-{n:02d}', 'switch', len(out) + 1))
    return out


def _down(name, now=None):
    now = time.time() if now is None else now
    return name == FLAPPING and int(now // 60) % 4 == 0


def _wave(seed, now=None, period=300.0):
    """0..1, slowly moving, different per seed."""
    now = time.time() if now is None else now
    return 0.5 + 0.5 * math.sin(now / period * 2 * math.pi + seed * 1.7)


def _level(value, warn, down, higher_is_better=False):
    """up, warn or down for a ratio against two thresholds."""
    if higher_is_better:
        return 'down' if value <= down else 'warn' if value <= warn else 'up'
    return 'down' if value >= down else 'warn' if value >= warn else 'up'


def _model(name):
    if name.startswith('core'):
        return 'Example Core 9000'
    return 'Example Agg 24X' if name.startswith('dist') else 'Example Access 48P'


def _short(hostname):
    return (hostname or '').lower().split('.')[0]


class Plugin(Plugin):
    # inventory --------------------------------------------------------------------------
    def inventory(self):
        return [{'id': name, 'name': name, 'role': role, 'model': _model(name),
                 'serial': f'DEMO{i:05d}', 'mgmt_ip': f'198.51.100.{i}', 'hall': 'Demo hall',
                 'status': 'active'} for name, role, i in _switches()]

    # seat mapping -----------------------------------------------------------------------
    def seat_mapping(self):
        return {seat: {'ip': _ip(i), 'mac': _mac(i), 'nick': f'player-{i + 1:02d}'}
                for seat, _b, _n, i in _seats() if _taken(i)}

    # monitoring -------------------------------------------------------------------------
    def configured(self):
        return True

    def devices(self):
        return [{'display': name, 'hostname': f'{name}.{DOMAIN}', 'sysName': name,
                 'status': 0 if _down(name) else 1, 'status_reason': 'icmp' if _down(name) else ''}
                for name, _role, _i in _switches()]

    def device_details(self, hostname):
        name = _short(hostname)
        found = next(((n, i) for n, _r, i in _switches() if n == name), None)
        if not found:
            return {'status': 'unknown', 'hostname': hostname}
        name, i = found
        if _down(name):
            return {'status': 'offline', 'hostname': hostname, 'ip': f'198.51.100.{i}'}
        players = [idx for _s, b, n, idx in _seats() if _switch_for(b, n)[0] == name and _taken(idx)]
        traffic = sum(sum(self._rates(idx)) for idx in players) * 8
        return {'status': 'online', 'hostname': hostname, 'ip': f'198.51.100.{i}',
                'cpu_load': round(8 + 30 * _wave(i)), 'mem_percent': round(35 + 15 * _wave(i + 3, period=900)),
                'temperature': round(38 + 8 * _wave(i, period=1200), 1),
                'total_ports': 48, 'up_ports': len(players) + 2, 'total_traffic_bps': round(traffic),
                'traffic_util': round(100 * traffic / (48 * 1e9), 1)}

    def resolve_ip(self, ip_address, search_device=None):
        seat = next((s for s in _seats() if _taken(s[3]) and _ip(s[3]) == ip_address), None)
        if not seat:
            return None
        _label, block, number, i = seat
        switch, port = _switch_for(block, number)
        return {'ip': ip_address, 'mac': _mac(i), 'device_name': switch, 'hostname': f'{switch}.{DOMAIN}',
                'port': port, 'vlan': '100', 'arp_source': 'core-01',
                'stats': self.port_stats(f'{switch}.{DOMAIN}', port)}

    def port_stats(self, hostname, interface):
        name = _short(hostname)
        seat = next((s for s in _seats() if _switch_for(s[1], s[2]) == (name, interface)), None)
        if not seat:
            return None
        _label, block, number, i = seat
        rx, tx = self._rates(i) if _taken(i) else (0, 0)
        up = _taken(i) and not _down(name) and _bounced.get((name, interface), 0) < time.time()
        raw = {'ifOperStatus': 'up' if up else 'down', 'ifAdminStatus': 'up',
               'ifInOctets_rate': tx if up else 0, 'ifOutOctets_rate': rx if up else 0, 'ifSpeed': 1_000_000_000,
               'ifDuplex': 'halfDuplex' if (block, number) == HALF_DUPLEX else 'fullDuplex',
               'ifInErrors_rate': 2.5 if (block, number) == ERRORS else 0, 'ifOutErrors_rate': 0,
               'ifInErrors': 1200 if (block, number) == ERRORS else 0, 'ifOutErrors': 0,
               'poll_time': int(time.time()), 'ifAlias': f'Seat {block}-{number}'}
        return summarize_port(raw)

    def arp(self, query):
        q = (query or '').lower()
        return [{'ipv4_address': _ip(i), 'mac_address': _mac(i), 'hostname': f'core-01.{DOMAIN}'}
                for _s, _b, _n, i in _seats() if _taken(i) and q in (_ip(i), _mac(i))]

    @staticmethod
    def _rates(index):
        """(download, upload) in bytes per second: mostly quiet, a few heavy downloaders."""
        heavy = index % 11 == 0
        down = (40e6 if heavy else 1.5e6) * (0.2 + _wave(index))
        return down, down * (0.08 + 0.1 * _wave(index + 5, period=120))

    # port actions -----------------------------------------------------------------------
    def port_login(self):
        return False      # nothing real to log in to

    def bounce_port(self, target):
        name = _short(target['switch'])
        if not any(n == name for n, _r, _i in _switches()):
            raise PluginError(f"{target['switch']} is not a demo switch.")
        _bounced[(name, target['port'])] = time.time() + BOUNCE_SECONDS
        return {'message': f"{target['port']} on {name} is down for {BOUNCE_SECONDS} s (demo: no switch was touched)."}

    # health wall ------------------------------------------------------------------------
    def health_checks(self):
        now = time.time()
        players = sum(_taken(s[3]) for s in _seats())
        left = DHCP_POOL - players
        hit = round(62 + 28 * _wave(1, now, period=600))
        saved = round(40 + (now % 86400) / 86400 * 900 * _wave(2, now, period=3600), 1)
        uplink = round(35 + 50 * _wave(3, now, period=900))
        game_down = int(now // 60) % 5 < 2          # two minutes in five, so alerts can be tried
        dns_ms = round(3 + 9 * _wave(4, now, period=120))
        return [
            {'id': 'dhcp-players', 'name': 'DHCP players', 'kind': 'dhcp', 'link': '/dashboard',
             'status': _level(left / DHCP_POOL, warn=0.25, down=0.05, higher_is_better=True),
             'summary': f'{left} of {DHCP_POOL} leases left',
             'metrics': [{'label': 'Leases left', 'value': left}, {'label': 'In use', 'value': players}]},
            {'id': 'dhcp-staff', 'name': 'DHCP staff', 'kind': 'dhcp', 'status': 'up',
             'summary': '52 of 64 leases left', 'metrics': [{'label': 'Leases left', 'value': 52}]},
            {'id': 'dns-1', 'name': 'DNS resolver 1', 'kind': 'dns', 'status': 'up',
             'summary': f'Answers in {dns_ms} ms',
             'metrics': [{'label': 'Answer time', 'value': dns_ms, 'unit': 'ms'}]},
            {'id': 'dns-2', 'name': 'DNS resolver 2', 'kind': 'dns', 'status': 'up',
             'summary': f'Answers in {dns_ms + 2} ms',
             'metrics': [{'label': 'Answer time', 'value': dns_ms + 2, 'unit': 'ms'}]},
            {'id': 'cache', 'name': 'LAN cache', 'kind': 'cache',
             'status': _level(hit / 100, warn=0.5, down=0.2, higher_is_better=True),
             'summary': f'{hit} % hit rate, {saved} GB saved',
             'metrics': [{'label': 'Hit rate', 'value': hit, 'unit': '%'},
                         {'label': 'Saved', 'value': saved, 'unit': 'GB'}]},
            {'id': 'game-1', 'name': 'Game server 1', 'kind': 'game', 'status': 'up',
             'summary': '18 of 20 players', 'metrics': [{'label': 'Players', 'value': '18/20'}]},
            {'id': 'game-2', 'name': 'Game server 2', 'kind': 'game', 'status': 'up',
             'summary': '9 of 10 players', 'metrics': [{'label': 'Players', 'value': '9/10'}]},
            {'id': 'game-3', 'name': 'Game server 3', 'kind': 'game', 'status': 'down' if game_down else 'up',
             'summary': 'Not answering' if game_down else '4 of 10 players',
             'metrics': [] if game_down else [{'label': 'Players', 'value': '4/10'}]},
            {'id': 'uplink', 'name': 'Internet uplink', 'kind': 'uplink',
             'status': _level(uplink / 100, warn=0.8, down=0.95),
             'summary': f'{uplink / 10:.1f} of 10 Gbit/s in use',
             'metrics': [{'label': 'In use', 'value': uplink, 'unit': '%', 'tone': 'warn' if uplink >= 80 else ''},
                         {'label': 'Loss', 'value': 0, 'unit': '%'}]},
        ]

    def test(self):
        return f'Demo data: {len(_switches())} switches and {sum(_taken(s[3]) for s in _seats())} players.'
