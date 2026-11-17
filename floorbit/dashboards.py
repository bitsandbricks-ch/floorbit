"""Dashboards: widgets on a grid, saved under a name, for the ops desk or a big screen.
See docs/dashboards.md.

A dashboard is a list of ``sections``, each with an optional ``title`` (a named, foldable section;
every section after the first draws a divider) and its ``panels``. A panel sits on a grid of
:data:`COLS` columns (``x``, ``w``) and rows (``y``, ``h``) and holds a ``node``. ``fit`` stretches the
rows so the whole dashboard fills the screen, for a wall; otherwise rows have a fixed height and the
page scrolls. Older layouts with one ``root`` node are read as one panel filling the first section.

A node is a tree: a node is either a split (``split`` "row" puts its children side by side,
"column" stacks them; ``sizes`` are their shares in percent) or one pane. A pane is

- ``plan``: a hall (``hall``, empty for the first one), the part of it to show (``area``: the whole
  hall, a seat block by name, a zone mark by id, or a box in drawing units), a layer ``preset``
  (frontend/src/pages/plan/layers.ts PRESETS), a seat filter (``show``) and how seats are numbered
  (``labels``, frontend/src/pages/plan/labels.ts);
- ``tile``: one dashboard plugin tile (``<plugin>/w/<id>``, floorbit/dashboard_layouts.py);
- ``dashboard``: a saved dashboard layout, by id;
- ``page``: one of the other big-screen pages (:data:`PAGES`);
- ``view``: a rich widget by id (frontend/src/widgets/views.ts); unknown ids show a note;
- ``text``: your own words (``text``, the Markdown subset of frontend/src/components/Markdown.tsx),
  in a ``size`` that reads from across the hall and ``align``-ed left or centred;
- ``empty``: nothing yet.

Every pane may have a ``title``; ``hide_title`` leaves its head off for a cleaner wall.

Kept in data.json under ``dashboards``. Panes that name something gone (a hall, a tile, a
dashboard layout) show a note on the screen instead of failing: the screen keeps running.
"""
import copy
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
ID_RE = re.compile(r'^[a-z0-9][a-z0-9-]{0,31}$')
TILE_RE = re.compile(r'^[\w.-]{1,64}/w/[\w.-]{1,64}$')
REF_RE = re.compile(r'^[\w .:-]{1,120}$')
KINDS = ('plan', 'tile', 'dashboard', 'page', 'view', 'text', 'empty')
SPLITS = ('row', 'column')
AREAS = ('hall', 'block', 'zone', 'box')
PRESETS = ('overview', 'network', 'electrical', 'ops')
FILTERS = ('all', 'problems', 'offline', 'recent', 'note', 'checked_in')
LABELS = ('auto', 'all', 'none')
# The big-screen pages a pane can hold (each one's ``?screen=1`` version).
PAGES = {'health': '/health?screen=1', 'stats': '/stats?screen=1', 'wall': '/wall?screen=1', 'status': '/status'}
TITLE_MAX = 40
TEXT_MAX = 2000
TEXT_SIZES = ('s', 'm', 'l', 'xl')
TEXT_ALIGN = ('start', 'center')
_lock = threading.Lock()


class LayoutError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def _plan(**over):
    return {'pane': {'kind': 'plan', 'hall': '', 'area': {'kind': 'hall'}, 'preset': 'overview', 'show': 'all',
                     'labels': 'auto', **over}}


# Ready-made dashboards, listed until someone saves their own under the same id (deleting that brings
# the ready-made one back). The kiosk: the plan on a big screen, with what's down beside it.
BUILTIN = {
    'kiosk': {'name': 'Kiosk', 'fit': True, 'sections': [{'panels': [
        {'x': 0, 'y': 0, 'w': 18, 'h': 12, 'node': _plan()},
        {'x': 18, 'y': 0, 'w': 6, 'h': 5, 'node': {'pane': {'kind': 'tile', 'tile': 'floorbit/w/switches'}}},
        {'x': 18, 'y': 5, 'w': 6, 'h': 7, 'node': {'pane': {'kind': 'tile', 'tile': 'floorbit/w/problems'}}},
    ]}]},
}


def _whole(node):
    return {'x': 0, 'y': 0, 'w': COLS, 'h': 12, 'node': node}


def _upgrade(layout):
    """A layout saved as one split tree, read as a grid with that tree filling the screen."""
    if 'root' not in layout or 'sections' in layout:
        return layout
    rest = {k: v for k, v in layout.items() if k != 'root'}
    return {**rest, 'fit': True, 'sections': [{'panels': [_whole(layout['root'])]}]}


def _saved(data=None):
    data = load_data() if data is None else data
    raw = data.get(KEY)
    return [_upgrade(x) for x in raw if isinstance(x, dict)] if isinstance(raw, list) else []


def all_layouts(data=None):
    """The saved dashboards, then the ready-made ones nobody replaced (``builtin``: true)."""
    saved = _saved(data)
    taken = {x.get('id') for x in saved}
    return saved + [{'id': k, **copy.deepcopy(v), 'builtin': True} for k, v in BUILTIN.items() if k not in taken]


def get(layout_id, data=None):
    return next((x for x in all_layouts(data) if x.get('id') == layout_id), None)


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
        if preset not in PRESETS:
            raise LayoutError(f'A layer preset is one of: {", ".join(PRESETS)}.')
        if show not in FILTERS:
            raise LayoutError(f'Show is one of: {", ".join(FILTERS)}.')
        if labels not in LABELS:
            raise LayoutError(f'Seat numbers are one of: {", ".join(LABELS)}.')
        pane.update(hall=hall, area=_area(raw.get('area') or {'kind': 'hall'}), preset=preset, show=show, labels=labels)
    elif kind == 'tile':
        tile = str(raw.get('tile') or '')
        if not TILE_RE.match(tile):
            raise LayoutError('Pick a dashboard tile.')
        pane['tile'] = tile
    elif kind == 'dashboard':
        layout = str(raw.get('layout') or '')
        if not ID_RE.match(layout):
            raise LayoutError('Pick a dashboard layout.')
        pane['layout'] = layout
    elif kind == 'view':
        view = str(raw.get('view') or '')
        if not ID_RE.match(view):
            raise LayoutError('Pick a widget.')
        pane['view'] = view
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
    elif kind == 'page':
        if raw.get('page') not in PAGES:
            raise LayoutError(f'A page is one of: {", ".join(PAGES)}.')
        pane['page'] = raw['page']
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
    out = {'name': name, 'sections': sections, 'fit': bool(body.get('fit', 'sections' not in body))}
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
