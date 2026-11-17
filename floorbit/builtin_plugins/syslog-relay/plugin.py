"""Syslog from the hall (docs/syslog.md): what the agent part heard goes to the same place as
syslog a local agent relays without the plugin (floorbit/syslog.py, ``relay``)."""
from flask import current_app

from floorbit import agent_link, features
from floorbit.plugins.base import Plugin as Base
from floorbit.plugins.base import PluginError

BATCH = 2000


class Plugin(Base):
    def agent_lines(self, agent, payload):
        receiver = current_app.extensions.get('floorbit_syslog')
        if receiver is None or not features.on('syslog'):
            raise PluginError('Syslog is turned off on this Floorbit (Settings > Features).')
        lines = payload.get('lines') if isinstance(payload.get('lines'), list) else []
        dropped = payload.get('dropped') if isinstance(payload.get('dropped'), int) else 0
        taken = receiver.relay(agent['name'], lines[:BATCH], dropped=dropped)
        if lines:
            agent_link.tunnel.relayed(agent['id'], 'syslog', taken)
        return {'taken': taken}
