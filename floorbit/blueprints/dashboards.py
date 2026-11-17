"""Dashboards: screens split into panes (floorbit/dashboards.py, docs/dashboards.md).

- ``GET /dashboards``: the list and the editor; ``GET /dashboards/<id>``: one dashboard full screen.
- ``GET /api/dashboards``, ``GET /api/dashboards/<id>``: everyone who sees the floor plan.
- ``PUT``/``DELETE /api/dashboards/<id>``: floorplan.edit (auth/roles.py).
"""
from flask import Blueprint, g, jsonify, request

from .. import audit, dashboards, spa

bp = Blueprint('dashboards', __name__)


def _error(message, status=400):
    return jsonify({'error': message}), status


@bp.route('/dashboards')
def dashboards_page():
    return spa.render('Dashboards')


@bp.route('/dashboards/<layout_id>')
def dashboard_screen(layout_id):
    return spa.render('Dashboard')


@bp.route('/api/dashboards', methods=['GET'])
def list_layouts():
    return jsonify({'layouts': dashboards.all_layouts(), 'pages': list(dashboards.PAGES)})


@bp.route('/api/dashboards/<layout_id>', methods=['GET'])
def get_layout(layout_id):
    layout = dashboards.get(layout_id)
    if not layout:
        return _error('No such dashboard.', 404)
    return jsonify(layout)


@bp.route('/api/dashboards/<layout_id>', methods=['PUT'])
def save_layout(layout_id):
    user = g.get('audit_user')
    try:
        layout = dashboards.save(layout_id, request.get_json(silent=True), user)
    except dashboards.LayoutError as exc:
        return _error(str(exc), exc.status)
    audit.record('settings', 'Saved dashboard', user, layout['name'])
    return jsonify(layout)


@bp.route('/api/dashboards/<layout_id>', methods=['DELETE'])
def delete_layout(layout_id):
    try:
        dashboards.delete(layout_id)
    except dashboards.LayoutError as exc:
        return _error(str(exc), exc.status)
    audit.record('settings', 'Removed dashboard', g.get('audit_user'), layout_id)
    return jsonify({'ok': True})
