"""High availability of the local agents (docs/agent.md, "Two agents for the same devices").

Agents that serve the same tags form a group (issue #869; tags took the place of halls). With VRRP
(floorbit-agent's docs/vrrp.md) they share
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


def groups(agents, tag_names=None):
    """``[{id, tags, label, state, mode, primary, agents: [{id, name, connected, role, holds}], vips}]``."""
    tag_names = tag_names or {}
    by_key = {}
    for a in agents:
        key = tuple(sorted(a.get('tags') or ()))
        by_key.setdefault(key, []).append(a)
    out = []
    for key, members in sorted(by_key.items(), key=lambda kv: (bool(kv[0]), kv[0])):
        connected = [a for a in members if a.get('connected')]
        vrrp = {a['id']: _vrrp(a) for a in connected}
        # Agents that take Floorbit's lease (issue #1405): it picks the primary, VRRP only moves addresses.
        leased = bool(connected) and all(_lease(a) is not None for a in connected)
        if leased:
            holder = lease_holder(members)
            primaries = [a for a in connected if a['id'] == holder]
        else:
            primaries = [a for a in connected if (vrrp[a['id']] or {}).get('primary', vrrp[a['id']] is None)]
        holders = {a['id']: list((vrrp[a['id']] or {}).get('holds') or []) for a in connected}
        if not connected:
            state = 'down'
        elif not leased and len([a for a in connected if vrrp[a['id']] and vrrp[a['id']].get('primary')]) > 1:
            state = 'split'
        elif not leased and len(connected) > 1 and any(vrrp[a['id']] is None for a in connected):
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

        def role(a, vrrp=vrrp, primary=primary, leased=leased):
            if not a.get('connected'):
                return 'offline'
            if a['id'] == primary or (not leased and (vrrp.get(a['id']) or {}).get('primary')):
                return 'primary'
            return 'standby' if leased or vrrp.get(a['id']) else 'active'
        out.append({
            'id': '|'.join(key) or '*', 'tags': list(key),
            'label': ', '.join(tag_names.get(h, h) for h in key),
            'state': state, 'mode': mode, 'primary': primary,
            'agents': [{'id': a['id'], 'name': a['name'], 'connected': bool(a.get('connected')), 'role': role(a),
                        'holds': holders.get(a['id'], [])} for a in members],
            'vips': sorted({v for h in holders.values() for v in h}),
        })
    return out


def _lease(agent):
    """True or False when the agent says whether it holds its group's lease, None for an agent that
    knows no leases (before floorbit-agent #94): VRRP alone makes those primary."""
    value = (agent.get('report') or {}).get('lease')
    return value if isinstance(value, bool) else None


def _group_of(agent_id, agents):
    me = next((a for a in agents if a['id'] == agent_id), None)
    if me is None:
        return None, []
    mine = sorted(me.get('tags') or ())
    return me, [a for a in agents if sorted(a.get('tags') or ()) == mine]


def group_key(agent_id):
    """A stable name for the agent's group (its tags), or None for an agent Floorbit doesn't know.
    What one agent of a group passes on stands for the group (librenms_alerts.take)."""
    from . import agent_link
    me = next((a for a in agent_link.load_data().get(agent_link.KEY) or [] if a['id'] == agent_id), None)
    return None if me is None else 'group:' + '|'.join(sorted(me.get('tags') or ()))


_granted = {}    # group (its tags) -> the agent this pod last gave the lease, until its report says so


def lease_holder(members):
    """The group's primary, picked here (issue #1405): the connected agent that holds the lease
    already keeps it (sticky; the smallest id if two say so for a moment), else the group's VRRP
    primary, else the smallest connected id. None when nobody of the group is connected.
    Asked fresh on every pull, so every pod that hears the same reports picks the same agent."""
    connected = sorted(a['id'] for a in members if a.get('connected'))
    if not connected:
        return None
    by_id = {a['id']: a for a in members}
    holding = [i for i in connected if _lease(by_id[i])]
    if holding:
        return holding[0]
    # Given out but not reported yet (its report comes within half a minute): keep it there, or an
    # agent that comes back in between would take it straight back.
    key = tuple(sorted(members[0].get('tags') or ()))
    if _granted.get(key) in connected:
        return _granted[key]
    vrrp = [i for i in connected if (_vrrp(by_id[i]) or {}).get('primary')]
    _granted[key] = vrrp[0] if len(vrrp) == 1 else connected[0]
    return _granted[key]


def lease_for(agent_id, agents=None, now=None):
    """``{"primary", "members"}`` for the agent's plugin config: whether it is its group's primary
    now, and how many agents the group has (one alone is always primary, uplink or not)."""
    if agents is None:
        from . import agent_link
        agents = agent_link.all_agents(now=now)
    me, members = _group_of(agent_id, agents)
    if me is None:
        return None
    return {'primary': lease_holder(members) == agent_id, 'members': len(members)}


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
    mine = sorted(me.get('tags') or ())
    rivals = [a['id'] for a in agents
              if a['id'] != agent_id and _claims_primary(a) and sorted(a.get('tags') or ()) == mine]
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
    mine = sorted(me.get('tags') or ())
    for other in agents:
        if (other['id'] != agent_id and other.get('connected') and sorted(other.get('tags') or ()) == mine
                and (_vrrp(other) or {}).get('primary')):
            flows = (other.get('relays') or {}).get('flows')
            if flows and now - flows['at'] < FLOWS_FRESH:
                return True
    return False


def one_per_group(agent_ids, now=None):
    """``agent_ids`` (connected agents) by group: ``[(stable id, [the ids to ask, primary first])]``.
    For what each agent of a pair would only fetch twice, like a NetBox inventory feed. The stable
    id is the group's smallest member id, connected or not, so the feed keeps its id on failover."""
    import time

    from . import agent_link
    wanted = set(agent_ids)
    agents = agent_link.all_agents(now=now or time.time())
    known = {a['id'] for a in agents}
    out, seen = [], set()
    for a in sorted(agents, key=lambda a: a['id']):
        if a['id'] in seen:
            continue
        _me, members = _group_of(a['id'], agents)
        seen |= {m['id'] for m in members}
        ask = sorted(m['id'] for m in members if m['id'] in wanted)
        if not ask:
            continue
        first = lease_holder([{**m, 'connected': m['id'] in wanted} for m in members])
        out.append((min(m['id'] for m in members), sorted(ask, key=lambda i: (i != first, i))))
    out += [(i, [i]) for i in sorted(wanted - known)]
    return out


def action_targets(agent_ids, now=None):
    """Which of ``agent_ids`` (connected agents) a plugin action that changes something in the hall
    goes to: one per group, its primary. Two agents of one group sharing the work must not both
    clear the cache or bounce the port. A group without a single primary (no VRRP: each agent is
    its own primary; or a split) keeps every member, as before."""
    import time

    from . import agent_link
    wanted = set(agent_ids)
    agents = [a for a in agent_link.all_agents(now=now or time.time()) if a['id'] in wanted]
    out = set(wanted - {a['id'] for a in agents})      # not in the list: nothing to judge by
    for group in groups([{**a, 'connected': True} for a in agents]):
        members = [m['id'] for m in group['agents']]
        out |= {group['primary']} if group['primary'] and group['state'] in ('ok', 'degraded') else set(members)
    return sorted(out)

