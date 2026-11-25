"""Fill area (#1565): seat blocks and walkways laid out over a box the editor draws (floorbit/fill_area.py)."""
import copy
import uuid

from flask import Blueprint, jsonify, request

from .. import fill_area, halls, plan_groups, plan_marks
from ..store import load_data, save_data
from .inventory import data_lock
from .seat_blocks import BlockError, _clash, _clash_error, make_block, with_hall

bp = Blueprint('fill_area', __name__)


def _refused(exc):
    # Only the message our own checks raised goes back, never the exception itself.
    return jsonify({'error': exc.args[0] if exc.args else 'The area could not be filled'}), 400


@bp.route('/api/seat-blocks/fill', methods=['POST'])
def fill():
    """``{hall_id, x, y, w, h, seats, rows, spacer, walkway, row_start, labels, group}``: the box
    filled with runs and walkways, put in one group named ``group`` (none when empty). With
    ``preview`` it only counts. All or nothing: ``{blocks, marks, group}``."""
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({'error': 'Send the area as a JSON object.'}), 400
    with data_lock:
        data = load_data()
        try:
            hall_id = halls.check_id(data, body.get('hall_id'))
            raw_blocks, raw_marks = fill_area.layout(body, fill_area.options(body))
            if body.get('preview'):
                return jsonify({'blocks': len(raw_blocks), 'marks': len(raw_marks),
                                'seats': sum(b['cols'] * b['rows'] for b in raw_blocks)})
            blocks = [make_block(b, hall_id) for b in raw_blocks]
        except (fill_area.FillError, BlockError, halls.HallError) as exc:
            return _refused(exc)
        except (KeyError, TypeError, ValueError):
            return jsonify({'error': 'Valid coordinates and dimensions are required'}), 400
        seat = _clash(blocks, data)
        if seat:
            return _clash_error(seat)
        # Marks and the group go on a copy, so a refusal halfway leaves the plan as it was.
        new = copy.deepcopy(data)
        try:
            marks = [plan_marks.add(new, {**m, 'hall_id': hall_id}) for m in raw_marks]
            group = None
            name = str(body.get('group') or '').strip()
            if name and len(blocks) + len(marks) > 1:
                members = ([{'kind': 'block', 'id': b['id']} for b in blocks]
                           + [{'kind': 'mark', 'id': m['id']} for m in marks])
                group = plan_groups.add(new, {'id': f'g-{uuid.uuid4().hex[:8]}', 'hall_id': hall_id,
                                              'name': name, 'members': members})
        except (plan_marks.MarkError, plan_groups.GroupError) as exc:
            return _refused(exc)
        new.setdefault('seat_blocks', []).extend(blocks)
        save_data(new)
    return jsonify({'blocks': with_hall(blocks, new), 'marks': marks, 'group': group}), 201
