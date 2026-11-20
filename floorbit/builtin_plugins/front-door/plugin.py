"""The attendees' front door (docs/agent.md): all of it runs on the agent. The requests it hands on
are checked here with the agent's key, as before the plugin existed. ``state`` is what the agent's
check-in note on phones asks: which addresses are done."""
from flask import current_app

from floorbit.plugins.base import Plugin as Base
from floorbit.plugins.base import PluginError


class Plugin(Base):
    def agent_get_state(self, agent):
        from integrations import config
        if not config.get_bool('CHECKIN_ENABLED', False):
            raise PluginError('Check-in is turned off on this Floorbit.')
        from floorbit import captive
        return captive.answer(current_app, agent=agent.get('name'))
