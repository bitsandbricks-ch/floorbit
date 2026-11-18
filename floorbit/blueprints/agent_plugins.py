"""Agent plugins (floorbit/agent_plugins.py, docs/agent-plugins.md), for the agent with its key:

- ``GET /api/agent/v1/plugins``: ``{"plugins": {id: {version, settings, sends, calls, actions,
  fetches}}, "local": {...}, "etag"}``, the plugins it runs. ``If-None-Match`` with the etag: 304
  while nothing changed.

For the crew (``plugins.run``):

- ``POST /api/agent-plugins/<agent id>/<plugin id>/unblock`` ``{"device", "credential"}``: a tech
  cleared a failed login; the agent may try it again. Audit-logged.

For the agent:

- ``POST /api/agent/v1/plugins/<id>/<kind>`` ``{"payload"}``: what a plugin's agent part sent.
  404 for a plugin with no agent part, 409 while it is off here, 422 when the payload breaks the
  plugin's privacy rule (an address in an aggregate kind).
- ``GET /api/agent/v1/plugins/<id>/<kind>``: ``{"data": ...}``, what the agent part asks the
  hosted part for (``agent_get_<kind>``, listed under ``agent.fetches``), such as the seats' addresses.
- ``GET /api/agent/v1/bundles/<file>``: a signed plugin bundle named under ``bundles`` in the
  plugins' config. The agent checks its signature itself (floorbit/plugins/bundles.py).
"""
from flask import Blueprint, jsonify, request, send_file

from .. import agent_plugins
from .agent import BodyRefused, _agent, _agent_body, _body_refused, _refused

bp = Blueprint('agent_plugins', __name__)
bp.register_error_handler(BodyRefused, _body_refused)


@bp.route('/api/agent/v1/plugins', methods=['GET'])
def plugins_config():
    agent = _agent(reachable=False)
    if agent is None:
        return _refused()
    cfg = agent_plugins.config(agent_id=agent['id'])
    if request.headers.get('If-None-Match', '').strip('"') == cfg['etag']:
        return '', 304
    resp = jsonify(cfg)
    resp.headers['ETag'] = f'"{cfg["etag"]}"'
    resp.headers['Cache-Control'] = 'no-store'      # settings hold secrets
    return resp


@bp.route('/api/agent/v1/plugins/<plugin_id>/<kind>', methods=['POST'])
def plugin_sent(plugin_id, kind):
    agent = _agent(reachable=False)
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


@bp.route('/api/agent/v1/plugins/<plugin_id>/<kind>', methods=['GET'])
def plugin_fetch(plugin_id, kind):
    agent = _agent(reachable=False)
    if agent is None:
        return _refused()
    try:
        answer = agent_plugins.give(agent, plugin_id, kind)
    except agent_plugins.Refused as exc:
        return jsonify({'error': str(exc)}), exc.status
    resp = jsonify({'data': answer})
    resp.headers['Cache-Control'] = 'no-store'
    return resp


@bp.route('/api/agent-plugins/<agent_id>/<plugin_id>/unblock', methods=['POST'])
def unblock(agent_id, plugin_id):
    from ..plugins.base import PluginError
    from .agent import _who
    body = request.get_json(silent=True) or {}
    device, credential = body.get('device'), body.get('credential')
    if not isinstance(device, str) or not device or not (credential is None or isinstance(credential, str)):
        return jsonify({'error': 'Send the device and the credential.'}), 400
    try:
        cleared = agent_plugins.unblock(agent_id, plugin_id, device, credential, user=_who())
    except PluginError as exc:
        return jsonify({'error': str(exc)}), 409
    return jsonify({'ok': True, 'cleared': cleared})


# The agent has no session: its key is checked in each view (auth's guard leaves these paths alone).
for _view in (plugins_config, plugin_sent, plugin_fetch):
    _view._auth_public = True


@bp.route('/api/agent/v1/bundles/<name>', methods=['GET'])
def bundle(name):
    agent = _agent(reachable=False)
    if agent is None:
        return _refused()
    path = agent_plugins.bundle_file(name)
    if path is None:
        return jsonify({'error': 'No such bundle here.'}), 404
    return send_file(path, mimetype='application/gzip', max_age=0)
