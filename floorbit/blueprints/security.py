"""Security findings (issue #29). The checks come from security plugins (floorbit/security.py).

- ``GET /security``: the findings page.
- ``GET /api/security``: active and recently cleared findings, and the ports Floorbit shut.
  Findings hold MACs and IPs, so this needs ``seats.view`` (auth/roles.py).
- ``GET /api/security/markers``: active findings per seat and switch, for the floor plan.
- ``POST /api/security/<id>/ack``: ``{"on": true|false}``, someone is on it.
- ``POST /api/security/check``: ask every security plugin now (``plugins.run``).
Shutting a finding's port goes through the port actions: ``POST /api/ports/shutdown {finding}``.
"""
from flask import Blueprint, current_app, g, jsonify, request

from .. import audit, inventory, ports, spa
from ..store import load_data

bp = Blueprint('security', __name__)


def _watch():
    return current_app.extensions['floorbit_security']


@bp.route('/security')
def security_page():
    return spa.render('Security')


@bp.route('/api/security', methods=['GET'])
def findings():
    from auth import current_user, roles  # late: auth imports floorbit while it loads
    snap = _watch().fresh()
    user = current_user()
    may_act = not current_app.extensions['auth'].enabled or bool(user and roles.can(user, 'ports.act'))
    info = ports.info(current_app.extensions['floorbit_plugins']) if may_act else {'available': False}
    return jsonify({**snap, 'shut_ports': ports.shut_ports(), 'can_act': bool(info.get('available')),
                    'needs_login': bool(info.get('needs_login'))})


@bp.route('/api/security/markers', methods=['GET'])
def markers():
    by_name = {d['name'].lower(): d['id'] for d in inventory.devices(load_data())}
    seats, switches = {}, {}
    for f in _watch().snapshot()['findings']:
        if f['seat']:
            seats[f['seat']] = seats.get(f['seat'], 0) + 1
        elif f['switch'].lower() in by_name:
            sid = by_name[f['switch'].lower()]
            switches[sid] = switches.get(sid, 0) + 1
    return jsonify({'seats': seats, 'switches': switches})


@bp.route('/api/security/<path:finding_id>/ack', methods=['POST'])
def acknowledge(finding_id):
    on = bool((request.get_json(silent=True) or {}).get('on', True))
    found = _watch().acknowledge(finding_id, g.get('audit_user'), on)
    if not found:
        return jsonify({'error': 'That finding is not active any more.'}), 404
    audit.record('security', 'Acknowledged finding' if on else 'Took back acknowledgement',
                 user=g.get('audit_user'), target=found['title'])
    return jsonify(found)


@bp.route('/api/security/check', methods=['POST'])
def check_now():
    _watch().poll_once()
    return findings()
