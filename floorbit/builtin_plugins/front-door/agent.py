"""The attendees' front door in the hall: the agent's front door (floorbit_agent/front_door.py),
answering on the event network with the agent's own link to Floorbit. One listener for everything
attendees and the crew open in the hall: check-in, the speed test, the check-in note on phones
(floorbit_agent/captive.py) and the seat walk-through's hello."""
import os

from floorbit.plugins.agent import AgentPlugin as Base
from floorbit.plugins.agent import HostedSaidNo
from floorbit.plugins.base import PluginError

EVERY = 10         # seconds between the numbers in the report


class AgentPlugin(Base):
    door = api = None
    servers = ()
    answering = ''

    def start(self):
        address = (self.settings.get('address') or '').strip()
        plain = (self.settings.get('http_address') or '').strip()
        if not address and not plain:
            self.ctx.health('off', 'No address set: the agent does not answer attendees.')
            return
        from floorbit_agent import captive, front_door  # this part only ever runs in the agent
        agent = getattr(self.ctx, 'host', None) and self.ctx.host.agent
        proxies = [p for p in str(self.settings.get('proxies') or '').split(',') if p.strip()]
        # The crew's seat walk-through (docs/seat-walk.md) says hello on the same port.
        self.api = captive.Captive(self._ask, '', proxies, log=self.ctx.log,
                                   say_hello=agent.seat_walk_hello if agent else None,
                                   floorbit_url=agent.url if agent else '')
        # Signed with the agent's own key (identity.py): Floorbit trusts the attendee's address only then.
        self.door = front_door.FrontDoor(agent.url if agent else '', agent.key if agent else '',
                                         proxies=proxies, log=self.ctx.log, auth=getattr(agent, 'signer', None))
        servers, where = [], []
        # A new certificate (Floorbit's or the hall's) restarts this plugin with it (PluginHost.restart_tls).
        self.ctx.tls_wanted = True
        try:
            # The agent machine's certificate (FLOORBIT_AGENT_TLS_CERT/KEY), as for telemetry.
            env = self.ctx.host.env if getattr(self.ctx, 'host', None) is not None else os.environ
            context = front_door.tls_context(env)
            if address:
                servers.append(front_door.serve(self.door, address, context, captive=self.api, log=self.ctx.log))
                where.append(f"{'https' if context else 'http'}://{address}")
            if plain:
                servers.append(front_door.serve(self.door, plain, None, captive=self.api, log=self.ctx.log,
                                                to_https=context is not None))
                where.append(f'http://{plain}' + (' (on to HTTPS)' if context else ''))
        except (ValueError, OSError, OverflowError) as exc:
            for server in servers:
                server.shutdown()
                server.server_close()
            self.door = self.api = None
            raise PluginError(f'cannot answer on {address or plain} (host:port, and the TLS certificate if set): '
                              f'{exc}') from exc
        self.servers = servers
        for server in servers:
            self.ctx.on_stop(server.server_close)
            self.ctx.on_stop(server.shutdown)
        self.ctx.on_stop(self.api.stop)
        self.ctx.thread(self.api.run, name='front-door-note')
        self.answering = ' and '.join(where)
        self.ctx.log(f'answering attendees on {self.answering}')
        self.ctx.health('ok', f'answering attendees on {self.answering}')
        self.ctx.thread(self._numbers, name='front-door-numbers')

    def _ask(self):
        try:
            return self.ctx.fetch('state')
        except HostedSaidNo as exc:      # check-in is off there: say nothing to anyone
            raise RuntimeError(str(exc)) from exc

    def _numbers(self):
        while not self.ctx.stopping.wait(EVERY):
            door = self.door
            if door is None:
                return
            for outcome, n in dict(door.counts).items():
                self.ctx.gauge(f'requests_{outcome}', n)
            self.ctx.gauge('open', door.open)

    def check(self):
        if self.door is None:
            return 'off (no address set)'
        if self.api is not None and self.api.error:
            return (f"answering attendees on {self.answering}, {sum(self.door.counts.values())} requests so far; "
                    f"check-in note: {self.api.error}")
        return f"answering attendees on {self.answering}, {sum(self.door.counts.values())} requests so far"
