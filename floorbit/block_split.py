"""Splitting a seat block in two at a row (#1208), the other way round from floorbit/block_merge.py.

The rows above ``at`` stay in the block (its id, name and settings); the rows from ``at`` on become
a new block in the same hall, turned the same way. Both parts stay where their seats were on the
plan. A block named by its rows keeps every row's letter; a block with a name gives the new part
the next free name, since its seats start counting at 1 again.
"""
import math
import uuid

from . import seat_names, seat_rows
from .block_merge import PLAN_SEATS_H, PLAN_SEATS_W


class SplitError(ValueError):
    pass


def _centre(block, part):
    """The middle of the seats of rows ``part`` (a range), on the plan in %."""
    at, w, h = seat_rows.layout(block)
    seats = [xy for (r, _), xy in at.items() if r in part]
    xs, ys = [s[0] for s in seats], [s[1] for s in seats]
    # From the middle of the whole block to the middle of the part, in seats, then turned.
    dx = (min(xs) + max(xs)) / 2 - w / 2
    dy = (min(ys) + max(ys)) / 2 - h / 2
    a = math.radians(int(block.get('rotation') or 0))
    tx, ty = dx * math.cos(a) - dy * math.sin(a), dx * math.sin(a) + dy * math.cos(a)
    return (round(float(block['x']) + tx / PLAN_SEATS_W * 100, 2),
            round(float(block['y']) + ty / PLAN_SEATS_H * 100, 2))


def _free_name(name, taken):
    """A name for the new part: the next free letters after a lettered name (A gives B), else the
    name with the next free number (Gaming gives Gaming 2); an unnamed block's part gets a letter."""
    taken = {t.upper() for t in taken}
    letters = name.upper() if seat_names.LETTERS_RE.match(name.upper()) else ''
    start = seat_names.letter_index(letters) + 1 if letters else 0
    if letters or not name:
        for i in range(start, 26 * 27):
            candidate = seat_names.row_letter(i)
            if candidate not in taken:
                return candidate
    n = 2
    while f'{name} {n}'.upper() in taken:
        n += 1
    return f'{name} {n}'


def split(block, at, taken=()):
    """``(kept, new)``: the fields of ``block`` with its rows before ``at``, and of a new block with
    the rest. ``taken``: the block names already in use. Raises SplitError."""
    rows = [dict(r) for r in seat_rows.rows_of(block)]
    if not isinstance(at, int) or isinstance(at, bool) or not 0 < at < len(rows):
        raise SplitError('Pick a row after the first to split the block at')
    if block.get('seat_at'):
        raise SplitError('Seat blocks with seats placed freely cannot be split')
    kept = {**block, 'rows': rows[:at], 'seat_at': None}
    new = {**block, 'id': str(uuid.uuid4()), 'rows': [{**rows[at], 'gap': 0}, *rows[at + 1:]], 'seat_at': None}
    kept['x'], kept['y'] = _centre(block, range(at))
    new['x'], new['y'] = _centre(block, range(at, len(rows)))
    if (block.get('naming') or 'block') == 'rows':
        letters = seat_names.row_letters(block)
        for part, span in ((kept, letters[:at]), (new, letters[at:])):
            part['row_start'] = min(span, key=seat_names.letter_index)
    else:
        new['name'] = _free_name(str(block.get('name') or ''), [*taken, block.get('name') or ''])
    return kept, new
