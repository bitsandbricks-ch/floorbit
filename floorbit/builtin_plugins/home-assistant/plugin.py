"""Home Assistant meters (docs/power.md): what the agent read, for the Electrics page's poll."""
from floorbit import power
from floorbit.plugins.base import Plugin as Base


class Plugin(Base):
    def agent_readings(self, agent, payload):
        return {'kept': power.keep_agent_readings('home-assistant', payload.get('readings'))}

    def power_readings(self):
        return power.agent_readings('home-assistant')
