"""Agent plugins (floorbit/agent_plugins.py, docs/agent-plugins.md), for the agent with its key:

- ``GET /api/agent/v1/plugins``: ``{"plugins": {id: {version, settings, sends, calls, actions}},
  "etag"}``, the plugins it runs. ``If-None-Match`` with the etag: 304 while nothing changed.
- ``POST /api/agent/v1/plugins/<id>/<kind>`` ``{"payload"}``: what a plugin's agent part sent.
  404 for a plugin with no agent part, 409 while it is off here, 422 when the payload breaks the
  plugin's privacy rule (an address in an aggregate kind).
"""
from flask import Blueprint, jsonify, request

from .. import agent_plugins
from .agent import _agent, _agent_body, _refused

bp = Blueprint('agent_plugins', __name__)


@bp.route('/api/agent/v1/plugins', methods=['GET'])
def plugins_config():
    agent = _agent()
    if agent is None:
        return _refused()
    cfg = agent_plugins.config()
    if request.headers.get('If-None-Match', '').strip('"') == cfg['etag']:
        return '', 304
    resp = jsonify(cfg)
    resp.headers['ETag'] = f'"{cfg["etag"]}"'
    resp.headers['Cache-Control'] = 'no-store'      # settings hold secrets
    return resp


@bp.route('/api/agent/v1/plugins/<plugin_id>/<kind>', methods=['POST'])
def plugin_sent(plugin_id, kind):
    agent = _agent()
    if agent is None:
        return _refused()
    body = _agent_body()
    try:
        answer = agent_plugins.take(agent, plugin_id, kind, body.get('payload'))
    except agent_plugins.Refused as exc:
        return jsonify({'error': str(exc)}), exc.status
    from .. import agent_link
    agent_link.tunnel.relayed(agent['id'], f'plugin:{plugin_id}', 1)
    return jsonify(answer)


# The agent has no session: its key is checked in each view (auth's guard leaves these paths alone).
for _view in (plugins_config, plugin_sent):
    _view._auth_public = True
