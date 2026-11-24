"""Merging seat blocks that sit next to each other into one (Mike: join blocks, rows and numbers carry on).

Blocks merge when they are turned the same way and line up: stacked (the rows of the lower ones
join the first's, the space between becomes the gap above the first joined row) or side by side
(straight rows only, as many in each block: each row gets longer, the space becomes a gap in it),
seen from the block's own frame before it is turned. The first block (top or left in that frame)
keeps its name and naming settings, so its seat names stay and the others' seats carry on after it.

The plan is 50 seats wide and 31.25 seats high (the editor's 1000 x 625 px at a 20 px seat pitch,
the Seats view's 1600 x 1000 at 32): that turns positions in % into seats.
"""
import math

from . import seat_gaps, seat_rows

PLAN_SEATS_W = 50.0
PLAN_SEATS_H = 31.25
LINE_UP = 0.5        # seats the blocks may be off from each other across the join
TOUCH = 0.125        # seats of space (or overlap) that count as touching


class MergeError(ValueError):
    pass


def _size(block):
    _, w, h = seat_rows.layout(block)
    return w, h


def _local(block, rotation):
    """The block's centre in seats, turned back by ``rotation`` into the blocks' own frame."""
    x, y = float(block['x']) / 100 * PLAN_SEATS_W, float(block['y']) / 100 * PLAN_SEATS_H
    a = math.radians(-rotation)
    return x * math.cos(a) - y * math.sin(a), x * math.sin(a) + y * math.cos(a)


def _shift(gaps, by):
    return [{'after': int(g['after']) + by, 'size': g['size']} for g in gaps or []]


def _gaps_between(block):
    return [float(r.get('gap') or 0) for r in seat_rows.rows_of(block)[1:]]


def merge(blocks):
    """The fields of one block made of ``blocks`` (two or more dicts), keeping the first one's id
    and settings; raises MergeError when they can't be joined."""
    if len(blocks) < 2:
        raise MergeError('Select two or more seat blocks to merge')
    rotation = int(blocks[0].get('rotation') or 0) % 360
    if any(int(b.get('rotation') or 0) % 360 != rotation for b in blocks):
        raise MergeError('Seat blocks that are turned differently cannot be merged')
    if len({b.get('naming') or 'block' for b in blocks}) > 1:
        raise MergeError('Seat blocks that name their seats differently cannot be merged')
    if len({b.get('hall_id') for b in blocks}) > 1:
        raise MergeError('Seat blocks in different halls cannot be merged')
    if any(b.get('seat_at') for b in blocks):
        raise MergeError('Seat blocks with seats placed freely cannot be merged')

    at = [(_local(b, rotation), _size(b), b) for b in blocks]
    xs = [p[0] for p, _, _ in at]
    ys = [p[1] for p, _, _ in at]
    # The join runs along the axis the blocks are spread out on.
    across = (max(xs) - min(xs)) >= (max(ys) - min(ys))
    at.sort(key=lambda t: t[0][0] if across else t[0][1])
    first = at[0][2]
    rows = [dict(r) for r in seat_rows.rows_of(first)]
    if across:
        straight = all((r.get('shape') or 'line') == 'line' and not r.get('shift')
                       and (r.get('align') or 'start') == 'start' for _, _, b in at for r in seat_rows.rows_of(b))
        if not straight or any(seat_rows.count(b) != len(rows) or _gaps_between(b) != _gaps_between(first)
                               for _, _, b in at[1:]):
            raise MergeError('Only seat blocks with the same straight rows can be merged side by side')
    (px, py), (pw, ph), _ = at[0]
    start = (px - pw / 2) if across else (py - ph / 2)
    end = (px + pw / 2) if across else (py + ph / 2)
    for (cx, cy), (w, h), b in at[1:]:
        if abs((cy - py) if across else (cx - px)) > LINE_UP:
            raise MergeError('The seat blocks do not line up: move them in line first')
        lo = (cx - w / 2) if across else (cy - h / 2)
        space = lo - end
        if space < -TOUCH:
            raise MergeError('The seat blocks overlap: move them apart first')
        if space > seat_gaps.MAX_SIZE:
            raise MergeError(f'The seat blocks are more than {seat_gaps.MAX_SIZE} seats apart')
        gap = round(max(space, seat_gaps.MIN_SIZE), 2) if space >= TOUCH else 0
        if across:
            for row, other in zip(rows, seat_rows.rows_of(b), strict=True):
                n = int(row['seats'])
                row['col_gaps'] = list(row.get('col_gaps') or []) + ([{'after': n, 'size': gap}] if gap else []) \
                    + _shift(other.get('col_gaps'), n)
                row['seats'] = n + int(other['seats'])
                if row['seats'] > seat_rows.MAX_SEATS:
                    raise MergeError(f'A row has at most {seat_rows.MAX_SEATS} seats')
        else:
            for i, other in enumerate(seat_rows.rows_of(b)):
                rows.append({**other, 'id': seat_rows.next_id(rows), 'gap': gap if i == 0 else other.get('gap', 0)})
            if len(rows) > seat_rows.MAX_ROWS:
                raise MergeError(f'A block has at most {seat_rows.MAX_ROWS} rows')
        end = (cx + w / 2) if across else (cy + h / 2)

    # The middle of the joined block, turned back onto the plan.
    mid_along = (start + end) / 2
    mid_across = sum((p[1] if across else p[0]) for p, _, _ in at) / len(at)
    lx, ly = (mid_along, mid_across) if across else (mid_across, mid_along)
    a = math.radians(rotation)
    x, y = lx * math.cos(a) - ly * math.sin(a), lx * math.sin(a) + ly * math.cos(a)
    return {**first, 'rows': rows,
            'x': round(x / PLAN_SEATS_W * 100, 2), 'y': round(y / PLAN_SEATS_H * 100, 2)}
