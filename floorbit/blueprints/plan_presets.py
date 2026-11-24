"""Plan presets (floorbit/plan_presets.py): items of the plan kept together to place again.

- ``GET /api/plan-presets``: the presets, each ``{id, name, saved, counts, items}``.
- ``POST /api/plan-presets`` ``{name, items: [{kind, body}]}``: items as the editor copies them.
- ``DELETE /api/plan-presets/<id>``.

Placing one is the editor posting each item again, like a paste.
"""
from flask import Blueprint, jsonify, request

from .. import plan_presets as presets

bp = Blueprint('plan_presets', __name__)


@bp.route('/api/plan-presets', methods=['GET'])
def list_presets():
    return jsonify({'presets': presets.all_presets()})


@bp.route('/api/plan-presets', methods=['POST'])
def save_preset():
    if (request.content_length or 0) > presets.MAX_BYTES + 4096:
        return jsonify({'error': f'A preset is at most {presets.MAX_BYTES // 1024} kB'}), 413
    body = request.get_json(silent=True) or {}
    try:
        preset = presets.add(body.get('name'), body.get('items'))
    except presets.PresetError as exc:
        return jsonify({'error': str(exc)}), 400
    return jsonify(preset), 201


@bp.route('/api/plan-presets/<preset_id>', methods=['DELETE'])
def delete_preset(preset_id):
    try:
        presets.delete(preset_id)
    except KeyError:
        return jsonify({'error': 'No such preset'}), 404
    return jsonify({'success': True})
