"""Syslog receiver (issue #91): switches, firewalls and DHCP servers send their logs; Floorbit keeps
them for a short while, finds the switch, port and seat a line is about, and lets the crew search
and follow them. See docs/syslog.md.

Secure by design:

- **Off by default.** ``SYSLOG_ENABLED`` turns the listener on (UDP, and TCP with ``SYSLOG_TCP``),
  on ``SYSLOG_PORT`` (5514, so no root is needed; map 514 to it in Docker).
- **Allow-list.** Only senders in ``SYSLOG_ALLOW`` (addresses and networks) and, with
  ``SYSLOG_ALLOW_SWITCHES`` (on), the switches' management addresses from the inventory. Anything
  else is dropped and counted.
- **Caps.** ``SYSLOG_RATE`` lines per second per sender (200, the rest dropped and counted),
  lines of at most 2 KB, at most ``SYSLOG_MAX_LINES`` (50,000) in memory and ``SYSLOG_MAX_MB``
  (100) on disk, kept ``SYSLOG_RETENTION_HOURS`` (24).

Lines are kept as received with what Floorbit worked out: the device (by sender address), the
severity, the program and the switch port and seat, when a port is named. Logs can name MACs and
IPs, so reading them needs ``seats.view``.
"""
import ipaddress
import json
import os
import re
import socketserver
import threading
import time
from collections import deque
from datetime import datetime

from integrations import config

from . import features, inventory, store

MAX_LINE = 2048
SEVERITIES = ('emerg', 'alert', 'crit', 'err', 'warning', 'notice', 'info', 'debug')
# RFC 3164: <PRI>Mmm dd hh:mm:ss host tag: msg   RFC 5424: <PRI>1 2026-11-14T10:00:00Z host app pid msgid - msg
RFC5424 = re.compile(r'^<(\d{1,3})>1 (\S+) (\S+) (\S+) (\S+) (\S+) (?:-|(?:\[.*?\])+) ?(.*)$', re.S)
RFC3164 = re.compile(r'^<(\d{1,3})>(?:([A-Z][a-z]{2} [ \d]\d \d\d:\d\d:\d\d) )?'
                     r'(?:(\S+) )?([^:\[\s]{1,48})(?:\[\d+\])?: ?(.*)$',
                     re.S)
PRI_ONLY = re.compile(r'^<(\d{1,3})>(.*)$', re.S)
# Interface names as switches write them, long and short.
PORT_PREFIXES = {
    'gigabitethernet': 'gi', 'gi': 'gi', 'tengigabitethernet': 'te', 'te': 'te', 'fastethernet': 'fa', 'fa': 'fa',
    'twentyfivegige': 'twe', 'twe': 'twe', 'fortygigabitethernet': 'fo', 'fo': 'fo', 'hundredgige': 'hu',
    'hu': 'hu', 'ethernet': 'eth', 'eth': 'eth', 'ether': 'ether', 'sfp-sfpplus': 'sfp-sfpplus', 'sfp': 'sfp',
    'port': 'port', 'interface': '',
}
PORT_RE = re.compile(r'\b(GigabitEthernet|TenGigabitEthernet|FastEthernet|TwentyFiveGigE|FortyGigabitEthernet|'
                     r'HundredGigE|Ethernet|Gi|Te|Fa|Twe|Fo|Hu|Eth|ether|sfp-sfpplus|sfp|port|interface)\s?'
                     r'(\d+(?:/\d+){0,3})\b', re.I)

_receiver = None


def settings():
    return {
        'enabled': config.get_bool('SYSLOG_ENABLED', False),
        'tcp': config.get_bool('SYSLOG_TCP', False),
        'port': config.get_int('SYSLOG_PORT', 5514, minimum=1),
        'bind': (config.get('SYSLOG_BIND') or '0.0.0.0').strip(),
        'allow': [a.strip() for a in (config.get('SYSLOG_ALLOW') or '').split(',') if a.strip()],
        'allow_switches': config.get_bool('SYSLOG_ALLOW_SWITCHES', True),
        'rate': config.get_int('SYSLOG_RATE', 200, minimum=1),
        'max_lines': config.get_int('SYSLOG_MAX_LINES', 50_000, minimum=100),
        'max_mb': config.get_int('SYSLOG_MAX_MB', 100, minimum=1),
        'retention_hours': config.get_int('SYSLOG_RETENTION_HOURS', 24, minimum=1),
    }


def canonical_port(name):
    """'GigabitEthernet1/0/4' and 'Gi1/0/4' are the same port: 'gi1/0/4'."""
    m = re.match(r'^\s*([A-Za-z-]*)\s*(\d+(?:/\d+)*)', str(name or ''))
    if not m:
        return str(name or '').strip().lower()
    prefix = PORT_PREFIXES.get(m.group(1).lower(), m.group(1).lower())
    return prefix + m.group(2)


def ports_in(message):
    """Canonical ports a line names, in order."""
    out = []
    for prefix, number in PORT_RE.findall(message):
        port = canonical_port(f'{prefix}{number}')
        if port not in out:
            out.append(port)
    return out


def parse(raw, now=None):
    """{"severity", "facility", "host", "program", "message", "ts"} for one received line."""
    now = time.time() if now is None else now
    text = raw.decode('utf-8', 'replace') if isinstance(raw, bytes) else str(raw)
    text = text.strip('\x00\r\n ')[:MAX_LINE]
    pri, host, program, message, ts = None, None, None, text, now
    m = RFC5424.match(text)
    if m:
        pri, stamp, host, program, message = int(m[1]), m[2], m[3], m[4], m[7]
        try:
            ts = datetime.fromisoformat(stamp.replace('Z', '+00:00')).timestamp()
        except ValueError:
            ts = now
    else:
        m = RFC3164.match(text)
        if m:
            pri, host, program, message = int(m[1]), m[3], m[4], m[5]
        else:
            m = PRI_ONLY.match(text)
            if m:
                pri, message = int(m[1]), m[2]
    if pri is None or pri > 191:
        pri = 13   # user.notice, what RFC 3164 says to assume
    host = None if host in (None, '-') else host[:80]
    program = None if program in (None, '-') else program[:48]
    if ts > now + 300 or ts < now - 7 * 86400:
        ts = now   # a switch with a wrong clock: when it arrived is better
    return {'ts': ts, 'facility': pri // 8, 'severity': SEVERITIES[pri % 8], 'host': host, 'program': program,
            'message': message.strip()[:MAX_LINE]}


class SyslogReceiver:
    def __init__(self, path=None):
        self.path = path
        self._lock = threading.Lock()
        self.lines = deque()
        self.next_id = 1
        self.counts = {'received': 0, 'kept': 0, 'not_allowed': 0, 'rate_limited': 0}
        self._buckets = {}      # sender -> [tokens, last]
        self._servers = []
        self._allow_cache = (0, [], {})
        self.port_seats = lambda: {}
        self._seats_seen, self._seats_index = None, {}
        self.listening = None
        self.error = None
        self.demo = False
        self._load()

    # ── storage: one JSON line per log line, a file per hour ────────────────────────────
    def folder(self):
        return self.path or os.path.join(os.path.dirname(os.path.abspath(store.DATA_FILE)), 'syslog')

    def _load(self):
        folder = self.folder()
        if not os.path.isdir(folder):
            return
        cutoff = time.time() - settings()['retention_hours'] * 3600
        for name in sorted(os.listdir(folder)):
            if not name.endswith('.jsonl'):
                continue
            try:
                with open(os.path.join(folder, name), encoding='utf-8') as f:
                    for row in f:
                        try:
                            line = json.loads(row)
                        except ValueError:
                            continue
                        if isinstance(line, dict) and (line.get('ts') or 0) >= cutoff:
                            self.lines.append(line)
            except OSError:
                continue
        if self.lines:
            self.next_id = max(line.get('id', 0) for line in self.lines) + 1
        self._trim()

    def _write(self, line):
        folder = self.folder()
        try:
            os.makedirs(folder, exist_ok=True)
            name = time.strftime('%Y-%m-%d-%H', time.gmtime(line['ts'])) + '.jsonl'
            with open(os.path.join(folder, name), 'a', encoding='utf-8') as f:
                f.write(json.dumps(line, separators=(',', ':')) + '\n')
        except OSError as exc:
            self.error = f'Can\'t write the syslog files: {exc.strerror or exc}'

    def prune_files(self, now=None):
        """Drop hour files past the retention, then the oldest until under the size cap."""
        now = time.time() if now is None else now
        folder = self.folder()
        if not os.path.isdir(folder):
            return
        s = settings()
        files = sorted(f for f in os.listdir(folder) if f.endswith('.jsonl'))
        cutoff = time.strftime('%Y-%m-%d-%H', time.gmtime(now - s['retention_hours'] * 3600))
        sizes = {}
        for name in files:
            path = os.path.join(folder, name)
            if name[:-6] < cutoff:
                os.remove(path)
            else:
                sizes[name] = os.path.getsize(path)
        cap = s['max_mb'] * 1024 * 1024
        for name in sorted(sizes):
            if sum(sizes.values()) <= cap or len(sizes) == 1:
                break
            os.remove(os.path.join(folder, name))
            del sizes[name]

    def _trim(self, now=None):
        now = time.time() if now is None else now
        s = settings()
        cutoff = now - s['retention_hours'] * 3600
        while self.lines and (len(self.lines) > s['max_lines'] or self.lines[0]['ts'] < cutoff):
            self.lines.popleft()

    # ── who may send ────────────────────────────────────────────────────────────────
    def _allowed(self):
        """(networks, {address: switch name}), worked out at most every 30 seconds."""
        at, nets, switches = self._allow_cache
        if time.time() - at < 30:
            return nets, switches
        nets = []
        for entry in settings()['allow']:
            try:
                nets.append(ipaddress.ip_network(entry, strict=False))
            except ValueError:
                continue
        switches = {}
        try:
            for dev in inventory.devices(store.load_data()):
                if dev.get('mgmt_ip'):
                    switches[str(dev['mgmt_ip']).split('/')[0]] = dev['name']
        except Exception as exc:  # noqa: BLE001  # a broken data file must not stop the receiver
            print(f'[syslog] could not read the inventory: {exc}')
        self._allow_cache = (time.time(), nets, switches)
        return nets, switches

    def sender_ok(self, address):
        nets, switches = self._allowed()
        if settings()['allow_switches'] and address in switches:
            return True
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            return False
        return any(ip in net for net in nets)

    def _rate_ok(self, sender, now):
        rate = settings()['rate']
        tokens, last = self._buckets.get(sender, (rate, now))
        tokens = min(rate, tokens + (now - last) * rate)
        if tokens < 1:
            self._buckets[sender] = (tokens, now)
            return False
        self._buckets[sender] = (tokens - 1, now)
        return True

    # ── receiving ───────────────────────────────────────────────────────────────────
    def receive(self, raw, sender, now=None, check=True, device=None):
        """One datagram or TCP line from ``sender``. Returns the kept line, or None."""
        now = time.time() if now is None else now
        with self._lock:
            self.counts['received'] += 1
            if check and not self.sender_ok(sender):
                self.counts['not_allowed'] += 1
                return None
            if not self._rate_ok(sender, now):
                self.counts['rate_limited'] += 1
                return None
        line = parse(raw, now)
        _nets, switches = self._allowed()
        device = device or switches.get(sender) or line['host'] or sender
        ports = ports_in(line['message'])
        port = ports[0] if ports else None
        seat = self._seat_index().get((str(device).lower(), port)) if port else None
        with self._lock:
            line.update(id=self.next_id, sender=sender, device=device, port=port, seat=seat)
            self.next_id += 1
            self.lines.append(line)
            self.counts['kept'] += 1
            self._trim(now)
        self._write(line)
        return line

    def _seat_index(self):
        """{(switch, canonical port): seat}, rebuilt when the port watch has read the ports again."""
        seats = self.port_seats()
        if self._seats_seen is not seats:
            self._seats_seen = seats
            self._seats_index = {(switch, canonical_port(name)): seat for (switch, name), seat in seats.items()}
        return self._seats_index

    def _fill_seats(self, lines):
        # Lines that came before the port watch's first read (or before a cable was patched) get
        # their seat once it is known.
        index = self._seat_index()
        if not index:
            return
        for line in lines:
            if line.get('port') and not line.get('seat'):
                line['seat'] = index.get((str(line.get('device') or '').lower(), line['port']))

    # ── reading ─────────────────────────────────────────────────────────────────────
    def search(self, q='', device='', seat='', port='', severity='', after=0, before=None, limit=200):
        """Newest first. ``severity`` is the least severe level to show ('warning' shows emerg to warning)."""
        words = [w for w in str(q or '').lower().split() if w]
        worst = SEVERITIES.index(severity) if severity in SEVERITIES else len(SEVERITIES) - 1
        device, seat, port = str(device or '').lower(), str(seat or '').lower(), canonical_port(port) if port else ''
        with self._lock:
            lines = list(self.lines)
        self._fill_seats(lines)
        out = []
        for line in reversed(lines):
            if line['id'] <= after:
                break
            if before is not None and line['id'] >= before:
                continue
            if SEVERITIES.index(line['severity']) > worst:
                continue
            if device and str(line.get('device') or '').lower() != device:
                continue
            if seat and str(line.get('seat') or '').lower() != seat:
                continue
            if port and line.get('port') != port:
                continue
            if words:
                text = ' '.join(str(line.get(k) or '') for k in ('message', 'device', 'program', 'seat')).lower()
                if not all(w in text for w in words):
                    continue
            out.append(line)
            if len(out) >= limit:
                break
        return out

    def status(self):
        with self._lock:
            devices = sorted({str(line.get('device')) for line in self.lines if line.get('device')})
            return {'enabled': settings()['enabled'], 'listening': self.listening, 'error': self.error,
                    'counts': dict(self.counts), 'lines': len(self.lines), 'devices': devices,
                    'retention_hours': settings()['retention_hours'], 'demo': self.demo,
                    'last_id': self.lines[-1]['id'] if self.lines else 0}

    # ── listening ───────────────────────────────────────────────────────────────────
    def start(self):
        s = settings()
        if not s['enabled'] or self._servers:
            return
        receiver = self

        class Udp(socketserver.BaseRequestHandler):
            def handle(self):
                receiver.receive(self.request[0], self.client_address[0])

        class Tcp(socketserver.StreamRequestHandler):
            timeout = 120

            def handle(self):
                # Newline-framed (most senders); octet-counted framing isn't read.
                while True:
                    raw = self.rfile.readline(MAX_LINE + 1)
                    if not raw:
                        return
                    receiver.receive(raw, self.client_address[0])

        try:
            udp = socketserver.ThreadingUDPServer((s['bind'], s['port']), Udp)
            self._servers.append(udp)
            if s['tcp']:
                socketserver.ThreadingTCPServer.allow_reuse_address = True
                tcp = socketserver.ThreadingTCPServer((s['bind'], s['port']), Tcp)
                tcp.daemon_threads = True
                self._servers.append(tcp)
        except OSError as exc:
            self.error = f"Can't listen on port {s['port']}: {exc.strerror or exc}"
            print(f'[syslog] {self.error}')
            return
        for server in self._servers:
            threading.Thread(target=server.serve_forever, name='syslog', daemon=True).start()
        self.listening = {'port': self._servers[0].server_address[1], 'tcp': s['tcp'], 'bind': s['bind']}
        threading.Thread(target=self._housekeeping, name='syslog-prune', daemon=True).start()

    def _housekeeping(self):
        while self._servers:
            try:
                self.prune_files()
            except OSError as exc:
                print(f'[syslog] could not prune: {exc}')
            time.sleep(300)

    def stop(self):
        servers, self._servers = self._servers, []
        for server in servers:
            server.shutdown()
            server.server_close()
        self.listening = None


def demo_lines(now):
    """FLOORBIT_DEMO=1: what the demo hall's switches would send in the last minute."""
    from .builtin_plugins.demo.plugin import FLAPPING_PORT, _switch_for
    minute = int(now // 60)
    switch, short = _switch_for(*FLAPPING_PORT)
    port = 'GigabitEthernet' + short[2:]
    out = [(switch, f'<187>%LINK-3-UPDOWN: Interface {port}, changed state to down'),
           (switch, f'<189>%LINEPROTO-5-UPDOWN: Line protocol on Interface {port}, changed state to up')]
    if minute % 3 == 0:
        out.append(('sw-d-02', '<188>%SW_MATM-4-MACFLAP_NOTIF: Host 0200.0000.003d in vlan 100 is flapping '
                               'between port Gi1/0/6 and port Gi1/0/7'))
    if minute % 4 == 0:
        out.append(('sw-a-01', '<187>%DHCP_SNOOPING-3-DHCP_SNOOPING_UNTRUSTED_PORT: DHCP_SNOOPING drop message '
                               'on untrusted port, message type: DHCPOFFER, MAC sa: 0200.0000.0007, '
                               'vlan: 100, port: Gi1/0/7'))
    if minute % 5 == 0:
        out.append(('dhcp-01', '<30>dhcpd[812]: DHCPACK on 192.0.2.40 to 02:00:00:00:00:1e via eth1'))
    out.append(('fw-01', f'<134>filterlog[5512]: 5,,,1000000103,igb1,match,block,in,4,0x0,,64,{minute % 65000},0,'
                         'none,17,udp,76,203.0.113.9,198.51.100.1,123,123,56'))
    return out


def init_syslog(app, start_background=True):
    global _receiver
    receiver = _receiver = SyslogReceiver()
    app.extensions['floorbit_syslog'] = receiver

    def seats():
        watch = app.extensions.get('floorbit_attention')
        return getattr(watch, 'port_seats', {}) or {}

    receiver.port_seats = seats
    started = threading.Event()

    @app.before_request
    def start_syslog_once():
        if start_background and not started.is_set():
            started.set()
            if features.on('syslog'):
                receiver.start()

    return receiver


def start_demo(receiver):
    """Feed made-up lines from the demo hall, a minute's worth now and then every minute."""
    if receiver.demo:
        return
    receiver.demo = True

    def feed(now):
        for i, (device, raw) in enumerate(demo_lines(now)):
            receiver.receive(raw.encode(), '198.51.100.' + str(200 + i), now=now, check=False, device=device)

    def run():
        now = time.time()
        for k in range(30, 0, -1):
            feed(now - k * 60)
        while True:
            time.sleep(60)
            if features.on('syslog'):
                feed(time.time())

    threading.Thread(target=run, name='syslog-demo', daemon=True).start()
