"""Made-up data for every data area: inventory, seat mapping, monitoring, the health wall, port actions,
security findings, power readings and DNS lookups.

Everything is computed from the seat and switch numbers plus the clock, so it needs no state,
moves a little on every poll and looks the same on every instance. Names are generic, IPs come
from the documentation ranges (RFC 5737) and MACs are locally administered (02:...).

The hardware is a common LAN party mix: a Nexus core, Catalyst 4500-X distribution and Catalyst
2960-X access switches, with their real port names and counts, and ten firewalls behind the core.
"""
import ipaddress
import math
import time

from floorbit.builtin_plugins.demo.texts import text
from floorbit.builtin_plugins.librenms.ports import summarize_port
from floorbit.plugins.base import Plugin, PluginError

DOMAIN = 'example.com'
BLOCKS = ('A', 'B', 'C', 'D')     # the main hall
COLS, ROWS = 12, 2
SEATS_PER_SWITCH = 8
SWITCHES_PER_BLOCK = COLS * ROWS // SEATS_PER_SWITCH   # 3
# The side hall: one block on one switch whose patching nobody wrote down. Only rough port areas
# say which ports go where (and the ports have no descriptions), as at many events.
T = text()            # English, or German with FLOORBIT_DEMO_LANGUAGE=de (texts.py)
SIDE_HALL = T['side_hall']
SIDE_BLOCK, SIDE_COLS, SIDE_ROWS = 'E', 8, 2
SIDE_SWITCH = 'sw-e-01'
MAIN_HALL = T['main_hall']
FLAPPING = 'sw-c-02'          # goes down for a minute every four
HALF_DUPLEX = ('B', 5)        # one seat with a bad cable
ERRORS = ('D', 17)
SWAPPED = (('B', 2), ('B', 3))   # two players sat down at each other's seats
CREW_LAPTOP = ('sw-d-01', 'Gi1/0/40')   # on a port no seat is patched to
FLAPPING_PORT = ('C', 9)      # a loose cable: the link drops every 45 seconds
BOUNCE_SECONDS = 10          # a demo bounce keeps the port down this long
_bounced = {}                 # (switch, port) -> time the port comes back
_shut = set()                 # (switch, port) shut until turned on again
DHCP_POOL = 120               # small enough that the player scope shows amber

# Models and their ports: (port name, speed in bit/s) in the order the switch lists them.
CORE_MODEL = 'Cisco Nexus 93180YC-FX'
DIST_MODEL = 'Cisco Catalyst 4500-X-16'
ACCESS_MODEL = 'Cisco Catalyst 2960-X-48FPD-L'
FIREWALL_MODEL = 'OPNsense appliance'
AP_MODEL = 'Example AP 6'
G = 1_000_000_000
PORTS = {
    CORE_MODEL: [(f'Ethernet1/{n}', 25 * G) for n in range(1, 49)]
    + [(f'Ethernet1/{n}', 100 * G) for n in range(49, 55)],
    DIST_MODEL: [(f'Te1/{n}', 10 * G) for n in range(1, 17)],
    ACCESS_MODEL: [(f'Gi1/0/{n}', G) for n in range(1, 49)] + [(f'Te1/0/{n}', 10 * G) for n in (1, 2)],
}
ACCESS_UPLINK = 'Te1/0/1'
DIST_UPLINK = 'Te1/16'

# Access points: (name, where on the plan, (2.4 GHz channel or None, 5 GHz channel)). ap-02 and
# ap-03 share channel 44 a little too close together, so the Wi-Fi view has an overlap to show. The
# stage AP is 5 GHz only, as high-density APs often are. The top row sits between the access switches
# (at 14, 27, 40, 60, 73 and 86 % across), not on them, so their names don't print over each other.
# ap-10 is in the side hall.
APS = (('ap-01', (7, 30), (1, 36)), ('ap-02', (47, 30), (6, 44)), ('ap-03', (53, 30), (11, 44)),
       ('ap-04', (93, 30), (1, 52)), ('ap-05', (14, 92), (6, 100)), ('ap-06', (40, 92), (11, 116)),
       ('ap-07', (60, 92), (1, 132)), ('ap-08', (86, 92), (6, 149)), ('ap-stage', (50, 60), (None, 60)),
       ('ap-10', (75, 30), (11, 157)))
CROWDED_AP = 'ap-stage'     # the stage: always busy
# Ten firewalls behind the core, each serving a /28 of the seats; fw-03 is down, so its range has
# failed over to fw-04 (the firewall view's failover to show).
FIREWALLS = tuple(f'fw-{n:02d}' for n in range(1, 11))
DOWN_FIREWALL = 'fw-03'
# The core's two internet lines (the services view): port, line speed, how busy on average.
ISP_PORTS = (('Ethernet1/47', 10 * G, 0.55), ('Ethernet1/48', 10 * G, 0.25))

# Where things go on an empty floor plan (percent of the plan), used by floorbit/blueprints/demo.py.
# Blocks in a 2 x 2 grid (12 seats of 3.5 % each are 42 % wide), their switches just above them.
_CENTRES = {'A': (27, 42), 'B': (73, 42), 'C': (27, 78), 'D': (73, 78)}
LAYOUT = {
    'hall': MAIN_HALL,
    'devices': {'core-01': (50, 8), 'dist-01': (27, 20), 'dist-02': (73, 20),
                **{f'sw-{b.lower()}-{n:02d}': (x + (n - 2) * 13, y - 12)
                   for b, (x, y) in _CENTRES.items() for n in range(1, SWITCHES_PER_BLOCK + 1)},
                **{name: pos for name, pos, _ch in APS if name != 'ap-10'}},
    'blocks': [{'name': b, 'x': x, 'y': y, 'cols': COLS, 'rows': ROWS} for b, (x, y) in _CENTRES.items()],
    # The side hall has its own plan: one block, its switch and an access point.
    'halls': [{'name': SIDE_HALL,
               'devices': {SIDE_SWITCH: (35, 30), 'ap-10': (75, 30)},
               'blocks': [{'name': SIDE_BLOCK, 'x': 50, 'y': 55, 'cols': SIDE_COLS, 'rows': SIDE_ROWS}]}],
    # Two boards, one 16 A circuit per seat row (phases in turn) and one for the network rack.
    'power': {
        'boards': [{'name': 'DB-1', 'location': T['board_west'], 'x': 4, 'y': 42},
                   {'name': 'DB-2', 'location': T['board_east'], 'x': 96, 'y': 78}],
        'circuits': [{'board': 'DB-1' if b in 'AB' else 'DB-2', 'name': T['row'].format(b, r), 'rating_a': 16,
                      'phase': ('L1', 'L2', 'L3')[(BLOCKS.index(b) * ROWS + r - 1) % 3],
                      'meter': f'{b.lower()}{r}', 'block': b, 'rows': [r]}
                     for b in BLOCKS for r in range(1, ROWS + 1)]
        + [{'board': 'DB-1', 'name': T['rack'], 'rating_a': 32, 'phase': '3P', 'meter': 'rack',
            'switches': ['core-01', 'dist-01', 'dist-02']}],
    },
    # The seats are spread over 192.0.2.0 to .159 (see _ip): one /28 per firewall, the next one as its backup.
    'firewalls': [{'cidr': f'192.0.2.{16 * i}/28', 'name': T['range'].format(i + 1),
                   'firewalls': [fw, FIREWALLS[(i + 1) % len(FIREWALLS)]]} for i, fw in enumerate(FIREWALLS)],
    # The internet lines on core-01's ISP ports. The probes to their far ends are answered by the demo
    # itself (Plugin.answer), so nothing is sent out.
    'uplinks': [{'name': T['isp'].format(chr(65 + i)), 'device': 'core-01', 'port': port,
                 'capacity_mbps': bps // 1_000_000, 'probe_host': f'203.0.113.{i + 1}', 'probe_port': 443}
                for i, (port, bps, _busy) in enumerate(ISP_PORTS)],
}

# The servers in the rack. The LAN cache box is also the hall's DNS server (it answers the game
# download names with itself); the second resolver is the provider's, for comparison.
LANCACHE, LANCACHE_IP = 'lancache-01', '198.51.100.53'
LAYOUT['resolvers'] = [{'name': T['lancache_dns'], 'address': LANCACHE_IP, 'lookup': 'lancache.steamcontent.com'},
                       {'name': T['provider_dns'], 'address': '203.0.113.53', 'lookup': 'example.com'}]
# Game servers with RCON. The second one stops answering two minutes in five, so alerts can be tried.
# Their RCON password is made up when the hall is laid out; the demo answers whatever is sent.
GAME_SERVERS = (
    {'name': 'CS2 #1', 'game': 'Counter-Strike 2', 'host': '198.51.100.60', 'port': 27015, 'query': 'a2s',
     'rcon_port': 27015, 'map': 'de_mirage', 'max_players': 10},
    {'name': 'CS2 #2', 'game': 'Counter-Strike 2', 'host': '198.51.100.61', 'port': 27015, 'query': 'a2s',
     'rcon_port': 27015, 'map': 'de_inferno', 'max_players': 10, 'flaky': True},
    {'name': 'Minecraft', 'game': 'Minecraft', 'host': '198.51.100.62', 'port': 25565, 'query': 'minecraft',
     'rcon_port': 25575, 'max_players': 40, 'version': '1.21'},
    {'name': 'Trackmania', 'game': 'Trackmania', 'host': '198.51.100.63', 'port': 2350, 'query': 'tcp'},
)
LAYOUT['game_servers'] = [{k: s[k] for k in ('name', 'game', 'host', 'port', 'query', 'rcon_port') if k in s}
                          for s in GAME_SERVERS]


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
    """[(seat, block, number, global index)] for every seat: the main hall's blocks, then the side hall's."""
    out = []
    for b, n_seats in [*((b, COLS * ROWS) for b in BLOCKS), (SIDE_BLOCK, SIDE_COLS * SIDE_ROWS)]:
        for n in range(1, n_seats + 1):
            out.append((f'{b}-{n}', b, n, len(out)))
    return out


def _taken(index):
    return index % 7 != 3          # a few empty seats, like any LAN


def _ip(index):
    # DHCP hands addresses out as players arrive, so neighbours rarely share a range: seat i is in
    # firewall range i mod 10 (each /28 of 192.0.2.0 to .159), and every firewall serves about 11 seats.
    return f'192.0.2.{16 * (index % len(FIREWALLS)) + index // len(FIREWALLS) + 1}'


def _mac(index):
    return f'02:00:00:00:{index // 256:02x}:{index % 256:02x}'


def _switch_for(block, number):
    if block == SIDE_BLOCK:
        return SIDE_SWITCH, f'Gi1/0/{number}'
    n = (number - 1) // SEATS_PER_SWITCH + 1
    return f'sw-{block.lower()}-{n:02d}', f'Gi1/0/{(number - 1) % SEATS_PER_SWITCH + 1}'


def _switches():
    """[(name, role, mgmt index)] for the core, distribution and access switches."""
    out = [('core-01', 'router', 1), ('dist-01', 'switch', 2), ('dist-02', 'switch', 3)]
    for b in BLOCKS:
        for n in range(1, SWITCHES_PER_BLOCK + 1):
            out.append((f'sw-{b.lower()}-{n:02d}', 'switch', len(out) + 1))
    out.append((SIDE_SWITCH, 'switch', len(out) + 1))
    return out


SLOW_UPLINK = 'sw-c-02'      # its 10G uplink came up at 1G: a wrong optic or cable


def _dist_of(name):
    # Each distribution switch serves its side of the hall: dist-01 the left blocks, dist-02 the right.
    return 'dist-01' if name[3] in 'ac' else 'dist-02'


def _uplinks():
    """[(switch, port, other switch, other port, bps, cable type)]: access to distribution on 10G
    multi-mode fiber, distribution to the core on 10G single-mode fiber, the core to each firewall
    on a 10G DAC in the rack (what LLDP would report, both ways)."""
    out = [('dist-01', DIST_UPLINK, 'core-01', 'Ethernet1/1', 10 * G, 'fiber-sm'),
           ('dist-02', DIST_UPLINK, 'core-01', 'Ethernet1/2', 10 * G, 'fiber-sm')]
    out += [('core-01', f'Ethernet1/{10 + i}', fw, 'ix0', 10 * G, 'dac') for i, fw in enumerate(FIREWALLS, 1)]
    count = {'dist-01': 0, 'dist-02': 0}
    for name, _role, _i in _switches()[3:]:
        dist = _dist_of(name)
        count[dist] += 1
        out.append((name, ACCESS_UPLINK, dist, f'Te1/{count[dist]}', 10 * G, 'fiber-mm'))
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


def _platform(name):
    return 'NX-OS' if name == 'core-01' else 'IOS-XE' if name.startswith('dist-') else 'IOS'


def _model(name):
    if name.startswith('core'):
        return CORE_MODEL
    if name.startswith('fw-'):
        return FIREWALL_MODEL
    if name.startswith('ap-'):
        return AP_MODEL
    return DIST_MODEL if name.startswith('dist') else ACCESS_MODEL


def _hall(name):
    return SIDE_HALL if name in LAYOUT['halls'][0]['devices'] else MAIN_HALL


# The plan the crew would have drawn for this hall (floorbit/blueprints/demo.py seeds it once):
# - the uplinks with their cable type and planned speed (the topology and the plan's cables);
LAYOUT['links'] = [{'a': a, 'a_port': ap, 'b': b, 'b_port': bp, 'type': kind, 'speed': bps // G}
                   for a, ap, b, bp, bps, kind in _uplinks()]
# - block A's patch panel (the demo's imported cables run through it), on the wall above the block;
LAYOUT['patch_panels'] = [{'name': 'PP-A', 'x': 10, 'y': 34, 'ports': 24}]
# - two seat cables and one uplink routed by hand, with bends and round corners;
LAYOUT['cable_routes'] = {
    'lan:sw-b-03|Gi1/0/8': {'points': [[86, 33], [95.5, 33], [95.5, 45]], 'corners': 'round'},
    'lan:sw-d-01|Gi1/0/1': {'points': [[60, 70], [52, 70], [52, 76]], 'corners': 'square'},
}
# - rough port areas for the side hall's switch: two batches of eight ports, row by row;
LAYOUT['port_areas'] = [{'switch': SIDE_SWITCH, 'starts': [f'{SIDE_BLOCK}-1', f'{SIDE_BLOCK}-9'], 'size': 8}]
# - labels, walls, zones and icons on their layers (escape routes on safety, the rack on network);
LAYOUT['marks'] = [
    {'kind': 'zone', 'x': 40, 'y': 50, 'w': 20, 'h': 14, 'label': T['stage'], 'color': 'trace'},
    {'kind': 'zone', 'x': 44, 'y': 2, 'w': 12, 'h': 10, 'label': T['rack'], 'color': 'bit',
     'layer': 'network'},
    {'kind': 'icon', 'icon': 'server', 'x': 57, 'y': 8, 'layer': 'network'},
    {'kind': 'icon', 'icon': 'power', 'x': 4, 'y': 48, 'layer': 'electrical'},
    {'kind': 'icon', 'icon': 'socket', 'x': 96, 'y': 84, 'layer': 'electrical'},
    {'kind': 'wall', 'x': 1, 'y': 1, 'x2': 99, 'y2': 1},
    {'kind': 'wall', 'x': 1, 'y': 99, 'x2': 40, 'y2': 99},
    {'kind': 'wall', 'x': 60, 'y': 99, 'x2': 99, 'y2': 99},
    {'kind': 'wall', 'x': 40, 'y': 99, 'x2': 60, 'y2': 99, 'style': 'dashed'},
    {'kind': 'icon', 'icon': 'exit', 'x': 50, 'y': 96, 'layer': 'safety'},
    {'kind': 'icon', 'icon': 'escape', 'x': 2, 'y': 70, 'layer': 'safety'},
    {'kind': 'icon', 'icon': 'extinguisher', 'x': 98, 'y': 60, 'layer': 'safety'},
    {'kind': 'icon', 'icon': 'first-aid', 'x': 98, 'y': 8, 'layer': 'safety'},
    {'kind': 'icon', 'icon': 'bar', 'x': 4, 'y': 8},
    {'kind': 'icon', 'icon': 'wc', 'x': 4, 'y': 92},
    {'kind': 'icon', 'icon': 'info', 'x': 94, 'y': 92},
    {'kind': 'text', 'text': T['entrance'], 'x': 50, 'y': 92, 'size': 's'},
]
LAYOUT['halls'][0]['marks'] = [
    {'kind': 'text', 'text': SIDE_HALL, 'x': 50, 'y': 10, 'size': 'l'},
    {'kind': 'icon', 'icon': 'exit', 'x': 95, 'y': 90, 'layer': 'safety'},
    {'kind': 'icon', 'icon': 'coffee', 'x': 10, 'y': 85},
]
# - each block grouped with its switches (and block A with its patch panel), so they move as one.
LAYOUT['groups'] = [{'name': T['block'].format(b), 'block': b,
                     'switches': [f'sw-{b.lower()}-{n:02d}' for n in range(1, SWITCHES_PER_BLOCK + 1)],
                     'panels': ['PP-A'] if b == 'A' else []} for b in BLOCKS]


def _short(hostname):
    return (hostname or '').lower().split('.')[0]


def _rcon_answer(server, command, info, now):
    """A made-up answer in the style of the server's game, from the same player count the query shows."""
    words = command.split()
    first = words[0].lower() if words else ''
    rest = ' '.join(words[1:])
    k = GAME_SERVERS.index(server)
    nicks = [f'player-{(k * 13 + n * 7) % 96 + 1:02d}' for n in range(info.get('players') or 0)]
    if server['query'] == 'minecraft':
        if first == 'list':
            return (f"There are {len(nicks)} of a max of {server['max_players']} players online: "
                    + ', '.join(nicks))
        if first in ('say', 'tellraw', 'title'):
            return ''
        if first == 'time' and rest:
            return f'Set the time to {words[-1]}'
        if first == 'kick' and rest:
            return f'Kicked {words[1]}: Kicked by an operator'
        if first == 'tps':
            return 'TPS from last 1m, 5m, 15m: 20.0, 20.0, 19.98'
        return f'Unknown or incomplete command, see below for error\n{command}<--[HERE]'
    if first == 'status':
        rows = [f"hostname: {server['name']} (demo)", "version : 1.40.4.1 secure", f"map     : {info.get('map')}",
                f"players : {len(nicks)} humans, 0 bots ({server['max_players']} max)", '',
                '# userid name                uniqueid            connected ping state']
        rows += [f'# {n + 2:>6} "{nick}"{" " * (18 - len(nick))} [U:1:{100000 + n}]   '
                 f'{int(now // 60) % 50 + n:02d}:{n * 7 % 60:02d}    {12 + n * 3 % 20:>4} active'
                 for n, nick in enumerate(nicks)]
        return '\n'.join(rows)
    if first in ('changelevel', 'map') and rest:
        return f'Changing level to {words[1]}...'
    if first == 'say':
        return f'Console: {rest}'
    if first in ('kick', 'kickid') and rest:
        return f'Kicked {words[1]} from the server'
    if first == 'mp_restartgame':
        return 'Restarting the game...'
    return f'Unknown command "{first}"'


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
        aps = [{'id': name, 'name': name, 'role': 'access-point', 'model': AP_MODEL, 'serial': f'DEMOAP{i:03d}',
                'mgmt_ip': f'198.51.100.{100 + i}', 'hall': _hall(name), 'status': 'active'}
               for i, (name, _pos, _ch) in enumerate(APS, 1)]
        return [{'id': name, 'name': name, 'role': role, 'model': _model(name),
                 'serial': f'DEMO{i:05d}', 'mgmt_ip': f'198.51.100.{i}', 'hall': _hall(name),
                 'status': 'active', 'platform': _platform(name)} for name, role, i in _switches()] + aps + [
            {'id': name, 'name': name, 'role': 'firewall', 'model': FIREWALL_MODEL, 'serial': f'DEMOFW{i:03d}',
             'mgmt_ip': f'198.51.100.{200 + i}', 'hall': MAIN_HALL, 'status': 'active', 'platform': 'OPNsense'}
            for i, name in enumerate(FIREWALLS, 1)] + [
            {'id': LANCACHE, 'name': LANCACHE, 'role': 'server', 'model': 'LAN cache and DNS server',
             'serial': 'DEMOSRV001', 'mgmt_ip': LANCACHE_IP, 'hall': MAIN_HALL, 'status': 'active'}]

    # wifi -------------------------------------------------------------------------------
    def wifi_aps(self):
        out = []
        for i, (name, _pos, (ch24, ch5)) in enumerate(APS):
            busy = name == CROWDED_AP
            load = 0.8 + 0.2 * _wave(i, period=600) if busy else 0.15 + 0.45 * _wave(i, period=900)
            n24, n5 = round(4 + 10 * load), round(8 + (40 if busy else 30) * load)
            out.append({'name': name, 'model': AP_MODEL, 'status': 'up',
                        'radios': ([{'band': '2.4', 'channel': ch24, 'width': 20,
                                     'utilization': round(30 + 55 * load), 'clients': n24}] if ch24 else [])
                        + [{'band': '5', 'channel': ch5, 'width': 80, 'utilization': round(10 + 75 * load),
                            'clients': n5}]})
        return out

    def cables(self):
        # The first block's seats run through a patch panel, the rest go straight to the switch. The
        # side hall's patching was never written down: its seats have none (port areas only).
        out = []
        for seat, block, number, _i in _seats():
            if block == SIDE_BLOCK:
                continue
            switch, port = _switch_for(block, number)
            panel = f'PP-{block}' if block == BLOCKS[0] else ''
            out.append({'label': f'NB-{seat}', 'switch': switch, 'port': port, 'panel': panel,
                        'panel_port': str(number) if panel else '', 'seat': seat, 'color': 'blue',
                        'length_m': 5 if panel else 10, 'type': 'cat6a' if panel else 'cat6', 'speed': 1})
        return out

    # seat mapping -----------------------------------------------------------------------
    def seat_mapping(self):
        # Every seat has its port (the key); only a taken seat has a machine, so an IP and MAC. The side
        # hall's ports aren't known yet: its seats have an IP and MAC as a hint only.
        out = {seat: (dict(zip(('switch', 'port'), _switch_for(b, n), strict=True)) if b != SIDE_BLOCK else {})
               for seat, b, n, _i in _seats()}
        for seat, _b, _n, i in _seats():
            if _taken(i):
                out[seat].update(ip=_ip(i), mac=_mac(i), nick=f'player-{i + 1:02d}')
        return out

    # monitoring -------------------------------------------------------------------------
    def configured(self):
        return True

    def devices(self):
        return [{'display': name, 'hostname': f'{name}.{DOMAIN}', 'sysName': name,
                 'status': 0 if _down(name) else 1, 'status_reason': 'icmp' if _down(name) else ''}
                for name, _role, _i in _switches()] + [
            {'display': name, 'hostname': f'{name}.{DOMAIN}', 'sysName': name, 'status': 1, 'status_reason': ''}
            for name, _pos, _ch in APS] + [
            {'display': name, 'hostname': f'{name}.{DOMAIN}', 'sysName': name, 'status': int(name != DOWN_FIREWALL),
             'status_reason': 'icmp' if name == DOWN_FIREWALL else ''} for name in FIREWALLS] + [
            {'display': LANCACHE, 'hostname': f'{LANCACHE}.{DOMAIN}', 'sysName': LANCACHE, 'status': 1,
             'status_reason': ''}]

    def device_details(self, hostname):
        name = _short(hostname)
        found = next(((n, i) for n, _r, i in _switches() if n == name), None)
        ap = next((i for i, (n, _p, _c) in enumerate(APS, 1) if n == name), None)
        if ap:
            return {'status': 'online', 'hostname': hostname, 'ip': f'198.51.100.{100 + ap}',
                    'cpu_load': round(10 + 20 * _wave(ap)), 'total_ports': 1, 'up_ports': 1}
        if not found:
            return {'status': 'unknown', 'hostname': hostname}
        name, i = found
        if _down(name):
            return {'status': 'offline', 'hostname': hostname, 'ip': f'198.51.100.{i}'}
        players = [idx for _s, b, n, idx in _seats() if _switch_for(b, n)[0] == name and _taken(idx)]
        ports = PORTS[_model(name)]
        traffic = sum(sum(self._rates(idx)) for idx in players) * 8
        return {'status': 'online', 'hostname': hostname, 'ip': f'198.51.100.{i}',
                'cpu_load': round(8 + 30 * _wave(i)), 'mem_percent': round(35 + 15 * _wave(i + 3, period=900)),
                'temperature': round(38 + 8 * _wave(i, period=1200), 1),
                'total_ports': len(ports), 'up_ports': len(players) + 2, 'total_traffic_bps': round(traffic),
                'traffic_util': round(100 * traffic / sum(b for _p, b in ports), 1)}

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
               'poll_time': int(time.time()), 'ifAlias': '' if block == SIDE_BLOCK else f'Seat {block}-{number}'}
        out = summarize_port(raw)
        if flapping:
            out['last_change'] = int(time.time() // 45) * 45
        return out

    def device_ports(self, hostname):
        """Every port the switch's model has, in its order: seat ports as ``port_stats`` reads them,
        the uplinks and internet lines, and the rest down with nothing plugged in."""
        name = _short(hostname)
        model = _model(name)
        if model not in PORTS or not any(n == name for n, _r, _i in _switches()):
            return []
        seat_ports = {port for _s, b, n, _i in _seats() for sw, port in [_switch_for(b, n)] if sw == name}
        seats = [{'name': port, **(self.port_stats(hostname, port) or {})} for port, _bps in PORTS[model]
                 if port in seat_ports]
        special = {}
        for a, a_port, b, b_port, bps, _kind in _uplinks():
            for me, port, other in ((a, a_port, b), (b, b_port, a)):
                if me != name:
                    continue
                # One access uplink came up at 1G, so the topology has something to show.
                slow = SLOW_UPLINK in (name, other)
                state = 'down' if _down(name) or _down(other) or other == DOWN_FIREWALL else 'up'
                entry = {'name': port, 'state': state, 'description': f'Uplink to {other}' if port == ACCESS_UPLINK
                         else f'Link to {other}', 'duplex': 'full', 'speed_bps': G if slow else bps,
                         'errors_in': 0, 'errors_out': 0, 'last_change': None}
                if port == ACCESS_UPLINK and state == 'up':
                    # Everything the access switch's seats send and get.
                    down = sum(p.get('download_bps') or 0 for p in seats)
                    up = sum(p.get('upload_bps') or 0 for p in seats)
                    entry.update(download_bps=up, upload_bps=down,
                                 utilization=round(max(down, up) / entry['speed_bps'], 4))
                special[port] = entry
        if name == 'core-01':
            for i, (port, bps, busy) in enumerate(ISP_PORTS):
                load = busy * (0.7 + 0.6 * _wave(40 + i))
                special[port] = {'name': port, 'state': 'up', 'description': f'Internet line {i + 1}',
                                 'duplex': 'full', 'speed_bps': bps, 'upload_bps': round(bps * load),
                                 'download_bps': round(bps * load * 0.12),
                                 'utilization': round(load, 4), 'errors_in': 0, 'errors_out': 0, 'last_change': None}
        if name == CREW_LAPTOP[0] and not _down(name):
            special[CREW_LAPTOP[1]] = {'name': CREW_LAPTOP[1], 'state': 'up', 'description': '', 'duplex': 'full',
                                       'speed_bps': G, 'download_bps': 120_000, 'upload_bps': 40_000,
                                       'utilization': 0.0002, 'errors_in': 0, 'errors_out': 0, 'last_change': None}
        by_name = {p['name']: p for p in seats}
        out = []
        for port, bps in PORTS[model]:
            found = by_name.get(port) or special.get(port)
            out.append(found or {'name': port, 'state': 'down', 'description': '', 'duplex': None, 'speed_bps': bps,
                                 'download_bps': 0, 'upload_bps': 0, 'utilization': None, 'errors_in': 0,
                                 'errors_out': 0, 'last_change': None})
        return out

    def neighbours(self, hostname):
        name = _short(hostname)
        out = []
        for a, a_port, b, b_port, _bps, _kind in _uplinks():
            if a == name:
                out.append({'port': a_port, 'remote': b, 'remote_port': b_port, 'protocol': 'lldp'})
            elif b == name:
                out.append({'port': b_port, 'remote': a, 'remote_port': a_port, 'protocol': 'lldp'})
        return out

    def port_clients(self, hostname):
        name = _short(hostname)
        if _down(name):
            raise PluginError(f'{name} is not answering')
        where = {(b, n): i for _s, b, n, i in _seats()}
        swap = {SWAPPED[0]: SWAPPED[1], SWAPPED[1]: SWAPPED[0]}
        out = []
        for _s, block, number, i in _seats():
            switch, port = _switch_for(block, number)
            if switch != name:
                continue
            machine = where.get(swap.get((block, number)), i)
            if _taken(machine):
                out.append({'port': port, 'mac': _mac(machine), 'vlan': 100})
        if out:
            # The uplink sees every MAC behind it.
            out += [{'port': ACCESS_UPLINK, 'mac': f'02:00:00:01:00:{n:02x}', 'vlan': 100} for n in range(12)]
        if name == CREW_LAPTOP[0]:
            out.append({'port': CREW_LAPTOP[1], 'mac': '02:00:00:02:00:01', 'vlan': 100})
        return out

    def arp(self, query):
        q = (query or '').lower()
        try:
            net = ipaddress.ip_network(q) if '/' in q else None
        except ValueError:
            net = None
        rows = [{'ipv4_address': _ip(i), 'mac_address': _mac(i), 'hostname': f'core-01.{DOMAIN}'}
                for _s, _b, _n, i in _seats() if _taken(i)]
        rows.append({'ipv4_address': '192.0.2.250', 'mac_address': '02:00:00:02:00:01',
                     'hostname': f'core-01.{DOMAIN}'})
        if net is not None:
            return [r for r in rows if ipaddress.ip_address(r['ipv4_address']) in net]
        return [r for r in rows if q in (r['ipv4_address'], r['mac_address'])]

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
            elif words[:3] == ['show', 'ip', 'arp']:
                parts.append(self._demo_arp(name, words[3] if len(words) > 3 else None))
            elif 'mac' in command:
                address = words[words.index('address') + 1] if 'address' in words[:-1] else None
                parts.append(self._demo_macs(name, port, address))
            elif words[:2] == ['show', 'interfaces'] and 'status' in words:
                parts.append(self._demo_status(name))
            elif 'errors' in words:
                parts.append(self._demo_errors(name))
            elif words[:2] == ['show', 'interface'] and port:
                parts.append(self._demo_interface(name, port))
            elif words[:2] == ['show', 'running-config']:
                parts.append(self._demo_config(name))
            elif words[:2] == ['show', 'version']:
                parts.append(f'Cisco IOS Software, Version 15.2(7)E (demo)\n{name} uptime is 3 days, 4 hours\n'
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

    def _demo_config(self, name):
        """A made-up IOS running config: ports shut from Floorbit show up as shutdown."""
        lines = ['Building configuration...', '', 'Current configuration : 4211 bytes', '!',
                 f'! Last configuration change at {time.strftime("%H:%M:%S UTC %a %b %d %Y", time.gmtime())}',
                 'version 15.2', f'hostname {name}', '!',
                 'enable secret 9 $9$demo.example.hash', 'username netops privilege 15 secret 9 $9$demo.example.hash',
                 '!', 'vlan 100', ' name players', 'vlan 999', ' name mgmt', '!']
        for seat, _b, _n, _i, port in self._demo_ports(name):
            lines += [f'interface {port}', f' description Seat {seat}', ' switchport access vlan 100',
                      ' switchport mode access', ' spanning-tree portfast', ' spanning-tree bpduguard enable']
            if (name, port) in _shut:
                lines.append(' shutdown')
            lines.append('!')
        lines += ['snmp-server community demo-read-only RO', 'logging host 198.51.100.250', 'ntp server 198.51.100.1',
                  'end']
        return '\n'.join(lines)

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

    def _demo_arp(self, name, ip):
        """The core holds the hall's ARP table (seat walk-through, floorbit/seat_walk.py)."""
        rows = ['Protocol  Address          Age (min)  Hardware Addr   Type   Interface']
        if name == 'core-01':
            for _seat, _b, _n, i in _seats():
                if _taken(i) and (not ip or _ip(i) == ip):
                    mac = _mac(i).replace(':', '')
                    rows.append(f'Internet  {_ip(i):<16} 0          {mac[0:4]}.{mac[4:8]}.{mac[8:12]}  ARPA   Vlan100')
        return '\n'.join(rows)

    def _demo_macs(self, name, port, address=None):
        rows = ['          Mac Address Table', '-------------------------------------------',
                'Vlan    Mac Address       Type        Ports', '----    -----------       --------    -----']
        want = address.replace('.', '').lower() if address else None
        for _seat, _b, _n, i, p in self._demo_ports(name):
            if _taken(i) and (not port or p.lower() == port.lower()):
                mac = _mac(i).replace(':', '')
                if want and mac != want:
                    continue
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
             'title': 'Broadcast storm on sw-d-02', 'switch': 'sw-d-02', 'port': ACCESS_UPLINK,
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
        # The DHCP scopes and the LAN cache. The resolvers, internet lines and game servers have tiles
        # of their own (floorbit/services.py, floorbit/game_servers.py), answered by Plugin.answer.
        now = time.time()
        players = sum(_taken(s[3]) for s in _seats())
        left = DHCP_POOL - players
        hit = round(62 + 28 * _wave(1, now, period=600))
        saved = round(40 + (now % 86400) / 86400 * 900 * _wave(2, now, period=3600), 1)
        return [
            {'id': 'dhcp-players', 'name': 'DHCP players', 'kind': 'dhcp', 'link': '/dashboard',
             'status': _level(left / DHCP_POOL, warn=0.25, down=0.05, higher_is_better=True),
             'summary': f'{left} of {DHCP_POOL} leases left',
             'metrics': [{'label': 'Leases left', 'value': left}, {'label': 'In use', 'value': players}]},
            {'id': 'dhcp-staff', 'name': 'DHCP staff', 'kind': 'dhcp', 'status': 'up',
             'summary': '52 of 64 leases left', 'metrics': [{'label': 'Leases left', 'value': 52}]},
            {'id': 'cache', 'name': 'LAN cache', 'kind': 'cache',
             'status': _level(hit / 100, warn=0.5, down=0.2, higher_is_better=True),
             'summary': f'{hit} % hit rate, {saved} GB saved',
             'metrics': [{'label': 'Hit rate', 'value': hit, 'unit': '%'},
                         {'label': 'Saved', 'value': saved, 'unit': 'GB'}]},
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

    # servers and services (probes, game servers, RCON) ---------------------------------
    @staticmethod
    def _site_answer(host, now):
        """The usual internet sites (floorbit/services.py COMMON_SITES) as seen from the hall: one of
        them gets slow three minutes in ten, so the sites tile has something to say."""
        from floorbit import services
        hosts = [h for _name, h in services.COMMON_SITES]
        if host not in hosts:
            return None
        k = hosts.index(host)
        avg = round(5 + 3 * (k % 4) + 4 * _wave(90 + k, now, period=300), 1)
        if k == 7 and int(now // 60) % 10 < 3:
            avg = round(170 + 30 * _wave(99, now, period=60), 1)
        return {'sent': 3, 'lost': 0, 'avg_ms': avg}

    def answer(self, method, args):
        """What the demo's made-up servers answer to a probe, a game query or an RCON command, so the
        services and game servers pages work without sending anything out. None for any other host:
        that one is asked for real."""
        now = time.time()
        if method == 'dns_probe':
            server, name = args[0], args[1]
            found = next((r for r in LAYOUT['resolvers'] if r['address'] == server), None)
            if found is None:
                return None
            fast = found['address'] == LANCACHE_IP
            ms = round((1.5 if fast else 9) + (3 if fast else 14) * _wave(50 + fast, now, period=180), 1)
            return {'ms': ms, 'rcode': 'NOERROR', 'answers': 1 if fast else 2, 'name': name}
        if method == 'tcp_probe':
            host = args[0]
            line = next((u for u in LAYOUT['uplinks'] if u['probe_host'] == host), None)
            if line is None:
                return self._site_answer(host, now)
            k = LAYOUT['uplinks'].index(line)
            avg = round(8 + 4 * k + 6 * _wave(60 + k, now, period=240), 1)
            return {'sent': 5, 'lost': 1 if k == 1 and int(now // 60) % 9 == 0 else 0, 'avg_ms': avg}
        if method == 'game_query':
            host, port = args[1], int(args[2])
            server = next((s for s in GAME_SERVERS if (s['host'], s['port']) == (host, port)), None)
            if server is None:
                return None
            from floorbit.game_query import QueryError
            if server.get('flaky') and int(now // 60) % 5 < 2:      # two minutes in five, so alerts can be tried
                raise QueryError('No answer to the server query.')
            k = GAME_SERVERS.index(server)
            if server['query'] == 'tcp':
                return {'ping_ms': round(1 + 2 * _wave(80 + k, now, period=60), 1)}
            top = server['max_players']
            players = min(top, round(top * (0.45 + 0.5 * _wave(70 + k, now, period=900))))
            return {'name': server['name'], 'map': server.get('map', ''), 'game': server['game'],
                    'version': server.get('version', ''), 'players': players, 'max_players': top, 'bots': 0,
                    'ping_ms': round(1 + 2 * _wave(80 + k, now, period=60), 1)}
        if method == 'game_rcon':
            host, port, _password, command = args[0], int(args[1]), args[2], str(args[3])
            server = next((s for s in GAME_SERVERS if (s['host'], s.get('rcon_port')) == (host, port)), None)
            if server is None:
                return None
            return _rcon_answer(server, command, self.answer('game_query', ('', server['host'], server['port'])), now)
        return None

    def test(self):
        return f'Demo data: {len(_switches())} switches and {sum(_taken(s[3]) for s in _seats())} players.'
