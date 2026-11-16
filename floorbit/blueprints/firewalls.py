"""Firewalls and the seat ranges they serve (issue #470). Rules in floorbit/firewalls.py, docs in
docs/firewalls.md.

- ``GET /firewalls``: the page.
- ``GET /api/firewalls``: the firewalls with their health, every range with the firewall it takes now.
- ``POST /api/firewalls/ranges``, ``PUT/DELETE /api/firewalls/ranges/<id>``: ``floorplan.edit``.
- ``GET /api/firewalls/seats``: the seats not on their planned firewall, for the plan's layer.
- ``POST /api/firewalls/ranges/split``: cut a network into ranges, shared out over the firewalls in turn.
"""
from flask import Blueprint, g, jsonify, request

from .. import audit, firewalls, spa

bp = Blueprint('firewalls', __name__)


@bp.route('/firewalls')
def firewalls_page():
    return spa.render('Firewalls')


@bp.route('/api/firewalls', methods=['GET'])
def get_firewalls():
    return jsonify(firewalls.overview())


@bp.route('/api/firewalls/seats', methods=['GET'])
def seat_routes():
    return jsonify(firewalls.seat_routes())


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


@bp.route('/api/firewalls/ranges/split', methods=['POST'])
def split_ranges():
    body = request.get_json(silent=True) or {}
    try:
        out = firewalls.split(body, g.get('audit_user'))
    except firewalls.FirewallError as exc:
        return jsonify({'error': str(exc)}), exc.status
    if out['added']:
        audit.record('floor plan', 'Split a network into firewall ranges', g.get('audit_user'),
                     f"{body.get('cidr')} into {out['added']} ranges")
    return jsonify(out), 201 if out['added'] else 200


@bp.route('/api/firewalls/ranges/<range_id>', methods=['DELETE'])
def delete_range(range_id):
    gone = firewalls.delete(range_id)
    if gone is None:
        return jsonify({'error': 'No such range.'}), 404
    audit.record('floor plan', 'Removed firewall range', g.get('audit_user'), gone['cidr'])
    return jsonify({'ok': True})
