"""Traffic from the hall (docs/agent.md, "Traffic"): the seats' addresses for the agent's
collector, and its summary for the Traffic page, as the agent sends them without the plugin."""
from floorbit import features
from floorbit.plugins.base import Plugin as Base
from floorbit.plugins.base import PluginError

OFF = 'Traffic is turned off on this Floorbit (Settings > Plugins > Built in).'


class Plugin(Base):
    def agent_get_seats(self, agent):
        if not features.on('traffic'):
            raise PluginError(OFF)
        from floorbit import applications, game_servers
        from floorbit.flows import seat_maps
        seat_of, area_of = seat_maps()
        # The applications' ports and addresses travel with the seats, so the agent names games too.
        return {'seat_of': seat_of, 'area_of': area_of,
                'applications': applications.flow_rules(servers=game_servers.listing())}

    def agent_summary(self, agent, payload):
        if not features.on('traffic'):
            raise PluginError(OFF)
        from floorbit.blueprints.agent import take_flow_summary
        if not take_flow_summary(agent, payload):
            raise PluginError('snapshot is missing')
        return {'ok': True}
