"""Switches on the floor plan: the placed devices of the inventory (floorbit/inventory.py).

The editor's API from before the inventory, kept so the floor plan works unchanged: every
inventory device is a switch here, whoever created it.
"""
from flask import Blueprint, jsonify, request

from .. import inventory
from ..store import load_data, save_data
from .inventory import data_lock, run_sync

bp = Blueprint('switches', __name__)


@bp.route('/api/switches', methods=['GET'])
def get_switches():
    return jsonify([inventory.as_switch(d) for d in inventory.devices(load_data())])


@bp.route('/api/switches/sync', methods=['POST'])
def sync_switches():
    """Pull devices from every inventory plugin that's on (NetBox), then list them."""
    reports = run_sync()
    if not reports:
        return jsonify({'error': 'No inventory source is on. Turn on NetBox under Settings > Plugins.'}), 400
    errors = [r for r in reports if r.get('error')]
    if len(errors) == len(reports):
        return jsonify({'error': '; '.join(r['error'] for r in errors), 'reports': reports}), 502
    return jsonify([inventory.as_switch(d) for d in inventory.devices(load_data())])


@bp.route('/api/switches', methods=['POST'])
def add_switch():
    """Create and place a switch made by hand."""
    body = request.get_json(force=True) or {}
    try:
        x, y = float(body['x']), float(body['y'])
    except (KeyError, TypeError, ValueError):
        return jsonify({'error': 'Valid numeric x and y coordinates are required'}), 400
    with data_lock:
        data = load_data()
        try:
            dev = inventory.create(data, {'name': body.get('name') or 'Switch', 'role': 'switch', 'x': x, 'y': y})
        except inventory.InventoryError as exc:
            return jsonify({'error': str(exc)}), 400
        save_data(data)
    return jsonify(inventory.as_switch(dev)), 201


@bp.route('/api/switches/<switch_id>', methods=['PUT'])
def update_switch(switch_id):
    body = request.get_json(force=True) or {}
    patch = {k: body[k] for k in ('name', 'x', 'y') if k in body}
    if ('x' in patch) != ('y' in patch):
        patch.pop('x', None)
        patch.pop('y', None)
    with data_lock:
        data = load_data()
        try:
            dev, _ = inventory.update(data, switch_id, patch)
        except KeyError:
            return jsonify({'error': 'Switch not found'}), 404
        except inventory.InventoryError as exc:
            return jsonify({'error': str(exc)}), 400
        save_data(data)
    return jsonify(inventory.as_switch(dev))


@bp.route('/api/switches/<switch_id>', methods=['DELETE'])
def delete_switch(switch_id):
    """Takes a switch off the floor plan: a fed one stays in the inventory, unplaced."""
    with data_lock:
        data = load_data()
        dev = inventory.find(data, switch_id)
        if dev is None:
            return jsonify({'error': 'Switch not found'}), 404
        if dev.get('refs'):
            inventory.unplace(data, switch_id)
        else:
            inventory.delete(data, switch_id)
        save_data(data)
    return jsonify({'success': True})
