"""The Problems page and alert mutes (issue #10). See docs/alerts.md.

- ``GET /problems``: everything wrong right now.
- ``GET /api/problems``: the list (floorbit/problems.py), with the running mutes.
- ``POST /api/alerts/mutes``: ``{"switch_id", "minutes", "reason"}`` mutes a switch's alerts;
  ``{"service_id", ...}`` mutes a service on the health wall instead (issue #256).
- ``PATCH /api/alerts/mutes/<id>``: ``{"minutes"}`` makes a running mute last longer (issue #264).
- ``DELETE /api/alerts/mutes/<id>``: ends a mute (a switch id, or ``health:<service id>``).
Mutes need ``incidents.work`` (auth/roles.py): the people working problems decide what pages them.
"""
from flask import Blueprint, current_app, g, jsonify, request

from integrations import alerting, events

from .. import audit, inventory, problems, spa
from ..store import load_data

bp = Blueprint('problems', __name__)


def _user():
    from auth import current_user  # late: auth imports floorbit while it loads
    return current_user()


def _can(permission):
    from auth import roles
    if not current_app.extensions['auth'].enabled:
        return True
    user = _user()
    return bool(user and roles.can(user, permission))


@bp.route('/problems')
def problems_page():
    return spa.render('Problems')


@bp.route('/api/problems', methods=['GET'])
def list_problems():
    return jsonify({**problems.current(_can('seats.view')), 'can_mute': _can('incidents.work')})


@bp.route('/api/alerts/mutes', methods=['POST'])
def add_mute():
    body = request.get_json(silent=True) or {}
    if body.get('service_id'):
        wall = current_app.extensions.get('floorbit_health')
        check = next((c for c in (wall.snapshot()['checks'] if wall else []) if c['id'] == body['service_id']), None)
        if not check:
            return jsonify({'error': 'There is no such service.'}), 400
        key, name, label = alerting.service_key(check['id']), check['name'], 'Muted service alerts'
    else:
        device = next((d for d in inventory.devices(load_data(), include_hidden=True)
                       if d['id'] == body.get('switch_id')), None)
        if not device:
            return jsonify({'error': 'There is no such switch.'}), 400
        key, name, label = device['id'], device['name'], 'Muted switch alerts'
    try:
        mute = alerting.mute(key, name, body.get('minutes'), g.get('audit_user'), body.get('reason'))
    except alerting.MuteError as exc:
        return jsonify({'error': str(exc)}), 400
    audit.record('alerts', label, user=g.get('audit_user'), target=name)
    events.publish('alerts.changed', {})
    return jsonify({'switch_id': key, **mute}), 201


@bp.route('/api/alerts/mutes/<path:switch_id>', methods=['PATCH'])
def extend_mute(switch_id):
    try:
        found = alerting.extend(switch_id, (request.get_json(silent=True) or {}).get('minutes'))
    except alerting.MuteError as exc:
        return jsonify({'error': str(exc)}), 400
    if not found:
        return jsonify({'error': 'That switch is not muted.'}), 404
    audit.record('alerts', 'Extended mute', user=g.get('audit_user'), target=found.get('name'))
    events.publish('alerts.changed', {})
    return jsonify({'switch_id': switch_id, **found})


@bp.route('/api/alerts/mutes/<path:switch_id>', methods=['DELETE'])
def end_mute(switch_id):
    found = alerting.unmute(switch_id)
    if not found:
        return jsonify({'error': 'That switch is not muted.'}), 404
    audit.record('alerts', 'Ended mute', user=g.get('audit_user'), target=found.get('name'))
    events.publish('alerts.changed', {})
    return jsonify({'ok': True})
