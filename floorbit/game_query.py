"""Asking a game server how it is (issue #472), with the standard library only.

- **A2S** (Valve's server query, UDP): Counter-Strike, Team Fortress, Rust, ARK, Valheim and most
  other Source and Steam games. Name, map, players, bots, version.
- **Minecraft** server list ping (TCP): version, players, the message of the day.
- **TCP**: only whether the port answers, for games with neither.
- **RCON** (Source RCON over TCP, also what Minecraft speaks): one command, its answer.

Each function opens its own socket with a short timeout and closes it again; nothing is kept. The
local agent runs the same functions on the event network for a hosted Floorbit.
"""
import json
import socket
import struct
import time

TIMEOUT = 2.0
MAX_ANSWER = 64 * 1024      # an RCON answer is cut here (a "status" of a full server is ~10 KB)
PROTOCOLS = ('a2s', 'minecraft', 'tcp')


class QueryError(RuntimeError):
    pass


def _ms(start):
    return round((time.monotonic() - start) * 1000, 1)


# ── A2S ─────────────────────────────────────────────────────────────────────
A2S_INFO = b'\xff\xff\xff\xffTSource Engine Query\x00'


def _cstr(data, at):
    end = data.index(b'\x00', at)
    return data[at:end].decode('utf-8', 'replace'), end + 1


def parse_a2s_info(data):
    """The fields of an A2S_INFO answer (after the 0xFFFFFFFF 'I' header)."""
    at = 1                                  # protocol version
    name, at = _cstr(data, at)
    map_, at = _cstr(data, at)
    _folder, at = _cstr(data, at)
    game, at = _cstr(data, at)
    at += 2                                 # Steam app id
    players, max_players, bots = data[at], data[at + 1], data[at + 2]
    at += 7                                 # server type, environment, visibility, VAC
    version = _cstr(data, at)[0] if at < len(data) else ''
    return {'name': name, 'map': map_, 'game': game, 'players': players, 'max_players': max_players,
            'bots': bots, 'version': version}


def a2s(host, port, timeout=TIMEOUT):
    start = time.monotonic()
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout)
        try:
            sock.sendto(A2S_INFO, (host, int(port)))
            data = sock.recv(1400)
            # Newer servers first answer with a challenge, to be sent back with the query.
            if data[4:5] == b'A':
                sock.sendto(A2S_INFO + data[5:9], (host, int(port)))
                data = sock.recv(1400)
        except TimeoutError:
            raise QueryError('No answer to the server query.') from None
        except OSError as exc:
            raise QueryError(f'The server query failed: {exc.strerror or exc}') from None
    ping = _ms(start)
    if data[:4] != b'\xff\xff\xff\xff' or data[4:5] != b'I':
        raise QueryError('The server answered something that is not a server query answer.')
    try:
        info = parse_a2s_info(data[5:])
    except (ValueError, IndexError):
        raise QueryError('The server query answer is cut short.') from None
    return {**info, 'ping_ms': ping}


# ── Minecraft server list ping ──────────────────────────────────────────────
def _varint(value):
    out = b''
    value &= 0xFFFFFFFF
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out += bytes([byte | 0x80])
        else:
            return out + bytes([byte])


def _read_exact(sock, n):
    data = b''
    while len(data) < n:
        chunk = sock.recv(n - len(data))
        if not chunk:
            raise QueryError('The server closed the connection.')
        data += chunk
    return data


def _read_varint(sock):
    value = 0
    for shift in range(0, 35, 7):
        byte = _read_exact(sock, 1)[0]
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value
    raise QueryError('The server answered something that is not a Minecraft status.')


def _motd(description):
    if isinstance(description, str):
        return description
    if isinstance(description, dict):
        return (description.get('text') or '') + ''.join(_motd(part) for part in description.get('extra') or [])
    return ''


def minecraft(host, port, timeout=TIMEOUT):
    start = time.monotonic()
    try:
        with socket.create_connection((host, int(port)), timeout=timeout) as sock:
            sock.settimeout(timeout)
            addr = str(host).encode('utf-8')
            handshake = (b'\x00' + _varint(-1 & 0xFFFFFFFF) + _varint(len(addr)) + addr
                         + struct.pack('>H', int(port)) + _varint(1))
            sock.sendall(_varint(len(handshake)) + handshake + b'\x01\x00')
            length = _read_varint(sock)
            if length > 1 << 20:
                raise QueryError('The Minecraft status is too long.')
            body = _read_exact(sock, length)
    except TimeoutError:
        raise QueryError('No answer to the server query.') from None
    except OSError as exc:
        raise QueryError(f'The server query failed: {exc.strerror or exc}') from None
    ping = _ms(start)
    if not body or body[0] != 0:
        raise QueryError('The server answered something that is not a Minecraft status.')
    at, text_len, shift = 1, 0, 0
    while True:                                  # the JSON's length, a varint inside the packet
        byte = body[at]
        text_len |= (byte & 0x7F) << shift
        at, shift = at + 1, shift + 7
        if not byte & 0x80:
            break
    try:
        status = json.loads(body[at:at + text_len].decode('utf-8'))
    except ValueError:
        raise QueryError('The server answered something that is not a Minecraft status.') from None
    players = status.get('players') or {}
    return {'name': ' '.join(_motd(status.get('description')).split())[:120], 'map': '',
            'game': 'Minecraft', 'players': int(players.get('online') or 0),
            'max_players': int(players.get('max') or 0), 'bots': 0,
            'version': str((status.get('version') or {}).get('name') or '')[:40], 'ping_ms': ping}


def tcp(host, port, timeout=TIMEOUT):
    start = time.monotonic()
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            pass
    except TimeoutError:
        raise QueryError('The port did not answer.') from None
    except OSError as exc:
        raise QueryError(f'The port did not answer: {exc.strerror or exc}') from None
    return {'ping_ms': _ms(start)}


def query(protocol, host, port, timeout=TIMEOUT):
    """``{"ping_ms", ...}`` for a server that answers; QueryError for one that doesn't."""
    if protocol not in PROTOCOLS:
        raise QueryError(f'{protocol} is not a query Floorbit knows.')
    return {'a2s': a2s, 'minecraft': minecraft, 'tcp': tcp}[protocol](host, port, timeout)


# ── RCON ────────────────────────────────────────────────────────────────────
AUTH, AUTH_RESPONSE, EXEC, RESPONSE = 3, 2, 2, 0


def _packet(req_id, kind, body):
    payload = struct.pack('<ii', req_id, kind) + body.encode('utf-8') + b'\x00\x00'
    return struct.pack('<i', len(payload)) + payload


def _read_packet(sock):
    size = struct.unpack('<i', _read_exact(sock, 4))[0]
    if size < 10 or size > 1 << 16:
        raise QueryError('The server sent an RCON packet Floorbit cannot read.')
    data = _read_exact(sock, size)
    req_id, kind = struct.unpack('<ii', data[:8])
    return req_id, kind, data[8:-2].decode('utf-8', 'replace')


def rcon(host, port, password, command, timeout=TIMEOUT * 2):
    """Send one command; returns the server's answer (text, cut at MAX_ANSWER)."""
    try:
        with socket.create_connection((host, int(port)), timeout=timeout) as sock:
            sock.settimeout(timeout)
            sock.sendall(_packet(1, AUTH, password))
            while True:                  # Source sends an empty RESPONSE before the AUTH_RESPONSE
                req_id, kind, _ = _read_packet(sock)
                if kind == AUTH_RESPONSE:
                    break
            if req_id == -1:
                raise QueryError('The server refused the RCON password.')
            sock.sendall(_packet(2, EXEC, command))
            parts = []
            req_id, kind, body = _read_packet(sock)
            parts.append(body)
            # Long answers come in several packets; take what follows closely.
            sock.settimeout(0.3)
            try:
                while sum(map(len, parts)) < MAX_ANSWER:
                    req_id, kind, body = _read_packet(sock)
                    if req_id == 2:
                        parts.append(body)
            except (TimeoutError, QueryError):
                pass
    except TimeoutError:
        raise QueryError('The server did not answer on its RCON port.') from None
    except OSError as exc:
        raise QueryError(f'RCON failed: {exc.strerror or exc}') from None
    return ''.join(parts)[:MAX_ANSWER]
