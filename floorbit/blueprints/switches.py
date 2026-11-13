"""Switches on the floor plan: NetBox devices (positions stored here) and manual ones."""
import uuid

import requests
from flask import Blueprint, jsonify, request

from .. import sources
from ..sources.netbox import merge_devices_with_positions
from ..store import load_data, save_data

bp = Blueprint('switches', __name__)


@bp.route('/api/switches', methods=['GET'])
def get_switches():
    data = load_data()
    manual = data.get('switches', [])
    if sources.inventory().enabled():
        netbox = merge_devices_with_positions(
            data.get('cached_devices', []),
            data.get('positions', {}),
        )
        return jsonify(netbox + manual)
    return jsonify(manual)


@bp.route('/api/switches/sync', methods=['POST'])
def sync_switches():
    """Re-fetch device list from NetBox and persist it (NetBox mode only)."""
    if not sources.inventory().enabled():
        return jsonify({'error': 'NetBox is not configured'}), 400
    try:
        devices = sources.inventory().fetch_devices()
    except requests.RequestException as exc:
        return jsonify({'error': f'NetBox request failed: {exc}'}), 502

    data = load_data()
    data['cached_devices'] = devices
    data.setdefault('positions', {})
    save_data(data)
    return jsonify(merge_devices_with_positions(devices, data['positions']))


@bp.route('/api/switches', methods=['POST'])
def add_switch():
    """Create and place a manual switch (available in both manual and NetBox mode)."""
    body = request.get_json(force=True)
    try:
        x = float(body['x'])
        y = float(body['y'])
    except (KeyError, TypeError, ValueError):
        return jsonify({'error': 'Valid numeric x and y coordinates are required'}), 400

    switch = {
        'id':     str(uuid.uuid4()),
        'name':   body.get('name', 'Switch'),
        'x':      x,
        'y':      y,
        'placed': True,
        'source': 'manual',
        'status': 'unknown',
    }
    data = load_data()
    data.setdefault('switches', []).append(switch)
    save_data(data)
    return jsonify(switch), 201


@bp.route('/api/switches/<switch_id>', methods=['PUT'])
def update_switch(switch_id):
    body = request.get_json(force=True)
    data = load_data()

    if sources.inventory().enabled():
        device = next(
            (d for d in data.get('cached_devices', []) if d['id'] == switch_id),
            None,
        )
        if device:
            positions = data.setdefault('positions', {})
            pos = positions.get(switch_id, {})
            if 'x' in body and 'y' in body:
                try:
                    pos = {'x': float(body['x']), 'y': float(body['y'])}
                except (TypeError, ValueError):
                    return jsonify({'error': 'Invalid coordinates'}), 400
            positions[switch_id] = pos
            save_data(data)
            return jsonify({
                'id':            device['id'],
                'name':          device['name'],
                'netbox_status': device.get('netbox_status', 'unknown'),
                'x':             pos.get('x'),
                'y':             pos.get('y'),
                'placed':        True,
                'status':        'unknown',
            })
        # Fall through to handle manual switches in NetBox mode

    for switch in data.get('switches', []):
        if switch['id'] == switch_id:
            for key in ('name', 'x', 'y'):
                if key in body:
                    switch[key] = body[key]
            save_data(data)
            return jsonify(switch)
    return jsonify({'error': 'Switch not found'}), 404


@bp.route('/api/switches/<switch_id>', methods=['DELETE'])
def delete_switch(switch_id):
    data = load_data()

    if sources.inventory().enabled():
        positions = data.setdefault('positions', {})
        if switch_id in positions:
            del positions[switch_id]
            save_data(data)
            return jsonify({'success': True})
        # Fall through to handle manual switches in NetBox mode

    before = len(data.get('switches', []))
    data['switches'] = [s for s in data['switches'] if s['id'] != switch_id]
    if len(data['switches']) == before:
        return jsonify({'error': 'Switch not found'}), 404
    save_data(data)
    return jsonify({'success': True})
