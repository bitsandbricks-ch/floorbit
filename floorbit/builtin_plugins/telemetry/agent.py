"""The telemetry plugin's part on the local agent (docs/telemetry.md, docs/agent-plugins.md).

On the agent it is the collector: Telegraf (a sidecar next to the agent) gets its config from here
and posts line protocol to this plugin's own listener; the API pollers (NX-API, RESTCONF,
OPNsense) run here too. The picture of each device stays in the agent's memory, where the
monitoring calls through the agent link read it, so MAC tables and ARP never leave the hall. The
hosted Floorbit only gets the per-port and per-device numbers for its history (``series``).
"""
import base64
import contextlib
import gzip
import os
import secrets
import threading
import time
from urllib.parse import parse_qs, urlsplit

from floorbit.plugins.agent import AgentPlugin as Base
from floorbit.telemetry import lineproto, pollers, telegraf
from floorbit.telemetry import state as state_mod
from floorbit.telemetry import storage as storage_mod

PORT_ENV = 'FLOORBIT_TELEMETRY_PORT'
OUTPUT_ENV = 'FLOORBIT_TELEGRAF_OUTPUT'
CONF_ENV = 'FLOORBIT_TELEGRAF_CONF'
PORT = 8186
POLL_EVERY = 60
SEND_EVERY = 60
QUIET_AFTER = 180          # no line from Telegraf for this long, while it has work: warn
MAX_BODY = 32 * 1024 * 1024
# Drivers that Telegraf does; the others are pollers that run in this plugin.
TELEGRAF_DRIVERS = frozenset({'snmp', 'traps', 'gnmi', 'mdt'})


class AgentPlugin(Base):
    restart_on_configure = False

    def start(self):
        self.state = state_mod.state
        self.lock = threading.Lock()
        self.last_write = None
        self.poll_errors = {}
        self.token = self._token()
        self.targets = []
        self.configure(self.settings)
        self.port = self.ctx.listen_http(int(os.environ.get(PORT_ENV) or PORT), self.handle)
        self.ctx.thread(self.loop, name='telemetry-poll')
        self.ctx.health('ok', 'waiting for devices')

    # settings: the devices, from Settings > Telemetry on the hosted Floorbit ------------------
    def configure(self, settings):
        self.ctx.settings = settings
        found = settings.get('targets') if isinstance(settings, dict) else None
        with self.lock:
            self.targets = [t for t in (found or []) if isinstance(t, dict) and t.get('name')]
        self.state.know(self.targets)
        self.write_conf()
        return True

    def _token(self):
        """The token Telegraf sends here with. Kept in the plugin's own folder, so a restart doesn't
        need a new Telegraf config; it never leaves the agent."""
        path = os.path.join(self.ctx.state_dir or '.', 'ingest-token')
        try:
            with open(path, encoding='utf-8') as f:
                token = f.read().strip()
                if token:
                    return token
        except OSError:
            pass
        token = 'fba_' + secrets.token_urlsafe(24)
        if self.ctx.state_dir:
            with open(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), 'w', encoding='utf-8') as f:
                f.write(token)
        return token

    def conf_path(self):
        return os.environ.get(CONF_ENV) or os.path.join(self.ctx.state_dir or '.', 'telegraf.conf')

    def output_url(self):
        return os.environ.get(OUTPUT_ENV) or f'http://agent:{os.environ.get(PORT_ENV) or PORT}/write'

    def write_conf(self):
        """telegraf.conf for the sidecar, written only when it changed (Telegraf reloads on change)."""
        with self.lock:
            text = telegraf.render(list(self.targets), self.output_url(), self.token)
        path = self.conf_path()
        try:
            with open(path, encoding='utf-8') as f:
                if f.read() == text:
                    return False
        except OSError:
            pass
        try:
            os.makedirs(os.path.dirname(path) or '.', mode=0o700, exist_ok=True)
            tmp = path + '.tmp'
            # Telegraf runs as another user in the sidecar and only reads it.
            with open(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o640), 'w', encoding='utf-8') as f:
                f.write(text)
            os.replace(tmp, path)
        except OSError as exc:
            self.ctx.error(f'cannot write {path}: {exc}')
            return False
        self.ctx.counter('conf_written')
        return True

    # Telegraf's pushes ----------------------------------------------------------------------
    def handle(self, method, path, headers, body):
        route = path.split('?', 1)[0].rstrip('/')
        if route == '/ping' or (method == 'GET' and route in ('', '/health')):
            return 204, b''
        if method != 'POST' or route not in ('/write', '/api/v2/write'):
            return 404, 'not found'
        if not self._authorised(path, headers):
            self.ctx.counter('refused_writes')
            return 401, 'bad token'
        if (headers.get('Content-Encoding') or headers.get('content-encoding') or '').lower() == 'gzip':
            try:
                body = gzip.decompress(body)
            except (OSError, EOFError):
                return 400, 'bad gzip'
        if len(body) > MAX_BODY:
            return 413, 'too large'
        taken = self.take(body.decode('utf-8', 'replace'))
        return (204, b'') if taken is not None else (400, 'nothing understood')

    def _authorised(self, path, headers):
        given = set()
        auth = headers.get('Authorization') or headers.get('authorization') or ''
        scheme, _, value = auth.partition(' ')
        if scheme.lower() == 'token':
            given.add(value.strip())
        elif scheme.lower() == 'basic':
            with contextlib.suppress(ValueError):
                given.add(base64.b64decode(value).decode().partition(':')[2])
        given.update(parse_qs(urlsplit(path).query).get('p') or [])
        return any(secrets.compare_digest(g, self.token) for g in given if g)

    def take(self, text, now=None):
        points, bad = lineproto.parse(text)
        if bad:
            self.ctx.counter('bad_lines', bad)
        if not points:
            return None if bad else 0
        taken = self.state.apply(points, now)
        self.last_write = time.time() if now is None else now
        self.ctx.counter('points', len(points))
        return taken

    # the API pollers, the series for the hosted Floorbit, and health -------------------------
    def loop(self):
        next_poll = next_send = 0.0
        while not self.ctx.stopping.wait(5):
            now = time.time()
            try:
                if now >= next_poll:
                    next_poll = now + POLL_EVERY
                    self.poll(now)
                if now >= next_send:
                    next_send = now + SEND_EVERY
                    self.send_series(now)
                self.report(now)
            except Exception as exc:  # noqa: BLE001  # a bad round must not end the collector
                self.ctx.error(f'{type(exc).__name__}: {exc}')

    def poll(self, now):
        with self.lock:
            wanted = [t for t in self.targets if set(t.get('drivers') or []) & set(pollers.POLLERS)]
        if not wanted:
            return
        found, errors = pollers.poll_all(wanted, now, log=self.ctx.log, blocks=self.ctx)
        for name, err in errors.items():
            if self.poll_errors.get(name) != err:
                self.ctx.error(err)
        self.poll_errors = errors
        self.state.apply(found, now)
        self.ctx.counter('polled_points', len(found))

    def send_series(self, now):
        values = storage_mod.snapshot(self.state, now)
        if values:
            self.ctx.send('series', {'at': now, 'values': values})
            self.ctx.gauge('series', len(values))

    def report(self, now):
        with self.lock:
            telegraf_work = any(set(t.get('drivers') or []) & TELEGRAF_DRIVERS for t in self.targets)
            count = len(self.targets)
        heard = sum(1 for d in list(self.state.devices.values()) if d.online(now))
        self.ctx.gauge('devices', count)
        self.ctx.gauge('devices_heard', heard)
        if self.last_write is not None:
            self.ctx.gauge('telegraf_quiet_seconds', round(now - self.last_write))
        if not count:
            self.ctx.health('ok', 'no devices set up')
        elif telegraf_work and (self.last_write is None or now - self.last_write > QUIET_AFTER):
            self.ctx.health('warning', 'nothing from Telegraf: is the telegraf sidecar running?')
        elif self.poll_errors:
            self.ctx.health('warning', f'{len(self.poll_errors)} of {count} devices did not answer')
        else:
            self.ctx.health('ok', f'{heard} of {count} devices heard')

    def check(self):
        return (f'{len(self.targets)} devices, listening on :{self.port}, '
                f'Telegraf config {self.conf_path()}')
