"""Halls (or floors), each with its own floor plan (issue #20). Rules live in floorbit/halls.py.

- ``GET /api/halls``: the halls in order, with their background's URL and how much is in each.
- ``POST /api/halls``, ``PUT``/``DELETE /api/halls/<id>``: add, rename, delete (only an empty hall).
- ``GET``/``PUT``/``DELETE /api/halls/<id>/background``: the floor plan image under the hall.
- ``POST /api/halls/<id>/seat-blocks.csv``: add seat blocks from a CSV file, all or nothing.
"""
from flask import Blueprint, Response, jsonify, request

from .. import halls
from ..store import load_data, save_data
from .inventory import data_lock
from .seat_blocks import make_block

bp = Blueprint('halls', __name__)

MAX_BODY = 8 * 1024 * 1024   # a 5 MB image as base64, and some room


def _too_big():
    return (request.content_length or 0) > MAX_BODY


@bp.route('/api/halls', methods=['GET'])
def list_halls():
    data = load_data()
    return jsonify({'halls': [halls.public(data, h) for h in halls.halls(data)]})


@bp.route('/api/halls', methods=['POST'])
def add_hall():
    body = request.get_json(silent=True) or {}
    with data_lock:
        data = load_data()
        try:
            hall = halls.create(data, body.get('name'))
        except halls.HallError as exc:
            return jsonify({'error': str(exc)}), 400
        save_data(data)
    return jsonify(halls.public(data, hall)), 201


@bp.route('/api/halls/<hall_id>', methods=['PUT'])
def rename_hall(hall_id):
    body = request.get_json(silent=True) or {}
    with data_lock:
        data = load_data()
        try:
            hall = halls.rename(data, hall_id, body.get('name'))
        except KeyError:
            return jsonify({'error': 'No such hall'}), 404
        except halls.HallError as exc:
            return jsonify({'error': str(exc)}), 400
        save_data(data)
    return jsonify(halls.public(data, hall))


@bp.route('/api/halls/<hall_id>', methods=['DELETE'])
def delete_hall(hall_id):
    with data_lock:
        data = load_data()
        try:
            halls.delete(data, hall_id)
        except KeyError:
            return jsonify({'error': 'No such hall'}), 404
        except halls.HallError as exc:
            return jsonify({'error': str(exc)}), 409
        save_data(data)
    return jsonify({'success': True})


@bp.route('/api/halls/<hall_id>/background', methods=['GET'])
def get_background(hall_id):
    hall = halls.find(load_data(), hall_id)
    found = halls.read_background(hall) if hall else None
    if not found:
        return jsonify({'error': 'This hall has no background'}), 404
    resp = Response(found[1], mimetype=found[0])
    # An uploaded SVG is a document: never let it run script if opened directly.
    resp.headers['Content-Security-Policy'] = "default-src 'none'; style-src 'unsafe-inline'; sandbox"
    resp.headers['X-Content-Type-Options'] = 'nosniff'
    resp.headers['Cache-Control'] = 'private, max-age=31536000, immutable' if request.args.get('v') else 'no-cache'
    return resp


@bp.route('/api/halls/<hall_id>/background', methods=['PUT'])
def set_background(hall_id):
    if _too_big():
        return jsonify({'error': f'The background is at most {halls.IMAGE_MAX_BYTES // (1024 * 1024)} MB'}), 413
    body = request.get_json(silent=True) or {}
    with data_lock:
        data = load_data()
        halls.ensure(data)
        hall = halls.find(data, hall_id)
        if hall is None:
            return jsonify({'error': 'No such hall'}), 404
        try:
            mime, raw = halls.decode_image(body.get('image'))
        except halls.HallError as exc:
            return jsonify({'error': str(exc)}), 400
        halls.set_background(hall, mime, raw)
        save_data(data)
    return jsonify(halls.public(data, hall))


@bp.route('/api/halls/<hall_id>/background', methods=['DELETE'])
def delete_background(hall_id):
    with data_lock:
        data = load_data()
        halls.ensure(data)
        hall = halls.find(data, hall_id)
        if hall is None:
            return jsonify({'error': 'No such hall'}), 404
        halls.remove_background(hall)
        save_data(data)
    return jsonify(halls.public(data, hall))


@bp.route('/api/halls/<hall_id>/seat-blocks.csv', methods=['POST'])
def import_blocks(hall_id):
    """CSV in the body (text/csv), or ``{"csv": "..."}``. Nothing is added unless every row is fine."""
    if _too_big():
        return jsonify({'error': 'The file is too big'}), 413
    body = request.get_json(silent=True)
    text = body.get('csv') if isinstance(body, dict) else request.get_data(as_text=True)
    if not isinstance(text, str) or not text.strip():
        return jsonify({'error': 'Send the CSV file'}), 400
    blocks, errors = halls.parse_blocks_csv(text)
    with data_lock:
        data = load_data()
        if halls.find(data, hall_id) is None:
            return jsonify({'error': 'No such hall'}), 404
        # Seat numbers come from block names, and they must stay unique across every hall.
        taken = {str(b.get('name') or '').upper() for b in data.get('seat_blocks') or []}
        errors += [{'line': None, 'error': f'There already is a block "{b["name"]}"'}
                   for b in blocks if b['name'].upper() in taken]
        if errors:
            return jsonify({'error': 'Nothing was imported', 'errors': errors}), 400
        new = [make_block(b, hall_id) for b in blocks]
        data.setdefault('seat_blocks', []).extend(new)
        save_data(data)
    return jsonify({'added': len(new), 'seat_blocks': new}), 201
