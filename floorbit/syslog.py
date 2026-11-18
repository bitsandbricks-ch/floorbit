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
import contextlib
import ipaddress
import json
import os
import re
import socket
import socketserver
import threading
import time
from collections import OrderedDict, deque
from datetime import datetime

from integrations import config

from . import features, inventory, log_alerts, store

MAX_LINE = 2048
LATE = 120               # seconds: a relayed line older than this was kept by the agent (#465)
DUPLICATE_WINDOW = 10    # seconds: the same line id this close in time is a copy, not a repeat
SEEN_IDS = 100_000       # relayed line ids remembered for that
FORWARD_SECONDS = 10
FORWARD_BACKLOG = 20_000
SEVERITIES = ('emerg', 'alert', 'crit', 'err', 'warning', 'notice', 'info', 'debug')
# RFC 3164: <PRI>Mmm dd hh:mm:ss host tag: msg   RFC 5424: <PRI>1 2026-11-14T10:00:00Z host app pid msgid - msg
RFC5424 = re.compile(r'^<(\d{1,3})>1 (\S+) (\S+) (\S+) (\S+) (\S+) (?:-|(?:\[.*?\])+) ?(.*)$', re.S)
RFC3164 = re.compile(r'^<(\d{1,3})>(?:([A-Z][a-z]{2} [ \d]\d \d\d:\d\d:\d\d) )?'
                     r'(?:(\S+) )?([^:\[\s]{1,48})(?:\[\d+\])?: ?(.*)$',
                     re.S)
# Cisco IOS and NX-OS: an optional message counter ("113: ", or ": " from NX-OS), the hostname with
# "logging origin-id hostname", the device's own stamp, then %FACILITY-SEVERITY-MNEMONIC. Read as RFC 3164
# the counter would be the program and the hostname lost.
CISCO = re.compile(r'^<(\d{1,3})>(?:\d*: )?(?:([A-Za-z0-9][\w.-]{0,79}): )?'
                   r'(?:[*.]?(?:\d{4} )?[A-Z][a-z]{2} +\d{1,2}(?: \d{4})? \d\d:\d\d:\d\d(?:\.\d+)?(?: [A-Z]{2,5})?: )?'
                   r'(%[A-Z0-9_]+-\d-[A-Z0-9_]+): ?(.*)$', re.S)
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


_batch = threading.local()   # the settings for the batch this thread is taking in


def _hot_settings():
    """``settings()`` for the checks every line passes (allowed, rate, trim): read once per relayed
    batch, not per line; ten config lookups per line were a third of the server's time at 2,000
    lines a second."""
    return getattr(_batch, 'settings', None) or settings()


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
    elif m := CISCO.match(text):
        pri, host, program, message = int(m[1]), m[2], m[3], m[4]
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




def _tail(path, count, block=1 << 20):
    """The last ``count`` lines of a file (bytes, oldest first), read backwards in blocks."""
    if count <= 0:
        return []
    with open(path, 'rb') as f:
        f.seek(0, os.SEEK_END)
        end = f.tell()
        data = b''
        while end > 0 and data.count(b'\n') <= count:
            start = max(0, end - block)
            f.seek(start)
            data = f.read(end - start) + data
            end = start
    rows = data.split(b'\n')
    if end > 0:
        rows = rows[1:]          # cut mid-line at the block's start
    return [r for r in rows if r.strip()][-count:]


RCVBUF = 8 * 1024 * 1024      # a burst waits in the kernel while one line is handled
MAX_TCP = 256                 # senders at once; more are closed (a switch reconnects)


class UdpServer(socketserver.UDPServer):
    def server_bind(self):
        with contextlib.suppress(OSError):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, RCVBUF)
        super().server_bind()


class TcpServer(socketserver.ThreadingTCPServer):
    """A thread per sender, at most MAX_TCP of them."""
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, *a, **kw):
        self._slots = threading.BoundedSemaphore(MAX_TCP)
        super().__init__(*a, **kw)

    def process_request(self, request, client_address):
        if not self._slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self._slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._slots.release()


class SyslogReceiver:
    def __init__(self, path=None):
        self.path = path
        self._lock = threading.Lock()
        self.lines = deque()
        self.next_id = 1
        self.counts = {'received': 0, 'kept': 0, 'not_allowed': 0, 'rate_limited': 0, 'duplicates': 0}
        self._buckets = {}      # sender (or (sender, 'late')) -> [tokens, last]
        self._seen_ids = OrderedDict()   # a relayed line's id -> its time, to drop copies
        self._servers = []
        self._allow_cache = (0, [], {})
        self.port_seats = lambda: {}
        self._seats_seen, self._seats_index = None, {}
        self.alerts = log_alerts.LogAlerts()
        self.registry = None
        self.forwarded = {}     # plugin id -> {'id': last line sent, 'at', 'sent', 'error'}
        self.listening = None
        self.error = None
        self.demo = False
        self.relayed = {}       # agent name -> {'at', 'lines', 'dropped'}: lines a local agent sent
        self._load()

    # ── storage: one JSON line per log line, a file per hour ────────────────────────────
    def folder(self):
        return self.path or store.event_path('syslog')

    def _load(self):
        """The newest lines back into memory, newest file first, read from its end: only the last
        ``max_lines`` are kept, and parsing every stored line made a restart after a big event's
        night (7.6 million lines) take a minute before the first page answered."""
        folder = self.folder()
        if not os.path.isdir(folder):
            return
        s = settings()
        cutoff = time.time() - s['retention_hours'] * 3600
        want = s['max_lines']
        newest_first = []
        for name in sorted((n for n in os.listdir(folder) if n.endswith('.jsonl')), reverse=True):
            try:
                rows = _tail(os.path.join(folder, name), want - len(newest_first))
            except OSError:
                continue
            for row in reversed(rows):
                try:
                    line = json.loads(row)
                except ValueError:
                    continue
                if isinstance(line, dict) and (line.get('ts') or 0) >= cutoff:
                    newest_first.append(line)
            if len(newest_first) >= want:
                break
        self.lines.extend(reversed(newest_first))
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
        s = _hot_settings()
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
        if _hot_settings()['allow_switches'] and address in switches:
            return True
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            return False
        return any(ip in net for net in nets)

    def _rate_ok(self, sender, now):
        rate = _hot_settings()['rate']
        tokens, last = self._buckets.get(sender, (rate, now))
        # max(): relayed lines carry their own times, and two agents' lines can arrive out of order.
        tokens = min(rate, tokens + max(0, now - last) * rate)
        if tokens < 1:
            self._buckets[sender] = (tokens, now)
            return False
        self._buckets[sender] = (tokens - 1, now)
        return True

    # ── receiving ───────────────────────────────────────────────────────────────────
    def receive(self, raw, sender, now=None, check=True, device=None, late=False):
        """One datagram or TCP line from ``sender``. Returns the kept line, or None. ``late``: a line
        an agent kept while the uplink was down, sent long after it came."""
        now = time.time() if now is None else now
        with self._lock:
            self.counts['received'] += 1
            if check and not self.sender_ok(sender):
                self.counts['not_allowed'] += 1
                return None
            # Late lines come oldest first behind the live ones: on a bucket of their own, their
            # times refill it as the switch's own pace did, and they can't eat the live lines' share.
            if not self._rate_ok((sender, 'late') if late else sender, now):
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
        if not late:      # an alert about something hours ago would only send the crew running now
            self.alerts.observe(line, now)
        return line

    def relay(self, agent_name, lines, now=None, dropped=0):
        """Lines a local agent received on the event network (issue #2): ``[{"raw", "from", "at", "id"}]``.

        The original sender is checked against the allow-list as if it had sent here, and a line
        keeps the time the agent got it. An agent that couldn't reach us keeps lines on disk and
        sends them later (#465): they are placed at their own time, back to the retention limit.
        ``id`` is the same on every agent that heard the line: a second copy within DUPLICATE_WINDOW
        of the first (two agents, or a batch sent again) is dropped. Returns how many were kept."""
        now = time.time() if now is None else now
        if not lines:
            return 0     # the agent's check: nothing to count
        _batch.settings = settings()
        try:
            return self._relay(agent_name, lines, now, dropped)
        finally:
            _batch.settings = None

    def _relay(self, agent_name, lines, now, dropped):
        kept = 0
        for item in lines:
            if not isinstance(item, dict) or not isinstance(item.get('raw'), str):
                continue
            try:
                sender = str(ipaddress.ip_address(str(item.get('from') or '')))
            except ValueError:
                continue
            try:
                at = min(now, float(item.get('at') or now))
            except (TypeError, ValueError):
                at = now
            if at < now - settings()['retention_hours'] * 3600:
                continue                          # kept too long: it would be gone at once
            if self._duplicate(item.get('id'), at):
                continue
            late = now - at > LATE
            if self.receive(item['raw'][:MAX_LINE], sender, now=at, late=late) is not None:
                kept += 1
        with self._lock:
            seen = self.relayed.setdefault(str(agent_name)[:80], {'lines': 0, 'dropped': 0})
            seen['at'] = now
            seen['lines'] += kept
            seen['dropped'] = max(0, int(dropped or 0))
        return kept

    def _duplicate(self, line_id, at):
        if not isinstance(line_id, str) or not line_id:
            return False                          # an older agent: no ids, nothing to compare
        line_id = line_id[:64]
        with self._lock:
            seen = self._seen_ids.get(line_id)
            if seen is not None and abs(seen - at) <= DUPLICATE_WINDOW:
                self.counts['duplicates'] += 1
                return True
            self._seen_ids[line_id] = at
            self._seen_ids.move_to_end(line_id)
            while len(self._seen_ids) > SEEN_IDS:
                self._seen_ids.popitem(last=False)
        return False

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

    def markers(self, devices, now=None, minutes=10):
        with self._lock:
            lines = list(self.lines)
        self._fill_seats(lines)
        return log_alerts.markers(lines, devices, now=now, minutes=minutes)

    def alert_items(self, now=None):
        """Log alerts, with the seat filled in once the port watch knows it."""
        items = self.alerts.snapshot(now)
        index = self._seat_index()
        for item in items:
            if item['port'] and not item['seat']:
                item['seat'] = index.get((item['device'].lower(), item['port']))
        return items

    # ── keeping it longer: plugins in the logs area (Loki) get every line ─────────────
    def log_plugins(self):
        return self.registry.feeders('logs') if self.registry else []

    def forward_once(self, now=None):
        """Send each logs plugin the lines it hasn't had yet. A plugin that fails gets them next time,
        up to FORWARD_BACKLOG lines; past that the oldest are skipped."""
        from .plugins import PluginError
        now = time.time() if now is None else now
        with self._lock:
            lines = list(self.lines)
        last = lines[-1]['id'] if lines else 0
        for spec in self.log_plugins():
            state = self.forwarded.setdefault(spec.id, {'id': last, 'at': None, 'sent': 0, 'error': None})
            todo = [ln for ln in lines if ln['id'] > state['id']][-FORWARD_BACKLOG:]
            if not todo:
                continue
            try:
                self.registry.call(spec, 'push_logs', todo)
            except PluginError as exc:
                state['error'] = str(exc)
                continue
            state.update(id=todo[-1]['id'], at=now, sent=state['sent'] + len(todo), error=None)

    def _forwarding(self):
        while True:
            time.sleep(FORWARD_SECONDS)
            if features.on('syslog'):
                try:
                    self.forward_once()
                except Exception as exc:  # noqa: BLE001  # a plugin bug must not stop forwarding for good
                    print(f'[syslog] could not forward: {exc}')

    def query(self, plugin_id, query, start, end, limit):
        """Search a logs plugin (Loki) with its own query language."""
        spec = next((s for s in self.log_plugins() if s.id == plugin_id), None)
        if spec is None:
            return None
        return self.registry.call(spec, 'query_logs', query, start, end, limit)

    def status(self):
        with self._lock:
            devices = sorted({str(line.get('device')) for line in self.lines if line.get('device')})
            return {'enabled': settings()['enabled'], 'listening': self.listening, 'error': self.error,
                    'counts': dict(self.counts), 'lines': len(self.lines), 'devices': devices,
                    'retention_hours': settings()['retention_hours'], 'demo': self.demo,
                    # recent: the agent sent within five minutes, so its syslog is getting through.
                    'relayed': [{'agent': name, **seen, 'recent': time.time() - seen['at'] < 300}
                                for name, seen in sorted(self.relayed.items())],
                    'last_id': self.lines[-1]['id'] if self.lines else 0,
                    'stores': [{'id': s.id, 'name': s.name, **{k: v for k, v in self.forwarded.get(s.id, {}).items()
                                                               if k != 'id'}} for s in self.log_plugins()]}

    # ── listening ───────────────────────────────────────────────────────────────────
    def start(self):
        s = settings()
        if not s['enabled'] or self._servers:
            return
        from . import agent_link
        if not agent_link.lan_here():
            # The switches send to the local agent, which relays (FLOORBIT_AGENT_SYSLOG_PORT): this
            # server never listens on the event network itself.
            self.error = ('Syslog comes in through the local agent (FLOORBIT_AGENT_SYSLOG_PORT on the agent); '
                          'this server does not listen itself.')
            print(f'[syslog] {self.error}')
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
            # One thread reads the port: a thread per datagram fell over in a burst (the local
            # agent's relay learned the same, floorbit-agent's syslog_relay.py).
            udp = UdpServer((s['bind'], s['port']), Udp)
            self._servers.append(udp)
            if s['tcp']:
                tcp = TcpServer((s['bind'], s['port']), Tcp)
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
    if minute % 7 == 0:
        out.append(('sw-b-01', '<188>%PM-4-ERR_DISABLE: bpduguard error detected on Gi1/0/3, putting Gi1/0/3 in '
                               'err-disable state'))
    if minute % 6 == 0:
        out.append(('dist-01', '<189>%SPANTREE-5-TOPOTRAP: Topology Change Trap for vlan 100'))
    if minute % 5 == 0:
        out.append(('dhcp-01', '<30>dhcpd[812]: DHCPACK on 192.0.2.40 to 02:00:00:00:00:1e via eth1'))
    out.append(('fw-01', f'<134>filterlog[5512]: 5,,,1000000103,igb1,match,block,in,4,0x0,,64,{minute % 65000},0,'
                         'none,17,udp,76,203.0.113.9,198.51.100.1,123,123,56'))
    return out


def init_syslog(app, registry=None, start_background=True):
    global _receiver
    receiver = _receiver = SyslogReceiver()
    receiver.registry = registry
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
            threading.Thread(target=receiver._forwarding, name='syslog-forward', daemon=True).start()

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
