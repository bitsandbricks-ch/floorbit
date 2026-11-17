"""Text, walls, zones and icons on the floor plan (floorbit/plan_marks.py). An icon is a built-in one
or an uploaded one from the icon library; ``custom_icons`` carries the uploaded ones the marks use."""
from flask import Blueprint, jsonify, request

from .. import icon_library, plan_marks
from ..store import load_data, save_data
from .inventory import data_lock

bp = Blueprint('plan_marks', __name__)


@bp.route('/api/plan-marks', methods=['GET'])
def list_marks():
    """The marks (``?hall=<id>`` for one hall's) and the icons they can use."""
    data = load_data()
    marks = plan_marks.all_marks(data, request.args.get('hall') or None)
    return jsonify({'marks': marks, 'icons': plan_marks.ICONS,
                    'custom_icons': icon_library.data_uris(data, (m.get('icon') for m in marks))})


@bp.route('/api/plan-marks', methods=['POST'])
def add_mark():
    body = request.get_json(silent=True) or {}
    with data_lock:
        data = load_data()
        try:
            mark = plan_marks.add(data, body)
        except plan_marks.MarkError as exc:
            return jsonify({'error': str(exc)}), 400
        save_data(data)
    return jsonify(mark), 201


@bp.route('/api/plan-marks/<mark_id>', methods=['PUT'])
def change_mark(mark_id):
    body = request.get_json(silent=True) or {}
    with data_lock:
        data = load_data()
        try:
            mark = plan_marks.change(data, mark_id, body)
        except plan_marks.MarkError as exc:
            return jsonify({'error': str(exc)}), 400
        if mark is None:
            return jsonify({'error': 'No such mark on the plan'}), 404
        save_data(data)
    return jsonify(mark)


@bp.route('/api/plan-marks/<mark_id>', methods=['DELETE'])
def delete_mark(mark_id):
    with data_lock:
        data = load_data()
        if not plan_marks.remove(data, mark_id):
            return jsonify({'error': 'No such mark on the plan'}), 404
        save_data(data)
    return jsonify({'ok': True})
