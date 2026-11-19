"""LibreNMS alerts' part in the hall: an HTTP port LibreNMS's API transport posts to. The agent
checks the token and passes each alert on; it keeps nothing."""
import json
import secrets

from floorbit.plugins.agent import AgentPlugin as Base
from floorbit.plugins.base import PluginError

MAX_BODY = 256 * 1024     # one alert with its faults; LibreNMS sends far less
PATH = '/librenms'


class AgentPlugin(Base):
    port = None

    def start(self):
        port = int(self.settings.get('port') or 0)
        self.token = str(self.settings.get('token') or '')
        if not port:
            self.ctx.health('off', 'No port set: the agent does not take LibreNMS alerts.')
            return
        if not self.token:
            self.ctx.health('off', 'No token from Floorbit yet.')
            return
        try:
            self.port = self.ctx.listen_http(port, self.handle, tls=True)
        except (OSError, OverflowError) as exc:
            raise PluginError(f'cannot listen for LibreNMS alerts on port {port}: {exc}') from exc
        tls = bool(getattr(self.ctx, 'tls', False))
        self.ctx.gauge('tls', 1 if tls else 0)      # Floorbit shows LibreNMS http:// or https://
        self.ctx.health('ok', f"listening on port {self.port} ({'HTTPS' if tls else 'HTTP'})")

    def handle(self, method, path, headers, body):
        route = path.split('?', 1)[0].rstrip('/')
        if method != 'POST' or route != PATH:
            return 404, 'not found'
        auth = headers.get('Authorization') or headers.get('authorization') or ''
        scheme, _, given = auth.partition(' ')
        if scheme.lower() != 'bearer' or not secrets.compare_digest(given.strip(), self.token):
            self.ctx.counter('refused')
            return 401, 'bad token'
        if len(body) > MAX_BODY:
            return 413, 'too large'
        try:
            alert = json.loads(body.decode('utf-8', 'replace'))
        except ValueError:
            self.ctx.counter('bad_json')
            return 400, 'not JSON: check the body template in Floorbit'
        if not isinstance(alert, dict):
            return 400, 'not a JSON object'
        self.ctx.send('alert', alert)
        self.ctx.counter('alerts')
        return 202, b''

    def check(self):
        return f'listening for LibreNMS alerts on port {self.port}' if self.port else 'off'
