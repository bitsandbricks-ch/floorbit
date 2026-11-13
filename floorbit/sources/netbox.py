"""NetBox: the switch inventory (devices with the configured roles)."""
import requests

from ..runtime import rt


def fetch_netbox_devices():
    """Fetch all devices with the configured role from NetBox (handles pagination)."""
    headers = {
        'Authorization': f'Token {rt.netbox_token}',
        'Accept': 'application/json',
    }
    devices = []
    url = f'{rt.netbox_url}/api/dcim/devices/'
    params = {'role': rt.netbox_roles, 'limit': 500}
    while url:
        resp = requests.get(url, headers=headers, params=params,
                            timeout=15, verify=rt.netbox_verify_ssl)
        resp.raise_for_status()
        payload = resp.json()
        for d in payload.get('results', []):
            devices.append({
                'id':            str(d['id']),
                'name':          d['name'],
                'netbox_status': d.get('status', {}).get('value', 'unknown'),
            })
        url = payload.get('next')
        params = {}   # next URL already includes all query params
    return devices


def merge_devices_with_positions(cached_devices, positions):
    """Combine cached NetBox devices with locally stored floor-plan positions."""
    result = []
    for dev in cached_devices:
        pos = positions.get(dev['id'])
        result.append({
            'id':            dev['id'],
            'name':          dev['name'],
            'netbox_status': dev.get('netbox_status', 'unknown'),
            'x':             pos['x'] if pos else None,
            'y':             pos['y'] if pos else None,
            'placed':        pos is not None,
            'status':        'unknown',
        })
    return result
