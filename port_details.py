"""One switch port as LibreNMS sees it, for the seat inspector and the seat heatmap.

The seat lookup finds the switch and port name for a seat (ARP, then FDB). This module reads that
port's row from LibreNMS and turns it into what the inspector shows: state, link speed, duplex,
traffic from the player's side, errors and load.
"""

import requests

# Columns the app has always asked for; every LibreNMS version has them.
BASE_COLUMNS = ['port_id', 'device_id', 'ifName', 'ifOperStatus', 'ifInOctets_rate', 'ifOutOctets_rate', 'ifSpeed']
# The extra detail. If LibreNMS rejects one of these, fetch_port() falls back to BASE_COLUMNS.
DETAIL_COLUMNS = BASE_COLUMNS + [
    'ifAlias', 'ifAdminStatus', 'ifDuplex', 'ifHighSpeed',
    'ifInErrors', 'ifOutErrors', 'ifInErrors_rate', 'ifOutErrors_rate', 'poll_time',
]

DUPLEX = {'fullDuplex': 'full', 'halfDuplex': 'half'}


def fetch_port(base_url, headers, device_id, ifname, verify=True, timeout=10):
    """Return the LibreNMS port row named ifname on device_id, or None."""
    resp = None
    for columns in (DETAIL_COLUMNS, BASE_COLUMNS):
        try:
            resp = requests.get(
                f'{base_url}/api/v0/devices/{device_id}/ports',
                headers=headers, timeout=timeout, verify=verify,
                params={'columns': ','.join(columns)},
            )
        except requests.RequestException:
            return None
        if resp.ok:
            break
    if resp is None or not resp.ok:
        return None
    for port in resp.json().get('ports', []):
        if port.get('ifName') == ifname:
            return port
    return None


def _num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def summarize_port(port, base_url='', device_id=None):
    """Raw counters plus the derived values the inspector shows.

    LibreNMS counts from the switch's side: ifIn is what the player sends (upload) and ifOut is
    what the switch sends to the player (download).
    """
    in_bps = (_num(port.get('ifInOctets_rate')) or 0) * 8
    out_bps = (_num(port.get('ifOutOctets_rate')) or 0) * 8

    # ifSpeed is a 32-bit gauge that tops out at ~4.29 Gbps; ifHighSpeed (Mbps) doesn't.
    speed = _num(port.get('ifSpeed')) or 0
    high_speed = _num(port.get('ifHighSpeed'))
    if high_speed and high_speed * 1e6 > speed:
        speed = high_speed * 1e6

    rates = [_num(port.get('ifInErrors_rate')), _num(port.get('ifOutErrors_rate'))]
    error_rate = sum(r for r in rates if r is not None) if any(r is not None for r in rates) else None

    oper = port.get('ifOperStatus')
    if port.get('ifAdminStatus') == 'down':
        state = 'disabled'
    elif not oper:
        state = 'unknown'
    elif oper != 'up':
        state = 'down'
    elif error_rate:
        state = 'errors'
    else:
        state = 'up'

    errors_in = _num(port.get('ifInErrors'))
    errors_out = _num(port.get('ifOutErrors'))
    port_id = port.get('port_id')
    device_id = port.get('device_id') or device_id

    return {
        # Kept as-is for the seat heatmap and older callers.
        'ifOperStatus': oper,
        'ifInOctets_rate': port.get('ifInOctets_rate'),
        'ifOutOctets_rate': port.get('ifOutOctets_rate'),
        'ifSpeed': port.get('ifSpeed'),
        'ifAdminStatus': port.get('ifAdminStatus'),
        'state': state,
        'description': (port.get('ifAlias') or '').strip() or None,
        'duplex': DUPLEX.get(port.get('ifDuplex')),
        'speed_bps': speed or None,
        'download_bps': out_bps,
        'upload_bps': in_bps,
        # Busiest direction against the link speed (the link is full duplex).
        'utilization': (round(min(1.0, max(in_bps, out_bps) / speed), 4)
                        if speed and state in ('up', 'errors') else None),
        'errors_in': int(errors_in) if errors_in is not None else None,
        'errors_out': int(errors_out) if errors_out is not None else None,
        'error_rate': round(error_rate, 3) if error_rate is not None else None,
        'polled_at': int(_num(port.get('poll_time'))) if _num(port.get('poll_time')) else None,
        'port_id': port_id,
        'librenms_url': (f'{base_url.rstrip("/")}/device/device={device_id}/tab=port/port={port_id}/'
                         if base_url and device_id and port_id else None),
    }
