"""Big-screen rotation (issue #18) and the hall drawing other pages use. See docs/kiosk.md.

- ``GET /screen``: rotates through views on a timer (``?views=floor,heat,stats,health&every=30``,
  ``&hall=<id>`` for the floor plan views of another hall than the first).
  Needs ``floorplan.view`` like the Kiosk dashboard.
  The page is React; ``GET /api/screen`` with the same query string says what it shows.
"""
import re

from flask import Blueprint, jsonify, request

from .. import halls, icon_library, plan_marks, seat_gaps, seat_layout, spa, stacking
from ..seat_names import block_rows, row_letters, seat_one_first

bp = Blueprint('screen', __name__)

# floor and heat show a hall: ?hall= picks which.
VIEWS = {'floor': '/dashboards/kiosk', 'heat': '/plan?screen=1&layers=marks%2Cstatus',
         'stats': '/stats?screen=1', 'health': '/health?screen=1'}
DEFAULT_VIEWS = ('floor', 'heat', 'stats')
# Block positions are percentages of the floor plan; the public pages draw them on a canvas this
# big, with seats a bit larger than the editor's so they are easy to see on a phone.
PLAN_W, PLAN_H, CELL = 1600, 1000, 32


def _row_labels(block, w, h, ys):
    """Where each row's letter goes, in the block's own coordinates (centre of the letter):
    beside seat 1 for "start", past the last seat for "end" (floorbit/seat_names.py)."""
    letters = row_letters(block)
    where = block.get('row_labels') or 'start'
    if not letters or where == 'none':
        return []
    first_side = -w / 2 - CELL / 2
    last_side = w / 2 + CELL / 2
    one_first = seat_one_first(block)
    sides = {'start': [first_side if one_first else last_side], 'end': [last_side if one_first else first_side],
             'both': [first_side, last_side]}[where]
    return [{'text': letter, 'x': x, 'y': ys[r] * CELL - h / 2 + CELL / 2}
            for r, letter in enumerate(letters) for x in sides]


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
        cols, nrows = len(rows[0]), len(rows)
        cx, cy = float(block['x']) / 100 * PLAN_W, float(block['y']) / 100 * PLAN_H
        # Seat offsets inside the block; not ``xs``/``ys``, which collect the hall's extent.
        at, width, height = seat_layout.places(block, cols, nrows)
        _, _, row_at, _ = seat_gaps.layout(block, cols, nrows)
        w, h = width * CELL, height * CELL
        cells = []
        for r, row in enumerate(rows):
            for c, seat in enumerate(row):
                hit = seat == highlight
                if hit:
                    found = {'seat': seat, 'block': block.get('name') or '', 'row': r + 1, 'rows': nrows,
                             'col': c + 1}
                x, y = at[r, c]
                cells.append({'x': x * CELL - w / 2, 'y': y * CELL - h / 2, 'hit': hit, 'seat': seat,
                              'on': None if online is None else seat in online, 'rc': [r, c]})
        reach = max(w, h) / 2 + CELL * 2   # the row letters sit one cell out
        xs += [cx - reach, cx + reach]
        ys += [cy - reach - 40, cy + reach]   # room for the block's name above it
        shapes.append({'id': block.get('id'),
                       'cx': cx, 'cy': cy, 'rotation': int(block.get('rotation') or 0) % 360, 'w': w, 'h': h,
                       'name': block.get('name') or '', 'cells': cells,
                       # Row letters belong to rows; seats placed freely have none to stand by.
                       'rows': [] if block.get('seat_at') else _row_labels(block, w, h, row_at),
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


@bp.route('/screen')
def screen_page():
    """The page is React (frontend/src/pages/BigScreen.tsx), asking /api/screen what to show."""
    html, status = spa.render('Big screen')
    return html, status


@bp.route('/api/screen')
def screen_setup():
    """What /screen rotates through, for the same query string: ``views``, ``every`` (seconds, at
    least 10), ``theme`` and ``hall``. Unknown views are dropped; none left means the
    default views."""
    wanted = [v.strip() for v in (request.args.get('views') or ','.join(DEFAULT_VIEWS)).split(',')]
    views = [v for v in wanted if v in VIEWS] or list(DEFAULT_VIEWS)
    try:
        every = min(600, max(10, int(request.args.get('every') or 30)))
    except ValueError:
        every = 30
    theme = request.args.get('theme') or ''
    theme = theme if re.fullmatch(r'[a-z0-9-]{1,30}', theme) else ''
    hall = request.args.get('hall') or ''
    hall = hall if re.fullmatch(r'[\w-]{1,40}', hall) else ''
    urls = []
    for v in views:
        url = VIEWS[v]
        if hall and v in ('floor', 'heat'):
            url += ('&' if '?' in url else '?') + 'hall=' + hall
        if theme:
            url += ('&' if '?' in url else '?') + 'theme=' + theme
        urls.append({'id': v, 'url': url})
    return jsonify({'views': urls, 'every': every})
