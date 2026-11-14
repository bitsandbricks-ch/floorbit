"""The floor plan's seat view (issue #55): the React page and its two reads.

- ``GET /plan``: the page (React): every seat with one state, zoom levels and a seat inspector.
- ``GET /api/plan?hall=<id>``: the hall's drawing, a state per seat and counts per block.
- ``GET /api/plan/seats/<seat>``: one seat for the inspector. Nicks, IPs and MACs only with ``seats.view``.
- ``GET /api/plan/blocks/<name>``: one seat block for the block panel: states, problems, switches.
- ``GET /api/plan/switches/<name>``: one switch for the switch panel: status and the seats it serves.
- ``PUT /api/plan/seats/<seat>/note`` ``{text}``: the crew's note on the seat; empty text removes it.

Reading needs ``floorplan.view`` (the default rule in auth/roles.py), the note ``incidents.work``.
The rules live in floorbit/seat_view.py and floorbit/seat_notes.py.
"""
from flask import Blueprint, current_app, g, jsonify, request

from integrations import events

from .. import audit, incidents, seat_notes, seat_view, spa
from ..store import load_data

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
    out = seat_view.details(seat, people=_can('seats.view'), crew=_can('incidents.work'))
    if out is None:
        return jsonify({'error': 'No such seat.'}), 404
    return jsonify(out)


@bp.route('/api/plan/blocks/<name>')
def block_details(name):
    out = seat_view.block(name)
    if out is None:
        return jsonify({'error': 'No such block.'}), 404
    return jsonify(out)


@bp.route('/api/plan/switches/<name>')
def switch_details(name):
    out = seat_view.switch(name)
    if out is None:
        return jsonify({'error': 'No such switch.'}), 404
    return jsonify(out)


@bp.route('/api/plan/seats/<seat>/note', methods=['PUT'])
def seat_note(seat):
    seat = str(seat or '').upper()
    if seat not in incidents.seat_numbers(load_data()):
        return jsonify({'error': 'No such seat.'}), 404
    text = (request.get_json(silent=True) or {}).get('text')
    if text is not None and not isinstance(text, str):
        return jsonify({'error': 'The note is text.'}), 400
    from auth import current_user  # late: auth imports floorbit while it loads
    user = current_user() or {}
    note = seat_notes.set_note(seat, text, by=user.get('display_name') or user.get('username'))
    audit.record('incidents', 'Wrote a seat note' if note else 'Removed a seat note', g.get('audit_user'), seat)
    events.publish('plan.changed', {'seat': seat})
    return jsonify({'note': note})
