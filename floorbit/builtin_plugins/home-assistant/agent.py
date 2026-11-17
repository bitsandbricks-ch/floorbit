"""Home Assistant meters, the agent's part: one GET /api/states per round, the listed sensors'
values sent as watts or amps per meter id."""
import hashlib
import json
import ssl
import urllib.error
import urllib.request

from floorbit.plugins.agent import AgentPlugin as Base
from floorbit.plugins.base import PluginError

CREDENTIAL = 'home-assistant'
TIMEOUT = 8
UNITS = {'W': ('watts', 1), 'kW': ('watts', 1000), 'A': ('amps', 1), 'mA': ('amps', 0.001)}


def parse_sensors(text):
    """``[(meter, entity id)]`` from the Sensors setting; bad lines skipped."""
    out = []
    for line in str(text or '').splitlines():
        meter, sep, entity = line.partition('=')
        if sep and meter.strip() and '.' in entity.strip():
            out.append((meter.strip(), entity.strip()))
    return out


def reading(state):
    """``{"watts" | "amps": value}`` from one entity's state, or None."""
    unit = UNITS.get(str((state.get('attributes') or {}).get('unit_of_measurement') or ''))
    try:
        value = float(state.get('state'))
    except (TypeError, ValueError):
        return None                    # unavailable, unknown
    return {unit[0]: round(value * unit[1], 2)} if unit else None


class AgentPlugin(Base):
    def start(self):
        self.sensors = parse_sensors(self.settings.get('sensors'))
        self.url = (self.settings.get('url') or '').rstrip('/')
        self.interval = max(5, int(self.settings.get('interval') or 15))
        self.rev = hashlib.sha256(str(self.settings.get('token') or '').encode()).hexdigest()[:12]
        if not (self.url and self.settings.get('token') and self.sensors):
            self.ctx.health('off', 'Set the URL, the access token and the sensors.')
            return
        self.ctx.thread(self.loop, name='home-assistant-read')

    def states(self):
        req = urllib.request.Request(f'{self.url}/api/states',
                                     headers={'Authorization': f"Bearer {self.settings.get('token')}"})
        context = None
        if self.url.startswith('https://') and self.settings.get('verify_ssl') is False:
            context = ssl._create_unverified_context()   # the hall chose to skip the check
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=context) as resp:
            return {s.get('entity_id'): s for s in json.loads(resp.read()) if isinstance(s, dict)}

    def tick(self):
        if not self.ctx.may_login(self.url, CREDENTIAL, self.rev):
            self.ctx.health('error', 'The access token was refused: waiting for a tech to clear it.')
            return [], ['token refused']
        try:
            states = self.states()
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                why = f'Home Assistant refused the token (HTTP {exc.code})'
                self.ctx.auth_failed(self.url, CREDENTIAL, self.rev, why)
                self.ctx.health('error', 'The access token was refused.')
                return [], ['token refused']
            self.ctx.health('error', f'Home Assistant answered HTTP {exc.code}')
            return [], [f'HTTP {exc.code}']
        except (OSError, ValueError) as exc:
            self.ctx.health('error', f'cannot reach Home Assistant: {getattr(exc, "reason", exc)}')
            return [], ['unreachable']
        readings, failed = [], []
        for meter, entity in self.sensors:
            value = reading(states.get(entity) or {}) if entity in states else None
            if value is None:
                why = 'has no value in W, kW or A' if entity in states else 'not found'
                failed.append(f'{meter}: {entity} {why}')
            else:
                readings.append({'meter': meter, **value})
        if readings:
            self.ctx.send('readings', {'readings': readings})
        self.ctx.gauge('meters_read', len(readings))
        self.ctx.gauge('meters_failing', len(failed))
        if failed:
            self.ctx.health('warning' if readings else 'error',
                            f'{len(failed)} of {len(self.sensors)} sensors: {failed[0]}')
        else:
            self.ctx.health('ok', f'{len(readings)} sensors read')
        return readings, failed

    def loop(self):
        while not self.ctx.stopping.is_set():
            # Two agents in one hall (VRRP): only the primary asks, so no device is asked twice.
            if self.ctx.primary():
                self.tick()
            else:
                self.ctx.health('ok', 'Standby: the primary agent reads the sensors')
            self.ctx.stopping.wait(self.interval)

    def check(self):
        readings, failed = self.tick()
        if failed and not readings:
            raise PluginError(failed[0])
        return f'{len(readings)} of {len(self.sensors)} sensors read'
