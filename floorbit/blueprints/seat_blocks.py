"""Seat blocks (rows of seats) on the floor plan. Each is in one hall (``hall_id``, floorbit/halls.py)."""
import uuid

from flask import Blueprint, jsonify, request

from .. import halls
from ..store import load_data, save_data

bp = Blueprint('seat_blocks', __name__)


@bp.route('/api/seats', methods=['GET'])
def get_seats():
    data = load_data()
    return jsonify(data.get('seats', []))


def with_hall(blocks, data):
    """The blocks with the hall they are in written out, so clients needn't know the fallback."""
    ids = {h['id'] for h in halls.halls(data)}
    return [{**b, 'hall_id': halls.hall_of(b, data, ids)} for b in blocks]


@bp.route('/api/seat-blocks', methods=['GET'])
def get_seat_blocks():
    """All seat blocks, or with ``?hall=<id>`` only that hall's."""
    data = load_data()
    blocks = with_hall(data.get('seat_blocks', []), data)
    wanted = request.args.get('hall')
    return jsonify([b for b in blocks if b['hall_id'] == wanted] if wanted else blocks)


def make_block(body, hall_id):
    """A new block from a request or a CSV row. Raises KeyError, TypeError or ValueError."""
    return {
        'id': str(uuid.uuid4()),
        'name': body.get('name', ''),
        'x': float(body['x']),
        'y': float(body['y']),
        'cols': int(body.get('cols', 1)),
        'rows': int(body.get('rows', 1)),
        'seat_width': float(body.get('seat_width', 3)),
        'seat_height': float(body.get('seat_height', 3)),
        'spacing_x': float(body.get('spacing_x', 0.5)),
        'spacing_y': float(body.get('spacing_y', 1)),
        'rotation': body.get('rotation', 0),
        'reverse_numbers': body.get('reverse_numbers', False),
        'hall_id': hall_id,
    }


@bp.route('/api/seat-blocks', methods=['POST'])
def add_seat_block():
    """Create a seating block (row or multiple rows)."""
    body = request.get_json(force=True)
    data = load_data()
    try:
        hall_id = halls.check_id(data, body.get('hall_id'))
    except halls.HallError as exc:
        return jsonify({'error': str(exc)}), 400
    try:
        block = make_block(body, hall_id)
    except (KeyError, TypeError, ValueError):
        return jsonify({'error': 'Valid coordinates and dimensions are required'}), 400
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
            if 'hall_id' in body:
                try:
                    block['hall_id'] = halls.check_id(data, body['hall_id'])
                except halls.HallError as exc:
                    return jsonify({'error': str(exc)}), 400
            save_data(data)
            return jsonify(with_hall([block], data)[0])
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
