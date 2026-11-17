"""Groups of items on the floor plan (floorbit/plan_groups.py)."""
from flask import Blueprint, jsonify, request

from .. import plan_groups
from ..store import load_data, save_data
from .inventory import data_lock

bp = Blueprint('plan_groups', __name__)


@bp.route('/api/plan-groups', methods=['GET'])
def list_groups():
    """The groups (``?hall=<id>`` for one hall's)."""
    return jsonify({'groups': plan_groups.all_groups(load_data(), request.args.get('hall') or None)})


@bp.route('/api/plan-groups', methods=['POST'])
def add_group():
    body = request.get_json(silent=True) or {}
    with data_lock:
        data = load_data()
        try:
            group = plan_groups.add(data, body)
        except plan_groups.GroupError as exc:
            return jsonify({'error': str(exc)}), 400
        save_data(data)
    return jsonify(group), 201


@bp.route('/api/plan-groups', methods=['PUT'])
def replace_groups():
    """All of one hall's groups at once: ``{hall_id, groups: [{id, name, members}]}``."""
    body = request.get_json(silent=True) or {}
    with data_lock:
        data = load_data()
        try:
            groups = plan_groups.replace(data, body.get('hall_id'), body.get('groups'))
        except plan_groups.GroupError as exc:
            return jsonify({'error': str(exc)}), 400
        save_data(data)
    return jsonify({'groups': groups})


@bp.route('/api/plan-groups/<group_id>', methods=['PUT'])
def change_group(group_id):
    body = request.get_json(silent=True) or {}
    with data_lock:
        data = load_data()
        try:
            group = plan_groups.change(data, group_id, body)
        except plan_groups.GroupError as exc:
            return jsonify({'error': str(exc)}), 400
        if group is None:
            return jsonify({'error': 'No such group on the plan'}), 404
        save_data(data)
    return jsonify(group)


@bp.route('/api/plan-groups/<group_id>', methods=['DELETE'])
def delete_group(group_id):
    with data_lock:
        data = load_data()
        if not plan_groups.remove(data, group_id):
            return jsonify({'error': 'No such group on the plan'}), 404
        save_data(data)
    return jsonify({'ok': True})
