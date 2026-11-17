"""The check-in note's part in the hall: the agent's Captive Portal API (floorbit_agent/captive.py),
asking the hosted part which addresses are done."""
from floorbit.plugins.agent import AgentPlugin as Base
from floorbit.plugins.agent import HostedSaidNo
from floorbit.plugins.base import PluginError


class AgentPlugin(Base):
    api = server = None

    def start(self):
        address = (self.settings.get('address') or '').strip()
        if not address:
            self.ctx.health('off', 'No address set: the agent does not answer the Captive Portal API.')
            return
        from floorbit_agent import captive  # this part only ever runs in the agent
        proxies = [p for p in str(self.settings.get('proxies') or '').split(',') if p.strip()]
        self.api = captive.Captive(self._ask, self.settings.get('portal_url') or '', proxies, log=self.ctx.log)
        try:
            self.server = captive.serve(self.api, address, log=self.ctx.log)
        except (ValueError, OSError, OverflowError) as exc:
            raise PluginError(f'cannot answer on {address} (host:port): {exc}') from exc
        self.ctx.on_stop(self.api.stop)
        self.ctx.on_stop(self.server.shutdown)
        self.ctx.health('ok', f'answering on {address}')

    def _ask(self):
        try:
            return self.ctx.fetch('state')
        except HostedSaidNo as exc:      # check-in is off there: Captive says nothing to anyone
            raise RuntimeError(str(exc)) from exc

    def check(self):
        if self.api is None:
            return 'off (no address set)'
        if self.api.error:
            raise PluginError(self.api.error)
        return f'answering, {len(self.api.done)} addresses checked in'
