"""A seat block is a list of rows (Mike: "a block is just a group of rows, it can be one row as
well"), and a row needn't be straight: it can bend, wrap round a table as a U or an L, or follow a
path drawn point by point.

A block keeps ``rows``, top first, each a dict:

- ``id``: the row's id inside the block, a whole number as text. It never changes when rows are
  reordered, so a row walked, patched or fed by a circuit stays the same row (``<block>:<id>``,
  floorbit/seat_names.py). A block moved from the grid shape got ids 1, 2, 3 in its old order, so
  everything that named its rows by position before still names the same rows.
- ``seats``: how many seats the row has. Rows in a block may differ.
- ``shape``: ``line``, ``arc`` (``bend``: the turn from first to last seat in degrees), ``u`` and
  ``l`` (``sides``: seats on each side, first side first) or ``path`` (``path``: points in seats).
- ``gap``: empty space above the row in seats (the aisle, room for the switch). The first row's
  is ignored.
- ``align`` (``start``, ``middle``, ``end``) and ``shift`` (seats): where a row sits sideways
  against the widest one.
- ``side``: where the people sit, ``left`` or ``right`` of the way the row runs, or ``""`` for the
  shape's own default (none for a line or path, inside for an arc, U or L).
- ``reverse``: number this row the other way. ``col_gaps``: gaps inside the row,
  ``[{"after": n, "size": s}]`` (floorbit/seat_gaps.py).
- ``mirror`` and ``flip``: the shape turned over left to right, or upside down (Mike: "Mirror /
  Flip?"), so an L can turn the other way and a U open downwards. The seats keep their order and
  the people stay on the same side of the shape.

Everything is in seats: one seat is one unit. ``layout`` turns a block into each seat's centre and
the direction its row runs there; seat_layout.py turns that into what the pages draw.
"""
import itertools
import math

from . import seat_gaps

SHAPES = ('line', 'arc', 'u', 'l', 'path')
ALIGNS = ('start', 'middle', 'end')
SIDES = ('', 'left', 'right')
MAX_ROWS = 50
MAX_SEATS = 200      # in one row
MAX_GAP = 20         # seats between two rows
MAX_SHIFT = 200
MAX_BEND = 330       # degrees: a little short of a full circle
MAX_POINTS = 50


class RowError(ValueError):
    pass


def _num(value, lo, hi, what):
    try:
        n = float(value)
    except (TypeError, ValueError):
        raise RowError(f'{what} is a number') from None
    if not lo <= n <= hi:       # also false for NaN
        raise RowError(f'{what} is a number from {lo:g} to {hi:g}')
    return round(n, 2)


def _ids(rows):
    return {str(r.get('id')) for r in rows if isinstance(r, dict) and r.get('id') not in (None, '')}


def next_id(rows):
    """An id no row of ``rows`` has: one more than the highest."""
    numbers = [int(i) for i in _ids(rows) if i.isdigit()]
    return str(max(numbers, default=0) + 1)


def default_sides(shape, seats):
    """Seats per side when none are given: a U as wide as it's deep, an L with equal arms."""
    if shape == 'u':
        side = max(1, seats // 4) if seats >= 3 else 0
        return [side, seats - 2 * side, side] if side else [0, seats, 0]
    if shape == 'l':
        return [seats // 2, seats - seats // 2]
    return []


def clean_row(raw, used=()):
    """One row as stored; raises RowError. A row without an id (a new one) gets one not in ``used``."""
    if not isinstance(raw, dict):
        raise RowError('Each row is an object with at least "seats"')
    rid = str(raw.get('id') or '').strip()
    if not rid.isdigit() or len(rid) > 6:
        rid = next_id([{'id': i} for i in used])
    try:
        seats = int(raw.get('seats'))
    except (TypeError, ValueError):
        raise RowError('A row has a number of seats') from None
    if not 1 <= seats <= MAX_SEATS:
        raise RowError(f'A row has 1 to {MAX_SEATS} seats')
    shape = raw.get('shape') or 'line'
    if shape not in SHAPES:
        raise RowError('A row is a line, an arc, a U, an L or a path')
    align = raw.get('align') or 'start'
    if align not in ALIGNS:
        raise RowError('A row lines up at the start, the middle or the end')
    side = raw.get('side') or ''
    if side not in SIDES:
        raise RowError('People sit left or right of a row')
    try:
        col_gaps = seat_gaps.clean(raw.get('col_gaps'), seats)
    except seat_gaps.GapError as exc:
        raise RowError(str(exc)) from None
    row = {'id': rid, 'seats': seats, 'shape': shape,
           'gap': _num(raw.get('gap') or 0, 0, MAX_GAP, 'The space above a row'),
           'align': align, 'shift': _num(raw.get('shift') or 0, -MAX_SHIFT, MAX_SHIFT, 'A row\'s shift'),
           'side': side, 'reverse': bool(raw.get('reverse')), 'col_gaps': col_gaps,
           'mirror': bool(raw.get('mirror')), 'flip': bool(raw.get('flip'))}
    if shape == 'arc':
        row['bend'] = _num(raw.get('bend') if raw.get('bend') is not None else 60, -MAX_BEND, MAX_BEND, 'The bend')
    if shape in ('u', 'l'):
        row['sides'] = _sides(raw.get('sides'), shape, seats)
    if shape == 'path':
        row['path'] = _path(raw.get('path'), seats)
    return row


def _sides(raw, shape, seats):
    want = 3 if shape == 'u' else 2
    if raw in (None, '', []):
        return default_sides(shape, seats)
    if not isinstance(raw, list) or len(raw) != want:
        raise RowError('A U has 3 sides of seats' if shape == 'u' else 'An L has 2 sides of seats')
    try:
        sides = [int(n) for n in raw]
    except (TypeError, ValueError):
        raise RowError('Each side is a number of seats') from None
    if any(n < 0 for n in sides) or sum(sides) != seats:
        raise RowError(f'The sides add up to the row\'s {seats} seats')
    return sides


def _path(raw, seats):
    if raw in (None, '', []):
        return [[0, 0], [seats, 0]]
    if not isinstance(raw, list) or not 2 <= len(raw) <= MAX_POINTS:
        raise RowError(f'A path has 2 to {MAX_POINTS} points')
    out = []
    for p in raw:
        try:
            x, y = float(p[0]), float(p[1])
        except (TypeError, ValueError, IndexError, KeyError):
            raise RowError('A path is a list of [x, y] points in seats') from None
        if not (math.isfinite(x) and math.isfinite(y)) or abs(x) > MAX_SHIFT or abs(y) > MAX_SHIFT:
            raise RowError(f'A path point is at most {MAX_SHIFT} seats out')
        out.append([round(x, 2), round(y, 2)])
    if sum(math.dist(a, b) for a, b in itertools.pairwise(out)) <= 0:
        raise RowError('A path needs two different points')
    return out


def clean(raw):
    """A block's ``rows`` as stored; raises RowError. Ids stay unique: a repeated one is renewed."""
    if not isinstance(raw, list) or not 1 <= len(raw) <= MAX_ROWS:
        raise RowError(f'A block has 1 to {MAX_ROWS} rows')
    out, used = [], set()
    for item in raw:
        if isinstance(item, dict) and str(item.get('id') or '') in used:
            item = {**item, 'id': None}
        row = clean_row(item, used | _ids(raw))
        used.add(row['id'])
        out.append(row)
    return out


def grid(cols, rows, col_gaps=None, row_gaps=None):
    """``rows`` for a block of ``rows`` straight rows of ``cols`` seats: the Block tool's rectangle,
    and the shape blocks had before rows (``from_grid``). ``row_gaps`` become each row's ``gap``."""
    cols, rows = int(cols), int(rows)
    above = {int(g['after']) + 1: float(g['size']) for g in row_gaps or []
             if isinstance(g, dict) and str(g.get('after', '')).lstrip('-').isdigit()}
    return [{'id': str(i + 1), 'seats': cols, 'shape': 'line', 'gap': round(above.get(i + 1, 0), 2) if i else 0,
             'align': 'start', 'shift': 0, 'side': '', 'reverse': False, 'col_gaps': list(col_gaps or [])}
            for i in range(rows)]


def from_grid(block):
    """A block still in the grid shape (``cols``, ``rows`` as numbers, block-wide gaps, ``seat_at``
    keyed ``"row index,col"``) moved to rows, in place. A block in rows is left alone."""
    if isinstance(block.get('rows'), list):
        return block
    if block.get('rows') is None and block.get('cols') is None:
        return block     # no seats to move (a stand-in, half a record): nothing to make up
    try:
        cols, count = max(1, int(block.get('cols') or 1)), max(1, int(block.get('rows') or 1))
    except (TypeError, ValueError):
        cols, count = 1, 1
    try:
        col_gaps = seat_gaps.clean(block.get('col_gaps'), cols)
        row_gaps = seat_gaps.clean(block.get('row_gaps'), count)
    except seat_gaps.GapError:
        col_gaps, row_gaps = [], []
    block['rows'] = grid(cols, count, col_gaps, row_gaps)
    seat_at = block.get('seat_at')
    if isinstance(seat_at, dict):
        # Keys named the row by its place; the ids 1, 2, 3 keep that order.
        moved = {}
        for key, at in seat_at.items():
            r, _, c = str(key).partition(',')
            if r.isdigit() and c.isdigit():
                moved[f'{int(r) + 1},{c}'] = at
        block['seat_at'] = moved or None
    for key in ('cols', 'col_gaps', 'row_gaps'):
        block.pop(key, None)
    return block


def rows_of(block):
    """The block's rows (a block not moved yet is read as its grid)."""
    rows = block.get('rows')
    if isinstance(rows, list):
        return rows
    return from_grid(dict(block)).get('rows') or []


def count(block):
    return len(rows_of(block))


def seat_count(block):
    return sum(int(r.get('seats') or 0) for r in rows_of(block))


def default_side(row):
    shape = row.get('shape') or 'line'
    if shape in ('u', 'l'):
        return 'left'      # the shapes run down, then across: inside is on the left
    if shape == 'arc':
        return 'right' if float(row.get('bend') or 0) >= 0 else 'left'
    return ''


def side_of(row):
    side = row.get('side') or default_side(row)
    # Turned over once, left of the way the row runs is what was right: swap to stay on the same side.
    if side and bool(row.get('mirror')) != bool(row.get('flip')):
        return 'right' if side == 'left' else 'left'
    return side


# ── Laying the seats out ──────────────────────────────────────────────────────────────────

def _along(row):
    """Where each seat's centre is along the row, in seats from its start (gaps add space)."""
    starts, length = seat_gaps.offsets(row.get('col_gaps'), int(row['seats']))
    return [s + 0.5 for s in starts], length


def _line(row):
    at, _ = _along(row)
    return [(d, 0.5, 0.0) for d in at]


def _arc(row):
    at, length = _along(row)
    turn = math.radians(float(row.get('bend') or 0))
    if abs(turn) < 1e-3:
        return _line(row)
    radius = length / turn
    # Start the curve so its chord lies flat: the row's tangent runs from -turn/2 to +turn/2.
    start = -turn / 2
    out = []
    for d in at:
        phi = start + d / radius
        x = radius * (math.sin(phi) - math.sin(start))
        y = -radius * (math.cos(phi) - math.cos(start))
        out.append((x, y, math.degrees(phi)))
    return out


def _u(row):
    a, b, c = row.get('sides') or default_sides('u', int(row['seats']))
    deep = max(a, c)
    out = [(0.5, deep - a + i + 0.5, 90.0) for i in range(a)]
    out += [(1.5 + i if a else 0.5 + i, deep + 0.5, 0.0) for i in range(b)]
    right = (1.5 if a else 0.5) + b
    out += [(right, deep - i - 0.5, -90.0) for i in range(c)]
    return out


def _l(row):
    a, b = row.get('sides') or default_sides('l', int(row['seats']))
    out = [(0.5, i + 0.5, 90.0) for i in range(a)]
    out += [(1.5 + i if a else 0.5 + i, a + 0.5, 0.0) for i in range(b)]
    return out


def _on_path(row):
    points = row.get('path') or [[0, 0], [int(row['seats']), 0]]
    legs = [(p, q, math.dist(p, q)) for p, q in itertools.pairwise(points) if math.dist(p, q) > 0]
    at, _ = _along(row)
    out = []
    for d in at:
        walked = 0.0
        for i, (p, q, n) in enumerate(legs):
            if d <= walked + n or i == len(legs) - 1:     # past the end: carry on along the last leg
                t = (d - walked) / n
                x, y = p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t
                out.append((x, y, math.degrees(math.atan2(q[1] - p[1], q[0] - p[0]))))
                break
            walked += n
    return out


_SHAPES = {'line': _line, 'arc': _arc, 'u': _u, 'l': _l, 'path': _on_path}


def row_seats(row):
    """Each seat of one row on its own: ``[(x, y, angle)]`` centres in seats (any origin) and the
    direction the row runs there in degrees (0 = left to right), in seat order before numbering."""
    seats = _SHAPES.get(row.get('shape') or 'line', _line)(row)
    if row.get('mirror'):
        seats = [(-x, y, _turn(180 - a)) for x, y, a in seats]
    if row.get('flip'):
        seats = [(x, -y, _turn(-a)) for x, y, a in seats]
    return seats


def _turn(a):
    """An angle in degrees within -180..180, 0 for no turn at all."""
    a = (a + 180) % 360 - 180
    return 180.0 if a == -180 else a + 0.0


def _box(points):
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    return min(xs) - 0.5, min(ys) - 0.5, max(xs) + 0.5, max(ys) + 0.5


def layout(block):
    """``({(r, c): (x, y, angle)}, width, height)``: every seat's centre in the block's own frame
    (before it is turned) in seats, the box starting at 0,0, with ``r`` the row's place in the
    block and ``c`` the seat's place in the row. Seats moved by hand (``seat_at``, keyed
    ``"<row id>,<seat>"``, their top-left corner) stand where they were put."""
    rows = rows_of(block)
    laid = []
    for row in rows:
        seats = row_seats(row)
        left, top, right, bottom = _box(seats)
        laid.append((row, [(x - left, y - top, a) for x, y, a in seats], right - left, bottom - top))
    widest = max((w for _, _, w, _ in laid), default=0)
    at, y = {}, 0.0
    for r, (row, seats, w, h) in enumerate(laid):
        if r:
            y += float(row.get('gap') or 0)
        x = {'start': 0, 'middle': (widest - w) / 2, 'end': widest - w}[row.get('align') or 'start']
        x += float(row.get('shift') or 0)
        for c, (sx, sy, a) in enumerate(seats):
            at[r, c] = (sx + x, sy + y, a)
        y += h
    custom = block.get('seat_at') or {}
    if custom:
        index = {str(row.get('id')): r for r, row in enumerate(rows)}
        for key, p in custom.items():
            rid, _, c = str(key).partition(',')
            if rid in index and c.isdigit() and (index[rid], int(c)) in at:
                at[index[rid], int(c)] = (float(p[0]) + 0.5, float(p[1]) + 0.5, at[index[rid], int(c)][2])
    if not at:
        return {}, 0, 0
    left, top, right, bottom = _box(list(at.values()))
    return ({rc: (round(x - left, 4), round(y - top, 4), round(a, 2)) for rc, (x, y, a) in at.items()},
            round(right - left, 4), round(bottom - top, 4))
