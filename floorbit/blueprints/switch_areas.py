"""Which seats each switch serves (issue #948): rules in floorbit/switch_areas.py, docs in
docs/switch-areas.md.

- ``GET /api/switch-areas``: every switch with what it serves, where that comes from, its drift and
  the rows offered as pins.
- ``PUT /api/switch-areas/<switch>``: ``{"blocks", "rows", "seats", "exclude"}``: the manual area;
  all empty removes it.

Reading needs ``seats.view``, changing ``seats.edit`` (auth/roles.py).
"""
from flask import Blueprint, g, jsonify, request

from integrations import events

from .. import audit, spa, switch_areas
from ..blueprints.inventory import data_lock
from ..store import load_data, save_data

bp = Blueprint('switch_areas', __name__)


@bp.route('/switch-areas')
def page():
    return spa.render('Switch areas')


@bp.route('/api/switch-areas', methods=['GET'])
def overview():
    return jsonify(switch_areas.overview())


@bp.route('/api/switch-areas/<switch>', methods=['PUT'])
def pin(switch):
    with data_lock:
        data = load_data()
        try:
            area = switch_areas.pin(switch, request.get_json(silent=True), data)
        except switch_areas.AreaError as exc:
            return jsonify({'error': str(exc)}), exc.status
        save_data(data)
    audit.record('seats', 'Set the seats a switch serves', g.get('audit_user'), switch)
    events.publish('switch-areas.changed', {})
    return jsonify(area)
