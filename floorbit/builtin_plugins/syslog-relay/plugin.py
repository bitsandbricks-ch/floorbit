"""Syslog from the hall (docs/syslog.md): what the agent part heard goes to the same place as
syslog a local agent relays without the plugin (floorbit/syslog.py, ``relay``)."""
from flask import current_app

from floorbit import agent_clock, agent_link, features
from floorbit.plugins.base import Plugin as Base
from floorbit.plugins.base import PluginError

BATCH = 2000


class Plugin(Base):
    def agent_settings(self, settings, agent_id=None):
        """In a group that splits its devices (#1441), the addresses of those another agent owns:
        the agent part holds their lines for a takeover instead of sending them."""
        if agent_id is None:
            return settings
        from floorbit.telemetry import targets
        connected = agent_link.tunnel.connected_agents()
        given = targets.for_agent(targets.listing(), agent_id, connected)
        others = sorted({str(t[k]) for t in given if t.get('split') and not t.get('mine')
                         for k in ('address', 'name') if t.get(k)})
        return {**settings, 'others': others}

    def agent_lines(self, agent, payload):
        receiver = current_app.extensions.get('floorbit_syslog')
        if receiver is None or not features.on('syslog'):
            raise PluginError('Syslog is turned off on this Floorbit (Settings > Plugins > Built in).')
        lines = payload.get('lines') if isinstance(payload.get('lines'), list) else []
        dropped = payload.get('dropped') if isinstance(payload.get('dropped'), int) else 0
        taken = receiver.relay(agent['name'], lines[:BATCH], dropped=dropped,
                              offset=agent_clock.offset(agent))
        if lines:
            agent_link.tunnel.relayed(agent['id'], 'syslog', taken)
        return {'taken': taken}
