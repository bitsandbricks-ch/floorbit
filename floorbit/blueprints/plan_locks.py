"""Locked items on the floor plan (floorbit/plan_locks.py)."""
from flask import Blueprint, jsonify, request

from .. import halls, plan_locks
from ..store import load_data, save_data
from .inventory import data_lock

bp = Blueprint('plan_locks', __name__)


@bp.route('/api/plan-locks', methods=['GET'])
def list_locks():
    """The hall's locked items (``?hall=<id>``; the first hall without one)."""
    data = load_data()
    try:
        hall_id = halls.check_id(data, request.args.get('hall') or None)
    except halls.HallError as exc:
        return jsonify({'error': str(exc)}), 400
    return jsonify({'hall_id': hall_id, 'locks': plan_locks.locks(data, hall_id)})


@bp.route('/api/plan-locks', methods=['PUT'])
def set_locks():
    """Locks or unlocks items: ``{hall_id, items: [{kind, id}], locked: true|false}``."""
    body = request.get_json(silent=True) or {}
    with data_lock:
        data = load_data()
        try:
            out = plan_locks.set_locked(data, body.get('hall_id'), body.get('items'), body.get('locked'))
        except plan_locks.LockError as exc:
            return jsonify({'error': str(exc)}), 400
        save_data(data)
    return jsonify({'locks': out})
