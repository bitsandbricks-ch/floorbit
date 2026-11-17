"""Per-seat switch port throughput for the seat level of the traffic heatmap.

Each seat needs its own LibreNMS lookups (ARP, FDB, the port row), so doing
them one after another makes /api/seats/heatmap take seconds per hundred seats.
They are independent, so they run in a small thread pool instead.
"""

from concurrent.futures import ThreadPoolExecutor

# Enough to hide LibreNMS latency without flooding it with requests.
MAX_WORKERS = 8


def _by_port(seat_info, port_stats):
    """The seat's switch and port are the mapping (docs/seat-mapping.md): read that port, no IP needed."""
    switch, port = seat_info['switch'], seat_info['port']
    stats = port_stats(switch, port)
    if not stats:     # some sources answer {} for a port they don't know
        return None
    mac = seat_info.get('mac_address') or seat_info.get('mac')
    return {'stats': stats, 'device_name': switch, 'port': port, 'vlan': None, 'mac': mac}


def seat_port_usage(seat_info, resolve, port_stats=None):
    """Heatmap entry for one seat. Its mapped switch port when it has one (``port_stats(switch,
    port)``), else where its IP is seen (``resolve(ip)``, resolve_ip_to_switch_port). The IP and
    MAC are optional extras."""
    username = seat_info.get('username')
    ip_address = seat_info.get('ip_address')
    by_port = bool(port_stats and seat_info.get('switch') and seat_info.get('port'))
    if not by_port and not ip_address:
        return {'username': username, 'ip_address': None, 'resolved': False,
                'port_usage': None, 'error': 'No switch port or IP address'}

    try:
        result = _by_port(seat_info, port_stats) if by_port else resolve(ip_address)
        if by_port and result is None and ip_address:
            result = resolve(ip_address)     # the port isn't known to monitoring: try where the IP is
    except Exception as exc:  # noqa: BLE001 - one bad seat must not fail the whole map
        return {'username': username, 'ip_address': ip_address, 'resolved': False,
                'port_usage': None, 'error': f'Lookup failed: {exc}'}

    if not result or 'stats' not in result:
        return {'username': username, 'ip_address': ip_address, 'resolved': False,
                'port_usage': None, 'error': 'Could not resolve port stats'}

    stats = result['stats'] or {}
    in_rate = float(stats.get('ifInOctets_rate') or 0)
    out_rate = float(stats.get('ifOutOctets_rate') or 0)
    return {
        'username': username,
        'ip_address': ip_address,
        'resolved': True,
        'port_usage': {
            'total_bps': (in_rate + out_rate) * 8,
            'in_rate_bps': in_rate * 8,
            'out_rate_bps': out_rate * 8,
            'status': stats.get('ifOperStatus', 'unknown'),
            'speed_bps': float(stats.get('ifSpeed') or 0),
        },
        'device_name': result.get('device_name'),
        'port': result.get('port'),
        'vlan': result.get('vlan'),
        'mac': result.get('mac'),
    }


def seat_resolution(seat_info, resolve):
    """/api/seats/resolve entry for one seat with an IP: its switch port, or why not."""
    base = {'username': seat_info.get('username'), 'ip_address': seat_info['ip_address']}
    try:
        result = resolve(seat_info['ip_address'])
    except Exception as exc:  # noqa: BLE001 - one bad seat must not fail the whole batch
        return {**base, 'resolved': False, 'error': f'Lookup failed: {exc}'}
    if not result:
        return {**base, 'resolved': False, 'error': 'Could not resolve'}
    return {**base, 'resolved': True, **result}


def _each_seat(seats, entry, max_workers):
    items = list(seats.items())
    if not items:
        return {}
    with ThreadPoolExecutor(max_workers=max(1, min(max_workers, len(items)))) as pool:
        entries = pool.map(lambda item: entry(item[1]), items)
        return {number: e for (number, _), e in zip(items, entries, strict=True)}


def collect_seat_heatmap(seats, resolve, max_workers=MAX_WORKERS, port_stats=None):
    """{seat_number: entry} for every seat in the mapping, looked up in parallel."""
    return _each_seat(seats, lambda info: seat_port_usage(info, resolve, port_stats), max_workers)


def resolve_seats(seats, resolve, max_workers=MAX_WORKERS):
    """{seat_number: entry} for the seats that have an IP, looked up in parallel (issue #198)."""
    with_ip = {n: info for n, info in seats.items() if (info or {}).get('ip_address')}
    return _each_seat(with_ip, lambda info: seat_resolution(info, resolve), max_workers)
