import os
import json
import uuid
import time

import requests
import redis
from dotenv import load_dotenv
from flask import Flask, render_template, request, jsonify

from settings_store import SettingsStore, create_settings_blueprint

load_dotenv()

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 32 * 1024 * 1024

DATA_FILE = 'data.json'

# ── Service config ─────────────────────────────────────────────────────────────
# NetBox, LibreNMS and cache settings are edited on /settings, see
# "Runtime settings" below. Only Redis is configured from the environment.

# ── Redis config ─────────────────────────────────────────────────────────────
REDIS_HOST     = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT     = int(os.getenv('REDIS_PORT', 6379))
REDIS_DB       = int(os.getenv('REDIS_DB', 0))
REDIS_PASSWORD = os.getenv('REDIS_PASSWORD', None)

# ── Runtime settings ───────────────────────────────────────────────────────────
# Values saved on /settings live in data.json and win over env vars, which
# remain the defaults (see settings_store.py). apply_runtime_settings()
# rebinds these module globals, so the code below keeps reading them as-is.
settings_store = SettingsStore(DATA_FILE)

NETBOX_URL = NETBOX_TOKEN = LIBRENMS_URL = LIBRENMS_TOKEN = ''
NETBOX_ROLES = []
NETBOX_VERIFY_SSL = LIBRENMS_VERIFY_SSL = True
LIBRENMS_FDB_EXCLUDE = []
CACHE_TTL_ARP = CACHE_TTL_MAC = 300
CACHE_TTL_RESOLVE = 30
NETBOX_ENABLED = LIBRENMS_ENABLED = False
DISPLAY_DEFAULTS = {}


def apply_runtime_settings():
    global NETBOX_URL, NETBOX_TOKEN, NETBOX_ROLES, NETBOX_VERIFY_SSL
    global LIBRENMS_URL, LIBRENMS_TOKEN, LIBRENMS_VERIFY_SSL, LIBRENMS_FDB_EXCLUDE
    global CACHE_TTL_ARP, CACHE_TTL_MAC, CACHE_TTL_RESOLVE
    global NETBOX_ENABLED, LIBRENMS_ENABLED, DISPLAY_DEFAULTS
    s = settings_store
    NETBOX_URL           = s.get('netbox.url')
    NETBOX_TOKEN         = s.get('netbox.token')
    NETBOX_ROLES         = s.get('netbox.device_roles')
    NETBOX_VERIFY_SSL    = s.get('netbox.verify_ssl')
    LIBRENMS_URL         = s.get('librenms.url')
    LIBRENMS_TOKEN       = s.get('librenms.token')
    LIBRENMS_VERIFY_SSL  = s.get('librenms.verify_ssl')
    LIBRENMS_FDB_EXCLUDE = [p.lower() for p in s.get('librenms.fdb_exclude')]
    CACHE_TTL_ARP        = s.get('cache.ttl_arp')
    CACHE_TTL_MAC        = s.get('cache.ttl_mac')
    CACHE_TTL_RESOLVE    = s.get('cache.ttl_resolve')
    NETBOX_ENABLED       = bool(NETBOX_URL and NETBOX_TOKEN)
    LIBRENMS_ENABLED     = bool(LIBRENMS_URL and LIBRENMS_TOKEN)
    DISPLAY_DEFAULTS     = {
        'hide_labels':     s.get('display.hide_labels'),
        'exclude_heatmap': s.get('display.exclude_heatmap'),
    }


apply_runtime_settings()


@app.before_request
def refresh_runtime_settings():
    """Pick up settings saved by another process/worker (cheap mtime check)."""
    if settings_store.reload_if_changed():
        apply_runtime_settings()

# ── Redis connection ──────────────────────────────────────────────────────
redis_client = None

# Redis connection will be established in app context
@app.before_request
def setup_redis_connection():
    """Establish Redis connection before each request with retry logic."""
    global redis_client

    # If Redis client already exists and is connected, reuse it
    if redis_client:
        try:
            redis_client.ping()
            return
        except Exception:
            redis_client = None

    # Try to establish new connection with retries
    for attempt in range(5):  # Try up to 5 times
        try:
            redis_client = redis.Redis(
                host=REDIS_HOST,
                port=REDIS_PORT,
                db=REDIS_DB,
                password=REDIS_PASSWORD,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True,
                health_check_interval=30,
            )
            # Test connection
            redis_client.ping()
            print(f"Connected to Redis at {REDIS_HOST}:{REDIS_PORT} (attempt {attempt + 1})")
            return
        except Exception as e:
            if attempt < 4:  # Don't wait on the last attempt
                print(f"Redis connection attempt {attempt + 1} failed: {e}. Retrying in 2 seconds...")
                time.sleep(2)
            else:
                print(f"Warning: Could not connect to Redis after 5 attempts: {e}. Caching disabled for this request.")
                redis_client = None


def get_redis_client():
    """Get the current Redis client."""
    return redis_client



# ── Redis cache helpers ────────────────────────────────────────────────────────
def get_cached_arp(hostname):
    """Get cached ARP table for a device."""
    client = get_redis_client()
    if not client:
        return None
    try:
        cache_key = f"arp:{hostname}"
        cached = client.get(cache_key)
        if cached:
            return json.loads(cached)
    except Exception as e:
        print(f"Redis cache read error (ARP): {e}")
    return None


def set_cached_arp(hostname, arp_data):
    """Cache ARP table for a device."""
    client = get_redis_client()
    if not client:
        return
    try:
        cache_key = f"arp:{hostname}"
        client.setex(cache_key, CACHE_TTL_ARP, json.dumps(arp_data))
    except Exception as e:
        print(f"Redis cache write error (ARP): {e}")


def get_cached_mac(hostname):
    """Get cached MAC address table for a device."""
    client = get_redis_client()
    if not client:
        return None
    try:
        cache_key = f"mac:{hostname}"
        cached = client.get(cache_key)
        if cached:
            return json.loads(cached)
    except Exception as e:
        print(f"Redis cache read error (MAC): {e}")
    return None


def set_cached_mac(hostname, mac_data):
    """Cache MAC address table for a device."""
    client = get_redis_client()
    if not client:
        return
    try:
        cache_key = f"mac:{hostname}"
        client.setex(cache_key, CACHE_TTL_MAC, json.dumps(mac_data))
    except Exception as e:
        print(f"Redis cache write error (MAC): {e}")


def invalidate_hostname_cache(hostname):
    """Invalidate all cache entries for a specific hostname."""
    client = get_redis_client()
    if not client:
        return
    try:
        client.delete(f"arp:{hostname}")
        client.delete(f"mac:{hostname}")
    except Exception as e:
        print(f"Redis cache invalidation error: {e}")


# ── Persistence ────────────────────────────────────────────────────────────────

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    return {
        'switches':       [],   # manual mode switch list
        'cached_devices': [],   # netbox mode: cached device list
        'positions':      {},   # netbox mode: {str(device_id): {x, y}}
        'seats':          [],   # individual seats
        'seat_blocks':    [],   # seating blocks (rows/sections)
    }


def save_data(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)




# ── NetBox ─────────────────────────────────────────────────────────────────────

def fetch_netbox_devices():
    """Fetch all devices with the configured role from NetBox (handles pagination)."""
    headers = {
        'Authorization': f'Token {NETBOX_TOKEN}',
        'Accept': 'application/json',
    }
    devices = []
    url = f'{NETBOX_URL}/api/dcim/devices/'
    params = {'role': NETBOX_ROLES, 'limit': 500}
    while url:
        resp = requests.get(url, headers=headers, params=params,
                            timeout=15, verify=NETBOX_VERIFY_SSL)
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


# ── LibreNMS ───────────────────────────────────────────────────────────────────

def fetch_librenms_arp_by_ip(ip_address):
    """Fetch ARP entry for a specific IP address using the resources endpoint.

    Uses endpoint: /api/v0/resources/ip/arp/{ip_address}
    This is more efficient as it doesn't require device lookup.
    """
    headers = {
        'X-Auth-Token': LIBRENMS_TOKEN,
        'Accept': 'application/json',
    }

    try:
        resp = requests.get(
            f'{LIBRENMS_URL}/api/v0/resources/ip/arp/{ip_address}',
            headers=headers,
            timeout=10, verify=LIBRENMS_VERIFY_SSL,
        )
        if resp.ok:
            arp_data = resp.json().get('arp', [])
            # Cache the result with IP as key for direct IP lookups
            client = get_redis_client()
            if client:
                try:
                    cache_key = f"arp_ip:{ip_address}"
                    client.setex(cache_key, CACHE_TTL_ARP, json.dumps(arp_data))
                    # print(f"ARP data cached for IP {ip_address}")
                    # print(f"Cached ARP entries for IP {ip_address}: {arp_data}")
                except Exception as e:
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
        'X-Auth-Token': LIBRENMS_TOKEN,
        'Accept': 'application/json',
    }

    # First, get the device ID
    try:
        resp = requests.get(
            f'{LIBRENMS_URL}/api/v0/devices',
            headers=headers,
            params={'type': 'display', 'query': hostname},
            timeout=10, verify=LIBRENMS_VERIFY_SSL,
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
            f'{LIBRENMS_URL}/api/v0/devices/{device_id}/arp',
            headers=headers,
            timeout=10, verify=LIBRENMS_VERIFY_SSL,
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
        'X-Auth-Token': LIBRENMS_TOKEN,
        'Accept': 'application/json',
    }

    # First, get the device ID
    try:
        resp = requests.get(
            f'{LIBRENMS_URL}/api/v0/devices',
            headers=headers,
            params={'type': 'display', 'query': hostname},
            timeout=10, verify=LIBRENMS_VERIFY_SSL,
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
            f'{LIBRENMS_URL}/api/v0/devices/{device_id}/fdb',
            headers=headers,
            timeout=10, verify=LIBRENMS_VERIFY_SSL,
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
        'X-Auth-Token': LIBRENMS_TOKEN,
        'Accept': 'application/json',
    }

    # Normalize MAC address format
    mac_normalized = mac_address.lower().replace('-', ':')

    try:
        # Get all devices
        resp = requests.get(
            f'{LIBRENMS_URL}/api/v0/resources/fdb/{mac_normalized}/detail',
            headers=headers,
            timeout=10, verify=LIBRENMS_VERIFY_SSL,
        )

        if not resp.ok:
            return None

        # print(f"FDB search response for MAC {mac_address}: {resp.status_code}")
        
        ports = resp.json().get('ports_fdb', [])
        matches = {}
        for entry in ports:

            excludes = LIBRENMS_FDB_EXCLUDE
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
                stats = fetch_librenms_device_port_stats_by_interface(cached_result.get('hostname'), cached_result.get('port'))   

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
        except Exception as e:
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
            client.setex(resolve_cache_key, CACHE_TTL_RESOLVE, json.dumps(result))
            # print(f"Resolve result cached for IP {ip_address}")
        except Exception as e:
            print(f"Redis cache write error (resolve): {e}")

    return result

def fetch_librenms_device_by_hostname(hostname, headers):
    device = None
    try:
        query = hostname.split('.')[0]  # Use short hostname for broader search
        resp = requests.get(
            f'{LIBRENMS_URL}/api/v0/devices',
            headers=headers,
            params={'type': 'display', 'query': query},
            timeout=10, verify=LIBRENMS_VERIFY_SSL,
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

                if hn.split('.')[0] in d.get('display', '').lower() or hn.split('.')[0] in d.get('hostname', '').lower():
                    device = d  # Also consider short hostname matches

    except requests.RequestException:
        pass

    return device

def fetch_librenms_details(hostname):
    """Return a dict with status, ip, cpu_load, mem_percent, up_ports, total_ports.

    Searches LibreNMS by displayname so hostname mapping doesn't need to match exactly.
    """
    headers = {
        'X-Auth-Token': LIBRENMS_TOKEN,
        'Accept': 'application/json',
    }
    result = {'status': 'unknown', 'hostname': hostname}

    # ── Find device by displayname ────────────────────────────────────────────
    from typing import Optional
    device: Optional[dict] = fetch_librenms_device_by_hostname(hostname, headers)

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
            f'{LIBRENMS_URL}/api/v0/devices/{device_id}',
            headers=headers, timeout=10, verify=LIBRENMS_VERIFY_SSL,
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
            f'{LIBRENMS_URL}/api/v0/devices/{device_id}/sensors',
            headers=headers, timeout=10, verify=LIBRENMS_VERIFY_SSL,
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
            f'{LIBRENMS_URL}/api/v0/devices/{device_id}/ports',
            headers=headers, timeout=10, verify=LIBRENMS_VERIFY_SSL,
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

    headers = {
        'X-Auth-Token': LIBRENMS_TOKEN,
        'Accept': 'application/json',
    }

    result = {}
    try:
        device = fetch_librenms_device_by_hostname(hostname, headers)
        if not device:
            return result
        device_id = device.get('device_id') or device.get('hostname')
        resp = requests.get(
            f'{LIBRENMS_URL}/api/v0/devices/{device_id}/ports',
            headers=headers, timeout=10, verify=LIBRENMS_VERIFY_SSL,
            params={'columns': 'ifOperStatus,ifInOctets_rate,ifOutOctets_rate,ifSpeed,ifName'},
        )
        if resp.ok:
            ports = resp.json().get('ports', [])

            for p in ports:
                if p.get('ifName') == interface:
                    result['ifOperStatus'] = p.get('ifOperStatus')
                    result['ifInOctets_rate'] = p.get('ifInOctets_rate')
                    result['ifOutOctets_rate'] = p.get('ifOutOctets_rate')
                    result['ifSpeed'] = p.get('ifSpeed')
                    break


            # result['total_ports'] = len(ports)
            # result['up_ports']    = sum(1 for p in ports if p.get('ifOperStatus') == 'up')

            # total_traffic_bps  = 0.0
            # total_capacity_bps = 0.0
            # for p in ports:
            #     # if p.get('ifOperStatus') != 'up':
            #     #     continue
            #     in_rate  = float(p.get('ifInOctets_rate')  or 0)
            #     out_rate = float(p.get('ifOutOctets_rate') or 0)
            #     speed    = float(p.get('ifSpeed')          or 0)
            #     total_traffic_bps  += (in_rate + out_rate) * 8
            #     if speed > 0:
            #         total_capacity_bps += speed

            # result['total_traffic_bps'] = round(total_traffic_bps)
            # if total_capacity_bps > 0:
            #     result['traffic_util'] = round(
            #         min(1.0, total_traffic_bps / total_capacity_bps), 4
            #     )
    except requests.RequestException:
        pass

    return result
# ── Pages ──────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')


# ── Config ─────────────────────────────────────────────────────────────────────

@app.route('/api/config')
def get_config():
    return jsonify({
        'netbox_enabled':    NETBOX_ENABLED,
        'librenms_enabled':  LIBRENMS_ENABLED,
        'netbox_device_roles': NETBOX_ROLES,
        'display_defaults':  DISPLAY_DEFAULTS,
    })


def redis_info():
    client = get_redis_client()
    connected = False
    if client:
        try:
            connected = bool(client.ping())
        except Exception:
            connected = False
    return {'host': REDIS_HOST, 'port': REDIS_PORT, 'db': REDIS_DB, 'connected': connected}


# /settings page plus GET/PUT /api/settings and POST /api/settings/test/<service>
app.register_blueprint(create_settings_blueprint(
    settings_store,
    on_change=apply_runtime_settings,
    get_redis=get_redis_client,
    redis_info=redis_info,
))


# ── Switches ───────────────────────────────────────────────────────────────────

@app.route('/api/switches', methods=['GET'])
def get_switches():
    data = load_data()
    manual = data.get('switches', [])
    if NETBOX_ENABLED:
        netbox = merge_devices_with_positions(
            data.get('cached_devices', []),
            data.get('positions', {}),
        )
        return jsonify(netbox + manual)
    return jsonify(manual)


@app.route('/api/switches/sync', methods=['POST'])
def sync_switches():
    """Re-fetch device list from NetBox and persist it (NetBox mode only)."""
    if not NETBOX_ENABLED:
        return jsonify({'error': 'NetBox is not configured'}), 400
    try:
        devices = fetch_netbox_devices()
    except requests.RequestException as exc:
        return jsonify({'error': f'NetBox request failed: {exc}'}), 502

    data = load_data()
    data['cached_devices'] = devices
    data.setdefault('positions', {})
    save_data(data)
    return jsonify(merge_devices_with_positions(devices, data['positions']))


@app.route('/api/switches', methods=['POST'])
def add_switch():
    """Create and place a manual switch (available in both manual and NetBox mode)."""
    body = request.get_json(force=True)
    try:
        x = float(body['x'])
        y = float(body['y'])
    except (KeyError, TypeError, ValueError):
        return jsonify({'error': 'Valid numeric x and y coordinates are required'}), 400

    switch = {
        'id':     str(uuid.uuid4()),
        'name':   body.get('name', 'Switch'),
        'x':      x,
        'y':      y,
        'placed': True,
        'source': 'manual',
        'status': 'unknown',
    }
    data = load_data()
    data.setdefault('switches', []).append(switch)
    save_data(data)
    return jsonify(switch), 201


@app.route('/api/switches/<switch_id>', methods=['PUT'])
def update_switch(switch_id):
    body = request.get_json(force=True)
    data = load_data()

    if NETBOX_ENABLED:
        device = next(
            (d for d in data.get('cached_devices', []) if d['id'] == switch_id),
            None,
        )
        if device:
            positions = data.setdefault('positions', {})
            pos = positions.get(switch_id, {})
            if 'x' in body and 'y' in body:
                try:
                    pos = {'x': float(body['x']), 'y': float(body['y'])}
                except (TypeError, ValueError):
                    return jsonify({'error': 'Invalid coordinates'}), 400
            positions[switch_id] = pos
            save_data(data)
            return jsonify({
                'id':            device['id'],
                'name':          device['name'],
                'netbox_status': device.get('netbox_status', 'unknown'),
                'x':             pos.get('x'),
                'y':             pos.get('y'),
                'placed':        True,
                'status':        'unknown',
            })
        # Fall through to handle manual switches in NetBox mode

    for switch in data.get('switches', []):
        if switch['id'] == switch_id:
            for key in ('name', 'x', 'y'):
                if key in body:
                    switch[key] = body[key]
            save_data(data)
            return jsonify(switch)
    return jsonify({'error': 'Switch not found'}), 404


@app.route('/api/switches/<switch_id>', methods=['DELETE'])
def delete_switch(switch_id):
    data = load_data()

    if NETBOX_ENABLED:
        positions = data.setdefault('positions', {})
        if switch_id in positions:
            del positions[switch_id]
            save_data(data)
            return jsonify({'success': True})
        # Fall through to handle manual switches in NetBox mode

    before = len(data.get('switches', []))
    data['switches'] = [s for s in data['switches'] if s['id'] != switch_id]
    if len(data['switches']) == before:
        return jsonify({'error': 'Switch not found'}), 404
    save_data(data)
    return jsonify({'success': True})


# ── Seats (read-only for seat blocks) ───────────────────────────────────────

@app.route('/api/seats', methods=['GET'])
def get_seats():
    data = load_data()
    return jsonify(data.get('seats', []))


# ── Seat Blocks ───────────────────────────────────────────────────────────────

@app.route('/api/seat-blocks', methods=['GET'])
def get_seat_blocks():
    data = load_data()
    return jsonify(data.get('seat_blocks', []))


@app.route('/api/seat-blocks', methods=['POST'])
def add_seat_block():
    """Create a seating block (row or multiple rows)."""
    body = request.get_json(force=True)
    try:
        x = float(body['x'])
        y = float(body['y'])
        cols = int(body.get('cols', 1))
        rows = int(body.get('rows', 1))
        seat_width = float(body.get('seat_width', 3))
        seat_height = float(body.get('seat_height', 3))
        spacing_x = float(body.get('spacing_x', 0.5))
        spacing_y = float(body.get('spacing_y', 1))
    except (KeyError, TypeError, ValueError):
        return jsonify({'error': 'Valid coordinates and dimensions are required'}), 400

    block = {
        'id': str(uuid.uuid4()),
        'name': body.get('name', ''),
        'x': x,
        'y': y,
        'cols': cols,
        'rows': rows,
        'seat_width': seat_width,
        'seat_height': seat_height,
        'spacing_x': spacing_x,
        'spacing_y': spacing_y,
        'rotation': body.get('rotation', 0),
        'reverse_numbers': body.get('reverse_numbers', False),
    }
    data = load_data()
    data.setdefault('seat_blocks', []).append(block)
    save_data(data)
    return jsonify(block), 201


@app.route('/api/seat-blocks/<block_id>', methods=['PUT'])
def update_seat_block(block_id):
    body = request.get_json(force=True)
    data = load_data()

    for block in data.get('seat_blocks', []):
        if block['id'] == block_id:
            for key in ('name', 'x', 'y', 'cols', 'rows', 'seat_width', 'seat_height',
                       'spacing_x', 'spacing_y', 'rotation', 'reverse_numbers'):
                if key in body:
                    block[key] = body[key]
            save_data(data)
            return jsonify(block)
    return jsonify({'error': 'Seat block not found'}), 404


@app.route('/api/seat-blocks/<block_id>', methods=['DELETE'])
def delete_seat_block(block_id):
    data = load_data()
    before = len(data.get('seat_blocks', []))
    data['seat_blocks'] = [b for b in data['seat_blocks'] if b['id'] != block_id]
    if len(data['seat_blocks']) == before:
        return jsonify({'error': 'Seat block not found'}), 404
    save_data(data)
    return jsonify({'success': True})


# ── Cache Management ───────────────────────────────────────────────────────────

@app.route('/api/cache/invalid', methods=['POST'])
def invalidate_cache():
    """Invalidate Redis cache entries for specific hostnames."""
    client = get_redis_client()
    if not client:
        return jsonify({'error': 'Redis is not configured'}), 503

    body = request.get_json(force=True) or {}
    hostnames = body.get('hostnames', [])

    if not hostnames:
        # Invalidate all cache if no hostnames specified
        try:
            # Delete all ARP and MAC cache keys
            for key in client.scan_iter(match='arp:*'):
                client.delete(key)
            for key in client.scan_iter(match='mac:*'):
                client.delete(key)
            return jsonify({'success': True, 'message': 'All cache entries invalidated'})
        except Exception as e:
            return jsonify({'error': f'Failed to clear cache: {str(e)}'}), 500

    # Invalidate cache for specific hostnames
    invalidated = []
    for hostname in hostnames:
        try:
            invalidate_hostname_cache(hostname)
            invalidated.append(hostname)
        except Exception as e:
            print(f"Failed to invalidate cache for {hostname}: {e}")

    return jsonify({
        'success': True,
        'message': f'Cache invalidated for {len(invalidated)} hostnames',
        'invalidated': invalidated
    })


@app.route('/api/cache/stats', methods=['GET'])
def get_cache_stats():
    """Get Redis cache statistics."""
    client = get_redis_client()
    if not client:
        return jsonify({'error': 'Redis is not configured'}), 503

    try:
        # Count ARP and MAC cache keys
        arp_count = len(list(client.scan_iter(match='arp:*')))
        mac_count = len(list(client.scan_iter(match='mac:*')))
        total_keys = client.dbsize()

        return jsonify({
            'redis_connected': True,
            'total_keys': total_keys,
            'arp_cache_entries': arp_count,
            'mac_cache_entries': mac_count,
            'cache_ttl_arp': CACHE_TTL_ARP,
            'cache_ttl_mac': CACHE_TTL_MAC,
        })
    except Exception as e:
        return jsonify({'error': f'Failed to get cache stats: {str(e)}'}), 500


# ── Status ─────────────────────────────────────────────────────────────────────

@app.route('/api/switches/<switch_id>/status', methods=['GET'])
def get_switch_status(switch_id):
    if not LIBRENMS_ENABLED:
        return jsonify({
            'id':      switch_id,
            'status':  'unknown',
            'message': 'LibreNMS is not configured',
        })

    data = load_data()
    # Check manual switches first (present in both modes)
    switch = next((s for s in data.get('switches', []) if s['id'] == switch_id), None)
    if switch:
        hostname = switch['name']
    elif NETBOX_ENABLED:
        device = next(
            (d for d in data.get('cached_devices', []) if d['id'] == switch_id),
            None,
        )
        hostname = device['name'] if device else switch_id
    else:
        hostname = switch_id

    details = fetch_librenms_details(hostname)
    return jsonify({'id': switch_id, **details})


# ── IP Resolution ────────────────────────────────────────────────────────────────

@app.route('/api/resolve/<ip_address>', methods=['GET'])
def resolve_ip(ip_address):
    """Resolve an IP address to its switch and port using LibreNMS ARP and MAC tables."""
    if not LIBRENMS_ENABLED:
        return jsonify({
            'ip': ip_address,
            'error': 'LibreNMS is not configured',
        }), 400

    # Optional: specify a device to search for ARP entries
    search_device = request.args.get('device')

    result = resolve_ip_to_switch_port(ip_address, search_device)
    if result:
        return jsonify(result)
    else:
        return jsonify({
            'ip': ip_address,
            'error': 'Could not resolve IP address',
        }), 404


@app.route('/api/seats/info', methods=['GET'])
def get_seats_info():
    """Seat → user / IP mapping, merged from the configured seat sources."""
    seats = seat_sources.load()
    return jsonify({'seats': seats, 'errors': seat_sources.info()['errors']})


@app.route('/api/seats/resolve', methods=['POST'])
def resolve_seats():
    """Resolve all seat IP addresses to their switch and port mappings."""
    if not LIBRENMS_ENABLED:
        return jsonify({
            'error': 'LibreNMS is not configured',
        }), 400

    seats = seat_sources.load()
    if not seats:
        return jsonify({'error': 'No seat mapping available', 'sources': seat_sources.info()}), 400

    results = {}

    for seat_number, seat_info in seats.items():
        ip_address = seat_info.get('ip_address')
        if not ip_address:
            continue

        # Try to resolve the IP
        result = resolve_ip_to_switch_port(ip_address)
        if result:
            results[seat_number] = {
                'username': seat_info.get('username'),
                'ip_address': ip_address,
                'resolved': True,
                **result,
            }
        else:
            results[seat_number] = {
                'username': seat_info.get('username'),
                'ip_address': ip_address,
                'resolved': False,
                'error': 'Could not resolve',
            }

    return jsonify({'seats': results})


@app.route('/api/seats/heatmap', methods=['GET'])
def get_seats_heatmap():
    """Get seat heat map data based on port usage statistics."""
    if not LIBRENMS_ENABLED:
        return jsonify({
            'error': 'LibreNMS is not configured',
        }), 400

    seats = seat_sources.load()
    if not seats:
        return jsonify({'error': 'No seat mapping available', 'sources': seat_sources.info()}), 400

    results = {}

    for seat_number, seat_info in seats.items():
        ip_address = seat_info.get('ip_address')
        if not ip_address:
            results[seat_number] = {
                'username': seat_info.get('username'),
                'ip_address': None,
                'resolved': False,
                'port_usage': None,
                'error': 'No IP address',
            }
            continue

        # Try to resolve IP to get port stats
        result = resolve_ip_to_switch_port(ip_address)
        if result and 'stats' in result:
            stats = result['stats']
            # Calculate port usage metrics
            in_rate = float(stats.get('ifInOctets_rate') or 0)
            out_rate = float(stats.get('ifOutOctets_rate') or 0)
            total_bps = (in_rate + out_rate) * 8
            port_status = stats.get('ifOperStatus', 'unknown')
            port_speed = float(stats.get('ifSpeed') or 0)

            results[seat_number] = {
                'username': seat_info.get('username'),
                'ip_address': ip_address,
                'resolved': True,
                'port_usage': {
                    'total_bps': total_bps,
                    'in_rate_bps': in_rate * 8,
                    'out_rate_bps': out_rate * 8,
                    'status': port_status,
                    'speed_bps': port_speed,
                },
                'device_name': result.get('device_name'),
                'port': result.get('port'),
                'vlan': result.get('vlan'),
                'mac': result.get('mac'),
            }
        else:
            results[seat_number] = {
                'username': seat_info.get('username'),
                'ip_address': ip_address,
                'resolved': False,
                'port_usage': None,
                'error': 'Could not resolve port stats',
            }

    return jsonify({'seats': results})


# ── Integrations ───────────────────────────────────────────────────────────────
# Live push (/api/events), switch status monitor, Discord alerts, seat sources
# and the seat check-in page. See docs/integrations.md.
from integrations import init_integrations, seat_sources  # noqa: E402

init_integrations(app, load_data=load_data,
                  settings_store=globals().get('settings_store'))


if __name__ == '__main__':
    app.run(debug=True)
