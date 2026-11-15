"""Made-up data for every data area: inventory, seat mapping, monitoring, the health wall, port actions,
security findings, power readings and DNS lookups.

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
FLAPPING_PORT = ('C', 9)      # a loose cable: the link drops every 45 seconds
BOUNCE_SECONDS = 10          # a demo bounce keeps the port down this long
_bounced = {}                 # (switch, port) -> time the port comes back
_shut = set()                 # (switch, port) shut until turned on again
DHCP_POOL = 100               # small enough that the player scope shows amber

# Where things go on an empty floor plan (percent of the plan), used by floorbit/blueprints/demo.py.
# Blocks in a 2 x 2 grid (12 seats of 3.5 % each are 42 % wide), their switches just above them.
_CENTRES = {'A': (27, 42), 'B': (73, 42), 'C': (27, 78), 'D': (73, 78)}
LAYOUT = {
    'devices': {'core-01': (50, 8), 'dist-01': (27, 20), 'dist-02': (73, 20),
                **{f'sw-{b.lower()}-{n:02d}': (x + (n - 2) * 13, y - 12)
                   for b, (x, y) in _CENTRES.items() for n in range(1, SWITCHES_PER_BLOCK + 1)}},
    'blocks': [{'name': b, 'x': x, 'y': y, 'cols': COLS, 'rows': ROWS} for b, (x, y) in _CENTRES.items()],
    # Two boards, one 16 A circuit per seat row (phases in turn) and one for the network rack.
    'power': {
        'boards': [{'name': 'DB-1', 'location': 'West wall', 'x': 4, 'y': 42},
                   {'name': 'DB-2', 'location': 'East wall', 'x': 96, 'y': 78}],
        'circuits': [{'board': 'DB-1' if b in 'AB' else 'DB-2', 'name': f'{b} row {r}', 'rating_a': 16,
                      'phase': ('L1', 'L2', 'L3')[(BLOCKS.index(b) * ROWS + r - 1) % 3],
                      'meter': f'{b.lower()}{r}', 'block': b, 'rows': [r]}
                     for b in BLOCKS for r in range(1, ROWS + 1)]
        + [{'board': 'DB-1', 'name': 'Network rack', 'rating_a': 32, 'phase': '3P', 'meter': 'rack',
            'switches': ['core-01', 'dist-01', 'dist-02']}],
    },
}


# (name, weight, blocked by the resolver) for the demo lookups.
DNS_SITES = (
    ('cdn.steamcontent.com', 18, False), ('api.steampowered.com', 8, False), ('gateway.discord.gg', 10, False),
    ('cdn.discordapp.com', 5, False), ('video-edge.ttvnw.net', 8, False), ('www.twitch.tv', 3, False),
    ('rr3.googlevideo.com', 5, False), ('www.youtube.com', 3, False), ('eu.battle.net', 4, False),
    ('auth.riotgames.com', 3, False), ('download.windowsupdate.com', 3, False), ('api.spotify.com', 2, False),
    ('ads.doubleclick.net', 4, True), ('telemetry.tracker.example', 2, True), ('www.wikipedia.org', 2, False),
)


def _dns_pick(pick, index):
    """(domain, blocked) for a number below the weights' sum plus 6: past the sum, the seat's own."""
    for domain, weight, blocked in DNS_SITES:
        if pick < weight:
            return domain, blocked
        pick -= weight
    return (f'www.hobby-{index}.example' if pick < 4 else f'pc-{index}.lan'), False


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


class DemoShell:
    """A pretend switch CLI for the browser terminal: echoes keys and answers the show commands."""

    HELP = ('show interfaces status', 'show interface <port>', 'show mac address-table', 'show version', 'exit')

    def __init__(self, plugin, name):
        self.plugin, self.name, self.line, self.closed = plugin, name, '', False
        self.pending = (f'\r\n{name} (demo: no switch is touched)\r\n'
                        f'Type ? for the commands this pretend switch knows.\r\n\r\n{name}#')

    def recv(self):
        if self.closed and not self.pending:
            return None
        out, self.pending = self.pending, ''
        return out

    def send(self, data):
        for ch in data:
            if ch in '\r\n':
                self._enter()
            elif ch in '\x7f\b':
                if self.line:
                    self.line = self.line[:-1]
                    self.pending += '\b \b'
            elif ch == '?':
                self.pending += '?\r\n' + '\r\n'.join(f'  {c}' for c in self.HELP) + f'\r\n{self.name}#{self.line}'
            elif ch == '\x03':
                self.line = ''
                self.pending += f'^C\r\n{self.name}#'
            elif ch >= ' ':
                self.line += ch
                self.pending += ch

    def _enter(self):
        command, self.line = ' '.join(self.line.split()), ''
        if command in ('exit', 'quit', 'logout'):
            self.pending += '\r\n'
            self.closed = True
            return
        out = ''
        if command:
            out = self.plugin.send_commands({'switch': self.name, 'commands': [command]})['output']
        self.pending += '\r\n' + (out.replace('\n', '\r\n') + '\r\n' if out else '') + f'{self.name}#'

    def resize(self, cols, rows):
        pass

    def close(self):
        self.closed = True


class Plugin(Plugin):
    # inventory --------------------------------------------------------------------------
    def inventory(self):
        return [{'id': name, 'name': name, 'role': role, 'model': _model(name),
                 'serial': f'DEMO{i:05d}', 'mgmt_ip': f'198.51.100.{i}', 'hall': 'Demo hall',
                 'status': 'active'} for name, role, i in _switches()]

    def cables(self):
        # The first block's seats run through a patch panel, the rest go straight to the switch.
        out = []
        for seat, block, number, _i in _seats():
            switch, port = _switch_for(block, number)
            panel = f'PP-{block}' if block == BLOCKS[0] else ''
            out.append({'label': f'NB-{seat}', 'switch': switch, 'port': port, 'panel': panel,
                        'panel_port': str(number) if panel else '', 'seat': seat, 'color': 'blue',
                        'length_m': 5 if panel else 10})
        return out

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
        up = _taken(i) and not _down(name) and _bounced.get((name, interface), 0) < time.time() \
            and (name, interface) not in _shut
        flapping = (block, number) == FLAPPING_PORT
        if flapping:
            up = int(time.time() // 45) % 2 == 0
        raw = {'ifOperStatus': 'up' if up else 'down', 'ifAdminStatus': 'up',
               'ifInOctets_rate': tx if up else 0, 'ifOutOctets_rate': rx if up else 0, 'ifSpeed': 1_000_000_000,
               'ifDuplex': 'halfDuplex' if (block, number) == HALF_DUPLEX else 'fullDuplex',
               'ifInErrors_rate': 2.5 if (block, number) == ERRORS else 0, 'ifOutErrors_rate': 0,
               'ifInErrors': 1200 + int(time.time() // 2) % 100000 if (block, number) == ERRORS else 0,
               'ifOutErrors': 0,
               'poll_time': int(time.time()), 'ifAlias': f'Seat {block}-{number}'}
        out = summarize_port(raw)
        if flapping:
            out['last_change'] = int(time.time() // 45) * 45
        return out

    def device_ports(self, hostname):
        name = _short(hostname)
        ports = [_switch_for(b, n)[1] for _s, b, n, _i in _seats() if _switch_for(b, n)[0] == name]
        out = [{'name': port, **(self.port_stats(hostname, port) or {})} for port in ports]
        if ports and not _down(name):
            # The access switch's uplink: everything its seats send and get, on a 10G port.
            down = sum(p.get('download_bps') or 0 for p in out)
            up = sum(p.get('upload_bps') or 0 for p in out)
            dist = 'dist-01' if name[3] in 'ab' else 'dist-02'
            out.append({'name': 'Te1/1/1', 'state': 'up', 'description': f'Uplink to {dist}', 'duplex': 'full',
                        'speed_bps': 10_000_000_000, 'download_bps': up, 'upload_bps': down,
                        'utilization': round(max(down, up) / 10e9, 4), 'errors_in': 0, 'errors_out': 0,
                        'last_change': None})
        return out

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

    def set_port(self, target):
        name = _short(target['switch'])
        if not any(n == name for n, _r, _i in _switches()):
            raise PluginError(f"{target['switch']} is not a demo switch.")
        (_shut.discard if target.get('enabled') else _shut.add)((name, target['port']))
        state = 'on again' if target.get('enabled') else 'shut'
        return {'message': f"{target['port']} on {name} is {state} (demo: no switch was touched)."}

    # switch commands (issue #94) ---------------------------------------------------------
    def command_platform(self):
        return 'cisco_ios'

    def send_commands(self, target):
        """Made-up answers in Cisco IOS style, from the same seats the floor plan shows."""
        name = _short(target['switch'])
        if not any(n == name for n, _r, _i in _switches()):
            raise PluginError(f"{target['switch']} is not a demo switch.")
        parts = []
        for command in target.get('commands') or []:
            words = command.split()
            port = words[-1] if words and '/' in words[-1] else None
            if words[:1] == ['clear']:
                parts.append('')
            elif 'mac' in command:
                parts.append(self._demo_macs(name, port))
            elif words[:2] == ['show', 'interfaces'] and 'status' in words:
                parts.append(self._demo_status(name))
            elif 'errors' in words:
                parts.append(self._demo_errors(name))
            elif words[:2] == ['show', 'interface'] and port:
                parts.append(self._demo_interface(name, port))
            elif words[:2] == ['show', 'version']:
                parts.append(f'Example Switch Software, Version 17.9.4 (demo)\n{name} uptime is 3 days, 4 hours\n'
                             f'Model number: {_model(name)}')
            else:
                parts.append(f'% Invalid input detected at \'^\' marker. (demo: "{command}")')
                return {'output': '\n\n'.join(parts), 'refused': command}
        return {'output': '\n\n'.join(parts) or '(demo: no switch was touched)', 'refused': None}

    def open_shell(self, target):
        name = _short(target['switch'])
        if not any(n == name for n, _r, _i in _switches()):
            raise PluginError(f"{target['switch']} is not a demo switch.")
        return DemoShell(self, name)

    def _demo_ports(self, name):
        return [(s, b, n, i, _switch_for(b, n)[1]) for s, b, n, i in _seats() if _switch_for(b, n)[0] == name]

    def _demo_status(self, name):
        rows = ['Port      Name          Status       Vlan  Duplex  Speed Type']
        for seat, _b, _n, _i, port in self._demo_ports(name):
            st = self.port_stats(name, port) or {}
            up = st.get('state') == 'up'
            rows.append(f"{port:<9} {'Seat ' + seat:<13} {'connected' if up else 'notconnect':<12} 100   "
                        f"{'a-full' if up else 'auto':<7} {'a-1000' if up else 'auto':<5} 10/100/1000BaseTX")
        return '\n'.join(rows)

    def _demo_macs(self, name, port):
        rows = ['          Mac Address Table', '-------------------------------------------',
                'Vlan    Mac Address       Type        Ports', '----    -----------       --------    -----']
        for _seat, _b, _n, i, p in self._demo_ports(name):
            if _taken(i) and (not port or p.lower() == port.lower()):
                mac = _mac(i).replace(':', '')
                rows.append(f' 100    {mac[0:4]}.{mac[4:8]}.{mac[8:12]}    DYNAMIC     {p}')
        rows.append(f'Total Mac Addresses for this criterion: {len(rows) - 4}')
        return '\n'.join(rows)

    def _demo_errors(self, name):
        rows = ['Port        Align-Err     FCS-Err    Xmit-Err     Rcv-Err  UnderSize  OutDiscards']
        for _seat, b, n, _i, port in self._demo_ports(name):
            errors = 1200 + int(time.time() // 2) % 100000 if (b, n) == ERRORS else 0
            rows.append(f'{port:<11} {0:>9} {errors:>10} {0:>11} {errors:>11} {0:>10} {0:>12}')
        return '\n'.join(rows)

    def _demo_interface(self, name, port):
        st = self.port_stats(name, port)
        if not st:
            return f"% Invalid input detected at '^' marker. (demo: {port} is no seat port on {name})"
        up = st.get('state') == 'up'
        return (f"{port} is {'up' if up else 'down'}, line protocol is {'up' if up else 'down'}"
                f"{'' if up else ' (notconnect)'}\n"
                f"  Description: {st.get('description') or ''}\n"
                f"  {'Half' if st.get('duplex') == 'half' else 'Full'}-duplex, 1000Mb/s, media 1000BaseTX\n"
                f"  5 minute input rate {int(st.get('upload_bps') or 0)} bits/sec\n"
                f"  5 minute output rate {int(st.get('download_bps') or 0)} bits/sec\n"
                f"  {int(st.get('errors_in') or 0)} input errors, 0 CRC, 0 frame, 0 overrun, 0 ignored")

    # security findings ------------------------------------------------------------------
    def security_findings(self):
        """A few made-up findings; the rogue DHCP server comes and goes so alerts can be tried."""
        now = time.time()
        spoof = next(i for s, _b, _n, i in _seats() if s == 'B-4')
        victim = next(i for s, _b, _n, i in _seats() if s == 'B-9')
        flap = next(i for s, _b, _n, i in _seats() if s == 'C-14')
        out = [
            {'id': f'arp-{_ip(victim)}', 'kind': 'arp-spoof', 'severity': 'high',
             'title': f'{_ip(victim)} is answered by two MACs',
             'detail': 'Another seat answers ARP for this address: someone may be intercepting its traffic.',
             'switch': _switch_for('B', 4)[0], 'port': _switch_for('B', 4)[1], 'mac': _mac(spoof), 'ip': _ip(victim),
             'evidence': [f'{_mac(victim)} on {_switch_for("B", 9)[1]} (seat B-9, expected)',
                          f'{_mac(spoof)} on {_switch_for("B", 4)[1]} (seat B-4)']},
            {'id': f'flap-{_mac(flap)}', 'kind': 'mac-flap', 'severity': 'medium',
             'title': f'{_mac(flap)} moves between two ports',
             'detail': 'The same MAC shows up on two access ports in turn: a loop, or a cloned MAC.',
             'switch': _switch_for('C', 14)[0], 'port': _switch_for('C', 14)[1], 'mac': _mac(flap),
             'evidence': [f'{_switch_for("C", 14)[1]} and {_switch_for("C", 15)[1]}, 14 moves in 5 minutes']},
            {'id': 'storm-sw-d-02', 'kind': 'storm', 'severity': 'medium',
             'title': 'Broadcast storm on sw-d-02', 'switch': 'sw-d-02', 'port': 'Gi1/0/48',
             'detail': 'Broadcasts on the uplink are far above normal.',
             'evidence': [f'{round(4200 + 1800 * _wave(9, now, period=120))} broadcast packets/s, '
                          'normal is under 200']},
        ]
        if int(now // 60) % 6 < 3:
            rogue = next(i for s, _b, _n, i in _seats() if s == 'A-7')
            out.insert(0, {'id': f'dhcp-{_mac(rogue)}', 'kind': 'rogue-dhcp', 'severity': 'high',
                           'title': 'DHCP offers from a server that is not ours',
                           'detail': 'A device at a seat hands out addresses: players near it may get no internet.',
                           'switch': _switch_for('A', 7)[0], 'port': _switch_for('A', 7)[1], 'mac': _mac(rogue),
                           'ip': '192.0.2.250', 'evidence': ['Offers 10.0.0.0/24 with gateway 10.0.0.1']})
        return out

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

    # power ------------------------------------------------------------------------------
    def power_readings(self):
        """Load per meter in amps. B row 2 runs warm; C row 2 goes over the top two minutes in seven."""
        now = time.time()
        out = []
        for i, c in enumerate(LAYOUT['power']['circuits']):
            if c['meter'] == 'rack':
                amps = 9 + 3 * _wave(20, now, period=600)
            elif c['meter'] == 'b2':
                amps = 13.2 + 0.8 * _wave(21, now, period=300)
            elif c['meter'] == 'c2':
                amps = 15.6 + 0.4 * _wave(22, now) if int(now // 60) % 7 < 2 else 11 + _wave(22, now)
            else:
                amps = 6 + 5 * _wave(30 + i, now, period=900)
            out.append({'meter': c['meter'], 'amps': round(amps, 1)})
        return out

    # dns --------------------------------------------------------------------------------
    def dns_queries(self, since):
        """Lookups from every player, about two a minute each. Busy sites are looked up by many seats,
        each seat also looks up a site of its own (never named: too few clients) and its own PC."""
        now = time.time()
        total = sum(w for _d, w, _b in DNS_SITES)
        out = []
        for minute in range(int(max(since, now - 600) // 60), int(now // 60) + 1):
            for _seat, _b, _n, i in _seats():
                if not _taken(i):
                    continue
                for k in range(2):
                    ts = minute * 60 + (i * 7 + k * 29) % 60
                    if not since < ts <= now:
                        continue
                    domain, blocked = _dns_pick((i * 31 + minute * 17 + k * 13) % (total + 6), i)
                    out.append({'ts': ts, 'domain': domain, 'client': _ip(i), 'blocked': blocked})
        return out

    def test(self):
        return f'Demo data: {len(_switches())} switches and {sum(_taken(s[3]) for s in _seats())} players.'
