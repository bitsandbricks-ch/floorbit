"""High availability of the local agents (docs/agent.md, "Two agents in one hall").

Agents that serve the same halls form a group. With VRRP (floorbit-agent's docs/vrrp.md) they share
virtual addresses: the agent holding the first one is the group's primary, and only it polls devices
and logs in to them (``ctx.primary()``); the others listen and take over when it goes. Holding all
addresses on one agent is active/passive; spreading them (FLOORBIT_AGENT_VRRP_PREFER) is
active/active: both receive syslog, NetFlow and traps, and both answer the hosted side's calls.

This module reads what the agents report and says how each group stands, for the Local agents page,
and lets the Traffic intake keep the primary's summary (``standby_with_primary``).

Split brain: when the agents of a group can't hear each other's VRRP (a switch drops it, a cable
between them), each takes every address and calls itself primary, so both poll the devices and both
try the logins, which is what locks accounts. The hosted side hears both, so it settles it: the
agent with the smallest id stays primary and the others are told to stand by (``stand_by_for``, sent
with the plugin config they pull). Without the hosted side (uplink down too) VRRP alone decides.
"""
from __future__ import annotations

# How a group stands, worst first: what the Local agents page shows and colours.
STATES = ('down', 'split', 'no_vrrp', 'no_primary', 'degraded', 'single', 'ok')
FLOWS_FRESH = 120    # a primary's traffic summary this recent wins over a standby's


def _vrrp(agent):
    report = agent.get('report') or {}
    return report.get('vrrp') if isinstance(report.get('vrrp'), dict) else None


def groups(agents, hall_names=None):
    """``[{id, halls, label, state, mode, primary, agents: [{id, name, connected, role, holds}], vips}]``."""
    hall_names = hall_names or {}
    by_key = {}
    for a in agents:
        key = tuple(sorted(a.get('halls') or ()))
        by_key.setdefault(key, []).append(a)
    out = []
    for key, members in sorted(by_key.items(), key=lambda kv: (bool(kv[0]), kv[0])):
        connected = [a for a in members if a.get('connected')]
        vrrp = {a['id']: _vrrp(a) for a in connected}
        primaries = [a for a in connected if (vrrp[a['id']] or {}).get('primary', vrrp[a['id']] is None)]
        holders = {a['id']: list((vrrp[a['id']] or {}).get('holds') or []) for a in connected}
        if not connected:
            state = 'down'
        elif len([a for a in connected if vrrp[a['id']] and vrrp[a['id']].get('primary')]) > 1:
            state = 'split'
        elif len(connected) > 1 and any(vrrp[a['id']] is None for a in connected):
            state = 'no_vrrp'
        elif not primaries:
            state = 'no_primary'
        elif len(members) == 1:
            state = 'single'
        elif len(connected) < len(members):
            state = 'degraded'
        else:
            state = 'ok'
        holding = [i for i, h in holders.items() if h]
        mode = None
        if len(connected) > 1 and any(vrrp.values()):
            mode = 'active-active' if len(holding) > 1 else 'active-passive'
        primary = primaries[0]['id'] if len(primaries) == 1 else None

        def role(a, vrrp=vrrp, primary=primary):
            if not a.get('connected'):
                return 'offline'
            if a['id'] == primary or (vrrp.get(a['id']) or {}).get('primary'):
                return 'primary'
            return 'standby' if vrrp.get(a['id']) else 'active'
        out.append({
            'id': '|'.join(key) or '*', 'halls': list(key),
            'label': ', '.join(hall_names.get(h, h) for h in key),
            'state': state, 'mode': mode, 'primary': primary,
            'agents': [{'id': a['id'], 'name': a['name'], 'connected': bool(a.get('connected')), 'role': role(a),
                        'holds': holders.get(a['id'], [])} for a in members],
            'vips': sorted({v for h in holders.values() for v in h}),
        })
    return out


def _claims_primary(agent):
    return bool(agent.get('connected') and (_vrrp(agent) or {}).get('primary'))


def stand_by_for(agent_id, agents=None, now=None):
    """The agent that ``agent_id`` should leave polling and logins to while its group is split (both
    claim primary), or None. The smallest id wins: every pod and every pull agree without asking."""
    if agents is None:
        from . import agent_link
        agents = agent_link.all_agents(now=now)
    me = next((a for a in agents if a['id'] == agent_id), None)
    if me is None or not _claims_primary(me):
        return None
    mine = sorted(me.get('halls') or ())
    rivals = [a['id'] for a in agents
              if a['id'] != agent_id and _claims_primary(a) and sorted(a.get('halls') or ()) == mine]
    winner = min([agent_id, *rivals])
    return winner if winner != agent_id else None


def standby_with_primary(agent_id, now):
    """True when this agent is a VRRP standby and its group's primary sent a traffic summary within
    FLOWS_FRESH: then the standby's summary would only replace the primary's with a part of it."""
    from . import agent_link
    agents = agent_link.all_agents(now=now)
    me = next((a for a in agents if a['id'] == agent_id), None)
    if me is None or (_vrrp(me) or {}).get('primary', True):
        return False
    mine = sorted(me.get('halls') or ())
    for other in agents:
        if (other['id'] != agent_id and other.get('connected') and sorted(other.get('halls') or ()) == mine
                and (_vrrp(other) or {}).get('primary')):
            flows = (other.get('relays') or {}).get('flows')
            if flows and now - flows['at'] < FLOWS_FRESH:
                return True
    return False
