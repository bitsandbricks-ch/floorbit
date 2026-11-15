"""The floor plan's seat view (issue #55): the React page and its two reads.

- ``GET /plan``: the page (React): every seat with one state, zoom levels and a seat inspector.
- ``GET /api/plan?hall=<id>``: the hall's drawing, a state per seat and counts per block.
- ``GET /api/plan/seats/<seat>``: one seat for the inspector. Nicks, IPs and MACs only with ``seats.view``.

Both need ``floorplan.view`` (the default rule in auth/roles.py). The rules live in floorbit/seat_view.py.
"""
from flask import Blueprint, current_app, jsonify, request

from .. import seat_view, spa

bp = Blueprint('plan', __name__)


def _can(permission):
    from auth import current_user, roles  # late: auth imports floorbit while it loads
    if not current_app.extensions['auth'].enabled:
        return True
    user = current_user()
    return bool(user and roles.can(user, permission))


@bp.route('/plan')
def plan_page():
    return spa.render('Floor plan')


@bp.route('/api/plan')
def plan_view():
    return jsonify(seat_view.view(request.args.get('hall') or None))


@bp.route('/api/plan/seats/<seat>')
def seat_details(seat):
    out = seat_view.details(seat, people=_can('seats.view'))
    if out is None:
        return jsonify({'error': 'No such seat.'}), 404
    return jsonify(out)
