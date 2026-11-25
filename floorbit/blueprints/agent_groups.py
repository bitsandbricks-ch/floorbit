"""One group of local agents: the agents with the same tags, which back each other up (#1405) and
split their devices (#1441). For admins (``settings.manage``, as all of ``/api/agents``):

- ``GET /settings/agents/groups/<id>``: the page (React).
- ``GET /api/agents/groups/<id>``: the group as on the Local agents list, plus per agent its own
  address, the devices it owns now and whether it follows the split; 404 for a group nobody is in.
  ``<id>`` is the group's tags joined with ``|`` (``*`` for agents without tags), as ``agent_ha.groups``.
"""
from flask import Blueprint, jsonify

from .. import agent_ha, agent_link, inventory_scope, spa

bp = Blueprint('agent_groups', __name__)


@bp.route('/settings/agents/groups/<path:group_id>')
def group_page(group_id):
    return spa.render('Agent group')


@bp.route('/api/agents/groups/<path:group_id>', methods=['GET'])
def group(group_id):
    data = agent_link.load_data()
    agents = agent_link.all_agents(data)
    names = {t['id']: t['name'] for t in inventory_scope.tags(data)}
    found = next((g for g in agent_ha.groups(agents, names) if g['id'] == group_id), None)
    if found is None:
        return jsonify({'error': 'No agent is in this group.'}), 404
    return jsonify(detail(found, agents))


def detail(found, agents):
    """``found`` from agent_ha.groups, with who owns how many devices now. Unsplit, the primary
    collects every device nobody pinned; split, each connected agent its share (targets.for_agent)."""
    from ..telemetry import targets
    # The demo's made-up agents (agent_demo.py) count as connected, as on their own pages.
    connected = agent_link.tunnel.connected_agents() | {a['id'] for a in agents if a.get('demo') and a.get('connected')}
    by_id = {a['id']: a for a in agents}
    every = targets.listing()
    tags = {a['id']: set(a.get('tags') or ()) for a in agents}
    reports = {a['id']: a.get('report') for a in agents}
    rows, split = [], False
    for member in found['agents']:
        a = by_id.get(member['id'], {})
        owns = pinned = 0
        if member['id'] in connected:
            for t in targets.for_agent(every, member['id'], connected, tags, reports):
                split = split or bool(t.get('split'))
                if t.get('mine') and not t.get('split'):
                    pinned += 1
                elif t.get('mine') or ('mine' not in t and member['id'] == found['primary']):
                    owns += 1
        rows.append({**member, 'address': a.get('address') or '', 'version': a.get('version') or '',
                     'follows_split': agent_ha.splits(a.get('report')), 'owns': owns, 'pinned': pinned})
    live = [m['id'] for m in found['agents'] if m['id'] in connected]
    split = split or bool(live and agent_ha.split_group(live[0], connected, tags, reports))
    return {**found, 'agents': rows, 'split': split, 'devices': sum(r['owns'] + r['pinned'] for r in rows)}
