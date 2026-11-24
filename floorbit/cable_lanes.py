"""Where a row's seat cables run and plug in (Mike, issue #1342: "If a gap is between on the gap
side, else on the other side of the chair").

A straight row's cables run in a lane along the row and plug into each seat from that side. Which
side is the row's ``cables`` (floorbit/seat_rows.py):

- ``""`` (Auto): away from the chairs. A row without chairs plugs in on the side with a gap to the
  next row (the smaller gap when both have one: a cable gap, not the aisle), or on the seam when
  the next row touches. A row on its own without chairs keeps the route along the block.
- ``behind``: away from the chairs, like Auto (a row without chairs goes by Auto).
- ``chair``: on the chair side, where the player sits.

The lane runs in the middle of the gap to the next row, on the seam when the rows touch, and half a
seat out at the block's edge. Bent rows, U and L shapes, paths and seats placed freely keep the
route along the block (floorbit/cable_plan.py): they have no one line to run along.

Everything is in seats in the block's own frame before it is turned, as ``seat_rows.layout``.
"""
import math

from . import seat_rows

EDGE = 0.5   # seats out from the block's edge, where a lane runs with no row beyond it


def _chair(row, angle):
    """-1 when the chairs are above the row in the block's frame, 1 below, 0 none."""
    side = seat_rows.side_of(row)
    if not side:
        return 0
    up = -math.cos(math.radians(angle))          # left of the way the row runs
    v = up if side == 'left' else -up
    return -1 if v < 0 else 1


def lanes(block):
    """``{(r, c): v}``: for each seat that plugs in from a lane, where the lane runs across the
    block (``v`` in seats from the block's top). Seats not in it keep the route along the block."""
    if block.get('seat_at'):
        return {}
    rows = seat_rows.rows_of(block)
    at, _, _ = seat_rows.layout(block)
    extent = []
    for r, row in enumerate(rows):
        mine = [(c, x, y, a) for (rr, c), (x, y, a) in at.items() if rr == r]
        if not mine:
            extent.append(None)
            continue
        top = min(y for _, _, y, _ in mine) - 0.5
        bottom = max(y for _, _, y, _ in mine) + 0.5
        straight = (row.get('shape') or 'line') == 'line' and all(abs(math.sin(math.radians(a))) < 1e-6
                                                                    for *_, a in mine)
        extent.append((top, bottom, straight, mine))
    out = {}
    for r, row in enumerate(rows):
        if extent[r] is None or not extent[r][2]:
            continue
        top, bottom, _, mine = extent[r]
        above = next((max(0.0, top - extent[i][1]) for i in range(r - 1, -1, -1) if extent[i]), None)
        below = next((max(0.0, extent[i][0] - bottom) for i in range(r + 1, len(rows)) if extent[i]), None)
        chair = _chair(row, mine[0][3])
        mode = row.get('cables') or ''
        if chair:
            side = chair if mode == 'chair' else -chair
        else:
            near = [(g, s) for g, s in ((above, -1), (below, 1)) if g is not None]
            if not near:
                continue
            # A gap beats a seam, and a small gap (for cables) beats a wide one (the aisle).
            side = min(near, key=lambda n: (n[0] == 0, n[0]))[1]
        gap = above if side < 0 else below
        edge = top if side < 0 else bottom
        v = edge + side * (EDGE if gap is None else gap / 2)
        for c, *_ in mine:
            out[r, c] = round(v, 4)
    return out
