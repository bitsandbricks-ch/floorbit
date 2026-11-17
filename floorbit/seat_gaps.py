"""Gaps inside a seat block (Mike: room for fiber rolls in a row, and a lane between two rows for
the switch).

A block keeps two lists, each entry ``{"after": n, "size": s}``:

- ``col_gaps``: an empty space ``s`` seats wide after column ``n`` (columns counted from the left of
  the block as drawn before it is turned, 1 = the first column). Every row of the block gets it.
- ``row_gaps``: an empty lane ``s`` seats high after row ``n`` (counted from the top).

Gaps only move seats apart: seat names and numbers carry on across them. The editor has the same
rules in static/js/editor/gaps.js.
"""

MAX_GAPS = 50      # per direction, far more than any row needs
MAX_SIZE = 20      # seats
MIN_SIZE = 0.25


class GapError(ValueError):
    pass


def clean(raw, count):
    """``raw`` as a sorted list of gaps for ``count`` columns or rows; raises GapError. Gaps after
    the last column or row are dropped, so making a block smaller never fails over them."""
    if raw in (None, ''):
        return []
    if not isinstance(raw, list) or len(raw) > MAX_GAPS:
        raise GapError(f'A block has at most {MAX_GAPS} gaps in each direction')
    merged = {}
    for gap in raw:
        try:
            after, size = int(gap['after']), float(gap['size'])
        except (KeyError, TypeError, ValueError):
            raise GapError('Each gap has "after" (a column or row number) and "size" (in seats)') from None
        if not MIN_SIZE <= size <= MAX_SIZE:   # also false for NaN
            raise GapError(f'A gap is {MIN_SIZE} to {MAX_SIZE} seats wide')
        if 1 <= after < count:
            merged[after] = round(size, 2)
    return [{'after': a, 'size': s} for a, s in sorted(merged.items())]


def offsets(gaps, count):
    """Where each of ``count`` columns (or rows) starts, in seats from the first, and the total
    length in seats."""
    extra = {}
    for gap in gaps or []:
        extra[int(gap['after'])] = extra.get(int(gap['after']), 0) + float(gap['size'])
    starts, at = [], 0.0
    for i in range(count):
        starts.append(at)
        at += 1 + (extra.get(i + 1, 0) if i < count - 1 else 0)
    return starts, at


def layout(block, cols, rows):
    """``(xs, width, ys, height)`` in seats: each column's and row's start, and the block's size."""
    xs, width = offsets(block.get('col_gaps'), cols)
    ys, height = offsets(block.get('row_gaps'), rows)
    return xs, width, ys, height
