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
import ipaddress
import random
import socket
import struct
import time

from integrations import config

TIMEOUT = 2.0
PROBE_PORTS = (53, 80, 443, 853)   # what a TCP probe may connect to: answered by any server, never sent data
RCODES = {0: 'NOERROR', 1: 'FORMERR', 2: 'SERVFAIL', 3: 'NXDOMAIN', 4: 'NOTIMP', 5: 'REFUSED'}
MAX_COUNT = 10
DNS_PORT = 53


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
        ip = ipaddress.ip_address(addr.split('%')[0])
        if ip.is_link_local or ip.is_unspecified or ip.is_multicast:
            continue
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
