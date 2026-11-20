"""The attendees' front door in the hall: the agent's front door (floorbit_agent/front_door.py),
answering on the event network with the agent's own link to Floorbit."""
import os

from floorbit.plugins.agent import AgentPlugin as Base
from floorbit.plugins.base import PluginError

EVERY = 10         # seconds between the numbers in the report


class AgentPlugin(Base):
    door = server = None

    def start(self):
        address = (self.settings.get('address') or '').strip()
        if not address:
            self.ctx.health('off', 'No address set: the agent does not answer attendees.')
            return
        from floorbit_agent import front_door  # this part only ever runs in the agent
        agent = self.ctx.host.agent
        proxies = [p for p in str(self.settings.get('proxies') or '').split(',') if p.strip()]
        # Signed with the agent's own key (identity.py): Floorbit trusts the attendee's address only then.
        self.door = front_door.FrontDoor(agent.url, agent.key, proxies=proxies, log=self.ctx.log,
                                         auth=getattr(agent, 'signer', None))
        try:
            # The agent machine's certificate (FLOORBIT_AGENT_TLS_CERT/KEY), as for telemetry.
            context = front_door.tls_context(os.environ)
            self.server = front_door.serve(self.door, address, context)
        except (ValueError, OSError, OverflowError) as exc:
            self.door = None
            raise PluginError(f'cannot answer on {address} (host:port, and the TLS certificate if set): {exc}') from exc
        self.ctx.on_stop(self.server.shutdown)
        scheme = 'https' if context else 'http'
        self.ctx.health('ok', f'answering attendees on {scheme}://{address}')
        self.ctx.thread(self._numbers, name='front-door-numbers')

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
        return f"answering attendees, {sum(self.door.counts.values())} requests so far"
