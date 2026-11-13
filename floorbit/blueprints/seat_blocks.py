"""Seat blocks (rows of seats) on the floor plan."""
import uuid

from flask import Blueprint, jsonify, request

from ..store import load_data, save_data

bp = Blueprint('seat_blocks', __name__)


@bp.route('/api/seats', methods=['GET'])
def get_seats():
    data = load_data()
    return jsonify(data.get('seats', []))


@bp.route('/api/seat-blocks', methods=['GET'])
def get_seat_blocks():
    data = load_data()
    return jsonify(data.get('seat_blocks', []))


@bp.route('/api/seat-blocks', methods=['POST'])
def add_seat_block():
    """Create a seating block (row or multiple rows)."""
    body = request.get_json(force=True)
    try:
        x = float(body['x'])
        y = float(body['y'])
        cols = int(body.get('cols', 1))
        rows = int(body.get('rows', 1))
        seat_width = float(body.get('seat_width', 3))
        seat_height = float(body.get('seat_height', 3))
        spacing_x = float(body.get('spacing_x', 0.5))
        spacing_y = float(body.get('spacing_y', 1))
    except (KeyError, TypeError, ValueError):
        return jsonify({'error': 'Valid coordinates and dimensions are required'}), 400

    block = {
        'id': str(uuid.uuid4()),
        'name': body.get('name', ''),
        'x': x,
        'y': y,
        'cols': cols,
        'rows': rows,
        'seat_width': seat_width,
        'seat_height': seat_height,
        'spacing_x': spacing_x,
        'spacing_y': spacing_y,
        'rotation': body.get('rotation', 0),
        'reverse_numbers': body.get('reverse_numbers', False),
    }
    data = load_data()
    data.setdefault('seat_blocks', []).append(block)
    save_data(data)
    return jsonify(block), 201


@bp.route('/api/seat-blocks/<block_id>', methods=['PUT'])
def update_seat_block(block_id):
    body = request.get_json(force=True)
    data = load_data()

    for block in data.get('seat_blocks', []):
        if block['id'] == block_id:
            for key in ('name', 'x', 'y', 'cols', 'rows', 'seat_width', 'seat_height',
                       'spacing_x', 'spacing_y', 'rotation', 'reverse_numbers'):
                if key in body:
                    block[key] = body[key]
            save_data(data)
            return jsonify(block)
    return jsonify({'error': 'Seat block not found'}), 404


@bp.route('/api/seat-blocks/<block_id>', methods=['DELETE'])
def delete_seat_block(block_id):
    data = load_data()
    before = len(data.get('seat_blocks', []))
    data['seat_blocks'] = [b for b in data['seat_blocks'] if b['id'] != block_id]
    if len(data['seat_blocks']) == before:
        return jsonify({'error': 'Seat block not found'}), 404
    save_data(data)
    return jsonify({'success': True})
