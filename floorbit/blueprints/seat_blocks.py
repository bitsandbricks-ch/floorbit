"""Seat blocks (rows of seats) on the floor plan. Each is in one hall (``hall_id``, floorbit/halls.py).

How a block names its seats (a running number or row letters) is in floorbit/seat_names.py.
"""
import functools
import uuid

from flask import Blueprint, jsonify, request

from .. import block_merge, halls, seat_gaps, seat_layout, seat_names, stacking
from ..plan_marks import on_plan
from ..store import load_data, save_data
from .inventory import data_lock

bp = Blueprint('seat_blocks', __name__)

# The fields a client may set. Seat names come from name, cols, rows, rotation and the naming ones.
KEYS = ('name', 'x', 'y', 'cols', 'rows', 'seat_width', 'seat_height', 'spacing_x', 'spacing_y',
        'rotation', 'reverse_numbers', 'naming', 'row_start', 'row_labels', 'col_gaps', 'row_gaps', 'seat_at',
        'z')
MAX_SIDE = 200      # seats along one side: far beyond any hall, small enough to draw
MAX_MANY = 30       # blocks in one "add several"
# (field, smallest, default): the same bounds as the CSV import and layout templates.
SIZES = (('seat_width', 0.1, 3), ('seat_height', 0.1, 3), ('spacing_x', 0, 0.5), ('spacing_y', 0, 1))


class BlockError(ValueError):
    pass


def _locked(view):
    """One change at a time: the editor saves several blocks at once (a group, a turn), and two
    load-change-save rounds side by side would lose one of them."""
    @functools.wraps(view)
    def wrapper(*args, **kwargs):
        with data_lock:
            return view(*args, **kwargs)
    return wrapper


@bp.route('/api/seats', methods=['GET'])
def get_seats():
    data = load_data()
    return jsonify(data.get('seats', []))


def with_hall(blocks, data):
    """The blocks with the hall they are in written out, so clients needn't know the fallback."""
    ids = {h['id'] for h in halls.halls(data)}
    return [{**b, 'hall_id': halls.hall_of(b, data, ids), **drawn(b)} for b in blocks]


def drawn(block):
    """What a page needs to draw a block's seats without the numbering rules: the seat names row by
    row, each row's letter, and on which side seat 1 is (for the letter at the "start")."""
    return {'seat_rows': seat_names.block_rows(block), 'row_letters': seat_names.row_letters(block),
            'seat_one_first': seat_names.seat_one_first(block)}


def _clean(block):
    """Checks and tidies the naming fields in place; raises BlockError (ValueError for a position
    that isn't a number on the plan)."""
    block['x'], block['y'] = on_plan(block['x']), on_plan(block['y'])
    block['name'] = str(block.get('name') or '')
    # Every page draws with these: one that isn't a number would break the plan for everybody.
    for key, low, default in SIZES:
        n = float(block.get(key, default))
        if not low <= n <= 50:      # also false for NaN
            raise BlockError(f'{key} is a number from {low} to 50')
        block[key] = n
    try:
        block['rotation'] = int(block.get('rotation') or 0)
    except (OverflowError, TypeError, ValueError):
        raise BlockError('rotation is a whole number of degrees') from None
    for side in ('cols', 'rows'):
        if not 1 <= int(block[side]) <= MAX_SIDE:
            raise BlockError(f'A block has 1 to {MAX_SIDE} rows and columns')
        block[side] = int(block[side])
    naming = block.get('naming') or 'block'
    if naming not in seat_names.NAMINGS:
        raise BlockError('Seat names are "block" or "rows"')
    block['naming'] = naming
    start = str(block.get('row_start') or 'A').strip().upper()
    if not seat_names.LETTERS_RE.match(start):
        raise BlockError('The first row is one or two letters, like A or AA')
    block['row_start'] = start
    labels = block.get('row_labels') or 'start'
    if labels not in seat_names.ROW_LABELS:
        raise BlockError('Row letters go at the start, the end, both or none')
    block['row_labels'] = labels
    block['reverse_numbers'] = bool(block.get('reverse_numbers'))
    try:
        block['col_gaps'] = seat_gaps.clean(block.get('col_gaps'), block['cols'])
        block['row_gaps'] = seat_gaps.clean(block.get('row_gaps'), block['rows'])
    except seat_gaps.GapError as exc:
        raise BlockError(str(exc)) from None
    try:
        block['seat_at'] = seat_layout.clean(block.get('seat_at'), block['cols'], block['rows'])
    except seat_layout.LayoutError as exc:
        raise BlockError(str(exc)) from None
    seat_layout.settle(block)
    try:
        block['z'] = stacking.z_of(block.get('z'))
    except stacking.StackError as exc:
        raise BlockError(str(exc)) from None
    return block


def check(raw):
    """A stored block (a backup's, say) checked like an edit: a copy, with its id, hall and any
    fields from later versions kept. Raises BlockError, or KeyError, TypeError or ValueError."""
    return _clean({**raw, 'id': str(raw['id'])})


def _clash(new_blocks, data, skip=(), had=()):
    """The first seat name the new blocks share with each other or another block, or None.

    ``had``: names the block had before an edit. Only new names count, so a plan that has a clash
    from before (two unnamed blocks) can still have its blocks moved."""
    taken = set()
    old = {s.upper() for s in had}
    for b in data.get('seat_blocks') or []:
        if b.get('id') not in skip:
            taken.update(s.upper() for s in seat_names.seats(b))
    for b in new_blocks:
        for seat in seat_names.seats(b):
            if seat.upper() in taken and seat.upper() not in old:
                return seat
            taken.add(seat.upper())
    return None


def _clash_error(seat):
    return jsonify({'error': f'Seat {seat} is in another block already. Pick other row letters or another block name.',
                    'seat': seat}), 409


@bp.route('/api/seat-blocks', methods=['GET'])
def get_seat_blocks():
    """All seat blocks, or with ``?hall=<id>`` only that hall's."""
    data = load_data()
    blocks = with_hall(stacking.by_z(data.get('seat_blocks', [])), data)
    wanted = request.args.get('hall')
    return jsonify([b for b in blocks if b['hall_id'] == wanted] if wanted else blocks)


def make_block(body, hall_id):
    """A new block from a request or a CSV row. Raises KeyError, TypeError or ValueError."""
    return _clean({
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
        'naming': body.get('naming', 'block'),
        'row_start': body.get('row_start', 'A'),
        'row_labels': body.get('row_labels', 'start'),
        'col_gaps': body.get('col_gaps'),
        'row_gaps': body.get('row_gaps'),
        'seat_at': body.get('seat_at'),
        'z': body.get('z'),
        'hall_id': hall_id,
    })


@bp.route('/api/seat-blocks', methods=['POST'])
@_locked
def add_seat_block():
    """Create a seating block (row or multiple rows)."""
    body = request.get_json(force=True, silent=True)
    if not isinstance(body, dict):
        return jsonify({'error': 'Send the block as a JSON object.'}), 400
    data = load_data()
    try:
        hall_id = halls.check_id(data, body.get('hall_id'))
    except halls.HallError as exc:
        return jsonify({'error': str(exc)}), 400
    try:
        block = make_block(body, hall_id)
    except BlockError as exc:
        return jsonify({'error': str(exc)}), 400
    except (KeyError, TypeError, ValueError):
        return jsonify({'error': 'Valid coordinates and dimensions are required'}), 400
    seat = _clash([block], data)
    if seat:
        return _clash_error(seat)
    data.setdefault('seat_blocks', []).append(block)
    save_data(data)
    return jsonify(with_hall([block], data)[0]), 201


def _next_name(name, i):
    """The i-th copy's name: letters count on (A, B, C), anything else gets a number."""
    if not name:
        return ''
    if seat_names.LETTERS_RE.match(name.upper()):
        return seat_names.row_letter(seat_names.letter_index(name.upper()) + i)
    return f'{name} {i + 1}' if i else name


@bp.route('/api/seat-blocks/many', methods=['POST'])
@_locked
def add_many_seat_blocks():
    """Several blocks like one, ``count`` of them ``dx``/``dy`` apart (in % of the plan). Row
    letters and block names count on, so blocks of 2 rows from A give A-B, C-D, E-F. All or nothing."""
    body = request.get_json(force=True) or {}
    data = load_data()
    try:
        hall_id = halls.check_id(data, body.get('hall_id'))
    except halls.HallError as exc:
        return jsonify({'error': str(exc)}), 400
    try:
        count = int(body.get('count', 1))
        dx, dy = float(body.get('dx', 0)), float(body.get('dy', 0))
        if not 1 <= count <= MAX_MANY:
            raise BlockError(f'Add 1 to {MAX_MANY} blocks at once')
        first = make_block(body, hall_id)
        blocks = []
        for i in range(count):
            b = {**first, 'id': str(uuid.uuid4()), 'x': first['x'] + i * dx, 'y': first['y'] + i * dy,
                 'name': _next_name(first['name'], i) if first['naming'] == 'block' else first['name']}
            if first['naming'] == 'rows':
                b['row_start'] = seat_names.row_letter(seat_names.letter_index(first['row_start']) + i * first['rows'])
            blocks.append(_clean(b))
    except BlockError as exc:
        return jsonify({'error': str(exc)}), 400
    except (KeyError, TypeError, ValueError):
        return jsonify({'error': 'Valid coordinates and dimensions are required'}), 400
    seat = _clash(blocks, data)
    if seat:
        return _clash_error(seat)
    data.setdefault('seat_blocks', []).extend(blocks)
    save_data(data)
    return jsonify(with_hall(blocks, data)), 201


@bp.route('/api/seat-blocks/<block_id>', methods=['PUT'])
@_locked
def update_seat_block(block_id):
    body = request.get_json(force=True)
    data = load_data()

    for block in data.get('seat_blocks', []):
        if block['id'] == block_id:
            changed = {**block, **{k: body[k] for k in KEYS if k in body}}
            try:
                changed = _clean(changed)
            except BlockError as exc:
                return jsonify({'error': str(exc)}), 400
            except (TypeError, ValueError):
                return jsonify({'error': 'Valid coordinates and dimensions are required'}), 400
            if 'hall_id' in body:
                try:
                    changed['hall_id'] = halls.check_id(data, body['hall_id'])
                except halls.HallError as exc:
                    return jsonify({'error': str(exc)}), 400
            seat = _clash([changed], data, skip={block_id}, had=seat_names.seats(block))
            if seat:
                return _clash_error(seat)
            block.clear()
            block.update(changed)
            save_data(data)
            return jsonify(with_hall([block], data)[0])
    return jsonify({'error': 'Seat block not found'}), 404


@bp.route('/api/seat-blocks/<block_id>', methods=['DELETE'])
@_locked
def delete_seat_block(block_id):
    data = load_data()
    blocks = data.get('seat_blocks') or []      # a fresh install has none yet
    data['seat_blocks'] = [b for b in blocks if b.get('id') != block_id]
    before = len(blocks)
    if len(data['seat_blocks']) == before:
        return jsonify({'error': 'Seat block not found'}), 404
    save_data(data)
    return jsonify({'success': True})


@bp.route('/api/seat-blocks/merge', methods=['POST'])
@_locked
def merge_seat_blocks():
    """Joins ``ids`` (blocks next to each other, floorbit/block_merge.py) into the first of them;
    the others are removed. Answers the merged block and the ids that went."""
    body = request.get_json(silent=True) or {}
    ids = body.get('ids')
    if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids) or len(set(ids)) != len(ids):
        return jsonify({'error': 'Select two or more seat blocks to merge'}), 400
    data = load_data()
    known = {b['id']: b for b in data.get('seat_blocks', [])}
    if any(i not in known for i in ids):
        return jsonify({'error': 'Seat block not found'}), 404
    blocks = with_hall([known[i] for i in ids], data)
    try:
        merged = _clean(block_merge.merge(blocks))
    except (block_merge.MergeError, BlockError) as exc:
        return jsonify({'error': str(exc)}), 400
    for k in ('seat_rows', 'row_letters', 'seat_one_first'):
        merged.pop(k, None)
    had = [s for i in ids for s in seat_names.seats(known[i])]
    seat = _clash([merged], data, skip=set(ids), had=had)
    if seat:
        return _clash_error(seat)
    gone = [i for i in ids if i != merged['id']]
    data['seat_blocks'] = [b for b in data['seat_blocks'] if b['id'] not in gone]
    for b in data['seat_blocks']:
        if b['id'] == merged['id']:
            b.clear()
            b.update(merged)
            break
    save_data(data)
    return jsonify({'block': with_hall([merged], data)[0], 'removed': gone})
