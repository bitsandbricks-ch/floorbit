"""Electrics (issue #45): boards, circuits and their load. Rules live in floorbit/power.py.

- ``GET /power``: the Electrics page.
- ``GET /api/power``: boards and circuits with their load, state and what they feed.
- ``GET /api/power/markers``: per seat and switch the circuit's state, and the placed boards.
- ``POST /api/power/boards``, ``PATCH``/``DELETE /api/power/boards/<id>``: boards (``power.edit``).
- ``POST /api/power/circuits``, ``PATCH``/``DELETE /api/power/circuits/<id>``: circuits (``power.edit``).
- ``POST /api/power/circuits/<id>/reading``: ``{"amps": 12.5}`` or ``{"watts": 2900}``.
- ``POST /api/power/circuits/<id>/trip``: ``{"tripped": true|false}``.
  Readings and trips take ``power.edit``, or ``incidents.work`` in the Electrics team
  (``POWER_TEAM``), so the people on the floor can type them in.
- ``POST /api/power/check``: ask the power plugins now (``plugins.run``).
"""
from flask import Blueprint, abort, current_app, g, jsonify, request

from integrations import config, events

from .. import audit, power, spa

bp = Blueprint('power', __name__)


def _watch():
    return current_app.extensions['floorbit_power']


def _user():
    from auth import current_user  # late: auth imports floorbit while it loads
    return current_user()


def _may(user, reading=False):
    from auth import roles, teams
    if not current_app.extensions['auth'].enabled:
        return True
    if not user:
        return False
    if roles.can(user, 'power.edit'):
        return True
    team = config.get('POWER_TEAM', 'electrics')
    if team not in teams.teams_of(user):
        return False
    perms = teams.team_permissions(user, team)
    return 'power.edit' in perms or (reading and 'incidents.work' in perms)


def _need(reading=False):
    if not power.enabled():
        abort(409, description='The power layer is off (Settings > Electrics).')
    if not _may(_user(), reading):
        abort(403, description='Needs the "power" permission, or working incidents in the Electrics team.')


def _error(exc):
    return jsonify({'error': str(exc)}), getattr(exc, 'status', 400)


def _changed(area_action, target):
    audit.record('power', area_action, user=g.get('audit_user'), target=target)
    events.publish('power.changed', {})


@bp.app_context_processor
def power_flags():
    return {'power_on': power.enabled()}


@bp.route('/power')
def power_page():
    return spa.render('Electrics')


@bp.route('/api/power', methods=['GET'])
def overview():
    snap = _watch().snapshot()
    user = _user()
    return jsonify({**snap, 'can_edit': _may(user), 'can_read': _may(user, reading=True)})


@bp.route('/api/power/markers', methods=['GET'])
def markers():
    if not power.enabled():
        return jsonify({'enabled': False, 'seats': {}, 'switches': {}, 'boards': [], 'counts': {}})
    return jsonify(_watch().markers())


@bp.route('/api/power/boards', methods=['POST'])
@bp.route('/api/power/boards/<board_id>', methods=['PATCH', 'DELETE'])
def board(board_id=None):
    _need()
    try:
        if request.method == 'DELETE':
            found = power.delete_board(board_id)
            _changed('Removed board', found['name'])
            return jsonify({'ok': True})
        found = power.save_board(request.get_json(silent=True) or {}, board_id)
    except power.PowerError as exc:
        return _error(exc)
    _changed('Changed board' if board_id else 'Added board', found['name'])
    return jsonify(found), 200 if board_id else 201


@bp.route('/api/power/circuits', methods=['POST'])
@bp.route('/api/power/circuits/<circuit_id>', methods=['PATCH', 'DELETE'])
def circuit(circuit_id=None):
    _need()
    try:
        if request.method == 'DELETE':
            found = power.delete_circuit(circuit_id)
            _changed('Removed circuit', found['name'])
            return jsonify({'ok': True})
        found = power.save_circuit(request.get_json(silent=True) or {}, circuit_id)
    except power.PowerError as exc:
        return _error(exc)
    _changed('Changed circuit' if circuit_id else 'Added circuit', found['name'])
    _watch().evaluate()   # a lower rating can turn it red
    return jsonify(found), 200 if circuit_id else 201


@bp.route('/api/power/circuits/<circuit_id>/reading', methods=['POST'])
def reading(circuit_id):
    _need(reading=True)
    _watch().ensure_baseline()
    try:
        found = power.set_reading(circuit_id, request.get_json(silent=True) or {}, g.get('audit_user'))
    except power.PowerError as exc:
        return _error(exc)
    _changed('Entered reading', found['name'])
    alerts = _watch().evaluate()
    return jsonify({'circuit': found, 'alerts': alerts})


@bp.route('/api/power/circuits/<circuit_id>/trip', methods=['POST'])
def trip(circuit_id):
    _need(reading=True)
    _watch().ensure_baseline()
    tripped = bool((request.get_json(silent=True) or {}).get('tripped', True))
    try:
        found = power.set_tripped(circuit_id, tripped, g.get('audit_user'))
    except power.PowerError as exc:
        return _error(exc)
    _changed('Breaker tripped' if tripped else 'Breaker back on', found['name'])
    alerts = _watch().evaluate()
    return jsonify({'circuit': found, 'alerts': alerts})


@bp.route('/api/power/check', methods=['POST'])
def check_now():
    if not power.enabled():
        abort(409, description='The power layer is off (Settings > Electrics).')
    _watch().poll_once()
    return jsonify(_watch().snapshot())
