"""Updates of the agents themselves (floorbit/agent_updates.py), for the agent with its key:

- ``GET /api/agent/v1/agent-bundles/<file>``: the signed agent update named under ``agent_update``
  in its plugin config. The agent checks its signature itself, with the key in its image.
"""
from flask import Blueprint, jsonify, send_file

from .. import agent_updates
from .agent import _agent, _refused

bp = Blueprint('agent_updates', __name__)


@bp.route('/api/agent/v1/agent-bundles/<name>', methods=['GET'])
def agent_bundle(name):
    agent = _agent(reachable=False)
    if agent is None:
        return _refused()
    path = agent_updates.bundle_file(name)
    if path is None:
        return jsonify({'error': 'No such agent update here.'}), 404
    return send_file(path, mimetype='application/gzip', max_age=0)


# The agent has no session: its key is checked in the view (auth's guard leaves these paths alone).
agent_bundle._auth_public = True
