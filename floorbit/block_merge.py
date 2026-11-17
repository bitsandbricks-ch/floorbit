"""Merging seat blocks that sit next to each other into one (Mike: join blocks, rows and numbers carry on).

Blocks merge when they are turned the same way and line up: stacked (the same columns) or side by
side (the same rows), seen from the block's own frame before it is turned. The first block (top or
left in that frame) keeps its name and naming settings, so its seat names stay and the others'
seats carry on after it. Space between the blocks becomes a gap (floorbit/seat_gaps.py).

The plan is 50 seats wide and 31.25 seats high (the editor's 1000 x 625 px at a 20 px seat pitch,
the Seats view's 1600 x 1000 at 32): that turns positions in % into seats.
"""
import math

from . import seat_gaps

PLAN_SEATS_W = 50.0
PLAN_SEATS_H = 31.25
LINE_UP = 0.5        # seats the blocks may be off from each other across the join
TOUCH = 0.125        # seats of space (or overlap) that count as touching


class MergeError(ValueError):
    pass


def _size(block):
    _, w = seat_gaps.offsets(block.get('col_gaps'), int(block['cols']))
    _, h = seat_gaps.offsets(block.get('row_gaps'), int(block['rows']))
    return w, h


def _local(block, rotation):
    """The block's centre in seats, turned back by ``rotation`` into the blocks' own frame."""
    x, y = float(block['x']) / 100 * PLAN_SEATS_W, float(block['y']) / 100 * PLAN_SEATS_H
    a = math.radians(-rotation)
    return x * math.cos(a) - y * math.sin(a), x * math.sin(a) + y * math.cos(a)


def _shift(gaps, by):
    return [{'after': int(g['after']) + by, 'size': g['size']} for g in gaps or []]


def _same_gaps(a, b):
    return seat_gaps.clean(a, 10**6) == seat_gaps.clean(b, 10**6)


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
    key, other = ('rows', 'cols') if across else ('cols', 'rows')
    gaps_key, along_gaps = ('row_gaps', 'col_gaps') if across else ('col_gaps', 'row_gaps')
    for _, _, b in at[1:]:
        if int(b[key]) != int(first[key]) or not _same_gaps(b.get(gaps_key), first.get(gaps_key)):
            if across:
                raise MergeError('Only seat blocks with the same rows can be merged side by side')
            raise MergeError('Only seat blocks with the same columns can be merged one above the other')

    gaps = list(seat_gaps.clean(first.get(along_gaps), int(first[other])))
    count = int(first[other])
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
        if space >= TOUCH:
            gaps.append({'after': count, 'size': round(max(space, seat_gaps.MIN_SIZE), 2)})
        gaps += _shift(seat_gaps.clean(b.get(along_gaps), int(b[other])), count)
        count += int(b[other])
        end = (cx + w / 2) if across else (cy + h / 2)

    # The middle of the joined block, turned back onto the plan.
    mid_along = (start + end) / 2
    mid_across = sum((p[1] if across else p[0]) for p, _, _ in at) / len(at)
    lx, ly = (mid_along, mid_across) if across else (mid_across, mid_along)
    a = math.radians(rotation)
    x, y = lx * math.cos(a) - ly * math.sin(a), lx * math.sin(a) + ly * math.cos(a)
    return {**first, other: count, along_gaps: gaps,
            'x': round(x / PLAN_SEATS_W * 100, 2), 'y': round(y / PLAN_SEATS_H * 100, 2)}
