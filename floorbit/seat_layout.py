"""Seats placed freely inside a block (Mike: the admins sit in a U round their table).

A block's seats normally stand where their rows put them (floorbit/seat_rows.py). A block can
instead keep ``seat_at``: ``{"<row id>,<seat>": [x, y]}``, each seat's top-left corner in seats, in
the block's own frame before it is turned (the seat counts from 0 along its row). Names and numbers
still come from the rows (floorbit/seat_names.py), so a seat keeps its name wherever it is moved.

Positions are kept so the seats' box starts at 0,0, and the block's x/y is that box's middle, like a
block in rows: everything that draws a block (screen.py, cable_plan.py, dispatch.py) only needs
``places``.
"""
import math

from . import seat_rows

MAX_OFFSET = 200   # seats; far beyond any hall
STEP = 0.01


class LayoutError(ValueError):
    pass


def _key(r, c):
    return f'{r},{c}'


def clean(raw, rows):
    """``raw`` as ``{"<row id>,<seat>": [x, y]}`` for a block with ``rows`` (floorbit/seat_rows.py),
    or None for seats where their rows put them. Seats the block no longer has are dropped. Raises
    LayoutError."""
    if raw in (None, '', {}):
        return None
    seats = {str(r['id']): int(r['seats']) for r in rows}
    if not isinstance(raw, dict) or len(raw) > sum(seats.values()) + 1000:
        raise LayoutError('Seat places are {"row,seat": [x, y]}')
    out = {}
    for key, at in raw.items():
        try:
            r, c = str(key).split(',')
            c = int(c)
            x, y = float(at[0]), float(at[1])
        except (TypeError, ValueError, IndexError, KeyError):
            raise LayoutError('Seat places are {"row,seat": [x, y]}') from None
        if not (math.isfinite(x) and math.isfinite(y)) or abs(x) > MAX_OFFSET or abs(y) > MAX_OFFSET:
            raise LayoutError(f'A seat is at most {MAX_OFFSET} seats from its block')
        if r in seats and 0 <= c < seats[r]:
            out[f'{r},{c}'] = [round(x, 2), round(y, 2)]
    return out or None


def places(block):
    """``({(r, c): (x, y)}, width, height)`` in seats: where each seat's top-left corner is in the
    block (``r`` the row's place in the block, ``c`` the seat's in its row), and the block's size.
    Seats on a bent row are turned too: ``angles`` says how far."""
    at, width, height = seat_rows.layout(block)
    return {rc: (x - 0.5, y - 0.5) for rc, (x, y, _) in at.items()}, width, height


def angles(block):
    """``{(r, c): degrees}``: which way each seat's row runs there (0 = left to right)."""
    at, _, _ = seat_rows.layout(block)
    return {rc: a for rc, (_, _, a) in at.items()}


def settle(block):
    """Keeps a block with its own seat places in the form ``places`` expects, in place: every seat
    has a place and the places start at 0,0. The block's x/y stays the middle of the seats' box, so
    the editor sends the new middle with the places when a seat moves out to the side (and undo puts
    both back)."""
    if not block.get('seat_at'):
        block['seat_at'] = None
        return block
    rows = seat_rows.rows_of(block)
    at, _, _ = places(block)
    block['seat_at'] = {f"{rows[r]['id']},{c}": [round(x, 2), round(y, 2)] for (r, c), (x, y) in sorted(at.items())}
    return block
