"""The check-in note (docs/integrations.md): which addresses are done, for the agent's Captive Portal
API, as the agent asks for them without the plugin."""
from flask import current_app

from floorbit.plugins.base import Plugin as Base
from floorbit.plugins.base import PluginError


class Plugin(Base):
    def agent_get_state(self, agent):
        from integrations import config
        if not config.get_bool('CHECKIN_ENABLED', False):
            raise PluginError('Check-in is turned off on this Floorbit.')
        if not config.get_bool('CAPTIVE_ENABLED', False):
            raise PluginError('The captive portal is turned off on this Floorbit.')
        from floorbit import captive
        return captive.answer(current_app, agent=agent.get('name'))
