"""Firewalls and the seat ranges they serve (issue #470). Rules in floorbit/firewalls.py, docs in
docs/firewalls.md.

- ``GET /firewalls``: the page.
- ``GET /api/firewalls``: the firewalls with their health, every range with its parts (one per firewall)
  and the firewall each takes now.
- ``POST /api/firewalls/ranges``, ``PUT/DELETE /api/firewalls/ranges/<id>``: ``floorplan.edit``.
- ``GET /api/firewalls/seats``: the seats not on their planned firewall, for the plan's layer.
- ``GET /api/firewalls/lookup?q=<IP or seat>``: which part and firewall that address or seat goes through.
- Ranges from NetBox come with every inventory sync (``floorbit_firewalls`` on a prefix, issue #1347).
"""
from flask import Blueprint, current_app, g, jsonify, request

from .. import audit, firewalls, spa

bp = Blueprint('firewalls', __name__)


def _can(permission):
    from auth import current_user, roles  # late: auth imports floorbit while it loads
    auth = current_app.extensions.get('auth')
    if not (auth and auth.enabled):
        return True
    user = current_user()
    return bool(user and roles.can(user, permission))


@bp.route('/firewalls')
def firewalls_page():
    return spa.render('Firewalls')


@bp.route('/api/firewalls', methods=['GET'])
def get_firewalls():
    return jsonify(firewalls.overview())


@bp.route('/api/firewalls/seats', methods=['GET'])
def seat_routes():
    return jsonify(firewalls.seat_routes())


@bp.route('/api/firewalls/lookup', methods=['GET'])
def lookup():
    try:
        return jsonify(firewalls.lookup(request.args.get('q'), spans=_can('seats.view')))
    except firewalls.FirewallError as exc:
        return jsonify({'error': str(exc)}), exc.status


@bp.route('/api/firewalls/ranges', methods=['POST'])
@bp.route('/api/firewalls/ranges/<range_id>', methods=['PUT'])
def save_range(range_id=None):
    try:
        row = firewalls.save(request.get_json(silent=True) or {}, g.get('audit_user'), range_id)
    except firewalls.FirewallError as exc:
        return jsonify({'error': str(exc)}), exc.status
    audit.record('floor plan', 'Changed firewall range' if range_id else 'Added firewall range', g.get('audit_user'),
                 f"{row['cidr']} to {', '.join(row['firewalls'])}")
    return jsonify(row), 200 if range_id else 201


@bp.route('/api/firewalls/ranges/<range_id>', methods=['DELETE'])
def delete_range(range_id):
    gone = firewalls.delete(range_id)
    if gone is None:
        return jsonify({'error': 'No such range.'}), 404
    audit.record('floor plan', 'Removed firewall range', g.get('audit_user'), gone['cidr'])
    return jsonify({'ok': True})
