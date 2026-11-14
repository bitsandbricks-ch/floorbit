"""Port actions (issue #16). The rules live in floorbit/ports.py.

- ``GET /api/ports``: is a port actions plugin on, and does it need the tech's switch login?
- ``POST /api/ports/bounce|shutdown|enable``: ``{seat}``, ``{finding}`` or ``{switch, port}``, plus
  ``{username, password}`` when asked. Needs ``ports.act`` (auth/roles.py). The password is used
  for one connection, never kept.
- ``GET /api/ports/shut``: the ports Floorbit shut and nobody turned on again.
"""
from flask import Blueprint, current_app, g, jsonify, request

from .. import audit, ports

bp = Blueprint('ports', __name__)


def _registry():
    return current_app.extensions['floorbit_plugins']


@bp.route('/api/ports', methods=['GET'])
def port_info():
    return jsonify(ports.info(_registry()))


@bp.route('/api/ports/shut', methods=['GET'])
def shut_list():
    return jsonify({'ports': ports.shut_ports()})


@bp.route('/api/ports/<action>', methods=['POST'])
def act(action):
    if action not in ports.ACTIONS:
        return jsonify({'error': 'No such port action.'}), 404
    label = ports.ACTIONS[action][2]
    body = request.get_json(silent=True) or {}
    account = g.get('audit_user') or '?'
    try:
        switch, port, seat, message = ports.act(_registry(), account, body, action)
    except ports.PortError as exc:
        if exc.match_seat:
            # Not an attempt yet: the browser asks for the second confirmation.
            return jsonify({'error': str(exc), 'match_seat': exc.match_seat, 'seat': body.get('seat')}), 409
        # Failed attempts are logged too; the target is what was asked for, never the login.
        asked = body.get('finding') or body.get('seat') or f"{body.get('switch') or '?'} {body.get('port') or '?'}"
        audit.record('ports', f'{label}: failed', user=g.get('audit_user'), target=str(asked)[:80], ok=False)
        return jsonify({'error': str(exc)}), exc.status
    audit.record('ports', label, user=g.get('audit_user'),
                 target=f'{switch} {port}' + (f' (seat {seat})' if seat else ''))
    return jsonify({'ok': True, 'switch': switch, 'port': port, 'seat': seat, 'message': message})
