"""The inventory for local agents, with their key (docs/inventory.md#for-agents):

- ``GET /api/agent/v1/inventory/<plugin>?kinds=ssh,snmp_v3``: the devices the plugin is switched
  on for (device, tag, group or defaults) that have a usable credential of one of those kinds
  (any, without ``kinds``), each with its address, platform, properties and the credential opened.
  ``If-None-Match`` with the ETag: 304 while nothing changed. Devices blocked after a failed login
  are left out until a tech clears them.
- ``POST /api/agent/v1/inventory/auth-failed`` ``{"device_id", "credential_id", "rev", "plugin",
  "message"}``: a stored credential failed to log in; the device is blocked for it.

Agent plugins normally get the same list as ``settings["targets"]`` (floorbit/agent_plugins.py);
these routes are for agent parts that ask for it themselves.
"""
import hashlib
import json
import re

from flask import Blueprint, jsonify, request

from .. import inventory_scope
from .agent import _agent, _agent_body, _refused

bp = Blueprint('inventory_agent', __name__)
PLUGIN_RE = re.compile(r'^[a-z][a-z0-9-]{1,39}$')


@bp.route('/api/agent/v1/inventory/<plugin_id>', methods=['GET'])
def agent_targets(plugin_id):
    agent = _agent()
    if agent is None:
        return _refused()
    if not PLUGIN_RE.match(plugin_id):
        return jsonify({'error': 'No such plugin.'}), 404
    kinds = [k for k in (request.args.get('kinds') or '').split(',') if k in inventory_scope.KINDS] or None
    devices = inventory_scope.plugin_targets(plugin_id, kinds)
    etag = hashlib.sha256(json.dumps(devices, sort_keys=True, default=str).encode()).hexdigest()[:32]
    if request.headers.get('If-None-Match', '').strip('"') == etag:
        return '', 304
    resp = jsonify({'plugin': plugin_id, 'devices': devices, 'etag': etag})
    resp.headers['ETag'] = f'"{etag}"'
    resp.headers['Cache-Control'] = 'no-store'      # it holds secrets
    return resp


@bp.route('/api/agent/v1/inventory/auth-failed', methods=['POST'])
def agent_auth_failed():
    agent = _agent()
    if agent is None:
        return _refused()
    body = _agent_body()
    if not body.get('device_id') or not body.get('credential_id'):
        return jsonify({'error': 'Say which device and credential.'}), 400
    entry = inventory_scope.auth_failed(str(body['device_id'])[:80], str(body['credential_id'])[:40],
                                        str(body.get('rev') or '')[:40], str(body.get('plugin') or '')[:40],
                                        str(body.get('message') or '')[:300], agent.get('name'))
    # None: the credential was set again meanwhile (or is gone), so there is nothing to block.
    return jsonify({'blocked': entry is not None})


# The agent has no session: its key is checked in each view (auth's guard leaves these paths alone).
for _view in (agent_targets, agent_auth_failed):
    _view._auth_public = True
