"""LibreNMS: switch status and ports, and IP to switch port resolution (ARP, then FDB).

The LibreNMS plugin's API client (plugin.py wraps it). Nothing else in Floorbit talks to
LibreNMS: the core asks ``floorbit.sources.monitoring()``. Answers are cached in Redis (see
floorbit/cache.py) for the TTLs on the settings page.
"""
import json

import redis
import requests

from floorbit.cache import get_cached_arp, get_cached_mac, get_redis_client, set_cached_arp, set_cached_mac
from floorbit.runtime import rt

from . import ports as librenms_ports


def fetch_librenms_arp_by_ip(ip_address):
    """Fetch ARP entry for a specific IP address using the resources endpoint.

    Uses endpoint: /api/v0/resources/ip/arp/{ip_address}
    This is more efficient as it doesn't require device lookup.
    """
    headers = {
        'X-Auth-Token': rt.librenms_token,
        'Accept': 'application/json',
    }

    try:
        resp = requests.get(
            f'{rt.librenms_url}/api/v0/resources/ip/arp/{ip_address}',
            headers=headers,
            timeout=10, verify=rt.librenms_verify_ssl,
        )
        if resp.ok:
            arp_data = resp.json().get('arp', [])
            # Cache the result with IP as key for direct IP lookups
            client = get_redis_client()
            if client:
                try:
                    cache_key = f"arp_ip:{ip_address}"
                    client.setex(cache_key, rt.cache_ttl_arp, json.dumps(arp_data))
                    # print(f"ARP data cached for IP {ip_address}")
                    # print(f"Cached ARP entries for IP {ip_address}: {arp_data}")
                except redis.RedisError as e:
                    print(f"Redis cache write error (IP ARP): {e}")
            return arp_data
        else:
            print(f"Failed to fetch ARP for IP {ip_address}: {resp.status_code}")
    except requests.RequestException as e:
        print(f"Exception fetching ARP for IP {ip_address}: {e}")

    return None


def fetch_librenms_arp_table(hostname):
    """Fetch ARP table for a device from LibreNMS with Redis caching."""
    # Try to get from cache first
    cached = get_cached_arp(hostname)
    if cached is not None:
        # print(f"ARP cache hit for {hostname}")
        return cached

    headers = {
        'X-Auth-Token': rt.librenms_token,
        'Accept': 'application/json',
    }

    # First, get the device ID
    try:
        resp = requests.get(
            f'{rt.librenms_url}/api/v0/devices',
            headers=headers,
            params={'type': 'display', 'query': hostname},
            timeout=10, verify=rt.librenms_verify_ssl,
        )
        if not resp.ok:
            return []

        candidates = resp.json().get('devices', [])
        hn = hostname.lower()
        device = next(
            (d for d in candidates if d.get('display', '').lower() == hn),
            None,
        ) or next(
            (d for d in candidates if hn in d.get('hostname', '').lower()),
            None,
        )

        if not device:
            return []

        device_id = device.get('hostname') or device.get('device_id')
    except requests.RequestException:
        return []

    # Now fetch the ARP table
    arp_data = []
    try:
        resp = requests.get(
            f'{rt.librenms_url}/api/v0/devices/{device_id}/arp',
            headers=headers,
            timeout=10, verify=rt.librenms_verify_ssl,
        )
        if resp.ok:
            arp_data = resp.json().get('arp', [])
            # Cache the result
            set_cached_arp(hostname, arp_data)
            # print(f"ARP cache miss for {hostname} - fetched and cached")
    except requests.RequestException:
        pass

    return arp_data


def fetch_librenms_mac_table(hostname):
    """Fetch MAC address table (FDB) for a device from LibreNMS with Redis caching."""
    # Try to get from cache first
    cached = get_cached_mac(hostname)
    if cached is not None:
        # print(f"MAC cache hit for {hostname}")
        return cached

    headers = {
        'X-Auth-Token': rt.librenms_token,
        'Accept': 'application/json',
    }

    # First, get the device ID
    try:
        resp = requests.get(
            f'{rt.librenms_url}/api/v0/devices',
            headers=headers,
            params={'type': 'display', 'query': hostname},
            timeout=10, verify=rt.librenms_verify_ssl,
        )
        if not resp.ok:
            return []

        candidates = resp.json().get('devices', [])
        hn = hostname.lower()
        device = next(
            (d for d in candidates if d.get('display', '').lower() == hn),
            None,
        ) or next(
            (d for d in candidates if hn in d.get('hostname', '').lower()),
            None,
        )

        if not device:
            return []

        device_id = device.get('hostname') or device.get('device_id')
    except requests.RequestException:
        return []

    # Now fetch the MAC address table
    mac_data = []
    try:
        resp = requests.get(
            f'{rt.librenms_url}/api/v0/devices/{device_id}/fdb',
            headers=headers,
            timeout=10, verify=rt.librenms_verify_ssl,
        )
        if resp.ok:
            mac_data = resp.json().get('fdb', [])
            # Cache the result
            set_cached_mac(hostname, mac_data)
            # print(f"MAC cache miss for {hostname} - fetched and cached")
    except requests.RequestException:
        pass

    return mac_data


def find_mac_in_all_switches(mac_address):

    headers = {
        'X-Auth-Token': rt.librenms_token,
        'Accept': 'application/json',
    }

    # Normalize MAC address format
    mac_normalized = mac_address.lower().replace('-', ':')

    try:
        # Get all devices
        resp = requests.get(
            f'{rt.librenms_url}/api/v0/resources/fdb/{mac_normalized}/detail',
            headers=headers,
            timeout=10, verify=rt.librenms_verify_ssl,
        )

        if not resp.ok:
            return None

        # print(f"FDB search response for MAC {mac_address}: {resp.status_code}")

        ports = resp.json().get('ports_fdb', [])
        matches = {}
        for entry in ports:

            excludes = rt.librenms_fdb_exclude
            port_name = entry.get('ifName', '').lower()

            if any(ex in port_name for ex in excludes):
                # print(f"Skipping port {port_name} for MAC {mac_address} due to exclusion filter")
                continue

            hostname = entry.get('hostname', '').lower()
            int_id = f"{hostname}:{port_name}"
            matches[int_id] = entry

        if matches:

            # print(f"Found {len(matches)} matches for MAC {mac_address}: {matches}")
            # Return the first match with device and port info
            first = next(iter(matches.values()))
            # print(first)

            data = {
                'device_name': first.get('sysName', ''),
                'hostname': first.get('hostname', ''),
                'port': first.get('ifName', ''),
                'port_id': first.get('ifIndex', ''),
                'vlan': first.get('vlan', ''),
            }

            data.update(first)  # Include all original fields for debugging
            return data

    except requests.RequestException:
        pass

def resolve_ip_to_switch_port(ip_address, search_device=None):
    """Resolve an IP address to its switch and port using LibreNMS ARP and MAC tables.

    Uses the efficient /api/v0/resources/ip/arp/{ip_address} endpoint for ARP lookups.

    Args:
        ip_address: The IP address to resolve
        search_device: Optional hostname to limit ARP table search to a specific device

    Returns:
        Dictionary with ip, mac, device_name, port, vlan, or None if not found
    """
    result = {
        'ip': ip_address,
        'mac': None,
        'device_name': None,
        'hostname': None,
        'port': None,
        'vlan': None,
        'arp_source': None,
    }

    # Step 1: Find MAC address from ARP table using efficient IP-based endpoint
    # Check IP-based cache first
    client = get_redis_client()
    resolve_cache_key = f"resolve:{ip_address}"
    if client:
        cached = client.get(resolve_cache_key)
        if cached:
            cached_result = json.loads(cached)
            if cached_result.get('mac'):
                # print(f"Resolve cache hit for IP {ip_address}")
                stats = fetch_librenms_device_port_stats_by_interface(
                    cached_result.get('hostname'), cached_result.get('port'),
                )

                cached_result["stats"] = stats
                return cached_result

    if client:
        try:
            cache_key = f"arp_ip:{ip_address}"
            cached = client.get(cache_key)
            if cached:
                # Cast cached to proper type for json.loads
                cached_str = str(cached)
                arp_entries = json.loads(cached_str)
                # print(f"ARP IP cache hit for {ip_address}")
                # Find the MAC address for the IP
                # print(f"Cached ARP entries for IP {ip_address}: {arp_entries}")
                mac_address = None
                for entry in arp_entries:
                    if entry.get('ipv4_address') == ip_address:
                        mac_address = entry.get('mac_address')
                        break
                if mac_address:
                    result['mac'] = mac_address
                    result['arp_source'] = 'Redis cache (IP-based)'
        except (redis.RedisError, ValueError) as e:
            print(f"Redis cache read error (IP ARP): {e}")

    # If not in cache, fetch from LibreNMS
    if not result['mac']:
        # print(f"ARP IP cache miss for {ip_address}")
        arp_data = fetch_librenms_arp_by_ip(ip_address)
        if arp_data:
            # Find the MAC address for the IP
            mac_address = None
            for entry in arp_data:
                if entry.get('ipv4_address') == ip_address:
                    mac_address = entry.get('mac_address')
                    # Get source device from ARP entry if available
                    hostname = entry.get('hostname', entry.get('device', 'LibreNMS API'))
                    result['arp_source'] = hostname
                    break
            if mac_address:
                result['mac'] = mac_address

    if not result.get('mac'):
        return None

    # Step 2: Find the switch and port using MAC address
    switch_info = find_mac_in_all_switches(result['mac'])
    # print(f"Switch info found for MAC {result['mac']}: {switch_info}")
    if switch_info is not None:
        # print(f"Resolved IP {ip_address} to switch info: {switch_info}")
        result['device_name'] = switch_info.get('device_name')
        result['hostname'] = switch_info.get('hostname')
        result['port'] = switch_info.get('port')
        result['vlan'] = switch_info.get('vlan')

        result.update(switch_info)  # Include all original fields for debugging

        stats = fetch_librenms_device_port_stats_by_interface(switch_info.get('hostname'), switch_info.get('port'))

        result["stats"] = stats

    if client:
        try:
            client.setex(resolve_cache_key, rt.cache_ttl_resolve, json.dumps(result))
            # print(f"Resolve result cached for IP {ip_address}")
        except redis.RedisError as e:
            print(f"Redis cache write error (resolve): {e}")

    return result

def fetch_librenms_device_by_hostname(hostname, headers):
    device = None
    try:
        query = hostname.split('.')[0]  # Use short hostname for broader search
        resp = requests.get(
            f'{rt.librenms_url}/api/v0/devices',
            headers=headers,
            params={'type': 'display', 'query': query},
            timeout=10, verify=rt.librenms_verify_ssl,
        )
        # print(f"Device search response for hostname {hostname}: {resp.status_code}")
        if resp.ok:
            candidates = resp.json().get('devices', [])
            # print(f"Device search candidates for hostname {hostname}: {candidates}")
            hn = hostname.lower()
            # Prefer exact displayname match, fall back to partial

            for d in candidates:
                # print(f"Candidate device: display={d.get('display', '')}, hostname={d.get('hostname', '')}")
                if d.get('display', '').lower() == hn:
                    device = d
                    break
                if d.get('hostname', '').lower() == hn:
                    device = d
                    break

                if hn in d.get('display', '').lower() or hn in d.get('hostname', '').lower():
                    device = d  # Keep looking for better match, but remember this one

                short = hn.split('.')[0]
                if short in d.get('display', '').lower() or short in d.get('hostname', '').lower():
                    device = d  # Also consider short hostname matches

    except requests.RequestException:
        pass

    return device

def fetch_librenms_details(hostname):
    """Return a dict with status, ip, cpu_load, mem_percent, up_ports, total_ports.

    Searches LibreNMS by displayname so hostname mapping doesn't need to match exactly.
    """
    headers = {
        'X-Auth-Token': rt.librenms_token,
        'Accept': 'application/json',
    }
    result = {'status': 'unknown', 'hostname': hostname}

    # ── Find device by displayname ────────────────────────────────────────────
    device: dict | None = fetch_librenms_device_by_hostname(hostname, headers)

    # ── Extract device info ───────────────────────────────────────────────────
    if not device:
        return result   # not in LibreNMS: status stays 'unknown'
    result['status'] = 'online' if device.get('status', 0) == 1 else 'offline'
    # Try multiple possible IP field names from LibreNMS
    result['ip'] = (
        device.get('ip') or
        device.get('hostname') or
        device.get('sysName') or
        ''
    )

    # ── CPU and Memory from device endpoint ───────────────────────────────────
    device_id = device.get('hostname') or device.get('device_id')
    try:
        resp = requests.get(
            f'{rt.librenms_url}/api/v0/devices/{device_id}',
            headers=headers, timeout=10, verify=rt.librenms_verify_ssl,
        )
        if resp.ok:
            device_data = resp.json().get('devices', [{}])[0] if resp.json().get('devices') else {}
            # Try to get CPU from device stats
            if 'processor_usage' in device_data:
                result['cpu_load'] = round(float(device_data['processor_usage']))
            elif 'cpu_usage' in device_data:
                result['cpu_load'] = round(float(device_data['cpu_usage']))
            elif 'stats' in device_data:
                stats = device_data['stats']
                if 'processor' in stats:
                    result['cpu_load'] = round(float(stats['processor']))
            # Try to get memory from device stats
            if 'mempool' in device_data:
                result['mem_percent'] = round(float(device_data['mempool']))
            elif 'memory_usage' in device_data:
                result['mem_percent'] = round(float(device_data['memory_usage']))
            elif 'stats' in device_data:
                stats = device_data['stats']
                if 'mempool' in stats:
                    result['mem_percent'] = round(float(stats['mempool']))
    except requests.RequestException:
        pass


    # ── Temperature from device sensors ────────────────────────────────────────────
    try:
        resp = requests.get(
            f'{rt.librenms_url}/api/v0/devices/{device_id}/sensors',
            headers=headers, timeout=10, verify=rt.librenms_verify_ssl,
            params={'type': 'temperature'},
        )
        if resp.ok:
            sensors = resp.json().get('sensors', [])
            # Get the average temperature from all temperature sensors
            temps = [s.get('sensor_current') for s in sensors if s.get('sensor_current') is not None]
            if temps:
                result['temperature'] = round(sum(temps) / len(temps), 1)
    except requests.RequestException:
        pass

    # ── Port summary + traffic ────────────────────────────────────────────────
    try:
        resp = requests.get(
            f'{rt.librenms_url}/api/v0/devices/{device_id}/ports',
            headers=headers, timeout=10, verify=rt.librenms_verify_ssl,
            params={'columns': 'ifOperStatus,ifInOctets_rate,ifOutOctets_rate,ifSpeed'},
        )
        if resp.ok:

            ports = resp.json().get('ports', [])


            result['total_ports'] = len(ports)
            result['up_ports']    = sum(1 for p in ports if p.get('ifOperStatus') == 'up')

            total_traffic_bps  = 0.0
            total_capacity_bps = 0.0
            for p in ports:
                if p.get('ifOperStatus') != 'up':
                    continue
                in_rate  = float(p.get('ifInOctets_rate')  or 0)
                out_rate = float(p.get('ifOutOctets_rate') or 0)
                speed    = float(p.get('ifSpeed')          or 0)
                total_traffic_bps  += (in_rate + out_rate) * 8
                if speed > 0:
                    total_capacity_bps += speed

            result['total_traffic_bps'] = round(total_traffic_bps)
            if total_capacity_bps > 0:
                result['traffic_util'] = round(
                    min(1.0, total_traffic_bps / total_capacity_bps), 4
                )
    except requests.RequestException:
        pass

    # print(f"LibreNMS details for {hostname}: {result}")
    return result

def fetch_librenms_device_port_stats_by_interface(hostname, interface):
    """One port's state, speed, traffic and errors for the seat inspector (see ports.py)."""
    headers = {
        'X-Auth-Token': rt.librenms_token,
        'Accept': 'application/json',
    }

    result = {}
    if not hostname or not interface:
        return result
    try:
        device = fetch_librenms_device_by_hostname(hostname, headers)
        if not device:
            return result
        device_id = device.get('device_id') or device.get('hostname')
        port = librenms_ports.fetch_port(rt.librenms_url, headers, device_id, interface, verify=rt.librenms_verify_ssl)
        if port:
            result = librenms_ports.summarize_port(port, rt.librenms_url, device.get('device_id'))
    except requests.RequestException:
        pass

    return result


def list_devices():
    """Every LibreNMS device, as the API returns it (status, display, hostname, sysName, ...).
    Raises on failure, so the status monitor can show the error."""
    resp = requests.get(f'{rt.librenms_url}/api/v0/devices',
                        headers={'X-Auth-Token': rt.librenms_token, 'Accept': 'application/json'},
                        timeout=15, verify=rt.librenms_verify_ssl)
    resp.raise_for_status()
    return resp.json().get('devices', []) or []


def arp_entries(query):
    """ARP rows matching an IP or a MAC ([] when LibreNMS has none)."""
    resp = requests.get(f'{rt.librenms_url}/api/v0/resources/ip/arp/{query}',
                        headers={'X-Auth-Token': rt.librenms_token, 'Accept': 'application/json'},
                        timeout=10, verify=rt.librenms_verify_ssl)
    if not resp.ok:
        return []
    return resp.json().get('arp', []) or []
