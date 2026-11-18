"""DHCP leases from the DHCP server's syslog: a fresh IP to MAC source (issue #520, docs/syslog.md).

A DHCP server that sends its syslog to Floorbit (straight, or through the local agent's syslog
relay) tells who got which address the moment it happens. LibreNMS or telemetry ARP only knows it
after the next poll, so check-in, the seat walk and the IP search look here first and fall back to
ARP. Read from the lines of the servers events use, so the event's choice doesn't matter:

- ISC dhcpd (and pfSense/OPNsense with it): ``DHCPACK on 192.0.2.10 to aa:bb:cc:dd:ee:ff ...``
- Kea (and OPNsense with it): ``DHCP4_LEASE_ALLOC [hwtype=1 aa:bb:...], ...: lease 192.0.2.10 has
  been allocated for 3600 seconds``
- dnsmasq (and Pi-hole): ``DHCPACK(eth0) 192.0.2.10 aa:bb:cc:dd:ee:ff laptop``
- MikroTik: ``dhcp1 assigned 192.0.2.10 to AA:BB:CC:DD:EE:FF``

and the matching release lines. A lease is kept in Valkey (shared by every pod; in memory without
it) until its time runs out: Kea's own lease time, else ``DEFAULT_TTL``. Only the address pair is
kept, never the host name the line may carry.
"""
import ipaddress
import re
import threading
import time

DEFAULT_TTL = 12 * 3600       # dhcpd and dnsmasq don't log the lease time; an event's leases are hours
MIN_TTL, MAX_TTL = 60, 7 * 86400
MAC = r'([0-9A-Fa-f]{2}(?:[:-][0-9A-Fa-f]{2}){5})'
IP = r'(\d{1,3}(?:\.\d{1,3}){3})'

# (kind, pattern): the pattern's groups are ip and mac in the order the line has them.
GRANTS = (
    ('dhcpd', re.compile(rf'\bDHCPACK on {IP} to {MAC}')),
    ('dnsmasq', re.compile(rf'\bDHCPACK\([^)]*\) {IP} {MAC}')),
    ('mikrotik', re.compile(rf'\bassigned {IP} (?:for|to) {MAC}')),
)
RELEASES = (
    ('dhcpd', re.compile(rf'\bDHCPRELEASE of {IP} from {MAC}')),
    ('dnsmasq', re.compile(rf'\bDHCPRELEASE\([^)]*\) {IP} {MAC}')),
    ('mikrotik', re.compile(rf'\bdeassigned {IP} (?:for|from) {MAC}')),
)
KEA_GRANT = re.compile(rf'\bDHCP4_LEASE_ALLOC \[hwtype=\d+ {MAC}\].*?\blease {IP} has been allocated'
                       r'(?: for (\d+) seconds)?')
KEA_RELEASE = re.compile(rf'\bDHCP4_RELEASE \[hwtype=\d+ {MAC}\].*?\baddress {IP} was released')


def _mac(text):
    digits = re.sub(r'[^0-9a-f]', '', text.lower())
    return ':'.join(digits[i:i + 2] for i in range(0, 12, 2))


def _ip(text):
    try:
        addr = ipaddress.IPv4Address(text)
    except ValueError:
        return None
    return None if addr.is_unspecified or addr.is_multicast or addr.is_loopback else str(addr)


def parse(message):
    """("grant" | "release", ip, mac, ttl or None) for a lease line, else None."""
    message = str(message or '')
    if 'DHCP' not in message and 'assigned' not in message:
        return None          # most lines: one cheap look
    m = KEA_GRANT.search(message)
    if m:
        ip = _ip(m[2])
        return ('grant', ip, _mac(m[1]), int(m[3]) if m[3] else None) if ip else None
    m = KEA_RELEASE.search(message)
    if m:
        ip = _ip(m[2])
        return ('release', ip, _mac(m[1]), None) if ip else None
    for kind, table in (('grant', GRANTS), ('release', RELEASES)):
        for _server, rx in table:
            m = rx.search(message)
            if m:
                ip = _ip(m[1])
                return (kind, ip, _mac(m[2]), None) if ip else None
    return None


class Leases:
    """The current leases: ``ip:<ip>`` -> MAC and ``mac:<mac>`` -> IP, each with the lease's time."""

    def __init__(self):
        self._lock = threading.Lock()
        self._mem = {}           # without Valkey: key -> (value, expires)
        self.counts = {'granted': 0, 'released': 0}
        self.last_at = None

    # Valkey when it's there (every pod sees the same leases), else this process's memory.
    def _client(self):
        from .cache import get_redis_client
        return get_redis_client()

    def _get(self, key):
        client = self._client()
        if client is not None:
            try:
                value = client.get('dhcp:' + key)
                return value.decode() if isinstance(value, bytes) else value
            except Exception as exc:  # noqa: BLE001  # Valkey away: ARP answers instead
                print(f'[dhcp] lease read failed: {exc}')
                return None
        with self._lock:
            value, expires = self._mem.get(key, (None, 0))
            return value if expires > time.time() else None

    def _set(self, key, value, ttl):
        client = self._client()
        if client is not None:
            try:
                client.setex('dhcp:' + key, ttl, value)
            except Exception as exc:  # noqa: BLE001
                print(f'[dhcp] lease write failed: {exc}')
            return
        with self._lock:
            now = time.time()
            if len(self._mem) > 50000:      # a flood of made-up leases must not fill the memory
                self._mem = {k: v for k, v in self._mem.items() if v[1] > now}
            self._mem[key] = (value, now + ttl)

    def _delete(self, key):
        client = self._client()
        if client is not None:
            try:
                client.delete('dhcp:' + key)
            except Exception as exc:  # noqa: BLE001
                print(f'[dhcp] lease delete failed: {exc}')
            return
        with self._lock:
            self._mem.pop(key, None)

    def observe(self, message, now=None):
        """Take one syslog message. Returns what it said (see ``parse``), or None."""
        lease = parse(message)
        if not lease:
            return None
        kind, ip, mac, ttl = lease
        if kind == 'grant':
            ttl = min(MAX_TTL, max(MIN_TTL, ttl or DEFAULT_TTL))
            old_mac, old_ip = self._get('ip:' + ip), self._get('mac:' + mac)
            if old_mac and old_mac != mac and self._get('mac:' + old_mac) == ip:
                self._delete('mac:' + old_mac)     # the address moved to another machine
            if old_ip and old_ip != ip and self._get('ip:' + old_ip) == mac:
                self._delete('ip:' + old_ip)       # the machine got another address
            self._set('ip:' + ip, mac, ttl)
            self._set('mac:' + mac, ip, ttl)
        else:
            if self._get('ip:' + ip) == mac:
                self._delete('ip:' + ip)
            if self._get('mac:' + mac) == ip:
                self._delete('mac:' + mac)
        with self._lock:
            self.counts['granted' if kind == 'grant' else 'released'] += 1
            self.last_at = time.time() if now is None else now
        return lease

    def mac_for_ip(self, ip):
        ip = _ip(str(ip or '').strip())
        return self._get('ip:' + ip) if ip else None

    def ip_for_mac(self, mac):
        digits = re.sub(r'[^0-9a-f]', '', str(mac or '').lower())
        return self._get('mac:' + _mac(digits)) if len(digits) == 12 else None

    def reset(self):
        with self._lock:
            self._mem.clear()
            self.counts = {'granted': 0, 'released': 0}
            self.last_at = None

    def status(self):
        with self._lock:
            return {**self.counts, 'last_at': self.last_at}


leases = Leases()
