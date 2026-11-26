"""Fill area (#1565): a box on the plan filled with runs of seats and the walkways between them.

A run is one seat block of ``rows`` rows of ``seats`` seats with a ``spacer`` between its rows (the
room for the switch, #1547). Runs go side by side and in bands, ``walkway`` seats apart; each gap
gets a walkway mark (floorbit/plan_marks.py, #1564) unless the walkway is 0. Row letters count on
band by band, left to right, so the first run is A-B, the next C-D.

Everything here is in seats; the box comes in and the blocks and marks go out in % of the plan
(a seat is 2 % wide and 3.2 % tall: 32 drawing units on 1600 x 1000, floorbit/blueprints/screen.py).
"""
import math

from . import plan_marks, seat_gaps, seat_names, seat_rows

SEAT_X, SEAT_Y = 2.0, 3.2
MAX_RUNS = 100
EPS = 1e-6


class FillError(ValueError):
    pass


def _num(body, key, default, lo, hi, error):
    try:
        n = float(body.get(key, default) if body.get(key) not in (None, '') else default)
    except (TypeError, ValueError):
        raise FillError(error) from None
    if not lo <= n <= hi:     # also false for NaN
        raise FillError(error)
    return n


def options(body):
    """The run, spacer and walkway from a request, checked. Raises FillError."""
    seats = _num(body, 'seats', 10, 1, seat_rows.MAX_SEATS, f'A row has 1 to {seat_rows.MAX_SEATS} seats')
    rows = _num(body, 'rows', 2, 1, seat_rows.MAX_ROWS, f'A run has 1 to {seat_rows.MAX_ROWS} rows')
    if seats != int(seats) or rows != int(rows):
        raise FillError('Seats and rows are whole numbers')
    most = seat_gaps.MAX_SIZE
    spacer = _num(body, 'spacer', 1, 0, most, f'The space between rows is 0 to {most} seats')
    lo, hi = plan_marks.WALKWAY_WIDTH
    walkway = _num(body, 'walkway', plan_marks.WALKWAY_DEFAULT, 0, hi, f'A walkway is 0 or {lo} to {hi} seats wide')
    if 0 < walkway < lo:
        raise FillError(f'A walkway is 0 or {lo} to {hi} seats wide')
    start = str(body.get('row_start') or 'A').upper()
    if not seat_names.LETTERS_RE.match(start):
        raise FillError('Row letters start at a letter, A to ZZ')
    return {'seats': int(seats), 'rows': int(rows), 'spacer': spacer, 'walkway': walkway,
            'labels': body.get('labels', True) is not False, 'row_start': start}


def layout(box, opts):
    """``box`` (``x``, ``y``, ``w``, ``h`` in %, its top left corner) filled: ``(blocks, walkways)``,
    each a list of request bodies for a new seat block or plan mark. Raises FillError."""
    try:
        x0, y0 = plan_marks.on_plan(box['x']) / SEAT_X, plan_marks.on_plan(box['y']) / SEAT_Y
        width, height = abs(float(box['w'])) / SEAT_X, abs(float(box['h'])) / SEAT_Y
    except (KeyError, TypeError, ValueError):
        raise FillError('Draw the area as a box with x, y, w and h') from None
    seats, rows, walk = opts['seats'], opts['rows'], opts['walkway']
    # The row letter sits one seat out at the start of each row (on the left: seat 1 comes first).
    label = 1 if opts['labels'] else 0
    run_w, run_h = seats + label, rows + opts['spacer'] * (rows - 1)
    across = math.floor((width + walk + EPS) / (run_w + walk)) if math.isfinite(width) else 0
    down = math.floor((height + walk + EPS) / (run_h + walk)) if math.isfinite(height) else 0
    if across < 1 or down < 1:
        raise FillError('The area is too small for one run of seats')
    if across * down > MAX_RUNS:
        raise FillError(f'That makes more than {MAX_RUNS} runs: draw a smaller area or make the runs longer')
    first = seat_names.letter_index(opts['row_start'])
    blocks = []
    for j in range(down):
        top = y0 + j * (run_h + walk)
        for i in range(across):
            left = x0 + i * (run_w + walk) + label
            blocks.append({
                'x': round((left + seats / 2) * SEAT_X, 3), 'y': round((top + run_h / 2) * SEAT_Y, 3),
                'cols': seats, 'rows': rows, 'spacer': opts['spacer'], 'naming': 'rows',
                'row_start': seat_names.row_letter(first + (j * across + i) * rows),
                'row_labels': 'start' if label else 'none',
            })
    walkways = []
    if walk:
        used_w, used_h = across * run_w + (across - 1) * walk, down * run_h + (down - 1) * walk
        for j in range(down - 1):
            y = y0 + (j + 1) * run_h + j * walk + walk / 2
            walkways.append(_walkway(x0, y, x0 + used_w, y, walk))
        for i in range(across - 1):
            x = x0 + (i + 1) * run_w + i * walk + walk / 2
            walkways.append(_walkway(x, y0, x, y0 + used_h, walk))
    return blocks, walkways


def _walkway(x1, y1, x2, y2, width):
    return {'kind': 'walkway', 'x': round(x1 * SEAT_X, 3), 'y': round(y1 * SEAT_Y, 3),
            'x2': round(x2 * SEAT_X, 3), 'y2': round(y2 * SEAT_Y, 3), 'width': width}
