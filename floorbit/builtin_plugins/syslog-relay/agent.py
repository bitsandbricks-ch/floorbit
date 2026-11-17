"""The syslog relay's part in the hall: the agent's Relay (floorbit_agent/syslog_relay.py), fed
from a UDP port and sending through the plugin's disk spool instead of its own."""
from floorbit.plugins.agent import AgentPlugin as Base
from floorbit.plugins.base import PluginError

CHUNK = 500        # lines per send: well under the 4 MB a send may hold, at 2 KB a line
EVERY = 10         # seconds between the numbers in the report


class AgentPlugin(Base):
    relay = None

    def start(self):
        port = int(self.settings.get('port') or 0)
        if not port:
            self.ctx.health('off', 'No port set: the agent does not listen for syslog.')
            return
        from floorbit_agent.syslog_relay import Relay  # this part only ever runs in the agent
        self.relay = Relay(self._send, port, (self.settings.get('bind') or '').strip() or '0.0.0.0',
                           log=self.ctx.log)
        try:
            self.port = self.relay.start()
        except (OSError, OverflowError) as exc:
            self.relay = None
            raise PluginError(f'cannot listen for syslog on UDP {port}: {exc}') from exc
        self.ctx.on_stop(self.relay.stop)
        self.ctx.health('ok', f'listening on UDP {self.port}')
        self.ctx.thread(self._numbers, name='syslog-relay-numbers')

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

    def check(self):
        if self.relay is None:
            return 'off (no port set)'
        return f'listening for syslog on UDP {self.port}, {self.relay.received} lines so far'
