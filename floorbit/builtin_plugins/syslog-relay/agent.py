"""The syslog relay's part in the hall: the agent's Relay (floorbit_agent/syslog_relay.py), fed
from a UDP port and sending through the plugin's disk spool instead of its own."""
from floorbit.plugins.agent import AgentPlugin as Base
from floorbit.plugins.base import PluginError

CHUNK = 500        # lines per send: well under the 4 MB a send may hold, at 2 KB a line
EVERY = 10         # seconds between the numbers in the report


class AgentPlugin(Base):
    relay = None
    restart_on_configure = False

    def _keep(self):
        others = frozenset(self.settings.get('others') or ())
        return (lambda sender: sender not in others) if others else None

    def start(self):
        port = int(self.settings.get('port') or 0)
        if not port:
            self.ctx.health('off', 'No port set: the agent does not listen for syslog.')
            return
        from floorbit_agent.syslog_relay import Relay  # this part only ever runs in the agent
        bind = (self.settings.get('bind') or '').strip() or '0.0.0.0'
        try:
            self.relay = Relay(self._send, port, bind, log=self.ctx.log, keep=self._keep())
        except TypeError:   # an agent from before the split: it sends every line, as before
            self.relay = Relay(self._send, port, bind, log=self.ctx.log)
        self.listening = (port, bind)
        try:
            self.port = self.relay.start()
        except (OSError, OverflowError) as exc:
            self.relay = None
            raise PluginError(f'cannot listen for syslog on UDP {port}: {exc}') from exc
        self.ctx.on_stop(self.relay.stop)
        self.ctx.health('ok', f'listening on UDP {self.port}')
        self.ctx.thread(self._numbers, name='syslog-relay-numbers')

    def configure(self, settings):
        """New owners keep the relay running, so the held minute survives; a new port restarts it."""
        settings = settings or {}
        same = (int(settings.get('port') or 0), (settings.get('bind') or '').strip() or '0.0.0.0')
        if self.relay is None or getattr(self, 'listening', None) != same or not hasattr(self.relay, 'take_over'):
            return False
        self.ctx.settings = settings
        taken = self.relay.take_over(self._keep() or (lambda sender: True))
        if taken:
            self.ctx.log(f"took over {taken} held syslog lines of devices now this agent's own")
        return True

    def _send(self, lines, dropped):
        # The spool keeps them on disk until the hosted side has them; this never waits on the link.
        for i in range(0, len(lines), CHUNK):
            self.ctx.send('lines', {'lines': lines[i:i + CHUNK], 'dropped': dropped})

    def _numbers(self):
        while not self.ctx.stopping.wait(EVERY):
            relay = self.relay
            if relay is None:
                return
            self.ctx.gauge('received', relay.received)
            self.ctx.gauge('dropped', relay.all_dropped)
            self.ctx.gauge('waiting', len(relay.lines))
            self.ctx.gauge('held', len(getattr(relay, 'held', ())))

    def check(self):
        if self.relay is None:
            return 'off (no port set)'
        return f'listening for syslog on UDP {self.port}, {self.relay.received} lines so far'
