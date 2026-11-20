"""Dashboards: widgets on a grid, saved under a name, for the ops desk or a big screen.
See docs/dashboards.md.

A dashboard is a list of ``sections``, each with an optional ``title`` (a named, foldable section;
every section after the first draws a divider) and its ``panels``. A panel sits on a grid of
:data:`COLS` columns (``x``, ``w``) and rows (``y``, ``h``) and holds a ``node``. ``fit`` stretches the
rows so the whole dashboard fills the screen, for a wall; otherwise rows have a fixed height and the
page scrolls. Older layouts with one ``root`` node became one panel filling the first section when
their data was moved up (``upgrade``, floorbit/upgrades.py).

A node is a tree: a node is either a split (``split`` "row" puts its children side by side,
"column" stacks them; ``sizes`` are their shares in percent) or one pane. A pane is

- ``plan``: a hall (``hall``, empty for the first one), the part of it to show (``area``: the whole
  hall, a seat block by name, a zone mark by id, or a box in drawing units), a layer ``preset``
  (frontend/src/pages/plan/layers.ts PRESETS), a seat filter (``show``), how seats are numbered
  (``labels``, frontend/src/pages/plan/labels.ts) and which plan marks it draws (``marks``: ``all``
  the preset shows, ``public`` only the Overview and Safety ones, like the attendee pages, or ``none``);
- ``tile``: one data tile (``<plugin>/w/<id>``, the tiles of ``GET /api/dashboard``, Floorbit's own
  and the plugins'), drawn as a widget ``type`` (:data:`WIDGET_TYPES`; ``auto`` picks one from the
  data's shape) at a ``level`` (``auto`` picks small, medium or large from the box it gets, or one of
  ``s``, ``m``, ``l`` pinned). See frontend/src/widgets/kinds/.
- ``view``: a widget by id (frontend/src/widgets/views.ts), small unless ``expanded`` (its big size
  right on the grid, for a pane that fills a screen); unknown ids show a note;
- ``text``: your own words (``text``, the Markdown subset of frontend/src/components/Markdown.tsx),
  in a ``size`` that reads from across the hall and ``align``-ed left or centred;
- ``empty``: nothing yet.

Every pane may have a ``title``; ``hide_title`` leaves its head off for a cleaner wall.

A ``public`` dashboard opens without signing in, for a screen in the hall or the event website. It
then shows only what is safe for anyone (:func:`public_board`): plan panes with the public marks,
Floorbit's switch, seat and down-switch tiles, the "Event in numbers" widget, and texts. Other panes
say they need an account.

Kept in data.json under ``dashboards``. Panes that name something gone (a hall, a tile, a widget)
show a note on the screen instead of failing: the screen keeps running.
"""
import copy
import math
import re
import threading
import time

from .store import load_data, save_data

KEY = 'dashboards'
MAX_LAYOUTS = 30
COLS = 24
MAX_ROWS = 200
MAX_SECTIONS = 12
MAX_PANELS = 24
MAX_PANES = 40
MAX_DEPTH = 4
ID_RE = re.compile(r'^[a-z0-9][a-z0-9-]{0,31}\Z')
TILE_RE = re.compile(r'^[\w.-]{1,64}/w/[\w.-]{1,64}\Z')
REF_RE = re.compile(r'^[\w .:-]{1,120}\Z')
KINDS = ('plan', 'tile', 'view', 'text', 'empty')
# What a tile pane may calculate (issue #959); the browser does the maths on the widgets' data.
CALCS = ('count', 'sum', 'avg', 'min', 'max', 'first', 'last')
MAX_ALSO = 3
TONES = ('', 'ok', 'warn', 'err')
SORTS = ('value-desc', 'value-asc', 'name-asc', 'name-desc')
MAX_STEPS = 5
MAX_MAPPINGS = 10
KEY_RE = re.compile(r'^[\w.-]{1,64}\Z')
SPLITS = ('row', 'column')
AREAS = ('hall', 'block', 'zone', 'box')
PRESETS = ('overview', 'network', 'electrical', 'ops')
FILTERS = ('all', 'problems', 'offline', 'recent', 'note', 'checked_in')
LABELS = ('auto', 'all', 'none')
# Plan marks on a screen: "public" for one people walk past (plan_marks.PUBLIC_LAYERS only).
MARKS = ('all', 'public', 'none')
TITLE_MAX = 40
TEXT_MAX = 2000
TEXT_SIZES = ('s', 'm', 'l', 'xl')
TEXT_ALIGN = ('start', 'center')
# The generic widget types a tile is drawn as (#894); the browser draws each one (widgets/kinds/).
WIDGET_TYPES = ('auto', 'stat', 'gauge', 'status', 'list', 'table', 'bar', 'column', 'histogram', 'pie', 'graph')
LEVELS = ('auto', 's', 'm', 'l')
# How a tile with several series or segments is drawn; the first of each is the default.
LOOKS = {'stack': ('none', 'stacked', 'percent'), 'style': ('line', 'area'), 'trend': ('none', 'linear', 'average')}
# The tiles a public dashboard may show: counts and switch names, nothing about people or the crew.
PUBLIC_TILES = ('floorbit/w/switches', 'floorbit/w/seats', 'floorbit/w/down')
# The widgets a public dashboard may show: they read only public feeds (/wall.json).
PUBLIC_VIEWS = ('event-numbers',)
_lock = threading.Lock()


class LayoutError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def _plan(**over):
    return {'pane': {'kind': 'plan', 'hall': '', 'area': {'kind': 'hall'}, 'preset': 'overview', 'show': 'all',
                     'labels': 'auto', 'marks': 'all', **over}}


def _view(view, expanded=False):
    return {'pane': {'kind': 'view', 'view': view, **({'expanded': True} if expanded else {})}}


def _tile(tile, **look):
    return {'pane': {'kind': 'tile', 'tile': f'floorbit/w/{tile}', **look}}


def _at(x, y, w, h, node):
    return {'x': x, 'y': y, 'w': w, 'h': h, 'node': node}


# Ready-made dashboards, listed until someone saves their own under the same id (deleting that brings
# the ready-made one back). They are what the old one-off pages were (health, stats, traffic, ...),
# built from the same widgets anyone can put on their own dashboard.
BUILTIN = {
    # The plan on a big screen, often in a public place, so only the public marks; the switches on
    # the plan (network layer), how many switches and seats are up, and which switches are down.
    'kiosk': {'name': 'Kiosk', 'fit': True, 'public': True, 'sections': [{'panels': [
        _at(0, 0, 18, 12, _plan(preset='network', marks='public')),
        _at(18, 0, 6, 3, _tile('switches')),
        _at(18, 3, 6, 3, _tile('seats')),
        _at(18, 6, 6, 6, _tile('down')),
    ]}]},
    # The crew's start page: the numbers that matter, the hall, what is red, and how busy the network is.
    'overview': {'name': 'Overview', 'fit': False, 'sections': [{'panels': [
        _at(0, 0, 4, 3, _tile('seats')),
        _at(4, 0, 4, 3, _tile('switches')),
        _at(8, 0, 4, 3, _tile('bandwidth')),
        _at(12, 0, 4, 3, _tile('peak')),
        _at(16, 0, 4, 3, _tile('ports')),
        _at(20, 0, 4, 3, _tile('incidents')),
        _at(0, 3, 14, 9, _plan(preset='ops')),
        _at(14, 3, 10, 5, _view('health')),
        _at(14, 8, 10, 4, _tile('down')),
        _at(0, 12, 8, 8, _tile('switch_states', type='status')),
        _at(8, 12, 10, 8, _tile('traffic', type='graph', style='area')),
        _at(18, 12, 6, 8, _tile('uplinks', type='bar')),
        _at(0, 20, 8, 8, _tile('top_ports', type='bar', limit=8)),
        _at(8, 20, 8, 8, _tile('traffic_mix', type='pie')),
        _at(16, 20, 8, 8, _tile('anomalies', type='status')),
    ]}]},
    'health': {'name': 'Service health', 'fit': False, 'sections': [{'panels': [
        _at(0, 0, 24, 12, _view('health', expanded=True)),
        _at(0, 12, 12, 8, _view('services')),
        _at(12, 12, 12, 8, _view('lancache')),
    ]}]},
    'network': {'name': 'Network', 'fit': False, 'sections': [{'panels': [
        _at(0, 0, 6, 3, _tile('switches')),
        _at(6, 0, 6, 3, _tile('seats')),
        _at(12, 0, 6, 3, _tile('bandwidth')),
        _at(18, 0, 6, 3, _tile('ports')),
        _at(0, 3, 16, 9, _tile('traffic', type='graph', style='area')),
        _at(16, 3, 8, 9, _tile('down')),
        _at(0, 12, 8, 9, _tile('uplinks', type='bar')),
        _at(8, 12, 8, 9, _tile('top_ports', type='bar', limit=10)),
        _at(16, 12, 8, 9, _tile('switch_states', type='status')),
        _at(0, 21, 12, 6, _view('wifi')),
        _at(12, 21, 12, 3, _view('endpoints')),
        _at(12, 24, 12, 3, _view('network-status')),
    ]}]},
    'services': {'name': 'Services', 'fit': False, 'sections': [{'panels': [
        _at(0, 0, 24, 10, _view('services', expanded=True)),
        _at(0, 10, 12, 8, _view('health')),
        _at(12, 10, 12, 8, _view('lancache')),
    ]}]},
    'traffic': {'name': 'Traffic', 'fit': False, 'sections': [{'panels': [
        _at(0, 0, 6, 3, _tile('bandwidth')),
        _at(6, 0, 6, 3, _tile('peak')),
        _at(12, 0, 12, 6, _tile('anomalies', type='status')),
        _at(0, 3, 12, 9, _tile('traffic', type='graph', style='area')),
        _at(12, 6, 12, 6, _tile('traffic_mix', type='pie')),
        _at(0, 12, 8, 9, _tile('flow_services', type='bar', limit=10)),
        _at(8, 12, 8, 9, _tile('traffic_areas', type='bar')),
        _at(16, 12, 8, 9, _tile('top_ports', type='bar', limit=10)),
        _at(0, 21, 12, 10, _view('dns')),
        _at(12, 21, 12, 10, _view('games')),
        _at(0, 31, 24, 8, _view('speedtests')),
    ]}]},
    'power': {'name': 'Power load', 'fit': False, 'sections': [{'panels': [
        _at(0, 0, 24, 14, _view('power-load', expanded=True)),
    ]}]},
    # What the old public stats wall showed, for a screen in the hall: off until Settings > Attendee
    # pages turns on the stats wall.
    'event': {'name': 'Event in numbers', 'fit': True, 'public': True, 'sections': [{'panels': [
        _at(0, 0, 24, 12, _view('event-numbers', expanded=True)),
    ]}]},
}


def _whole(node):
    return {'x': 0, 'y': 0, 'w': COLS, 'h': 12, 'node': node}


def upgrade(layout):
    """A layout saved as one split tree, read as a grid with that tree filling the screen."""
    if 'root' not in layout or 'sections' in layout:
        return layout
    rest = {k: v for k, v in layout.items() if k != 'root'}
    return {**rest, 'fit': True, 'sections': [{'panels': [_whole(layout['root'])]}]}


def _saved(data=None):
    data = load_data() if data is None else data
    raw = data.get(KEY)
    return [x for x in raw if isinstance(x, dict)] if isinstance(raw, list) else []


def all_layouts(data=None):
    """The saved dashboards, then the ready-made ones nobody replaced (``builtin``: true)."""
    saved = _saved(data)
    taken = {x.get('id') for x in saved}
    return saved + [{'id': k, **copy.deepcopy(v), 'builtin': True} for k, v in BUILTIN.items() if k not in taken]


def get(layout_id, data=None):
    return next((x for x in all_layouts(data) if x.get('id') == layout_id), None)


MAX_LIMITED = 20   # dashboards one screen account may be limited to


def allowed_for(user):
    """The dashboard ids ``user`` is limited to (issue #702), or None when it may open every one."""
    ids = (user or {}).get('dashboards')
    return set(ids) if ids else None


def may_open(user, layout_id):
    allowed = allowed_for(user)
    return allowed is None or layout_id in allowed


def clean_limit(raw, data=None):
    """A screen account's dashboard list as sent from Settings > Users: known ids only, in order."""
    if raw is None or raw == []:
        return []
    if not isinstance(raw, list) or not all(isinstance(i, str) for i in raw):
        raise LayoutError('Send the dashboards as a list of their ids.')
    known = {layout['id'] for layout in all_layouts(data)}
    out = []
    for layout_id in raw:
        if layout_id not in known:
            raise LayoutError(f'There is no dashboard "{layout_id[:40]}".')
        if layout_id not in out:
            out.append(layout_id)
    if len(out) > MAX_LIMITED:
        raise LayoutError(f'An account can be limited to at most {MAX_LIMITED} dashboards.')
    return out


def _text(value, limit):
    return ' '.join(str(value or '').split())[:limit]


def _number(value, low, high, message):
    try:
        n = float(value)
    except (TypeError, ValueError):
        n = float('nan')
    if not low <= n <= high:   # also false for NaN
        raise LayoutError(message)
    return round(n, 2)


def _area(raw):
    if not isinstance(raw, dict) or raw.get('kind', 'hall') not in AREAS:
        raise LayoutError('An area is the whole hall, a seat block, a zone or a box.')
    kind = raw.get('kind', 'hall')
    if kind == 'hall':
        return {'kind': 'hall'}
    if kind in ('block', 'zone'):
        ref = str(raw.get('id') or '').strip()
        if not REF_RE.match(ref):
            raise LayoutError('Pick the seat block to show.' if kind == 'block' else 'Pick the zone to show.')
        return {'kind': kind, 'id': ref}
    off = 'The part of the plan to show is not on the plan.'
    box = {k: _number(raw.get(k), -100_000, 100_000, off) for k in ('x', 'y')}
    box.update({k: _number(raw.get(k), 1, 100_000, off) for k in ('w', 'h')})
    return {'kind': 'box', **box}


def _pane(raw):
    if not isinstance(raw, dict) or raw.get('kind') not in KINDS:
        raise LayoutError(f'A pane is one of: {", ".join(KINDS)}.')
    kind = raw['kind']
    pane = {'kind': kind}
    title = _text(raw.get('title'), TITLE_MAX)
    if title:
        pane['title'] = title
    if raw.get('hide_title'):
        pane['hide_title'] = True
    if kind == 'plan':
        hall = str(raw.get('hall') or '').strip()
        if hall and not REF_RE.match(hall):
            raise LayoutError('Pick a hall.')
        preset = raw.get('preset') or 'overview'
        show = raw.get('show') or 'all'
        labels = raw.get('labels') or 'auto'
        marks = raw.get('marks') or 'all'
        if preset not in PRESETS:
            raise LayoutError(f'A layer preset is one of: {", ".join(PRESETS)}.')
        if show not in FILTERS:
            raise LayoutError(f'Show is one of: {", ".join(FILTERS)}.')
        if labels not in LABELS:
            raise LayoutError(f'Seat numbers are one of: {", ".join(LABELS)}.')
        if marks not in MARKS:
            raise LayoutError(f'Plan marks are one of: {", ".join(MARKS)}.')
        pane.update(hall=hall, area=_area(raw.get('area') or {'kind': 'hall'}), preset=preset, show=show, labels=labels,
                    marks=marks)
    elif kind == 'tile':
        tile = str(raw.get('tile') or '')
        if not TILE_RE.match(tile):
            raise LayoutError('Pick a dashboard tile.')
        pane['tile'] = tile
        wtype = raw.get('type') or 'auto'
        level = raw.get('level') or 'auto'
        if wtype not in WIDGET_TYPES:
            raise LayoutError(f'A widget type is one of: {", ".join(WIDGET_TYPES)}.')
        if level not in LEVELS:
            raise LayoutError(f'A widget size is one of: {", ".join(LEVELS)}.')
        # Leave the defaults out, so a layout reads the same as before they existed.
        if wtype != 'auto':
            pane['type'] = wtype
        if level != 'auto':
            pane['level'] = level
        for key, allowed in LOOKS.items():
            value = raw.get(key) or allowed[0]
            if value not in allowed:
                raise LayoutError(f'The widget option {key} is one of: {", ".join(allowed)}.')
            if value != allowed[0]:
                pane[key] = value
        pane.update(_shaping(raw, tile))
        pane.update(_display(raw))
    elif kind == 'view':
        view = str(raw.get('view') or '')
        if not ID_RE.match(view):
            raise LayoutError('Pick a widget.')
        pane['view'] = view
        if raw.get('expanded'):
            pane['expanded'] = True
    elif kind == 'text':
        # Keep line breaks (they are the Markdown), drop other control characters.
        text = ''.join(c for c in str(raw.get('text') or '').replace('\r\n', '\n') if c == '\n' or c >= ' ').strip()
        if len(text) > TEXT_MAX:
            raise LayoutError(f'A text is at most {TEXT_MAX} characters.')
        size = raw.get('size') or 'm'
        align = raw.get('align') or 'start'
        if size not in TEXT_SIZES:
            raise LayoutError(f'A text size is one of: {", ".join(TEXT_SIZES)}.')
        if align not in TEXT_ALIGN:
            raise LayoutError(f'A text is aligned one of: {", ".join(TEXT_ALIGN)}.')
        pane.update(text=text, size=size, align=align)
    return pane


def _node(raw, depth, count):
    if not isinstance(raw, dict):
        raise LayoutError('A dashboard is made of splits and panes.')
    if 'pane' in raw:
        count[0] += 1
        if count[0] > MAX_PANES:
            raise LayoutError(f'A dashboard has at most {MAX_PANES} panes.')
        return {'pane': _pane(raw['pane'])}
    if depth >= MAX_DEPTH:
        raise LayoutError(f'Splits go at most {MAX_DEPTH} deep.')
    if raw.get('split') not in SPLITS:
        raise LayoutError('A split puts its panes side by side (row) or on top of each other (column).')
    children = raw.get('children')
    if not isinstance(children, list) or not 2 <= len(children) <= 4:
        raise LayoutError('A split has 2 to 4 parts.')
    sizes = raw.get('sizes')
    if not isinstance(sizes, list) or len(sizes) != len(children):
        sizes = [100 / len(children)] * len(children)
    message = 'Each part of a split takes 5 to 95 percent of it.'
    sizes = [_number(s, 0.01, 10_000, message) for s in sizes]
    total = sum(sizes)
    sizes = [round(s * 100 / total, 2) for s in sizes]
    if min(sizes) < 5:
        raise LayoutError(message)
    return {'split': raw['split'], 'sizes': sizes, 'children': [_node(c, depth + 1, count) for c in children]}


def _int(value, low, high, message):
    n = _number(value, low, high, message)
    if n != int(n):
        raise LayoutError(message)
    return int(n)


def _panel(raw, count):
    if not isinstance(raw, dict):
        raise LayoutError('A section is made of panels.')
    off = f'A panel sits inside the {COLS} columns of the grid.'
    x, w = _int(raw.get('x', 0), 0, COLS - 1, off), _int(raw.get('w', COLS), 1, COLS, off)
    if x + w > COLS:
        raise LayoutError(off)
    y = _int(raw.get('y', 0), 0, MAX_ROWS, f'A dashboard has at most {MAX_ROWS} rows.')
    h = _int(raw.get('h', 8), 1, 60, 'A panel is 1 to 60 rows high.')
    return {'x': x, 'y': y, 'w': w, 'h': h, 'node': _node(raw.get('node'), 0, count)}


def _overlap(a, b):
    return (a['x'] < b['x'] + b['w'] and b['x'] < a['x'] + a['w']
            and a['y'] < b['y'] + b['h'] and b['y'] < a['y'] + a['h'])


def _sections(raw, count):
    if not isinstance(raw, list) or not 1 <= len(raw) <= MAX_SECTIONS:
        raise LayoutError(f'A dashboard has 1 to {MAX_SECTIONS} sections.')
    out, panels = [], 0
    for part in raw:
        if not isinstance(part, dict) or not isinstance(part.get('panels', []), list):
            raise LayoutError('A section is made of panels.')
        items = [_panel(p, count) for p in part.get('panels', [])]
        panels += len(items)
        if panels > MAX_PANELS:
            raise LayoutError(f'A dashboard has at most {MAX_PANELS} panels.')
        if any(_overlap(a, b) for n, a in enumerate(items) for b in items[n + 1:]):
            raise LayoutError('Two panels of a section overlap.')
        section = {'panels': sorted(items, key=lambda p: (p['y'], p['x']))}
        title = _text(part.get('title'), 60)
        if title:
            section['title'] = title
        if part.get('folded'):
            section['folded'] = True
        out.append(section)
    return out


def clean(body):
    """The layout in ``body`` checked and trimmed, without id and bookkeeping."""
    name = _text(body.get('name'), 60)
    if not name:
        raise LayoutError('Give the dashboard a name.')
    count = [0]
    if 'sections' in body:
        sections = _sections(body.get('sections'), count)
    else:   # one split tree, as saved before the grid
        sections = [{'panels': [_whole(_node(body.get('root'), 0, count))]}]
    out = {'name': name, 'sections': sections, 'fit': bool(body.get('fit', 'sections' not in body)),
           'public': bool(body.get('public'))}
    # Rotate through the halls on every plan pane that shows a whole hall, like /plan?cycle=.
    if body.get('cycle'):
        out['cycle'] = int(_number(body.get('cycle'), 10, 600, 'Each hall stays 10 to 600 seconds.'))
    return out


def save(layout_id, body, by):
    layout_id = str(layout_id or '').strip().lower()
    if not ID_RE.match(layout_id):
        raise LayoutError('A dashboard id is up to 32 lower-case letters, digits or -, for example main-hall.')
    if not isinstance(body, dict):
        raise LayoutError('Send the dashboard as a JSON object.')
    layout = {'id': layout_id, **clean(body), 'updated_at': time.time(), 'by': by}
    with _lock:
        data = load_data()
        layouts = _saved(data)
        old = next((n for n, x in enumerate(layouts) if x.get('id') == layout_id), None)
        if old is None:
            if len(layouts) >= MAX_LAYOUTS:
                raise LayoutError(f'Floorbit keeps at most {MAX_LAYOUTS} dashboards.')
            layouts.append(layout)
        else:
            layouts[old] = layout
        data[KEY] = layouts
        save_data(data)
    return layout


def delete(layout_id):
    with _lock:
        data = load_data()
        layouts = _saved(data)
        kept = [x for x in layouts if x.get('id') != layout_id]
        if len(kept) == len(layouts):
            raise LayoutError('No such dashboard.', 404)
        data[KEY] = kept
        save_data(data)


def _shaping(raw, tile):
    """A tile pane's extra sources, grouping and calculations; left out when unused."""
    out = {}
    also = raw.get('also') or []
    if not isinstance(also, list) or len(also) > MAX_ALSO:
        raise LayoutError(f'A widget draws at most {MAX_ALSO} more tiles.')
    also = [str(a) for a in also]
    if any(not TILE_RE.match(a) for a in also) or tile in also or len(set(also)) != len(also):
        raise LayoutError('Pick each extra tile once, and not the first tile again.')
    if also:
        out['also'] = also
    group_by = str(raw.get('group_by') or '')
    if group_by:
        if not KEY_RE.match(group_by):
            raise LayoutError('Group by a column of the data.')
        out['group_by'] = group_by
    reduce = raw.get('reduce') or ''
    if reduce:
        if reduce not in CALCS:
            raise LayoutError(f'A calculation is one of: {", ".join(CALCS)}.')
        out['reduce'] = reduce
    legend = raw.get('legend') or []
    if not isinstance(legend, list) or any(c not in CALCS for c in legend) or len(set(legend)) != len(legend):
        raise LayoutError(f'A calculation is one of: {", ".join(CALCS)}.')
    if legend:
        out['legend'] = legend
    return out


def _num(value, what, lo=None, hi=None, whole=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise LayoutError(f'{what} must be a number.')
    if whole and (value != int(value) or not lo <= value <= hi):
        raise LayoutError(f'{what} is a whole number from {lo} to {hi}.')
    return int(value) if whole else value


def _tone(value):
    tone = value or ''
    if tone not in TONES:
        raise LayoutError(f'A colour is one of: {", ".join(t for t in TONES if t)}.')
    return tone


def _display(raw):
    """How a tile pane shows its numbers (issue #960); left out when unused."""
    out = {}
    steps = raw.get('thresholds') or []
    if not isinstance(steps, list) or len(steps) > MAX_STEPS:
        raise LayoutError(f'A widget has at most {MAX_STEPS} colour steps.')
    if steps:
        out['thresholds'] = [{'at': _num((s or {}).get('at'), 'A colour step'), 'tone': _tone((s or {}).get('tone'))}
                             for s in steps if isinstance(s, dict)]
        if len(out['thresholds']) != len(steps):
            raise LayoutError('A colour step must be a number.')
        if raw.get('threshold_mode') not in (None, '', 'value', 'percent'):
            raise LayoutError('Colour steps compare the value or the percent of the max.')
        if raw.get('threshold_mode') == 'percent':
            out['threshold_mode'] = 'percent'
    maps = raw.get('mappings') or []
    if not isinstance(maps, list) or len(maps) > MAX_MAPPINGS or not all(isinstance(m, dict) for m in maps):
        raise LayoutError(f'A widget has at most {MAX_MAPPINGS} value mappings.')
    if maps:
        out['mappings'] = []
        for m in maps:
            entry = {'text': _text(m.get('text'), 40)}
            for end in ('from', 'to'):
                if m.get(end) is not None:
                    entry[end] = _num(m[end], 'A mapped value')
            if m.get('tone'):
                entry['tone'] = _tone(m['tone'])
            out['mappings'].append(entry)
    unit = _text(raw.get('unit'), 16)
    if unit:
        out['unit'] = unit
    if raw.get('decimals') is not None:
        out['decimals'] = _num(raw['decimals'], 'Decimals', 0, 4, whole=True)
    if raw.get('short'):
        out['short'] = True
    sort = raw.get('sort') or ''
    if sort:
        if sort not in SORTS:
            raise LayoutError(f'Sort is one of: {", ".join(SORTS)}.')
        out['sort'] = sort
    if raw.get('limit') is not None:
        out['limit'] = _num(raw['limit'], 'Show at most', 1, 100, whole=True)
    if raw.get('hide_zero'):
        out['hide_zero'] = True
    return out


def pane_tiles(pane):
    """Every tile a tile pane reads."""
    return [pane['tile'], *pane.get('also', [])] if pane.get('kind') == 'tile' else []


def _public_node(node):
    if 'pane' not in node:
        return {**node, 'children': [_public_node(c) for c in node['children']]}
    pane = node['pane']
    kind = pane['kind']
    head = {k: pane[k] for k in ('title', 'hide_title') if k in pane}
    if kind == 'plan':
        return {'pane': {**pane, 'marks': 'none' if pane.get('marks') == 'none' else 'public'}}
    if kind in ('text', 'empty') or (kind == 'tile' and all(t in PUBLIC_TILES for t in pane_tiles(pane))) or (
            kind == 'view' and pane['view'] in PUBLIC_VIEWS):
        return {'pane': pane}
    return {'pane': {'kind': 'private', **head}}


def public_board(layout):
    """A public dashboard as a screen nobody signed in to gets it: crew panes become ``private``
    (the screen says they need an account), plan panes draw the public marks only."""
    sections = [{**sec, 'panels': [{**p, 'node': _public_node(p['node'])} for p in sec['panels']]}
                for sec in layout['sections']]
    head = {k: layout[k] for k in ('id', 'name', 'fit', 'cycle') if k in layout}
    return {**head, 'public': True, 'sections': sections}


def _panes(node):
    if 'pane' in node:
        yield node['pane']
    else:
        for child in node['children']:
            yield from _panes(child)


def public_panes(layout):
    """Every pane of a public dashboard, as :func:`public_board` hands them out."""
    for sec in public_board(layout)['sections']:
        for panel in sec['panels']:
            yield from _panes(panel['node'])
