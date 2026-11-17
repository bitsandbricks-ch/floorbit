"""Cables drawn on the floor plan (floorbit/cable_plan.py).

- ``GET /api/cable-plan?hall=<id>``: the cables to draw in a hall, the patch panels on it, and
  whether automatic cabling is on.
- ``PUT /api/cable-plan/routes``: ``{"routes": {key: {"points", "corners"} | null}}``: bends the
  crew placed, round or square corners; null goes back to the automatic route.
- ``PUT /api/cable-plan/panels/<name>``: ``{"x", "y", "hall_id"}`` puts a patch panel on the plan;
  ``DELETE`` takes it off.

Reading needs ``floorplan.view``, changing ``floorplan.edit`` (auth/roles.py).
"""
from flask import Blueprint, g, jsonify, request

from integrations import events

from .. import cable_plan, halls
from ..cables import all_cables
from ..store import load_data

bp = Blueprint('cable_plan', __name__)


def _error(exc):
    return jsonify({'error': str(exc)}), getattr(exc, 'status', 400)


@bp.route('/api/cable-plan', methods=['GET'])
def cable_drawing():
    data = load_data()
    try:
        hall = halls.check_id(data, request.args.get('hall') or None)
    except halls.HallError as exc:
        return jsonify({'error': str(exc)}), 404
    out = cable_plan.plan(data, hall)
    out['panel_names'] = sorted({c['panel'] for c in all_cables(data) if c.get('panel')}, key=str.lower)
    return jsonify(out)


@bp.route('/api/cable-plan/routes', methods=['PUT'])
def change_routes():
    body = request.get_json(silent=True) or {}
    try:
        saved = cable_plan.set_routes(body.get('routes'), g.get('audit_user'))
    except cable_plan.RouteError as exc:
        return _error(exc)
    events.publish('cables.changed', {})
    return jsonify({'routes': saved})


@bp.route('/api/cable-plan/panels/<path:name>', methods=['PUT'])
def place_panel(name):
    try:
        panel = cable_plan.place_panel(name, request.get_json(silent=True) or {})
    except (cable_plan.RouteError, halls.HallError) as exc:
        return _error(exc)
    events.publish('cables.changed', {})
    return jsonify(panel)


@bp.route('/api/cable-plan/panels/<path:name>', methods=['DELETE'])
def remove_panel(name):
    if not cable_plan.remove_panel(name):
        return jsonify({'error': 'No such patch panel on the plan'}), 404
    events.publish('cables.changed', {})
    return jsonify({'ok': True})
