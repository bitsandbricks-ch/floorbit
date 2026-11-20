"""LibreNMS: switch status and ports, and IP to switch port resolution (ARP, then FDB).

The LibreNMS plugin's API client (plugin.py wraps it). Nothing else in Floorbit talks to
LibreNMS: the core asks ``floorbit.sources.monitoring()``. Answers are cached in Redis (see
floorbit/cache.py) for the TTLs on the settings page.
"""
import ipaddress
import json
from collections import Counter
from urllib.parse import quote

import redis
import requests

from floorbit import edge_ports
from floorbit.cache import get_cached_mac, get_redis_client, set_cached_mac
from floorbit.runtime import rt

from . import breaker
from . import facts as librenms_facts
from . import ports as librenms_ports
from .memo import Memo

# In front of Redis, and the only cache on the local agent (which has no Redis).
_devices = Memo()        # switch name -> its LibreNMS device row
_mac_counts = Memo()     # switch name -> {port_id: MACs learned on it}
_resolved = Memo()       # IP -> where it sits (switch and port, not the live port numbers)
_port_rows = Memo(2000)  # switch -> its port rows, for a seat's port numbers
DEVICE_TTL = 300         # a switch's device_id doesn't change during an event
UNKNOWN_DEVICE_TTL = 30  # an unknown name is asked again soon, but not on every lookup
# A seat's port numbers: LibreNMS has new ones once per poll (minutes), and the ten seats on one
# switch checking in together would otherwise each read all its ports.
PORT_ROWS_TTL = 15


def reset_caches():
    for memo in (_devices, _mac_counts, _resolved, _port_rows):
        memo.clear()
    librenms_facts.reset_caches()
    librenms_ports._refused.clear()


def _ip(value):
    """The IP as LibreNMS writes it, or None when it isn't one (nothing else is sent on)."""
    try:
        return str(ipaddress.ip_address(str(value).strip()))
    except ValueError:
        return None


def _seg(value):
    """One URL path segment: an IP, MAC or device name from elsewhere can't reach another endpoint."""
    return quote(str(value), safe=':')   # MACs and IPv6 keep their colons


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
        resp = breaker.get(
            f'{rt.librenms_url}/api/v0/resources/ip/arp/{_seg(ip_address)}',
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
                except redis.RedisError as e:
                    print(f"Redis cache write error (IP ARP): {e}")
            return arp_data
        else:
            print(f"Failed to fetch ARP for IP {ip_address}: {resp.status_code}")
    except requests.RequestException as e:
        print(f"Exception fetching ARP for IP {ip_address}: {e}")

    return None


def fetch_librenms_mac_table(hostname):
    """Fetch MAC address table (FDB) for a device from LibreNMS with Redis caching."""
    # Try to get from cache first
    cached = get_cached_mac(hostname)
    if cached is not None:
        return cached

    headers = {
        'X-Auth-Token': rt.librenms_token,
        'Accept': 'application/json',
    }

    device = fetch_librenms_device_by_hostname(hostname, headers)
    if not device:
        return []
    device_id = _seg(device.get('device_id') or device.get('hostname'))

    # Now fetch the MAC address table
    mac_data = []
    try:
        resp = breaker.get(
            f'{rt.librenms_url}/api/v0/devices/{device_id}/fdb',
            headers=headers,
            timeout=10, verify=rt.librenms_verify_ssl,
        )
        if resp.ok:
            body = resp.json()
            # Either key: the LibreNMS API docs say "ports_fdb", the older code here read "fdb".
            mac_data = body.get('ports_fdb') or body.get('fdb') or []
            # Cache the result
            set_cached_mac(hostname, mac_data)
    except requests.RequestException:
        pass

    return mac_data


EDGE_PORT_MACS = edge_ports.EDGE_PORT_MACS     # one rule for a seat's port (floorbit/edge_ports.py)


def pick_edge_port(entries, macs_on_port, excludes=(), uplink=None):
    """The FDB row of the access port a MAC is plugged into, or None.

    ARP lives on the core only; the access switches have only their MAC tables, and every switch
    between the core and the seat learns the MAC too, on its uplink or trunk. So: drop ignored port
    names and ports described as uplinks, then take the port with the fewest MACs on it. A port
    with many MACs only wins when nothing better is left.
    """
    candidates = []
    for entry in entries:
        name = str(entry.get('ifName') or '').lower()
        if not name or any(ex in name for ex in excludes):
            continue
        if uplink is not None and uplink.search(str(entry.get('ifAlias') or '')):
            continue
        candidates.append((macs_on_port(entry), name, entry))
    if not candidates:
        return None
    candidates.sort(key=lambda c: (c[0] is None, c[0] or 0, c[1]))
    return candidates[0][2]


def _macs_on_port(entry):
    """How many MACs the entry's switch has learned on the entry's port (None when unknown)."""
    port_id = entry.get('port_id')
    hostname = entry.get('hostname')
    if port_id is None or not hostname:
        return None
    return mac_counts(hostname).get(port_id) or None


def mac_counts(hostname):
    """{port_id: MACs} of one switch's MAC table. Only the counts are kept: a core's table at a
    10,000-seat event is 10,000 rows, and the lookup only needs how many sit on each port."""
    def load():
        return dict(Counter(r.get('port_id') for r in fetch_librenms_mac_table(hostname) or []))
    return _mac_counts.load(hostname, load, lambda: rt.cache_ttl_mac, keep=bool)


def find_mac_in_all_switches(mac_address):
    """The access switch and port a MAC sits on, from the MAC tables (FDB) of every switch."""
    from floorbit.stats import _uplink_re

    headers = {
        'X-Auth-Token': rt.librenms_token,
        'Accept': 'application/json',
    }
    mac_normalized = mac_address.lower().replace('-', ':')
    try:
        resp = breaker.get(
            f'{rt.librenms_url}/api/v0/resources/fdb/{_seg(mac_normalized)}/detail',
            headers=headers,
            timeout=10, verify=rt.librenms_verify_ssl,
        )
        if not resp.ok:
            return None
        entries = resp.json().get('ports_fdb', []) or []
    except requests.RequestException:
        return None
    # The MAC count per port picks the access port and tells an AP or desk switch from a PC: one
    # MAC table read per switch that knows the MAC, cached (fetch_librenms_mac_table).
    counts = {}

    def counter(entry):
        key = (entry.get('hostname'), entry.get('port_id'))
        if key not in counts:
            counts[key] = _macs_on_port(entry)
        return counts[key]
    first = pick_edge_port(entries, counter, rt.librenms_fdb_exclude, _uplink_re())
    if first is None:
        return None
    data = {
        'device_name': first.get('sysName', ''),
        'hostname': first.get('hostname', ''),
        'port': first.get('ifName', ''),
        'port_id': first.get('ifIndex', ''),
        'vlan': first.get('vlan', ''),
    }
    data.update(first)  # Include all original fields for debugging
    data['macs_on_port'] = counter(first)    # check-in: more than a few means not one PC (checkin.py)
    return data


NOT_FOUND_TTL = 10   # an IP LibreNMS doesn't know (yet): not asked again on every page load


def resolve_ip_to_switch_port(ip_address, search_device=None):
    """{ip, mac, device_name, hostname, port, vlan, stats, ...} for an IP, or None.

    Where the IP sits is cached (``cache.ttl_resolve``) and asked for once when many ask at the
    same time; the port's numbers (``stats``) are always live. Anything that isn't an IP address is
    None without asking LibreNMS."""
    ip = _ip(ip_address)
    if ip is None:
        return None
    where = _resolved.load(ip, lambda: _locate(ip), lambda: rt.cache_ttl_resolve, keep=lambda r: bool(r))
    if not where:
        if _resolved.get(ip)[0] is False:
            _resolved.put(ip, None, NOT_FOUND_TTL)
        return None
    result = dict(where)
    result['stats'] = fetch_librenms_device_port_stats_by_interface(result.get('hostname'), result.get('port')) \
        if result.get('hostname') else {}
    return result


def _locate(ip_address):
    """Where an IP sits, from LibreNMS's ARP (the core) and MAC tables (the access switch), or None.
    Cached in Redis too, for the other pods."""
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
    try:
        cached = client.get(resolve_cache_key) if client else None
        cached_result = json.loads(cached) if cached else None
    except (redis.RedisError, ValueError) as e:
        print(f"Redis cache read error (resolve): {e}")
        cached_result = None
    if isinstance(cached_result, dict) and cached_result.get('mac'):
        cached_result.pop('stats', None)     # the caller asks for live ones
        return cached_result

    if client:
        try:
            cache_key = f"arp_ip:{ip_address}"
            cached = client.get(cache_key)
            if cached:
                # Cast cached to proper type for json.loads
                cached_str = str(cached)
                arp_entries = json.loads(cached_str)
                # Find the MAC address for the IP
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
    if switch_info is not None:
        result['device_name'] = switch_info.get('device_name')
        result['hostname'] = switch_info.get('hostname')
        result['port'] = switch_info.get('port')
        result['vlan'] = switch_info.get('vlan')

        result.update(switch_info)  # Include all original fields for debugging

    if client:
        try:
            client.setex(resolve_cache_key, rt.cache_ttl_resolve, json.dumps(result))
        except redis.RedisError as e:
            print(f"Redis cache write error (resolve): {e}")

    return result

def best_device(candidates, hostname):
    """The candidate that is ``hostname``: the same display name, hostname or sysName, else the same
    short name (before the first dot), else the one candidate whose name contains it. None when
    several only contain it: ``sw-a1`` must not turn into ``sw-a10`` by the order LibreNMS lists them."""
    hn = (hostname or '').strip().lower()
    if not hn:
        return None
    short = hn.split('.')[0]

    def names(d):
        return [str(d.get(k) or '').lower() for k in ('display', 'hostname', 'sysName')]
    for test in (lambda n: n == hn, lambda n: n.split('.')[0] == short):
        for d in candidates:
            if any(n and test(n) for n in names(d)):
                return d
    partial = [d for d in candidates if any(hn in n for n in names(d))]
    return partial[0] if len(partial) == 1 else None


def fetch_librenms_device_by_hostname(hostname, headers):
    """The LibreNMS device for a switch name from the inventory, or None (see ``best_device``).
    Kept a few minutes: every port, MAC table and seat lookup starts here."""
    if not hostname:
        return None
    key = (rt.librenms_url, str(hostname).lower())
    found, device = _devices.get(key)
    if found:
        return device
    try:
        device = _devices.load(key, lambda: _search_device(hostname, headers), DEVICE_TTL,
                               keep=lambda d: d is not None)
    except (requests.RequestException, ValueError):
        return None          # LibreNMS didn't answer: ask again next time
    if device is None:       # LibreNMS answered and doesn't know it
        _devices.put(key, None, UNKNOWN_DEVICE_TTL)
    return device


def _search_device(hostname, headers):
    resp = breaker.get(
        f'{rt.librenms_url}/api/v0/devices',
        headers=headers,
        params={'type': 'display', 'query': hostname.split('.')[0]},   # short name: the broader search
        timeout=10, verify=rt.librenms_verify_ssl,
    )
    if not resp.ok:
        raise requests.HTTPError(f'LibreNMS answered {resp.status_code}')
    return best_device(resp.json().get('devices', []) or [], hostname)


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
    device_id = _seg(device.get('device_id') or device.get('hostname'))
    try:
        resp = breaker.get(
            f'{rt.librenms_url}/api/v0/devices/{device_id}',
            headers=headers, timeout=10, verify=rt.librenms_verify_ssl,
        )
        if resp.ok:
            device_data = resp.json().get('devices', [{}])[0] if resp.json().get('devices') else {}
            # The search above is kept for minutes; this answer is fresh. A switch that went down
            # or came back would otherwise show its old status until the search is asked again.
            if 'status' in device_data:
                result['status'] = 'online' if str(device_data['status']).lower() in ('1', 'true') else 'offline'
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
        resp = breaker.get(
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
        resp = breaker.get(
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
        rows = _port_rows.load((rt.librenms_url, device_id), lambda: librenms_ports.fetch_ports(
            rt.librenms_url, headers, device_id, verify=rt.librenms_verify_ssl), PORT_ROWS_TTL,
            keep=lambda r: r is not None)
        port = next((p for p in rows or [] if p.get('ifName') == interface), None)
        if port:
            result = librenms_ports.summarize_port(port, rt.librenms_url, device.get('device_id'))
    except requests.RequestException:
        pass

    return result


def fetch_device_ports(hostname):
    """Every port of one switch, summarised like port_stats plus its name, last change and what
    discovery takes as the interface's (mac, ips, vlan, mode; facts.port_facts)."""
    headers = {'X-Auth-Token': rt.librenms_token, 'Accept': 'application/json'}
    device = fetch_librenms_device_by_hostname(hostname, headers)
    if not device:
        return []
    device_id = _seg(device.get('device_id') or device.get('hostname'))
    rows = librenms_ports.fetch_ports(
        rt.librenms_url, headers, device_id, verify=rt.librenms_verify_ssl,
        tiers=(librenms_ports.FACT_COLUMNS, librenms_ports.WATCH_COLUMNS, librenms_ports.DETAIL_COLUMNS,
               librenms_ports.BASE_COLUMNS)) or []
    ips = librenms_facts.ips_by_port(device_id) if rows else {}
    return [{'name': row.get('ifName'), 'last_change': row.get('ifLastChange'),
             **librenms_ports.summarize_port(row, rt.librenms_url, device.get('device_id')),
             **librenms_facts.port_facts(row, ips)}
            for row in rows if row.get('ifName')]


def device_facts(hostname):
    """What LibreNMS knows the device is (VLANs, networks, optics), shaped like telemetry's
    ``Device.summary()``; {} when LibreNMS doesn't know it."""
    headers = {'X-Auth-Token': rt.librenms_token, 'Accept': 'application/json'}
    device = fetch_librenms_device_by_hostname(hostname, headers)
    if not device:
        return {}
    device_id = _seg(device.get('device_id') or device.get('hostname'))
    ports = librenms_ports.fetch_ports(rt.librenms_url, headers, device_id, verify=rt.librenms_verify_ssl,
                                       tiers=(['port_id', 'ifIndex', 'ifName'],)) or []
    return librenms_facts.summary(device_id, ports)


def list_devices():
    """Every LibreNMS device, as the API returns it (status, display, hostname, sysName, ...).
    Raises on failure, so the status monitor can show the error."""
    resp = breaker.get(f'{rt.librenms_url}/api/v0/devices',
                        headers={'X-Auth-Token': rt.librenms_token, 'Accept': 'application/json'},
                        timeout=15, verify=rt.librenms_verify_ssl)
    resp.raise_for_status()
    return resp.json().get('devices', []) or []


def arp_entries(query):
    """ARP rows matching an IP or a MAC ([] when LibreNMS has none)."""
    resp = breaker.get(f'{rt.librenms_url}/api/v0/resources/ip/arp/{_seg(query)}',
                        headers={'X-Auth-Token': rt.librenms_token, 'Accept': 'application/json'},
                        timeout=10, verify=rt.librenms_verify_ssl)
    if not resp.ok:
        return []
    return resp.json().get('arp', []) or []


def port_clients(hostname):
    """A switch's MAC table by port name: [{"port", "mac", "vlan"}]. Raises when LibreNMS can't say,
    so the cables page names the switch instead of showing it as empty."""
    headers = {'X-Auth-Token': rt.librenms_token, 'Accept': 'application/json'}
    device = fetch_librenms_device_by_hostname(hostname, headers)
    if not device:
        raise LookupError(f'LibreNMS does not know {hostname}')
    device_id = _seg(device.get('device_id') or device.get('hostname'))
    ports = librenms_ports.fetch_ports(rt.librenms_url, headers, device_id, verify=rt.librenms_verify_ssl,
                                       tiers=(['port_id', 'ifName'],))
    if ports is None:
        raise LookupError(f'LibreNMS did not list the ports of {hostname}')
    names = {p.get('port_id'): p.get('ifName') for p in ports if p.get('ifName')}
    resp = breaker.get(f'{rt.librenms_url}/api/v0/devices/{device_id}/fdb', headers=headers,
                        timeout=15, verify=rt.librenms_verify_ssl)
    resp.raise_for_status()
    body = resp.json()
    # Either key: the LibreNMS API docs say "ports_fdb", the older code here read "fdb".
    rows = body.get('ports_fdb') or body.get('fdb') or []
    return [{'port': names[r.get('port_id')], 'mac': r.get('mac_address'), 'vlan': r.get('vlan_id')}
            for r in rows if r.get('port_id') in names and r.get('mac_address')]


def neighbours(hostname):
    """What a switch sees on its ports by LLDP or CDP: [{"port", "remote", "remote_port", "protocol"}]."""
    headers = {'X-Auth-Token': rt.librenms_token, 'Accept': 'application/json'}
    device = fetch_librenms_device_by_hostname(hostname, headers)
    if not device:
        raise LookupError(f'LibreNMS does not know {hostname}')
    device_id = _seg(device.get('device_id') or device.get('hostname'))
    ports = librenms_ports.fetch_ports(rt.librenms_url, headers, device_id, verify=rt.librenms_verify_ssl,
                                       tiers=(['port_id', 'ifName'],))
    if ports is None:
        raise LookupError(f'LibreNMS did not list the ports of {hostname}')
    names = {p.get('port_id'): p.get('ifName') for p in ports if p.get('ifName')}
    resp = breaker.get(f'{rt.librenms_url}/api/v0/devices/{device_id}/links', headers=headers,
                        timeout=15, verify=rt.librenms_verify_ssl)
    resp.raise_for_status()
    return [{'port': names[r.get('local_port_id')], 'remote': r.get('remote_hostname'),
             'remote_port': r.get('remote_port'), 'protocol': r.get('protocol') or ''}
            for r in resp.json().get('links') or []
            if r.get('local_port_id') in names and r.get('remote_hostname') and r.get('remote_port')]
