"""Find a player by nick, seat, IP or MAC and say where they sit (issue #14).

The seat sources (hand mapping, seats.json, check-ins, plugins) answer nicks, seats and the IPs and
MACs they know. A full IP or MAC that no source knows is looked up in the monitoring source's ARP
data (IP to MAC and back), and for an IP or MAC query the seat's switch port is resolved too, so the
floor plan can light up both. Results name people, so the route needs ``seats.view``.
"""
import ipaddress

from integrations import seat_sources

from . import inventory, sources
from .power import block_rows
from .seatmap import MappingError, clean_mac
from .store import load_data

LIMIT = 10


def kind_of(query):
    q = query.strip()
    try:
        ipaddress.ip_address(q)
        return 'ip', q
    except ValueError:
        pass
    try:
        return 'mac', clean_mac(q)
    except MappingError:
        return 'text', q.lower()


def _mac_of(info):
    try:
        return clean_mac(info.get('mac_address') or info.get('mac') or '')
    except MappingError:
        return ''


def _seat_blocks(data):
    where = {}
    for block in data.get('seat_blocks') or []:
        for row in block_rows(block):
            for seat in row:
                where[seat] = block['id']
    return where


def _switch_id(data, hostname):
    if not hostname:
        return None
    name = str(hostname).lower()
    short = name.split('.')[0]   # LibreNMS hostnames often carry the domain, inventory names don't
    for dev in inventory.devices(data):
        if str(dev.get('name') or '').lower() in (name, short):
            return dev['id']
    return None


def find(query):
    query = (query or '').strip()
    if len(query) < 2:
        return {'query': query, 'kind': 'text', 'results': []}
    kind, needle = kind_of(query)
    seats = seat_sources.load()
    monitor = sources.monitoring()
    looked_up = None   # the other address of the pair, from ARP

    def entry(seat, info, matched):
        return {'seat': seat, 'username': info.get('username') or '', 'ip': info.get('ip_address') or '',
                'mac': _mac_of(info), 'matched': matched}

    hits = []
    if kind == 'ip':
        hits = [entry(s, i, 'ip') for s, i in seats.items() if (i or {}).get('ip_address') == needle]
        if not hits and monitor.enabled():
            looked_up = monitor.mac_for_ip(needle)
            mac = _mac_of({'mac': looked_up}) if looked_up else ''
            hits = [entry(s, i, 'mac') for s, i in seats.items() if mac and _mac_of(i or {}) == mac]
    elif kind == 'mac':
        hits = [entry(s, i, 'mac') for s, i in seats.items() if _mac_of(i or {}) == needle]
        if not hits and monitor.enabled():
            looked_up = monitor.ip_for_mac(needle)
            hits = [entry(s, i, 'ip') for s, i in seats.items()
                    if looked_up and (i or {}).get('ip_address') == looked_up]
    else:
        for seat, info in seats.items():
            info = info or {}
            if needle in str(info.get('username') or '').lower():
                hits.append(entry(seat, info, 'nick'))
            elif needle in seat.lower():
                hits.append(entry(seat, info, 'seat'))
        hits.sort(key=lambda h: (h['matched'] != 'nick', h['seat']))

    data = load_data()
    blocks = _seat_blocks(data)
    results = []
    for hit in hits[:LIMIT]:
        hit['block_id'] = blocks.get(hit['seat'])
        if kind != 'text' and monitor.enabled():
            ip = hit['ip'] or (needle if kind == 'ip' else looked_up)
            if not ip and hit['mac']:
                ip = looked_up = monitor.ip_for_mac(hit['mac'])   # known to the seat sources by MAC only
            port = monitor.resolve_ip(ip) if ip else None
            if port:
                hit['switch'] = port.get('device_name') or port.get('hostname')
                hit['port'] = port.get('port')
                hit['switch_id'] = _switch_id(data, hit['switch'])
        results.append(hit)
    if not results and kind != 'text' and monitor.enabled():
        # Nobody sits there by the seat sources, but the address is plugged in somewhere.
        ip = needle if kind == 'ip' else looked_up
        port = monitor.resolve_ip(ip) if ip else None
        if port and port.get('port'):
            switch = port.get('device_name') or port.get('hostname')
            results.append({'seat': None, 'username': '', 'ip': ip or '', 'mac': port.get('mac') or '',
                            'matched': kind, 'block_id': None, 'switch': switch, 'port': port.get('port'),
                            'switch_id': _switch_id(data, switch)})
    out = {'query': query, 'kind': kind, 'results': results}
    if looked_up:
        out['arp'] = looked_up
    return out
