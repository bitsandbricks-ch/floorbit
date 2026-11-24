"""Saved floor plan views (floorbit/plan_views.py).

- ``GET /api/plan-views?hall=``: the views you see (shared, and your private ones), of one hall or all.
- ``POST /api/plan-views`` ``{name, hall, view: {x, y, w, h}, layers, fade, show, private}``.
- ``PUT /api/plan-views/<id>``: the same fields, replacing the view's.
- ``DELETE /api/plan-views/<id>``.

Writing needs ``floorplan.edit`` (auth/roles.py).
"""
from flask import Blueprint, current_app, jsonify, request

from .. import plan_views as views

bp = Blueprint('plan_views', __name__)


def _user():
    from auth import current_user  # late: auth imports floorbit while it loads
    if not current_app.extensions['auth'].enabled:
        return ''
    user = current_user()
    return (user or {}).get('username') or ''


@bp.route('/api/plan-views', methods=['GET'])
def list_views():
    hall = request.args.get('hall')
    return jsonify({'views': views.visible(_user(), hall or None)})


@bp.route('/api/plan-views', methods=['POST'])
def add_view():
    try:
        view = views.add(request.get_json(silent=True) or {}, _user())
    except views.ViewError as exc:
        return jsonify({'error': views.public(exc)}), 400
    return jsonify(view), 201


@bp.route('/api/plan-views/<view_id>', methods=['PUT'])
def update_view(view_id):
    try:
        view = views.update(view_id, request.get_json(silent=True) or {}, _user())
    except views.ViewError as exc:
        return jsonify({'error': views.public(exc)}), 400
    except KeyError:
        return jsonify({'error': 'No such view'}), 404
    return jsonify(view)


@bp.route('/api/plan-views/<view_id>', methods=['DELETE'])
def delete_view(view_id):
    try:
        views.delete(view_id, _user())
    except KeyError:
        return jsonify({'error': 'No such view'}), 404
    return jsonify({'success': True})
