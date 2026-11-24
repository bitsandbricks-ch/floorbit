"""Small network probes for the services view (issue #471), with the standard library only.

- **DNS**: one A query over UDP to a resolver; how long it took, the answer code and how many
  addresses came back.
- **TCP**: a few connects to a host and port; the average time and how many got no answer. ICMP
  ping needs a raw socket (root); a TCP connect to a port the target always answers (443 on a
  public web server, 53 on a resolver) measures the same path without it.

Each call opens its own socket with a short timeout and closes it again. The local agent runs the
same functions on the event network for a hosted Floorbit.

``target`` decides what the server itself may reach (also for game server queries and RCON): never
link-local addresses (the cloud metadata service lives there), and only ``PROBE_NETS`` when it is set,
so a hosted Floorbit can't be pointed at its own network.
"""
import http.client
import ipaddress
import random
import socket
import ssl
import struct
import time
from urllib.parse import urlsplit

from integrations import config

TIMEOUT = 2.0
PROBE_PORTS = (53, 80, 443, 853)   # what a TCP probe may connect to: answered by any server, never sent data
RCODES = {0: 'NOERROR', 1: 'FORMERR', 2: 'SERVFAIL', 3: 'NXDOMAIN', 4: 'NOTIMP', 5: 'REFUSED'}
MAX_COUNT = 10
DNS_PORT = 53
_stand_in = None


def stand_in(answer):
    """Demo mode (floorbit/blueprints/demo.py) answers for its made-up servers, so nothing is sent out.
    ``answer(method, args)`` returns what the probe would, or None to send it for real."""
    global _stand_in
    _stand_in = answer


def stood_in(method, args):
    return _stand_in(method, args) if _stand_in is not None else None


class ProbeError(RuntimeError):
    pass


def _nets():
    out = []
    for entry in (config.get('PROBE_NETS', '') or '').split(','):
        try:
            out.append(ipaddress.ip_network(entry.strip(), strict=False))
        except ValueError:
            continue
    return out


NAT64 = (ipaddress.ip_network('64:ff9b::/96'), ipaddress.ip_network('64:ff9b:1::/48'))


def _embedded(ip):
    """The IPv4 address an IPv6 one reaches through, if any: ::ffff:a.b.c.d (mapped), 2002:: (6to4)
    and 64:ff9b:: (NAT64, where the last 32 bits are the IPv4 address). On a network with NAT64,
    64:ff9b::a9fe:a9fe is the metadata service at 169.254.169.254."""
    if ip.version != 6:
        return ip
    if ip.ipv4_mapped or ip.sixtofour:
        return ip.ipv4_mapped or ip.sixtofour
    if any(ip in net for net in NAT64):
        return ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
    return ip


def unreachable(addr):
    """Is ``addr`` (an address string) one the server never sends anything to: link-local (the
    cloud metadata service lives there), unspecified or multicast? Webhooks ask the same."""
    ip = ipaddress.ip_address(str(addr).split('%')[0])
    return any(i.is_link_local or i.is_unspecified or i.is_multicast for i in (ip, _embedded(ip)))


def target(host):
    """The address the server may probe for ``host``, or ProbeError. Host names are resolved here so
    that the check sees the address that is connected to."""
    host = str(host or '').strip()
    try:
        addrs = {info[4][0] for info in socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)}
    except (OSError, UnicodeError):
        raise ProbeError(f'{host} cannot be resolved.') from None
    nets = _nets()
    for addr in sorted(addrs):
        if unreachable(addr):
            continue
        ip = ipaddress.ip_address(addr.split('%')[0])
        ip = getattr(ip, 'ipv4_mapped', None) or ip
        if not nets or any(ip in net for net in nets):
            return str(ip)
    raise ProbeError(f'{host} is not an address Floorbit may probe.')


def _ms(start):
    return round((time.monotonic() - start) * 1000, 1)


def _name(name):
    out = b''
    for label in str(name).strip('.').split('.'):
        raw = label.encode('idna')
        if not 0 < len(raw) < 64:
            raise ProbeError('The test name is not a domain name.')
        out += bytes([len(raw)]) + raw
    return out + b'\x00'


def dns(server, name, timeout=TIMEOUT):
    """``{"ms", "rcode", "answers"}`` for one A query of ``name`` at ``server`` (an IP, port 53)."""
    qid = random.randrange(1 << 16)
    packet = struct.pack('>HHHHHH', qid, 0x0100, 1, 0, 0, 0) + _name(name) + struct.pack('>HH', 1, 1)
    family = socket.AF_INET6 if ':' in str(server) else socket.AF_INET
    start = time.monotonic()
    with socket.socket(family, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout)
        try:
            sock.sendto(packet, (str(server), DNS_PORT))
            while True:
                data, _addr = sock.recvfrom(4096)
                if len(data) >= 12 and struct.unpack('>H', data[:2])[0] == qid:
                    break
        except TimeoutError:
            raise ProbeError('The resolver did not answer.') from None
        except OSError as exc:
            raise ProbeError(f'The resolver did not answer: {exc.strerror or exc}') from None
    flags, _qd, answers = struct.unpack('>HHH', data[2:8])
    code = flags & 0x0F
    return {'ms': _ms(start), 'rcode': RCODES.get(code, str(code)), 'answers': answers}


def tcp(host, port, count=5, timeout=TIMEOUT):
    """``{"sent", "lost", "avg_ms"}`` for ``count`` connects to ``host``:``port``."""
    if int(port) not in PROBE_PORTS:
        raise ProbeError(f"The probe port is one of {', '.join(map(str, PROBE_PORTS))}.")
    count = max(1, min(int(count), MAX_COUNT))
    times = []
    for _ in range(count):
        start = time.monotonic()
        try:
            with socket.create_connection((str(host), int(port)), timeout=timeout):
                times.append(_ms(start))
        except OSError:
            continue
    return {'sent': count, 'lost': count - len(times),
            'avg_ms': round(sum(times) / len(times), 1) if times else None}


# ── own checks (issue #1338) ────────────────────────────────────────────────
# A crew's own checks on the Services page: ping, a TCP port, a UDP port or an HTTP(S) address. They
# only ever run on the local agent (agent-only LAN access); ``resolve`` is the agent's own rule for
# what it may reach. A TCP check connects and sends nothing; a UDP check sends one harmless question
# of a known protocol (or an empty datagram); an HTTP check sends a plain GET and keeps the status,
# the time and the certificate's end, never the page.
CHECK_KINDS = ('ping', 'tcp', 'udp', 'http')
UDP_ASKS = ('dns', 'ntp', 'a2s', 'none')
CHECK_TRIES = 3
HTTP_TIMEOUT = 5.0
HTTP_READ = 65536           # enough of a page to look for a word in
_UDP_QUESTIONS = {
    'ntp': b'\x1b' + 47 * b'\x00',                                # a client asking for the time
    'a2s': b'\xff\xff\xff\xffTSource Engine Query\x00',           # Steam/Source "who are you"
}


def _family(ip):
    return socket.AF_INET6 if ':' in str(ip) else socket.AF_INET


def ping(ip, count=CHECK_TRIES, timeout=TIMEOUT):
    """``{"sent", "lost", "avg_ms"}`` for ``count`` ICMP echoes. Uses the unprivileged ICMP socket
    Linux offers (``net.ipv4.ping_group_range``, open in Docker by default), so no root."""
    v6 = _family(ip) == socket.AF_INET6
    try:
        sock = socket.socket(_family(ip), socket.SOCK_DGRAM, socket.IPPROTO_ICMPV6 if v6 else socket.IPPROTO_ICMP)
    except OSError:
        raise ProbeError('This machine does not allow ping without root (net.ipv4.ping_group_range). '
                         'Check a TCP port instead.') from None
    times = []
    with sock:
        sock.settimeout(timeout)
        for seq in range(1, count + 1):
            # The kernel sets the identifier and the checksum on this kind of socket.
            packet = struct.pack('>BBHHH', 128 if v6 else 8, 0, 0, 0, seq) + b'floorbit'
            start = time.monotonic()
            try:
                sock.sendto(packet, (str(ip), 0))
                while True:
                    data = sock.recv(1024)
                    if len(data) >= 8 and data[0] == (129 if v6 else 0) and struct.unpack('>H', data[6:8])[0] == seq:
                        times.append(_ms(start))
                        break
            except OSError:
                continue
    return {'sent': count, 'lost': count - len(times), 'avg_ms': round(sum(times) / len(times), 1) if times else None}


def tcp_any(ip, port, count=CHECK_TRIES, timeout=TIMEOUT):
    """Like ``tcp`` for any port: connects only, sends nothing."""
    times = []
    for _ in range(count):
        start = time.monotonic()
        try:
            with socket.create_connection((str(ip), int(port)), timeout=timeout):
                times.append(_ms(start))
        except OSError:
            continue
    return {'sent': count, 'lost': count - len(times), 'avg_ms': round(sum(times) / len(times), 1) if times else None}


def udp(ip, port, ask, timeout=TIMEOUT):
    """``{"answered", "ms", "closed"}`` for one question to a UDP port. UDP has no handshake: an answer
    says it is up, an ICMP "port unreachable" (``closed``) says it is down, silence says nothing."""
    if ask == 'dns':
        # Any answer counts, even "refused": the server is there.
        packet = struct.pack('>HHHHHH', random.randrange(1 << 16), 0x0100, 1, 0, 0, 0) + _name('example.com') \
            + struct.pack('>HH', 1, 1)
    else:
        packet = _UDP_QUESTIONS.get(ask, b'')
    with socket.socket(_family(ip), socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout)
        start = time.monotonic()
        try:
            sock.connect((str(ip), int(port)))
            sock.send(packet)
            sock.recv(2048)
        except ConnectionRefusedError:
            return {'answered': False, 'ms': None, 'closed': True}
        except TimeoutError:
            return {'answered': False, 'ms': None, 'closed': False}
        except OSError as exc:
            raise ProbeError(f'The port did not answer: {exc.strerror or exc}') from None
        return {'answered': True, 'ms': _ms(start), 'closed': False}


def http_get(url, resolve, contains='', timeout=HTTP_TIMEOUT):
    """``{"code", "ms", "cert_days", "found"}`` for one GET of ``url``. ``resolve(host)`` gives the
    address it may connect to; the name still goes in the Host header and the TLS handshake."""
    parts = urlsplit(str(url))
    if parts.scheme not in ('http', 'https') or not parts.hostname:
        raise ProbeError('The address is a URL starting with http:// or https://.')
    if any(ord(c) < 33 or ord(c) == 127 for c in str(url)):
        raise ProbeError('The address has no spaces or control characters.')
    secure = parts.scheme == 'https'
    port = parts.port or (443 if secure else 80)
    ip = resolve(parts.hostname)
    path = (parts.path or '/') + (f'?{parts.query}' if parts.query else '')
    host = parts.hostname if parts.port in (None, 443 if secure else 80) else f'{parts.hostname}:{port}'
    start = time.monotonic()
    cert_days = None
    try:
        sock = socket.create_connection((ip, port), timeout=timeout)
        if secure:
            context = ssl.create_default_context()
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            sock = context.wrap_socket(sock, server_hostname=parts.hostname)
            ends = (sock.getpeercert() or {}).get('notAfter')
            if ends:
                cert_days = int((ssl.cert_time_to_seconds(ends) - time.time()) // 86400)
        with sock:
            sock.sendall(f'GET {path} HTTP/1.1\r\nHost: {host}\r\nUser-Agent: Floorbit-check\r\n'
                         'Accept: */*\r\nConnection: close\r\n\r\n'.encode())
            resp = http.client.HTTPResponse(sock)
            resp.begin()
            found = None
            if contains:
                found = contains.lower() in resp.read(HTTP_READ).decode('utf-8', 'replace').lower()
            return {'code': resp.status, 'ms': _ms(start), 'cert_days': cert_days, 'found': found}
    except ssl.SSLCertVerificationError as exc:
        raise ProbeError(f'The certificate is not valid: {exc.verify_message or exc}') from None
    except (OSError, http.client.HTTPException) as exc:
        raise ProbeError(f'No answer: {getattr(exc, "strerror", None) or exc}') from None


def check(spec, resolve=None):
    """Run one own check (``spec`` as floorbit/services.py keeps it) and return what it saw:
    ``{"kind", "sent", "lost", "ms", "code", "cert_days", "found", "closed", "answered"}``."""
    resolve = resolve or target
    kind = spec.get('kind')
    if kind not in CHECK_KINDS:
        raise ProbeError('The check is ping, tcp, udp or http.')
    if kind == 'http':
        return {'kind': kind, **http_get(spec.get('url'), resolve, str(spec.get('contains') or '')[:100])}
    ip = resolve(spec.get('host'))
    if kind == 'ping':
        got = ping(ip)
        return {'kind': kind, 'sent': got['sent'], 'lost': got['lost'], 'ms': got['avg_ms']}
    port = int(spec.get('port') or 0)
    if not 1 <= port <= 65535:
        raise ProbeError('The port is a number from 1 to 65535.')
    if kind == 'tcp':
        got = tcp_any(ip, port)
        return {'kind': kind, 'sent': got['sent'], 'lost': got['lost'], 'ms': got['avg_ms']}
    ask = spec.get('ask') if spec.get('ask') in UDP_ASKS else 'none'
    return {'kind': kind, **udp(ip, port, ask)}
