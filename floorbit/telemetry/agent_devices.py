"""Each device as the agents' telemetry part sees it, for the Telemetry page and its widget.

Asked of the Telemetry plugin itself, not of the monitoring source: while LibreNMS answers
monitoring, its devices have no telemetry counts or problems (issue #1223).
"""
COUNTS = ('ports', 'macs', 'arp', 'neighbours')


def rows():
    """{name: {seen, online, problems, driver, ports?, macs?, arp?, neighbours?}}, by name."""
    found = _from_agents()
    return found if found is not None else _from_monitoring()


def _from_agents():
    """From every connected agent's "devices" call; the agent that collects a device wins over a
    standby one. None when no agent answered it."""
    from .. import agent_plugins, sources
    from ..plugins.base import PluginError
    spec = sources.registry.specs.get('telemetry') if sources.registry is not None else None
    if spec is None:
        return None
    try:
        answers = agent_plugins.ask(spec, 'call', 'devices', {})
    except PluginError:
        return None
    lists = [a['result'].get('devices') for a in answers if isinstance(a.get('result'), dict)]
    lists = [found for found in lists if isinstance(found, list)]
    if not lists:
        return None
    out, best = {}, {}
    for found in lists:
        for d in found:
            if not isinstance(d, dict) or not d.get('name'):
                continue
            name = str(d['name'])
            rank = (bool(d.get('collects')), d.get('seen') or 0)
            if name in best and best[name] >= rank:
                continue
            best[name] = rank
            drivers = d.get('drivers') if isinstance(d.get('drivers'), list) else []
            out[name] = _row(d, online=d.get('online'), driver=', '.join(map(str, drivers)))
    return dict(sorted(out.items()))


def _from_monitoring():
    """The monitoring source's telemetry rows: for an agent too old to answer "devices"."""
    from .. import sources
    from ..plugins.base import PluginError
    try:
        found = sources.monitoring().devices() or []
    except PluginError:
        return {}
    out = {}
    for d in found if isinstance(found, list) else []:
        if isinstance(d, dict) and d.get('source') == 'telemetry' and d.get('hostname'):
            out[str(d['hostname'])] = _row(d, online=d.get('status'), driver=str(d.get('driver') or ''))
    return out


def _row(d, online, driver):
    problems = [p for p in d.get('problems') or [] if isinstance(p, dict)]
    row = {'seen': d.get('seen'), 'online': bool(online), 'problems': problems[:10], 'driver': driver}
    # Counts only from an agent that sends them (older ones don't): the page leaves them out then.
    row.update({k: d[k] for k in COUNTS if isinstance(d.get(k), int) and not isinstance(d.get(k), bool)})
    return row
