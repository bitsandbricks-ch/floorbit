"""The local agent (issue #2). Rules in floorbit/agent_link.py, docs in docs/agent.md.

For admins (``settings.manage``):

- ``GET /settings/agents``: the page (React).
- ``GET /api/agents``: the enrolled agents, whether each is connected, and the tunnel's state.
- ``POST /api/agents`` ``{"name"}``: enrol one; the answer holds its key, this once.
- ``PATCH /api/agents/<id>`` ``{"halls": [ids]}``: the halls it answers for (empty: every hall).
- ``DELETE /api/agents/<id>``: revoke it.

For the agent, with its key in ``Floorbit-Agent-Key`` (no session, no browser):

- ``GET /api/agent/v1/hello``: checks the key; ``{"name", "server_version"}``.
- ``GET /api/agent/v1/calls?wait=25``: the calls waiting for it (a long poll).
- ``POST /api/agent/v1/answers`` ``{"answers": [{"id", "ok", "result", "error"}]}``.
"""
from flask import Blueprint, current_app, g, jsonify, request

from integrations import events

from .. import agent_link, audit, spa

bp = Blueprint('agent', __name__)
HEADER = 'Floorbit-Agent-Key'


def _who():
    from auth import current_user  # late: auth imports floorbit while it loads
    user = current_user() or {}
    return user.get('display_name') or user.get('username')


@bp.route('/settings/agents')
def agents_page():
    return spa.render('Local agents')


@bp.route('/api/agents', methods=['GET'])
def list_agents():
    server = current_app.config.get('FLOORBIT_VERSION') or '0'
    agents = [{**a, 'outdated': agent_link.outdated(a.get('version'), server)} for a in agent_link.all_agents()]
    return jsonify({'agents': agents, 'connected': agent_link.tunnel.connected(),
                    'max': agent_link.MAX_AGENTS, 'server_version': server})


@bp.route('/api/agents', methods=['POST'])
def enrol():
    try:
        record, key = agent_link.enrol((request.get_json(silent=True) or {}).get('name'), _who())
    except agent_link.AgentError as exc:
        return jsonify({'error': str(exc)}), exc.status
    audit.record('settings', 'Enrolled a local agent', g.get('audit_user'), record['name'])
    events.publish('agents.changed', {})
    return jsonify({**record, 'key': key}), 201


@bp.route('/api/agents/<agent_id>', methods=['PATCH'])
def set_halls(agent_id):
    body = request.get_json(silent=True) or {}
    try:
        name, halls = agent_link.set_halls(agent_id, body.get('halls', []))
    except agent_link.AgentError as exc:
        return jsonify({'error': str(exc)}), exc.status
    audit.record('agents', f"Set the halls of a local agent: {', '.join(halls) or 'every hall'}",
                 g.get('audit_user'), name, fields=['halls'])
    events.publish('agents.changed', {})
    return jsonify({'id': agent_id, 'halls': halls})


@bp.route('/api/agents/<agent_id>', methods=['DELETE'])
def revoke(agent_id):
    try:
        name = agent_link.revoke(agent_id)
    except agent_link.AgentError as exc:
        return jsonify({'error': str(exc)}), exc.status
    audit.record('settings', 'Revoked a local agent', g.get('audit_user'), name)
    events.publish('agents.changed', {})
    return jsonify({'ok': True})


def _agent():
    return agent_link.check(request.headers.get(HEADER), request.headers.get('Floorbit-Agent-Version'),
                            request.remote_addr)


def _refused():
    return jsonify({'error': 'The agent key is wrong or was revoked. Enrol the agent again.'}), 401


@bp.route('/api/agent/v1/hello', methods=['GET'])
def hello():
    agent = _agent()
    if agent is None:
        return _refused()
    events.publish('agents.changed', {})
    return jsonify({'name': agent['name'], 'server_version': current_app.config.get('FLOORBIT_VERSION') or '0'})


@bp.route('/api/agent/v1/calls', methods=['GET'])
def calls():
    agent = _agent()
    if agent is None:
        return _refused()
    try:
        wait = float(request.args.get('wait') or agent_link.MAX_WAIT)
    except ValueError:
        wait = agent_link.MAX_WAIT
    return jsonify({'calls': agent_link.tunnel.take(wait, agent=agent['id'])})


@bp.route('/api/agent/v1/answers', methods=['POST'])
def answers():
    agent = _agent()
    if agent is None:
        return _refused()
    body = request.get_json(silent=True) or {}
    items = body.get('answers') if isinstance(body.get('answers'), list) else []
    taken = sum(1 for a in items[:100] if isinstance(a, dict)
                and agent_link.tunnel.answer(a.get('id'), a.get('ok'), a.get('result'), a.get('error'),
                                                     agent=agent['id']))
    return jsonify({'taken': taken})


# The agent has no session: its key is checked in each view (auth's guard leaves these paths alone).
for _view in (hello, calls, answers):
    _view._auth_public = True
