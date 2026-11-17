"""Big-screen rotation and the "find your seat" page (issue #18). See docs/kiosk.md.

- ``GET /screen``: rotates through views on a timer (``?views=floor,heat,stats,health&every=30``,
  ``&hall=<id>`` for the floor plan views of another hall than the first),
  with a QR code to ``/find`` in the corner. Needs ``floorplan.view`` like ``/kiosk``.
- ``GET /find``: for players' phones, no account: type a seat number, see where it is in the hall.
  Finding by nick is off unless ``SEAT_FINDER_NICKS`` is on, and then only an exact nick finds a
  seat. ``SEAT_FINDER=false`` turns the page off.
"""
import re
import time
from threading import Lock

import segno
from flask import Blueprint, abort, current_app, render_template, request, url_for

from integrations import checkin, config, seat_sources

from .. import halls, plan_marks, seat_gaps
from ..seat_names import block_rows, row_letters, seat_one_first
from ..store import load_data

bp = Blueprint('screen', __name__)

VIEWS = {'floor': '/kiosk', 'heat': '/kiosk?view=heat', 'stats': '/stats?screen=1', 'health': '/health?screen=1'}
DEFAULT_VIEWS = ('floor', 'heat', 'stats')
# Block positions are percentages of the floor plan; the find page draws them on a canvas this big,
# with seats a bit larger than the editor's so they are easy to tap and see on a phone.
PLAN_W, PLAN_H, CELL = 1600, 1000, 32
RATE_LIMIT, RATE_WINDOW = 30, 60       # lookups per address and minute
_lookups, _lookups_lock = {}, Lock()

TEXTS = {
    'en': {'title': 'Find your seat', 'intro': 'Type the seat number from your ticket, for example D-17.',
           'intro_nick': 'Type your seat number (for example D-17) or your nick.', 'label': 'Seat',
           'label_nick': 'Seat or nick', 'go': 'Find', 'found': 'Seat {seat}',
           'where': 'Block {block}, row {row} of {rows}, seat {col} from the left as seen on the plan.',
           'none': 'No seat "{query}" on the floor plan. Check the number on your ticket, or ask at the info desk.',
           'busy': 'Too many searches from here. Please wait a minute.', 'off': 'The seat finder is switched off.',
           'map': 'Hall plan with seat {seat} marked'},
    'de': {'title': 'Finde deinen Platz', 'intro': 'Gib die Platznummer von deinem Ticket ein, zum Beispiel D-17.',
           'intro_nick': 'Gib deine Platznummer (zum Beispiel D-17) oder deinen Nick ein.', 'label': 'Platz',
           'label_nick': 'Platz oder Nick', 'go': 'Finden', 'found': 'Platz {seat}',
           'where': 'Block {block}, Reihe {row} von {rows}, Platz {col} von links, wie auf dem Plan.',
           'none': 'Kein Platz "{query}" auf dem Hallenplan. Prüfe die Nummer auf deinem Ticket oder frag am Infodesk.',
           'busy': 'Zu viele Suchen von hier. Warte bitte eine Minute.', 'off': 'Die Platzsuche ist ausgeschaltet.',
           'map': 'Hallenplan mit markiertem Platz {seat}'},
}


def finder_on():
    return config.get_bool('SEAT_FINDER', True)


def _texts():
    lang = request.accept_languages.best_match(['en', 'de'], default='en')
    return lang, TEXTS[lang]


def _rate_limited():
    ip = checkin.client_ip() or '?'   # per attendee behind a trusted proxy, not per proxy
    now = time.time()
    with _lookups_lock:
        recent = [t for t in _lookups.get(ip, []) if now - t < RATE_WINDOW]
        _lookups[ip] = [*recent, now]
        if len(_lookups) > 10000:
            for key in [k for k, v in _lookups.items() if not v or now - v[-1] > RATE_WINDOW]:
                _lookups.pop(key, None)
        return len(recent) >= RATE_LIMIT


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
    for block in data.get('seat_blocks') or []:
        if halls.hall_of(block, data, ids) != hall_id:
            continue
        rows = block_rows(block)
        if not rows or block.get('x') is None:
            continue
        cols, nrows = len(rows[0]), len(rows)
        cx, cy = float(block['x']) / 100 * PLAN_W, float(block['y']) / 100 * PLAN_H
        xs, width, ys, height = seat_gaps.layout(block, cols, nrows)
        w, h = width * CELL, height * CELL
        cells = []
        for r, row in enumerate(rows):
            for c, seat in enumerate(row):
                hit = seat == highlight
                if hit:
                    found = {'seat': seat, 'block': block.get('name') or '', 'row': r + 1, 'rows': nrows,
                             'col': c + 1}
                cells.append({'x': xs[c] * CELL - w / 2, 'y': ys[r] * CELL - h / 2, 'hit': hit, 'seat': seat,
                              'on': None if online is None else seat in online})
        reach = max(w, h) / 2 + CELL * 2   # the row letters sit one cell out
        xs += [cx - reach, cx + reach]
        ys += [cy - reach - 40, cy + reach]   # room for the block's name above it
        shapes.append({'cx': cx, 'cy': cy, 'rotation': int(block.get('rotation') or 0) % 360, 'w': w, 'h': h,
                       'name': block.get('name') or '', 'cells': cells, 'rows': _row_labels(block, w, h, ys)})
    if not shapes:
        return None, None
    marks, icons = _marks(data, hall_id, xs, ys, public)
    box = (min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))
    return {'shapes': shapes, 'box': ' '.join(f'{v:.0f}' for v in box), 'cell': CELL,
            'marks': marks, 'icons': icons}, found


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
            xs += [d['x'], d['x2']]
            ys += [d['y'], d['y2']]
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
    return out, {k: plan_marks.ICONS[k] for k in sorted(used) if k in plan_marks.ICONS}


def _by_nick(query):
    q = query.strip().lower()
    for seat, info in (seat_sources.load() or {}).items():
        if str((info or {}).get('username') or '').strip().lower() == q:
            return seat
    return None


def _locate(data, seat):
    """The drawing of the hall the seat is in, and where in it; with more than one hall, its name too."""
    all_halls = halls.halls(data)
    for hall in all_halls:
        drawing, found = plan(data, seat, hall_id=hall['id'], public=True)
        if found:
            found['hall'] = hall['name'] if len(all_halls) > 1 else ''
            return drawing, found
    return None, None


@bp.route('/find')
def find_page():
    lang, text = _texts()
    if not finder_on():
        return render_template('find.html', lang=lang, t=text, state='off'), 404
    nicks = config.get_bool('SEAT_FINDER_NICKS', False)
    query = (request.args.get('q') or '').strip()[:60]
    if not query:
        return render_template('find.html', lang=lang, t=text, state='ask', nicks=nicks, query='')
    if _rate_limited():
        return render_template('find.html', lang=lang, t=text, state='busy', nicks=nicks, query=query), 429
    data = load_data()
    drawing, found = _locate(data, query.upper())
    if not found and nicks:
        by_nick = _by_nick(query)
        if by_nick:
            drawing, found = _locate(data, by_nick)
    if not found:
        return render_template('find.html', lang=lang, t=text, state='none', nicks=nicks, query=query), 404
    return render_template('find.html', lang=lang, t=text, state='found', nicks=nicks, query=query,
                           found=found, drawing=drawing)


find_page._auth_public = True   # what auth.public_endpoint sets: players' phones have no account


def _find_url():
    base = (current_app.extensions['auth'].public_url() or '').rstrip('/')
    return base + url_for('screen.find_page') if base else url_for('screen.find_page', _external=True)


@bp.route('/screen')
def screen_page():
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
        if hall and url.startswith('/kiosk'):
            url += ('&' if '?' in url else '?') + 'hall=' + hall
        if theme:
            url += ('&' if '?' in url else '?') + 'theme=' + theme
        urls.append({'id': v, 'url': url})
    qr = None
    if finder_on() and request.args.get('qr') != '0':
        link = _find_url()
        qr = {'url': link, 'image': segno.make(link, error='m').svg_data_uri(scale=6, border=2)}
    if not urls:
        abort(404)
    return render_template('screen.html', views=urls, every=every, qr=qr)
