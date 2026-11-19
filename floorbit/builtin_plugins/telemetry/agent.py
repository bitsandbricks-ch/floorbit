"""The telemetry plugin's part on the local agent (docs/telemetry.md, docs/agent-plugins.md).

On the agent it is the collector: Telegraf gets its config from here and posts line protocol to
this plugin's own listener. The agent image carries Telegraf and this plugin runs it (supervisor.py),
reading its output for each device's problems (problems.py); an agent without the binary, or with
FLOORBIT_TELEGRAF=sidecar, leaves it to a sidecar that reads the config from the shared volume.
The API pollers (NX-API, RESTCONF, OPNsense) run here too. The picture of each device stays in
the agent's memory, where the monitoring calls through the agent link read it, so MAC tables
and ARP never leave the hall. The hosted Floorbit gets the per-port and per-device numbers for
its history (``series``) and where each machine was seen (``endpoints``).

With several agents sharing VIPs (VRRP, the agent's docs/vrrp.md) only the primary one, the holder
of the first VIP, collects: it polls and sends. The others listen only, so no device is polled or
logged into twice and the hosted Floorbit gets each minute once; a standby takes over within a
few seconds of the VIP moving to it.
"""
import base64
import collections
import contextlib
import gzip
import os
import re
import secrets
import subprocess
import tempfile
import threading
import time

from floorbit.plugins.agent import AgentPlugin as Base
from floorbit.telemetry import lineproto, pollers, supervisor, telegraf
from floorbit.telemetry import problems as problems_mod
from floorbit.telemetry import state as state_mod
from floorbit.telemetry import storage as storage_mod

PORT_ENV = 'FLOORBIT_TELEMETRY_PORT'
OUTPUT_ENV = 'FLOORBIT_TELEGRAF_OUTPUT'
CONF_ENV = 'FLOORBIT_TELEGRAF_CONF'
# "sidecar": leave Telegraf to a container next to the agent even when the image has it.
MODE_ENV = 'FLOORBIT_TELEGRAF'
DOCS = 'docs/agent.md, "Telegraf"'
PORT = 8186
POLL_EVERY = 60
SEND_EVERY = 60
QUIET_AFTER = 180          # no line from Telegraf for this long, while it has work: warn
POLL_LINE_DEVICES = 20     # devices named in the minute's poll line; the rest at debug
SUMMARY_EVERY = 300        # a line in the agent's log: what came in, from how many devices
RAW_KEPT = 50              # last lines per device for "Raw data", in memory only
RAW_DEVICES = 2000
RAW_LINE = 2000
DEVICE_TAG = re.compile(r'(?:^|,)device=((?:[^,\s\\]|\\.)+)')
TEST_TIMEOUT = 12          # a "Test now" must answer within the hosted side's call timeout (15 s)
MAX_BODY = 32 * 1024 * 1024
SERIES_PER_SEND = 30_000   # about 2 MB as JSON (keys like "sw-0001|Gi1/0/48|in_bps")
ENDPOINTS_PER_SEND = 10_000
# Drivers that Telegraf does; the others are pollers that run in this plugin.
TELEGRAF_DRIVERS = frozenset({'snmp', 'traps', 'gnmi', 'mdt'})


class AgentPlugin(Base):
    restart_on_configure = False

    def start(self):
        self.state = state_mod.state
        self.lock = threading.Lock()
        self.last_write = None
        self.poll_errors = {}
        self.problems = self.state.problems = problems_mod.Problems()
        self.binary = None if os.environ.get(MODE_ENV, '').strip().lower() == 'sidecar' else supervisor.binary()
        self.telegraf = None
        self.refused_seen = 0
        self.raw = {}                # device -> deque of its last lines, for "Raw data"
        self.heard_now = set()       # devices heard since the last look: logged when new or back
        self.summary = {'at': time.time(), 'points': 0, 'devices': set()}
        self.minute = {'at': time.time(), 'points': collections.Counter()}   # the poll line, every minute
        # Telegraf in here sends with its own token; devices that push themselves (a firewall's own
        # Telegraf, docs/telemetry.md) keep using ingest-token.
        self.push_token = self._token('ingest-token')
        self.token = self._token('own-telegraf-token') if self.binary else self.push_token
        self.targets = []
        self.primary = self.state.collecting = self.is_primary()
        self.configure(self.settings)
        # HTTPS when the hall gave the agent a certificate (FLOORBIT_AGENT_TLS_CERT/KEY): a firewall's
        # own Telegraf sends here across the event network.
        self.port = self.ctx.listen_http(int(os.environ.get(PORT_ENV) or PORT), self.handle, tls=True)
        self.write_conf()
        if self.binary:
            self._forget_sidecar_conf()
            self.telegraf = supervisor.Telegraf(self.binary, self.conf_path(), self.telegraf_line, self.ctx.log,
                                                self.ctx.stopping)
            self.telegraf.start()
        self.ctx.thread(self.loop, name='telemetry-poll')
        self.ctx.health('ok', 'waiting for devices')

    def stop(self):
        if self.telegraf:
            self.telegraf.stop()

    def _forget_sidecar_conf(self):
        """Telegraf runs in here now: a sidecar left from an older compose file finds no config on
        its next start and waits, instead of polling every device a second time."""
        if os.environ.get(CONF_ENV) or not self.ctx.state_dir:
            return
        with contextlib.suppress(OSError):
            os.remove(os.path.join(self.ctx.state_dir, 'telegraf.conf'))

    def _health(self, status, message, hint=''):
        try:
            self.ctx.health(status, message, hint=hint)
        except TypeError:      # an agent from before health hints
            self.ctx.health(status, message)

    # settings: the devices, from the hosted Floorbit's inventory ------------------
    def configure(self, settings):
        self.ctx.settings = settings
        found = settings.get('targets') if isinstance(settings, dict) else None
        with self.lock:
            self.targets = [t for t in (found or []) if isinstance(t, dict) and t.get('name')]
        self.state.know(self.targets)
        self.log_polling(settings.get('polling') if isinstance(settings, dict) else None)
        self.write_conf()
        return True

    def log_polling(self, plan):
        """Say who polls the switches when that changes (floorbit/telemetry/polling.py)."""
        if not isinstance(plan, dict) or plan == getattr(self, 'polling_said', None):
            return
        self.polling_said = plan
        if plan.get('who') == 'librenms':
            self.ctx.log(f'polling: LibreNMS polls ports and ARP/MAC tables ({plan.get("why")}); '
                         'here: traps, device facts and streams')
        else:
            minutes = plan.get('tables_minutes') or 0
            tables = f'ARP/MAC tables every {minutes} min' if minutes else 'no ARP/MAC table walks'
            self.ctx.log(f'polling: Telemetry polls ports, {tables} ({plan.get("why")})')

    def _token(self, name):
        """A token kept in the plugin's own folder, so a restart doesn't need a new Telegraf config;
        it never leaves the agent."""
        path = os.path.join(self.ctx.state_dir or '.', name)
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

    def is_primary(self):
        """Does this agent collect? Yes without VRRP; with it, while it holds the first VIP."""
        check = getattr(self.ctx, 'primary', None)
        return True if check is None else bool(check())

    def follow_role(self):
        """Became primary or standby since the last look (the VIP moved)? Then Telegraf's config
        changes with it. True when it changed."""
        if self.is_primary() == self.primary:
            return False
        self.primary = self.state.collecting = not self.primary
        self.ctx.log(f'{"primary: collecting" if self.primary else "standby: another agent collects"}')
        self.write_conf()
        return True

    def conf_path(self):
        if os.environ.get(CONF_ENV):
            return os.environ[CONF_ENV]
        return os.path.join(self.ctx.state_dir or '.', 'own-telegraf', 'telegraf.conf') if self.binary \
            else os.path.join(self.ctx.state_dir or '.', 'telegraf.conf')

    def output_url(self):
        scheme = 'https' if getattr(self.ctx, 'tls', False) else 'http'
        # In here: the agent's own listener. A sidecar reaches it by its compose name.
        host = '127.0.0.1' if self.binary else 'agent'
        return os.environ.get(OUTPUT_ENV) or f'{scheme}://{host}:{os.environ.get(PORT_ENV) or PORT}/write'

    def write_conf(self):
        """telegraf.conf, written only when it changed; Telegraf reloads it then."""
        with self.lock:
            # Telegraf reaches the agent as 127.0.0.1 or by its compose name, which the hall's
            # certificate doesn't name.
            url = self.output_url()
            settings = self.ctx.settings if isinstance(getattr(self.ctx, 'settings', None), dict) else {}
            text = telegraf.render(list(self.targets), url, self.token,
                                   tables_interval=str(settings.get('tables_interval') or '60s'),
                                   output_insecure=url.startswith(('https://agent:', 'https://127.0.0.1:')),
                                   poll=self.primary)
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
        if getattr(self, 'telegraf', None):
            self.telegraf.reload()
        return True

    def telegraf_line(self, line):
        """One line of Telegraf's output: a device's error becomes a problem it can be told by."""
        found = problems_mod.parse_line(line)
        if found is not None and self.problems.note(found):
            who = found['device'] or found['driver']
            self._warn(f'{who} ({found["driver"]}): {problems_mod.hint(found)} [{found["detail"]}]')
        elif found is None and (' E! ' in line or ' W! ' in line):
            # Telegraf's own trouble (its config, an output): no device to pin it on, but worth seeing.
            self._warn(f'telegraf: {line}')
        else:
            self._debug(f'telegraf: {line}')    # the device's problem again, or Telegraf's chatter

    def _warn(self, message):
        # A warning in the agent's log; an agent from before log levels has only ctx.log.
        getattr(self.ctx, 'warning', self.ctx.log)(message)

    def _debug(self, message):
        # An agent from before FLOORBIT_AGENT_LOG_LEVEL has no ctx.debug: those lines are left out.
        debug = getattr(self.ctx, 'debug', None)
        if debug:
            debug(message)

    # Telegraf's pushes ----------------------------------------------------------------------
    def handle(self, method, path, headers, body):
        route = path.split('?', 1)[0].rstrip('/')
        if route == '/ping' or (method == 'GET' and route in ('', '/health')):
            return 204, b''
        if method != 'POST' or route not in ('/write', '/api/v2/write'):
            return 404, 'not found'
        which = self._authorised(path, headers)
        if which is None:
            self.ctx.counter('refused_writes')
            return 401, 'bad token'
        if (headers.get('Content-Encoding') or headers.get('content-encoding') or '').lower() == 'gzip':
            try:
                body = gzip.decompress(body)
            except (OSError, EOFError):
                return 400, 'bad gzip'
        if len(body) > MAX_BODY:
            return 413, 'too large'
        if which == 'push' and self.binary and b',driver=snmp' in body:
            # SNMP polled with Floorbit's config but not by the Telegraf in here: a sidecar left over
            # from an older compose file. Refused, so a device isn't polled twice, and the warning
            # names it. (Streams relayed with this token, as the test lab does, carry other drivers.)
            self.ctx.counter('sidecar_writes')
            return 401, 'Telegraf runs in the agent now: remove the telegraf container'
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
        for g in given:
            if g and secrets.compare_digest(g, self.token):
                return 'own'
            if g and secrets.compare_digest(g, self.push_token):
                return 'push'
        return None

    def take(self, text, now=None):
        self.keep_raw(text)
        points, bad = lineproto.parse(text)
        if bad:
            self.ctx.counter('bad_lines', bad)
            self._debug(f'{bad} lines from Telegraf not understood')
        if not points:
            return None if bad else 0
        taken = self.state.apply(points, now)
        self.last_write = time.time() if now is None else now
        names = {p.tags.get('device') for p in points if p.tags.get('device')}
        self.problems.heard(names, self.last_write)
        self.summary['points'] += len(points)
        self.summary['devices'] |= names
        self.minute['points'].update(p.tags.get('device') or '?' for p in points)
        self.ctx.counter('points', len(points))
        self._debug(f'Telegraf posted {len(points)} points from {", ".join(sorted(names)) or "no device"}')
        return taken

    # the API pollers, the series for the hosted Floorbit, and health -------------------------
    def loop(self):
        next_poll = next_send = 0.0
        while not self.ctx.stopping.wait(5):
            now = time.time()
            try:
                if self.follow_role():
                    next_poll = next_send = 0.0
                # A standby agent collects only the devices given to it by name (targets.for_agent).
                if not self.primary and not self.own_targets():
                    self.report(now)
                    continue
                if now >= next_poll:
                    next_poll = now + POLL_EVERY
                    self.poll(now)
                if now >= next_send:
                    next_send = now + SEND_EVERY
                    self.send_series(now)
                    self.send_endpoints(now)
                self.report(now)
            except Exception as exc:  # noqa: BLE001  # a bad round must not end the collector
                self.ctx.error(f'{type(exc).__name__}: {exc}')

    def own_targets(self):
        with self.lock:
            return [t for t in self.targets if t.get('mine')]

    def poll(self, now):
        with self.lock:
            wanted = [t for t in self.targets if set(t.get('drivers') or []) & set(pollers.POLLERS)
                      and (self.primary or t.get('mine'))]
        if not wanted:
            return
        began = time.monotonic()
        found, errors = pollers.poll_all(wanted, now, log=self._poll_log, blocks=self.ctx)
        self.minute['points'].update(p.tags.get('device') or '?' for p in found)
        self._debug(f'API poll of {len(wanted)} devices: {len(found)} points, {len(errors)} failed, '
                    f'{(time.monotonic() - began) * 1000:.0f} ms')
        for name, err in errors.items():
            if self.poll_errors.get(name) != err:
                self.ctx.error(err)
        self.poll_errors = errors
        driver_of = {t['name']: (next((d for d in t.get('drivers') or [] if d in pollers.POLLERS), 'api'),
                                 t.get('address') or '') for t in wanted}
        found_errors = {}
        for name, err in errors.items():
            driver, address = driver_of.get(name, ('api', ''))
            found_errors[name] = (driver, err, address)
        self.problems.sync(found_errors, now)
        self.state.apply(found, now)
        self.ctx.counter('polled_points', len(found))

    def _poll_log(self, message):
        self.ctx.log(str(message).removeprefix('[telemetry] '))     # ctx.log names the plugin itself

    def send_endpoints(self, now):
        from floorbit.telemetry import clients
        settings = self.ctx.settings or {}
        rows = clients.sightings(self.state, settings.get('uplink_macs') or 8, settings.get('exclude') or ())
        if rows:
            for start in range(0, len(rows), ENDPOINTS_PER_SEND):   # in parts, as the series
                self.ctx.send('endpoints', {'at': now, 'rows': rows[start:start + ENDPOINTS_PER_SEND]})
            self.ctx.gauge('endpoints', len(rows))

    def send_series(self, now):
        values = storage_mod.snapshot(self.state, now)
        if not values:
            return
        # In parts: a 1,000-switch hall is about 200,000 series, past the 4 MB a send may carry,
        # and the whole minute was refused. The hosted side stores each part as it comes.
        items = list(values.items())
        for start in range(0, len(items), SERIES_PER_SEND):
            self.ctx.send('series', {'at': now, 'values': dict(items[start:start + SERIES_PER_SEND])})
        self.ctx.gauge('series', len(values))

    def report(self, now):
        with self.lock:
            telegraf_work = any(set(t.get('drivers') or []) & TELEGRAF_DRIVERS for t in self.targets)
            count = len(self.targets)
        online = {d.name: d for d in list(self.state.devices.values()) if d.online(now)}
        heard = len(online)
        self.log_heard(online, now)
        found = self.problems.current(now)
        failing = len({p['device'] for p in found if p['device']})
        self.ctx.gauge('devices', count)
        self.ctx.gauge('devices_heard', heard)
        self.ctx.gauge('devices_failing', failing)
        if self.last_write is not None:
            self.ctx.gauge('telegraf_quiet_seconds', round(now - self.last_write))
        self.ctx.gauge('primary', int(self.primary))
        if self.telegraf:
            self.ctx.gauge('telegraf_restarts', self.telegraf.exits)
        quiet = self.last_write is None or now - self.last_write > QUIET_AFTER
        sidecar = self.health_number('sidecar_writes')
        sidecar_left = self.binary and sidecar > self.refused_seen
        self.refused_seen = sidecar
        if not count:
            self._health('ok', 'no devices set up')
        elif not self.primary:
            self._health('ok', 'standby: the agent holding the first VIP collects')
        elif telegraf_work and self.telegraf and not self.telegraf.running() and self.telegraf.last_exit:
            last = next((x for x in reversed(self.telegraf.last_exit[2]) if x), '')
            self._health('error', f'Telegraf does not run (exit code {self.telegraf.last_exit[1]}): {last}'[:300],
                         'telegraf_stopped')
        elif sidecar_left:
            self._health('warning', 'another Telegraf (the old telegraf container?) still polls and sends here: '
                         f'remove it from the compose file ({DOCS})', 'telegraf_sidecar_left')
        elif found:
            first = found[0]
            more = f' (and {len(found) - 1} more)' if len(found) > 1 else ''
            who = first['device'] or first['driver']
            self._health('warning', f'{failing or len(found)} of {count} devices fail. {who} '
                         f'({first["driver"]}): {problems_mod.hint(first)}{more}'[:300], 'device_problems')
        elif telegraf_work and quiet and not self.binary:
            self._health('warning', 'nothing from Telegraf: this agent image has no Telegraf and no telegraf '
                         f'container sends here. Update the agent image, or start the container ({DOCS})',
                         'telegraf_missing')
        elif telegraf_work and quiet:
            self._health('warning', 'Telegraf runs but sent nothing yet: the devices may not answer; '
                         'its lines are in the agent\'s log', 'telegraf_quiet')
        else:
            self._health('ok', f'{heard} of {count} devices heard')

    def keep_raw(self, text):
        for line in text.splitlines():
            head = line.split(' ', 1)[0]
            found = DEVICE_TAG.search(head)
            if not found:
                continue
            name = found.group(1).replace('\\', '')
            kept = self.raw.get(name)
            if kept is None:
                if len(self.raw) >= RAW_DEVICES:
                    continue
                kept = self.raw[name] = collections.deque(maxlen=RAW_KEPT)
            kept.append(line[:RAW_LINE])

    def call_raw(self, args):
        """The last lines Telegraf sent for one device, as it sent them."""
        name = str((args or {}).get('name') or '')
        with self.lock:
            known = any(t.get('name') == name for t in self.targets)
        return {'name': name, 'known': known, 'lines': list(self.raw.get(name) or [])}

    def log_heard(self, online, now):
        """A line when a device is first heard or back, and every few minutes what came in: the
        agent's log says it works, not only when it doesn't."""
        for name in sorted(set(online) - self.heard_now):
            dev = online[name]
            self.ctx.log(f'{name} heard: {len(dev.interfaces)} ports via {dev.driver or "?"}'
                         + (f', {len(dev.fdb)} MACs' if dev.fdb else '') + (f', {len(dev.arp)} ARP' if dev.arp else ''))
        for name in sorted(self.heard_now - set(online)):
            self.ctx.log(f'{name} silent for a few minutes')
        self.heard_now = set(online)
        if now - self.minute['at'] >= POLL_EVERY:
            self.log_polls(now)
        if now - self.summary['at'] >= SUMMARY_EVERY:
            minutes = round((now - self.summary['at']) / 60)
            self.ctx.log(f'last {minutes} min: {self.summary["points"]} points from '
                         f'{len(self.summary["devices"])} devices, {len(online)} of {len(self.targets)} heard')
            self.summary = {'at': now, 'points': 0, 'devices': set()}

    def log_polls(self, now):
        """Every minute, what each device gave: points from Telegraf's polls and the API pollers,
        and the devices that gave nothing, with their problem."""
        counts, self.minute = self.minute['points'], {'at': now, 'points': collections.Counter()}
        with self.lock:
            names = [t['name'] for t in self.targets if self.primary or t.get('mine')]
        if not names and not counts:
            return
        problem = {p['device']: problems_mod.hint(p) for p in self.problems.current(now) if p['device']}
        got = [f'{n} {counts[n]}' for n in sorted(counts, key=lambda n: (-counts[n], n)) if n != '?']
        silent = [n + (f' ({problem[n]})' if n in problem else '') for n in sorted(names) if not counts.get(n)]
        line = (f'polls, last minute: {sum(counts.values())} points from {len(got)} of {len(names)} devices'
                + (': ' + ', '.join(got[:POLL_LINE_DEVICES]) + (' ...' if len(got) > POLL_LINE_DEVICES else '')
                   if got else ''))
        self.ctx.log(line)
        if silent:
            self._warn(f'nothing in the last minute from {len(silent)}: '
                         + ', '.join(silent[:POLL_LINE_DEVICES]) + (' ...' if len(silent) > POLL_LINE_DEVICES else ''))
        if len(got) > POLL_LINE_DEVICES:
            self._debug('polls, every device: ' + ', '.join(got))

    # "Test now": one device, once, while you watch -------------------------------------------
    def call_test(self, args):
        """Collect from one device once and say what came back, or why nothing did. Telegraf runs
        with ``--test`` on that device alone, the API pollers once; what came in also goes into the
        picture, so the floor plan has it at once."""
        name = str((args or {}).get('name') or '')
        with self.lock:
            target = next((t for t in self.targets if t.get('name') == name), None)
        if target is None:
            self.ctx.log(f'Test now: {name or "?"} is not among the devices this agent collects from')
            return {'ok': False, 'error': f'{name or "?"} is not among the devices this agent collects from'}
        result = self._test(name, target)
        said = f'Test now on {name}: {result["points"]} points in {result["took_ms"]} ms'
        if result['problems']:
            said += ' with problems: ' + '; '.join(f'{p["driver"]}: {p["hint"]}' for p in result['problems'][:3])
        if result['ok']:
            self.ctx.log(said)
        else:
            self._warn(said if result['points'] else f'{said} (failed)')
        return result

    def _test(self, name, target):
        self.ctx.log(f'Test now on {name} ({", ".join(target.get("drivers") or []) or "no driver"})')
        started = time.time()
        points, problems, notes = [], [], []
        self.last_test_raw = []
        drivers = set(target.get('drivers') or [])
        if drivers & {'snmp', 'gnmi'}:
            if not self.binary:
                problems.append({'driver': 'snmp', 'kind': 'other', 'address': target.get('address') or '',
                                 'detail': 'this agent image has no Telegraf to test with'})
            else:
                found, lines = self._telegraf_once(target)
                points += found
                problems += [p for p in map(problems_mod.parse_line, lines) if p]
                notes += [x for x in lines if ' E! ' in x][-5:]
        if drivers & set(pollers.POLLERS):
            found, errors = pollers.poll_all([target], started, log=self._poll_log, blocks=self.ctx)
            points += found
            api = sorted(drivers & set(pollers.POLLERS))[0]
            for err in errors.values():
                problems.append({'driver': api, 'kind': problems_mod.kind_of(err),
                                 'address': target.get('address') or '', 'detail': err[:300]})
        if not drivers & ({'snmp', 'gnmi'} | set(pollers.POLLERS)):
            notes.append('traps and MDT come when the device sends: nothing to ask it now')
        if points and self.primary:
            self.state.apply(points, time.time())
            self.problems.heard({name}, time.time())
        # Telegraf says it once per table: one line per kind of problem is enough.
        problems = list({(p['driver'], p['kind']): p for p in problems}.values())
        for p in problems:
            p.setdefault('device', name)
            p['hint'] = problems_mod.hint(p)
        return {'ok': bool(points) and not problems, 'name': name, 'took_ms': round((time.time() - started) * 1000),
                'points': len(points), 'summary': _summarise(points), 'problems': problems[:10], 'notes': notes,
                'raw': self.last_test_raw or [_as_line(p) for p in points[:RAW_KEPT]]}

    def _telegraf_once(self, target):
        conf = telegraf.render([target], 'http://127.0.0.1:1/write', 'unused', listen_traps=False, listen_mdt=False)
        # Secrets in it: a private file in the plugin's own folder, gone right after.
        fd, path = tempfile.mkstemp(prefix='test-', suffix='.conf', dir=self.ctx.state_dir or None)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                f.write(conf)
            try:
                done = subprocess.run([self.binary, '--config', path, '--test'], capture_output=True, text=True,
                                      errors='replace', timeout=TEST_TIMEOUT)
                out, err = done.stdout, done.stderr
            except subprocess.TimeoutExpired as exc:
                out, err = _text(exc.stdout), _text(exc.stderr)
                err += (f'\nE! [inputs.snmp::{target["name"]}] Error in plugin: '
                        f'no answer within {TEST_TIMEOUT} s (timeout)')
        finally:
            with contextlib.suppress(OSError):
                os.remove(path)
        # "> " starts each metric Telegraf prints in test mode.
        raw = [x[2:][:RAW_LINE] for x in out.splitlines() if x.startswith('> ')]
        self.last_test_raw = raw[:RAW_KEPT]
        found, _bad = lineproto.parse('\n'.join(raw))
        now = time.time()
        for p in found:
            p.time = now
        return found, err.splitlines()

    def health_number(self, name):
        health = getattr(self.ctx, 'health_', None)
        return (getattr(health, 'counters', None) or {}).get(name, 0)

    def check(self):
        where = f'runs Telegraf {self.binary}' if self.binary else 'Telegraf in a telegraf container'
        return (f'{len(self.targets)} devices, listening on :{self.port}, {where}, '
                f'config {self.conf_path()}')


def _summarise(points):
    """What a test brought back, short: points per measurement, ports, the device's own name."""
    by = {}
    ports = set()
    sys_name = None
    for p in points:
        by[p.measurement] = by.get(p.measurement, 0) + 1
        if p.tags.get('ifName') or p.tags.get('name'):
            ports.add(p.tags.get('ifName') or p.tags.get('name'))
        sys_name = sys_name or p.fields.get('sysName') or p.tags.get('sysName')
    return {'measurements': dict(sorted(by.items())), 'ports': len(ports), 'sys_name': sys_name}


def _as_line(point):
    """A poller's point as line protocol, for "Raw data" (Telegraf's come as it sent them)."""
    tags = ''.join(f',{k}={v}' for k, v in sorted(point.tags.items()))
    fields = ','.join(f'{k}={v!r}' if isinstance(v, str) else f'{k}={v}' for k, v in point.fields.items())
    return f'{point.measurement}{tags} {fields}'[:RAW_LINE]


def _text(value):
    return value.decode('utf-8', 'replace') if isinstance(value, bytes) else (value or '')
