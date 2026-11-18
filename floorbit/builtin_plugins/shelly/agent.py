"""Shelly meters, the agent's part: ask each Shelly for its load over its local HTTP API and send
the watts per meter id. Later generations answer /rpc/Shelly.GetStatus (digest auth), the first
/status (basic auth)."""
import hashlib
import http.client
import json
import math
import urllib.error
import urllib.request

from floorbit.plugins.agent import AgentPlugin as Base

CREDENTIAL = 'shelly'
TIMEOUT = 4
# Later generations: where each kind of channel says its power.
RPC_POWER = {'switch': 'apower', 'pm1': 'apower', 'cover': 'apower', 'em1': 'act_power', 'em': 'total_act_power'}


def _watts(value):
    # A real reading: a finite number, not True (JSON lets a device send NaN, and bool is an int).
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


class Refused(Exception):
    """The Shelly wants a password, or another one."""


def parse_devices(text):
    """``[(meter, host, channel or None)]`` from the lines of the Meters setting; bad lines skipped."""
    out = []
    for line in str(text or '').splitlines():
        meter, sep, rest = line.partition('=')
        parts = rest.split()
        if sep and meter.strip() and parts:
            host = parts[0].removeprefix('http://').rstrip('/')
            out.append((meter.strip(), host, parts[1] if len(parts) > 1 else None))
    return out


def watts_from_rpc(status, channel=None):
    """Watts from a later generation's Shelly.GetStatus: one channel, or all of them added up."""
    total, found = 0.0, False
    if not isinstance(status, dict):
        return None
    for key, value in status.items():
        kind = key.split(':')[0]
        if kind not in RPC_POWER or not isinstance(value, dict) or (channel and key != channel):
            continue
        power = value.get(RPC_POWER[kind])
        if _watts(power):
            total, found = total + power, True
    return round(total, 1) if found else None


def watts_from_status(status, channel=None):
    """Watts from a first generation's /status: meters (plugs, relays) or emeters (EM, 3EM)."""
    if not isinstance(status, dict):
        return None
    rows = [r for key in ('meters', 'emeters') if isinstance(status.get(key), list) for r in status[key]]
    if channel is not None:
        try:
            index = int(channel)
            if index < 0:
                return None
            rows = [rows[index]]
        except (ValueError, IndexError):
            return None
    powers = [r.get('power') for r in rows if isinstance(r, dict) and _watts(r.get('power'))]
    return round(sum(powers), 1) if powers else None


class AgentPlugin(Base):
    def start(self):
        self.devices = parse_devices(self.settings.get('devices'))
        self.interval = max(5, int(self.settings.get('interval') or 15))
        password = self.settings.get('password') or ''
        # Which password was refused: a new one here is worth a try, the same one is not.
        self.rev = hashlib.sha256(f"{self.settings.get('username')}\n{password}".encode()).hexdigest()[:12]
        if not self.devices:
            self.ctx.health('off', 'No meters set.')
            return
        self.ctx.thread(self.loop, name='shelly-read')

    def _open(self, url):
        password = self.settings.get('password') or ''
        handlers = []
        if password:
            manager = urllib.request.HTTPPasswordMgrWithDefaultRealm()
            manager.add_password(None, url, self.settings.get('username') or 'admin', password)
            handlers = [urllib.request.HTTPDigestAuthHandler(manager), urllib.request.HTTPBasicAuthHandler(manager)]
        try:
            with urllib.request.build_opener(*handlers).open(url, timeout=TIMEOUT) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise Refused(exc.code) from exc
            raise

    def read(self, host, channel):
        try:
            return watts_from_rpc(self._open(f'http://{host}/rpc/Shelly.GetStatus'), channel)
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                raise
        return watts_from_status(self._open(f'http://{host}/status'), channel)   # first generation

    def tick(self):
        readings, failed = [], []
        for meter, host, channel in self.devices:
            if not self.ctx.may_login(host, CREDENTIAL, self.rev):
                failed.append(f'{meter}: password refused, waiting for a tech')
                continue
            try:
                watts = self.read(host, channel)
            except Refused as exc:
                self.ctx.auth_failed(host, CREDENTIAL, self.rev, f'{host} refused the password (HTTP {exc})')
                failed.append(f'{meter}: password refused')
                continue
            except (OSError, ValueError, http.client.HTTPException) as exc:
                # HTTPException: something that isn't a web server answers at that address.
                failed.append(f'{meter}: {getattr(exc, "reason", exc) or type(exc).__name__}')
                continue
            if watts is None:
                failed.append(f'{meter}: {host} has no power reading{" on " + channel if channel else ""}')
                continue
            readings.append({'meter': meter, 'watts': watts})
        if readings:
            self.ctx.send('readings', {'readings': readings})
        self.ctx.gauge('meters_read', len(readings))
        self.ctx.gauge('meters_failing', len(failed))
        if failed:
            self.ctx.health('warning' if readings else 'error',
                            f'{len(failed)} of {len(self.devices)} meters: {failed[0]}')
        else:
            self.ctx.health('ok', f'{len(readings)} meters read')
        return readings, failed

    def loop(self):
        while not self.ctx.stopping.is_set():
            # Two agents in one hall (VRRP): only the primary asks, so no device is asked twice.
            try:
                if self.ctx.primary():
                    self.tick()
                else:
                    self.ctx.health('ok', 'Standby: the primary agent reads the meters')
            except Exception as exc:  # noqa: BLE001  # one odd round must not stop the readings for the event
                self.ctx.health('error', f'a round failed: {type(exc).__name__}: {exc}'[:300])
                self.ctx.error(f'a round failed: {type(exc).__name__}: {exc}')
            self.ctx.stopping.wait(self.interval)

    def check(self):
        readings, failed = self.tick()
        if failed and not readings:
            from floorbit.plugins.base import PluginError
            raise PluginError(failed[0])
        return f'{len(readings)} of {len(self.devices)} meters read'
