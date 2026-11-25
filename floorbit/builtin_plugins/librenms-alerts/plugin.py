"""LibreNMS alerts (issue #951): the hosted part. Each agent gets the token LibreNMS shows; what
the agent passes on goes to floorbit/librenms_alerts.py."""
from floorbit import librenms_alerts
from floorbit.plugins.base import Plugin as Base
from floorbit.plugins.base import PluginError


class Plugin(Base):
    def agent_settings(self, settings):
        # Made on first use and kept sealed: nobody has to type a token in Floorbit (zero setup).
        return {**settings, 'token': librenms_alerts.token()}

    def agent_alert(self, agent, payload):
        try:
            from floorbit import agent_ha
            return {'result': librenms_alerts.take(payload, agent=agent.get('name'),
                                                   scope=agent_ha.group_key(agent.get('id')))}
        except librenms_alerts.AlertError as exc:
            # Declined, not retried: the same body would fail again. The plugin log says why.
            raise PluginError(str(exc)) from exc

    def test(self):
        found = librenms_alerts.setup()
        if not found['agents']:
            return 'No local agent yet: LibreNMS sends its alerts to one.'
        return 'LibreNMS posts to ' + ', '.join(a['url'] for a in found['agents'])
