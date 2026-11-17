"""Seats placed freely inside a block (Mike: the admins sit in a U round their table).

A block's seats normally stand in rows and columns, with gaps (floorbit/seat_gaps.py). A block can
instead keep ``seat_at``: ``{"<row>,<col>": [x, y]}``, each seat's top-left corner in seats, in the
block's own frame before it is turned (row and column count from 0, as drawn from the top left).
Names and numbers still come from the rows and columns (floorbit/seat_names.py), so a seat keeps its
name wherever it is moved.

Positions are kept so the seats' box starts at 0,0, and the block's x/y is that box's middle, like a
block in rows: everything that draws a block (screen.py, cable_plan.py, dispatch.py) only needs
``places``.
"""
import math

from . import seat_gaps

MAX_OFFSET = 200   # seats; far beyond any hall
STEP = 0.01


class LayoutError(ValueError):
    pass


def _key(r, c):
    return f'{r},{c}'


def clean(raw, cols, rows):
    """``raw`` as ``{"r,c": [x, y]}`` for a block of ``cols`` by ``rows``, or None for rows and
    columns. Seats beyond the block (after it got smaller) are dropped. Raises LayoutError."""
    if raw in (None, '', {}):
        return None
    if not isinstance(raw, dict) or len(raw) > cols * rows + 1000:
        raise LayoutError('Seat places are {"row,column": [x, y]}')
    out = {}
    for key, at in raw.items():
        try:
            r, c = (int(v) for v in str(key).split(','))
            x, y = float(at[0]), float(at[1])
        except (TypeError, ValueError, IndexError, KeyError):
            raise LayoutError('Seat places are {"row,column": [x, y]}') from None
        if not (math.isfinite(x) and math.isfinite(y)) or abs(x) > MAX_OFFSET or abs(y) > MAX_OFFSET:
            raise LayoutError(f'A seat is at most {MAX_OFFSET} seats from its block')
        if 0 <= r < rows and 0 <= c < cols:
            out[_key(r, c)] = [round(x, 2), round(y, 2)]
    return out or None


def places(block, cols, rows):
    """``({(r, c): (x, y)}, width, height)`` in seats: where each seat's top-left corner is in the
    block, and the block's size. Seats without a place of their own stand where rows put them."""
    xs, width, ys, height = seat_gaps.layout(block, cols, rows)
    grid = {(r, c): (xs[c], ys[r]) for r in range(rows) for c in range(cols)}
    custom = block.get('seat_at') or {}
    if not custom:
        return grid, width, height
    at = {rc: tuple(custom.get(_key(*rc), p)) for rc, p in grid.items()}
    left, top = min(p[0] for p in at.values()), min(p[1] for p in at.values())
    right, bottom = max(p[0] for p in at.values()) + 1, max(p[1] for p in at.values()) + 1
    return {rc: (x - left, y - top) for rc, (x, y) in at.items()}, right - left, bottom - top


def settle(block):
    """Keeps a block with its own seat places in the form ``places`` expects, in place: the places
    start at 0,0. The block's x/y stays the middle of the seats' box, so the editor sends the new
    middle with the places when a seat moves out to the side (and undo puts both back)."""
    custom = block.get('seat_at')
    if not custom:
        block['seat_at'] = None
        return block
    at, _, _ = places({**block, 'seat_at': custom}, int(block['cols']), int(block['rows']))
    block['seat_at'] = {_key(r, c): [round(x, 2), round(y, 2)] for (r, c), (x, y) in sorted(at.items())}
    return block
