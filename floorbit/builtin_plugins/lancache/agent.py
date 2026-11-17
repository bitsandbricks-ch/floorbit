"""The LAN cache plugin's part in the hall (docs/lancache.md): reads the cache's access log and
lancache-dns's query log, checks the cache answers, and sends hall-wide numbers only."""
import json
import os
import random
import shutil
import socket
import struct
import threading
import time
import urllib.error
import urllib.request

from floorbit.builtin_plugins.lancache.logs import Counter, Tail
from floorbit.plugins.agent import AgentPlugin as Base
from floorbit.plugins.base import PluginError

HEARTBEAT_PATH = '/lancache-heartbeat'
CHECK_NAME = 'lancache.steamcontent.com'    # every lancache-dns answers this with the cache


def resolve_a(server, name, timeout=3):
    """The IPv4 addresses ``server`` (port 53) answers for ``name``."""
    qid = random.randrange(1 << 16)
    qname = b''.join(bytes([len(p)]) + p.encode() for p in name.split('.')) + b'\0'
    packet = struct.pack('>HHHHHH', qid, 0x0100, 1, 0, 0, 0) + qname + struct.pack('>HH', 1, 1)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout)
        sock.sendto(packet, (server, 53))
        while True:
            data, _ = sock.recvfrom(4096)
            if len(data) >= 12 and struct.unpack('>H', data[:2])[0] == qid:
                break
    count = struct.unpack('>H', data[6:8])[0]
    pos = 12 + len(qname) + 4
    out = []
    for _ in range(count):
        if pos >= len(data):
            break
        if data[pos] & 0xC0 == 0xC0:          # a pointer to a name
            pos += 2
        else:
            while pos < len(data) and data[pos]:
                pos += data[pos] + 1
            pos += 1
        rtype, _cls, _ttl, size = struct.unpack('>HHIH', data[pos:pos + 10])
        pos += 10
        if rtype == 1 and size == 4:
            out.append(socket.inet_ntoa(data[pos:pos + 4]))
        pos += size
    return out


class AgentPlugin(Base):
    def start(self):
        s = self.settings
        self.interval = max(10, int(s.get('interval') or 30))
        self.counter = Counter(min_clients=s.get('min_clients') or 5)
        self.positions = self._load_positions()
        self.access = Tail(s['access_log'], self.positions.get('access')) if s.get('access_log') else None
        self.queries = Tail(s['dns_log'], self.positions.get('dns')) if s.get('dns_log') else None
        self.last = {}
        self._clearing = None
        if not (self.access or self.queries or s.get('cache_host') or s.get('cache_dir')):
            self.ctx.health('off', 'Nothing to read yet: set the access log, the DNS log or the cache host.')
        self.ctx.thread(self.loop, name='lancache-read')

    # ── reading and sending ────────────────────────────────────────────────────────────
    def _positions_file(self):
        return os.path.join(self.ctx.state_dir, 'positions.json') if self.ctx.state_dir else None

    def _load_positions(self):
        path = self._positions_file()
        try:
            with open(path, encoding='utf-8') as f:
                return json.load(f)
        except (OSError, TypeError, ValueError):
            return {}

    def _save_positions(self):
        path = self._positions_file()
        if not path:
            return
        data = {k: t.state for k, t in (('access', self.access), ('dns', self.queries)) if t}
        try:
            with open(path + '.tmp', 'w', encoding='utf-8') as f:
                json.dump(data, f)
            os.replace(path + '.tmp', path)
        except OSError as exc:
            self.ctx.error(f'cannot keep the log positions: {exc}')

    def tick(self, now=None, everything=False):
        """Read both logs, check the cache, send. One round; the loop calls it every interval."""
        problems = []
        if self.access:
            lines = self.access.read()
            self.ctx.counter('access_lines', self.counter.add_access(lines, now))
            if self.access.error:
                problems.append(self.access.error)
        if self.queries:
            lines = self.queries.read()
            self.ctx.counter('dns_lines', self.counter.add_queries(lines, now))
            if self.queries.error:
                problems.append(self.queries.error)
        if self.access or self.queries:
            payload = self.counter.payload(now=now, everything=everything)
            self.ctx.send('stats', payload)
            self._save_positions()
            hit = sum(v[0] for hours in payload['hours'].values() for v in hours.values())
            total = hit + sum(v[1] for hours in payload['hours'].values() for v in hours.values())
            if total:
                self.ctx.gauge('hit_ratio_pct', round(hit * 100 / total))
        status = self.status()
        self.ctx.send('status', status)
        problems += [v['error'] for v in (status.get('heartbeat'), status.get('dns_check')) if v and v.get('error')]
        disk = status.get('disk')
        if disk and disk.get('total'):
            self.ctx.gauge('disk_used_pct', round(disk['used'] * 100 / disk['total']))
        if problems:
            self.ctx.health('warning', problems[0])
            for p in problems:
                self.ctx.error(p)
        elif self.access or self.queries or self.settings.get('cache_host'):
            self.ctx.health('ok')

    def loop(self):
        first = True
        while not self.ctx.stopping.is_set():
            try:
                # The first round after a start sends every hour still kept: the hosted side may be new.
                self.tick(everything=first)
                first = False
            except PluginError as exc:
                self.ctx.error(str(exc))
            self.ctx.stopping.wait(self.interval)

    # ── checks ───────────────────────────────────────────────────────────────────────────
    def status(self):
        s = self.settings
        out = {'at': time.time(), 'clearing': self._clearing}
        if s.get('cache_dir'):
            try:
                usage = shutil.disk_usage(s['cache_dir'])
                out['disk'] = {'used': usage.used, 'total': usage.total, 'free': usage.free}
            except OSError as exc:
                out['disk'] = {'error': f"can't read {s['cache_dir']}: {exc.strerror or exc}"}
        host = (s.get('cache_host') or '').strip()
        if host:
            out['heartbeat'] = self.heartbeat(host)
        dns_server = (s.get('dns_server') or '').strip()
        if dns_server and host:
            out['dns_check'] = self.dns_check(dns_server, host)
        return out

    def heartbeat(self, host):
        """lancache.net answers ``/lancache-heartbeat`` with 204 and the ``X-LanCache-Processed-By`` header."""
        start = time.monotonic()
        try:
            req = urllib.request.Request(f'http://{host}{HEARTBEAT_PATH}', headers={'Host': CHECK_NAME})
            with urllib.request.urlopen(req, timeout=5) as resp:
                status, by = resp.status, resp.headers.get('X-LanCache-Processed-By')
        except urllib.error.HTTPError as exc:
            status, by = exc.code, exc.headers.get('X-LanCache-Processed-By')
        except (OSError, ValueError) as exc:
            return {'ok': False, 'error': f'the cache did not answer: {getattr(exc, "reason", exc)}'}
        ms = round((time.monotonic() - start) * 1000)
        if status != 204:
            return {'ok': False, 'ms': ms, 'error': f'the heartbeat answered HTTP {status}, not 204'}
        if not by:
            return {'ok': False, 'ms': ms,
                    'error': 'something answered, but not a LAN cache (no X-LanCache-Processed-By)'}
        return {'ok': True, 'ms': ms, 'processed_by': str(by)[:60]}

    def dns_check(self, server, host):
        """Does lancache-dns send the cache's names to the cache? (Only yes or no leaves the hall.)"""
        try:
            want = {a[4][0] for a in socket.getaddrinfo(host, 80, socket.AF_INET)}
            got = set(resolve_a(server, CHECK_NAME))
        except (OSError, struct.error) as exc:
            return {'ok': False, 'error': f'the DNS server did not answer: {exc}'}
        if not got:
            return {'ok': False, 'error': f'the DNS server has no answer for {CHECK_NAME}'}
        if not got & want:
            return {'ok': False, 'error': f'the DNS server sends {CHECK_NAME} somewhere else than the cache'}
        return {'ok': True}

    def check(self):
        parts = []
        for name, tail in (('access log', self.access), ('DNS log', self.queries)):
            if tail:
                if not os.access(tail.path, os.R_OK):
                    raise PluginError(f"can't read the {name} {tail.path}")
                parts.append(f'reading the {name}')
        host = (self.settings.get('cache_host') or '').strip()
        if host:
            beat = self.heartbeat(host)
            if not beat['ok']:
                raise PluginError(beat['error'])
            parts.append(f"the cache answers ({beat['ms']} ms)")
        return ', '.join(parts) or 'nothing set up yet'

    # ── calls and actions ──────────────────────────────────────────────────────────────
    def call_status(self, args):
        return {**self.status(), 'lines': self.counter.lines}

    def action_clear_cache(self, params):
        """Empty the cache folder, in the background. Needs it mounted writable on the agent."""
        folder = (self.settings.get('cache_dir') or '').rstrip('/')
        if not folder or folder in ('', '/') or not os.path.isdir(folder):
            raise PluginError('Set the cache folder (as the agent sees it) first.')
        if not os.access(folder, os.W_OK):
            raise PluginError(f'{folder} is read-only for the agent: mount it writable to clear the cache.')
        if self._clearing and self._clearing.get('running'):
            return {'message': 'The cache is already being cleared.'}
        self._clearing = {'running': True, 'started': time.time(), 'removed': 0, 'errors': 0}
        threading.Thread(target=self._clear, args=(folder,), name='lancache-clear', daemon=True).start()
        self.ctx.log('clearing the cache folder, asked by the hosted Floorbit')
        return {'message': 'Clearing the cache. It fills again as players download.'}

    def _clear(self, folder):
        state = self._clearing
        # Only what nginx keeps there: its two-level hash folders. Anything else is left alone.
        for top in os.listdir(folder):
            path = os.path.join(folder, top)
            if len(top) != 2 or top.strip('0123456789abcdef') or not os.path.isdir(path) or os.path.islink(path):
                continue
            try:
                for _root, _dirs, files in os.walk(path):
                    state['removed'] += len(files)
                shutil.rmtree(path)
            except OSError:
                state['errors'] += 1
        state.update(running=False, finished=time.time())
        self.ctx.log(f"cleared the cache: {state['removed']} files, {state['errors']} folders failed")
