"""What each plugin is doing (#1435), for the state badge on Settings > Plugins.

The switch says whether a plugin is meant to run; this says what it does: receiving data, set up
but waiting, not set up yet, failing, or off. Worked out from what is there (the plugin's own
``configured()``, each connected agent's last report), nothing stored.

``{id: {'state': ..., 'values': {...}}}``. States: ``broken`` (didn't load), ``off``, ``no_agent``
(an agent part and no agent connected), ``failing`` (an agent says its part fails),
``not_configured``, ``receiving`` (data arrives), ``waiting`` (running, nothing arrived yet), ``on``.
"""

# Counters in an agent's report that show a plugin's data arriving (since the agent started).
EVIDENCE = {
    'syslog-relay': ('syslog_received',),
    'netflow-relay': ('flows_packets',),
    'front-door': ('captive_shown', 'captive_done'),
}


def _number(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else 0


def _set_up(registry, spec):
    try:
        return registry.set_up(spec)
    except Exception:  # noqa: BLE001  # a plugin's own check must not break the list
        return False


def one(registry, spec, agents):
    """The state of one plugin. ``agents``: agent_link.all_agents(), connected or not."""
    if spec.error:
        return {'state': 'broken', 'values': {}}
    if not registry.enabled(spec):
        return {'state': 'off', 'values': {}}
    if not spec.agent:
        return {'state': 'on' if _set_up(registry, spec) else 'not_configured', 'values': {}}
    connected = [a for a in agents if a.get('connected')]
    if not connected:
        return {'state': 'no_agent', 'values': {}}
    health = {a['name']: ((a.get('report') or {}).get('plugins') or {}).get(spec.id) for a in connected}
    failing = sorted(n for n, h in health.items() if isinstance(h, dict) and h.get('status') == 'error')
    if failing:
        return {'state': 'failing', 'values': {'names': ', '.join(failing)}}
    counted = sum(_number((a.get('report') or {}).get(k)) for a in connected for k in EVIDENCE.get(spec.id, ()))
    running = [n for n, h in health.items() if isinstance(h, dict) and h.get('running')]
    if counted or (running and (spec.agent.get('sends') or {})):
        return {'state': 'receiving', 'values': {'count': len(running) or len(connected), 'total': len(connected)}}
    reported = [h for h in health.values() if isinstance(h, dict)]
    if reported and all(h.get('status') == 'off' for h in reported):
        return {'state': 'not_configured', 'values': {}}
    if not _set_up(registry, spec):
        return {'state': 'not_configured', 'values': {}}
    if running:
        return {'state': 'on', 'values': {'count': len(running), 'total': len(connected)}}
    return {'state': 'waiting', 'values': {}}


def states(registry, agents=None):
    if agents is None:
        from . import agent_link
        agents = agent_link.all_agents()
    return {pid: one(registry, spec, agents) for pid, spec in registry.specs.items()}
