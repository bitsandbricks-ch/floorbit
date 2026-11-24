"""Which devices one agent collects, and why one sends nothing: the Devices tab on the agent's page
(issue #1013). The list comes from what Floorbit gives the agent (telemetry/targets.py); the state
of each device from the agent's own memory, asked through its link (the telemetry plugin's
``devices`` call). No logins, only counts.
"""
from .telemetry import targets

# What the page shows of a device Floorbit gives the agent.
SHOWN = ('name', 'inventory_id', 'kind', 'platform', 'address', 'drivers')


def _state(row, answered):
    if not answered:
        return 'unknown'
    if row.get('collects') is False:
        return 'standby'
    if row.get('online'):
        return 'partial' if row.get('problems') else 'up'
    if row.get('problems'):
        return 'silent'
    # Traps come when something happens: a quiet trap-only device is not a problem.
    if set(row.get('drivers') or []) <= {'traps', 'mdt'}:
        return 'waiting'
    return 'silent' if row.get('seen') else 'never'


def devices_of(agent_id, registry=None):
    """``{agent, connected, primary, error, devices: [...]}`` or None when there is no such agent.
    ``error``: 'offline' (not connected), 'no_telemetry' (the plugin is off), 'no_answer' (it didn't
    answer, or is too old to know the call)."""
    from . import agent_link, agent_plugins
    from .plugins.base import PluginError
    agents = agent_link.all_agents()
    me = next((a for a in agents if a['id'] == agent_id), None)
    if me is None:
        return None
    connected = agent_link.tunnel.connected_agents()
    if me.get('demo'):
        connected = {*connected, agent_id}
    given = targets.for_agent(targets.listing(), agent_id, connected)
    answer, error, detail = None, None, ''
    spec = registry.specs.get('telemetry') if registry is not None else None
    if me.get('demo'):
        from . import agent_demo
        answer = agent_demo.devices_answer(given, agent_id)
    elif agent_id not in connected:
        error = 'offline'
    elif spec is None or not registry.enabled(spec):
        error = 'no_telemetry'
    else:
        try:
            [reply] = agent_plugins.ask(spec, 'call', 'devices', {}, agent=agent_id)
        except (PluginError, ValueError) as exc:
            reply = {'error': str(exc)}
        if isinstance(reply.get('result'), dict) and isinstance(reply['result'].get('devices'), list):
            answer = reply['result']
        else:
            error, detail = 'no_answer', str(reply.get('error') or '')[:300]
    live = {}
    for r in (answer or {}).get('devices') or []:
        if isinstance(r, dict) and r.get('name'):
            live[str(r['name']).lower()] = r
    rows = []
    for t in given:
        r = live.pop(str(t['name']).lower(), {})
        row = {**{k: t.get(k) for k in SHOWN}, 'pinned': bool(t.get('mine')), 'collects': r.get('collects'),
               'seen': r.get('seen'), 'online': bool(r.get('online')), 'problems': (r.get('problems') or [])[:10]}
        row.update({k: r[k] for k in ('ports', 'macs', 'arp', 'neighbours') if isinstance(r.get(k), int)})
        row['state'] = _state(row, answer is not None)
        rows.append(row)
    # Devices that send by themselves (a firewall's own Telegraf) without being given to it.
    for r in live.values():
        row = {'name': r['name'], 'inventory_id': None, 'kind': r.get('kind') or '', 'platform': '',
               'address': r.get('address') or '', 'drivers': r.get('drivers') or [], 'pinned': False,
               'collects': r.get('collects'), 'seen': r.get('seen'), 'online': bool(r.get('online')),
               'problems': (r.get('problems') or [])[:10], 'pushed': True}
        row.update({k: r[k] for k in ('ports', 'macs', 'arp', 'neighbours') if isinstance(r.get(k), int)})
        row['state'] = _state(row, True)
        rows.append(row)
    order = {'silent': 0, 'never': 1, 'partial': 2, 'unknown': 3, 'waiting': 4, 'standby': 5, 'up': 6}
    rows.sort(key=lambda r: (order.get(r['state'], 9), str(r['name']).lower()))
    return {'agent': {'id': me['id'], 'name': me.get('name')}, 'connected': agent_id in connected,
            'primary': (answer or {}).get('primary'), 'error': error, 'detail': detail, 'devices': rows}
