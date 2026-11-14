"""Port actions (issue #16). The rules live in floorbit/ports.py.

- ``GET /api/ports``: is a port actions plugin on, and does it need the tech's switch login?
- ``POST /api/ports/bounce``: ``{seat}`` or ``{switch, port}``, plus ``{username, password}`` when
  asked. Needs ``ports.act`` (auth/roles.py). The password is used for one connection, never kept.
"""
from flask import Blueprint, current_app, g, jsonify, request

from .. import audit, ports

bp = Blueprint('ports', __name__)


def _registry():
    return current_app.extensions['floorbit_plugins']


@bp.route('/api/ports', methods=['GET'])
def port_info():
    return jsonify(ports.info(_registry()))


@bp.route('/api/ports/bounce', methods=['POST'])
def bounce():
    body = request.get_json(silent=True) or {}
    account = g.get('audit_user') or '?'
    try:
        switch, port, seat, message = ports.bounce(_registry(), account, body)
    except ports.PortError as exc:
        # Failed attempts are logged too; the target is what was asked for, never the login.
        asked = body.get('seat') or f"{body.get('switch') or '?'} {body.get('port') or '?'}"
        audit.record('ports', 'Port bounce failed', user=g.get('audit_user'), target=str(asked)[:80], ok=False)
        return jsonify({'error': str(exc)}), exc.status
    audit.record('ports', 'Bounced port', user=g.get('audit_user'),
                 target=f'{switch} {port}' + (f' (seat {seat})' if seat else ''))
    return jsonify({'ok': True, 'switch': switch, 'port': port, 'seat': seat, 'message': message})
