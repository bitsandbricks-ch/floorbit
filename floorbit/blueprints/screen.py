"""The hall drawing the public pages use (the seat help page, Wi-Fi): seat blocks, rows and plan
marks as SVG shapes. The big-screen rotation that lived here is now dashboards that rotate
(``?rotate=`` on a dashboard, docs/dashboards.md)."""
import math

from flask import Blueprint

from .. import halls, icon_library, plan_marks, seat_layout, seat_rows, stacking
from ..seat_names import block_rows, label, row_id, row_label, row_letters, row_names, seat_one_first

bp = Blueprint('screen', __name__)

# Block positions are percentages of the floor plan; the public pages draw them on a canvas this
# big, with seats a bit larger than the editor's so they are easy to see on a phone.
PLAN_W, PLAN_H, CELL = 1600, 1000, 32


def _row_labels(block, at, angles, w, h):
    """Where each row's letter goes, in the block's own coordinates (centre of the letter): one
    seat before seat 1 for "start", one past the last seat for "end" (floorbit/seat_names.py),
    along the way the row runs there, so a bent row gets its letter at its ends too."""
    letters = row_letters(block)
    where = block.get('row_labels') or 'start'
    if not letters or where == 'none':
        return []
    one_first = seat_one_first(block)
    rows = seat_rows.rows_of(block)
    out = []
    for r, letter in enumerate(letters):
        row = rows[r]
        n = int(row['seats'])
        own = row.get('label') or where
        if own in ('hidden', 'none'):
            continue
        if own == 'moved' and row.get('label_at'):
            # Moved by hand: kept in the row's own frame (seat_rows.row_seats), so it moves with the row.
            sx, sy, _ = seat_rows.row_seats(row)[0]
            x0, y0 = at[r, 0]
            lx, ly = row['label_at']
            out.append({'text': letter, 'r': r,
                        'x': (x0 + 0.5 + lx - sx) * CELL - w / 2, 'y': (y0 + 0.5 + ly - sy) * CELL - h / 2})
            continue
        # (seat, -1 before it or +1 past it): seat 1 is the row's first seat or its last.
        first = one_first != bool(row.get('reverse'))
        before, after = ((0, -1), (n - 1, 1)) if first else ((n - 1, 1), (0, -1))
        ends = {'start': [before], 'end': [after], 'both': [before, after], 'moved': [before]}[own]
        for c, out_dir in ends:
            x, y = at[r, c]
            a = math.radians(angles[r, c])
            cx, cy = x + 0.5 + out_dir * math.cos(a), y + 0.5 + out_dir * math.sin(a)
            out.append({'text': letter, 'r': r, 'x': cx * CELL - w / 2, 'y': cy * CELL - h / 2})
    return out


def _rows_of(block, count):
    if not block.get('id'):
        return []
    names, naming, block_label = row_names(block), block.get('naming') or 'block', label(block)
    rows = seat_rows.rows_of(block)
    # ``row``: the row's own id in its block, what seat places are keyed by (floorbit/seat_layout.py).
    return [{'id': row_id(block, i + 1), 'row': str(rows[i]['id']),
             'name': row_label({'name': names[i] if i < len(names) else str(i + 1), 'naming': naming,
                                'block_label': block_label})} for i in range(count)]


def plan(data, highlight=None, online=None, hall_id=None, public=False):
    """One hall's seat blocks (the first hall's by default) as SVG shapes, cropped to the hall,
    with one seat marked.

    With ``online`` (a set of seat numbers) every cell also says whether its seat is online.
    ``public`` drops the marks on crew layers (network, electrical, services) for attendee pages.
    """
    shapes, xs, ys, found = [], [], [], None
    hall_id = hall_id or halls.default_id(data)
    ids = {h['id'] for h in halls.halls(data)}
    for block in stacking.by_z(data.get('seat_blocks') or []):
        if halls.hall_of(block, data, ids) != hall_id:
            continue
        rows = block_rows(block)
        if not rows or block.get('x') is None:
            continue
        nrows = len(rows)
        cx, cy = float(block['x']) / 100 * PLAN_W, float(block['y']) / 100 * PLAN_H
        # Seat offsets inside the block; not ``xs``/``ys``, which collect the hall's extent.
        at, width, height = seat_layout.places(block)
        angles = seat_layout.angles(block)
        sides = [seat_rows.side_of(r) for r in seat_rows.rows_of(block)]
        w, h = width * CELL, height * CELL
        cells = []
        for r, row in enumerate(rows):
            for c, seat in enumerate(row):
                hit = seat == highlight
                if hit:
                    found = {'seat': seat, 'block': block.get('name') or '', 'row': r + 1, 'rows': nrows,
                             'col': c + 1}
                x, y = at[r, c]
                cell = {'x': x * CELL - w / 2, 'y': y * CELL - h / 2, 'hit': hit, 'seat': seat,
                        'on': None if online is None else seat in online, 'rc': [r, c]}
                # Only what differs from a plain straight row, so a hall of rows stays small.
                if angles[r, c]:
                    cell['a'] = angles[r, c]
                if sides[r]:
                    cell['side'] = sides[r]
                cells.append(cell)
        reach = max(w, h) / 2 + CELL * 2   # the row letters sit one cell out
        xs += [cx - reach, cx + reach]
        ys += [cy - reach - 40, cy + reach]   # room for the block's name above it
        shapes.append({'id': block.get('id'),
                       'cx': cx, 'cy': cy, 'rotation': int(block.get('rotation') or 0) % 360, 'w': w, 'h': h,
                       'name': block.get('name') or '', 'cells': cells,
                       # Row letters belong to rows; seats placed freely have none to stand by.
                       'rows': [] if block.get('seat_at') else _row_labels(block, at, angles, w, h),
                       # Each row (cells' rc[0]) by its id and name, as /api/options/rows has them.
                       'row_list': _rows_of(block, nrows),
                       'free': bool(block.get('seat_at'))})
    if not shapes:
        return None, None
    marks, icons, custom = _marks(data, hall_id, xs, ys, public)
    box = (min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))
    return {'shapes': shapes, 'box': ' '.join(f'{v:.0f}' for v in box), 'cell': CELL,
            'marks': marks, 'icons': icons, 'custom_icons': custom}, found


def _marks(data, hall_id, xs, ys, public=False):
    """The hall's text, walls, zones and icons (floorbit/plan_marks.py) in drawing units, and the
    icons they use. Grows ``xs``/``ys`` so walls around the seats aren't cut off."""
    sx, sy = PLAN_W / 100, PLAN_H / 100
    out, used = [], set()
    for m in plan_marks.all_marks(data, hall_id):
        if public and m.get('layer', 'overview') not in plan_marks.PUBLIC_LAYERS:
            continue
        d = {**m, 'x': m['x'] * sx, 'y': m['y'] * sy}
        d.pop('hall_id', None)
        if m['kind'] == 'wall':
            d.update(x2=m['x2'] * sx, y2=m['y2'] * sy)
            if m.get('points'):
                d['points'] = [[x * sx, y * sy] for x, y in m['points']]
            xs += [d['x'], d['x2'], *(p[0] for p in d.get('points', []))]
            ys += [d['y'], d['y2'], *(p[1] for p in d.get('points', []))]
        elif m['kind'] == 'zone':
            d.update(w=m['w'] * sx, h=m['h'] * sy)
            xs += [d['x'], d['x'] + d['w']]
            ys += [d['y'], d['y'] + d['h']]
        else:
            if m['kind'] == 'icon':
                used.add(m['icon'])
            xs += [d['x'] - CELL * 2, d['x'] + CELL * 2]
            ys += [d['y'] - CELL * 2, d['y'] + CELL * 2]
        out.append(d)
    return (out, {k: plan_marks.ICONS[k] for k in sorted(used) if k in plan_marks.ICONS},
            icon_library.data_uris(data, used))

