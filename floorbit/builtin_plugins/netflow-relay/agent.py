"""Traffic from the hall, the agent's part: the agent's flow collector (floorbit_agent/flows_relay.py,
which runs floorbit/flows) on a UDP port, with the seats from the hosted part and its summary sent
through the plugin, newest only."""
from floorbit.plugins.agent import AgentPlugin as Base
from floorbit.plugins.base import PluginError

EVERY = 10


class _Link:
    """What FlowsRelay asks of the agent, answered through the plugin."""

    def __init__(self, ctx):
        self.ctx = ctx
        self.classifier = None   # the collector's, once the relay exists

    def flow_seats(self):
        body = self.ctx.fetch('seats') or {}
        # The applications' rules come with the seats (floorbit/applications.py).
        if self.classifier is not None and isinstance(body.get('applications'), list):
            self.classifier.set_applications(body['applications'])
        return body

    def send_flows(self, snapshot):
        self.ctx.send('summary', snapshot)


class AgentPlugin(Base):
    relay = None

    def start(self):
        port = int(self.settings.get('port') or 0)
        if not port:
            self.ctx.health('off', 'No port set: the agent does not collect flows.')
            return
        from floorbit_agent.flows_relay import FlowsRelay  # this part only ever runs in the agent
        link = _Link(self.ctx)
        self.relay = FlowsRelay(link, port, (self.settings.get('bind') or '').strip() or '0.0.0.0',
                                log=self.ctx.log)
        link.classifier = getattr(getattr(self.relay.collector, 'agg', None), 'classify', None)
        try:
            self.port = self.relay.start()
        except (OSError, OverflowError) as exc:
            self.relay = None
            raise PluginError(f'cannot listen for flows on UDP {port}: {exc}') from exc
        self.ctx.on_stop(self.relay.stop)
        self.ctx.health('ok', f'listening on UDP {self.port}')
        self.ctx.thread(self._numbers, name='netflow-relay-numbers')

    def _numbers(self):
        while not self.ctx.stopping.wait(EVERY):
            if self.relay is None:
                return
            self.ctx.gauge('packets', self.relay.packets)
            self.ctx.gauge('summaries', self.relay.sent)

    def check(self):
        if self.relay is None:
            return 'off (no port set)'
        return f'collecting flows on UDP {self.port}, {self.relay.packets} packets so far'
