"""Things on the floor plan besides switches and seats (Mike's hall plan): text labels, walls and
lines, zones, and icons for exits, toilets, the bar and the like.

Each mark is in one hall (``hall_id``) at ``x``/``y`` in percent of the plan, like a seat block:

- ``text``: ``text``, ``size`` (s, m, l), ``rotation`` (whole degrees, 0 to 359), ``scale``;
- ``icon``: ``icon`` (one of :data:`ICONS`, or an uploaded icon's id from floorbit/icon_library.py),
  ``size``, ``rotation``, ``scale``;

``scale`` (optional, :data:`SCALE` range) stretches a label or icon beyond its size step: the editor
sets it when someone drags the corner handle. Missing means 1.
- ``wall``: a line from ``x``/``y`` to ``x2``/``y2``, ``style`` solid or dashed (a wall, a fence, a door gap),
  with optional ``points``: the bends between the ends, ``[[x, y], …]`` (up to :data:`BENDS_MAX`);
- ``zone``: a box ``w`` by ``h`` from its top left corner ``x``/``y``, with an optional ``label``, ``color``
  and ``rotation`` (turned round its middle; missing is 0).

Any mark may have a ``tint`` (``#rrggbb``): the crew's own colour for it, over the theme's. Missing
means the theme's colour, which follows light and dark.

Every mark is on a ``layer`` of the floor plan (:data:`LAYERS`, ``overview`` unless set), so the Seats view
can show the escape routes or the server racks on their own and hide them otherwise.

They are kept in data.json under ``plan_marks``, travel in backups and templates, and are drawn on the
floor plan editor, the Seats view and the attendee hall view. The icons are Tabler's (MIT), the same set
the React app uses, so one list serves every page.
"""
import re
import uuid

from . import halls, icon_library, stacking
from .plan_icons import ICONS

KEY = 'plan_marks'
KINDS = ('text', 'icon', 'wall', 'zone')
SIZES = ('s', 'm', 'l')
STYLES = ('solid', 'dashed')
BENDS_MAX = 50
COLORS = ('muted', 'bit', 'trace', 'warn', 'down')
TINT = re.compile(r'#[0-9a-fA-F]{6}')
# The Seats view's layers a mark can be on (frontend/src/pages/plan/layers.ts).
LAYERS = ('overview', 'safety', 'network', 'electrical', 'services')
PUBLIC_LAYERS = ('overview', 'safety')   # what attendee pages show; the rest is for the crew
TEXT_MAX, LABEL_MAX = 60, 40
SCALE = (0.25, 8)
MAX_MARKS = 2000

class MarkError(ValueError):
    pass


# Positions are percent of the plan box, but the plan has no edge: things may sit outside the box
# and every view fits to what is drawn. The limit only keeps out nonsense (huge numbers, inf, NaN).
PLAN_LIMIT = 10_000


def on_plan(value):
    """``value`` as a position on the plan; raises ValueError for anything that isn't one."""
    n = float(value)
    if not -PLAN_LIMIT <= n <= PLAN_LIMIT:   # also false for NaN
        raise ValueError(value)
    return n


def _pct(value, what):
    try:
        return round(on_plan(value), 3)
    except (TypeError, ValueError):
        raise MarkError(f'{what} is a number from -10000 to 10000') from None


def _pick(value, allowed, default, what):
    if value in (None, ''):
        return default
    if value not in allowed:
        raise MarkError(f'{what} is one of: {", ".join(str(a) for a in allowed)}')
    return value


def clean(body, old=None):
    """A mark from a request (or ``old`` changed by it), checked. Raises MarkError."""
    if not isinstance(body, dict):
        raise MarkError('Expected a JSON object')
    m = {**(old or {}), **{k: v for k, v in body.items() if k not in ('id', 'hall_id')}}
    kind = m.get('kind')
    if kind not in KINDS:
        raise MarkError('A mark is text, icon, wall or zone')
    out = {'id': (old or {}).get('id') or uuid.uuid4().hex[:12], 'kind': kind,
           'x': _pct(m.get('x'), 'x'), 'y': _pct(m.get('y'), 'y'),
           'layer': _pick(m.get('layer'), LAYERS, 'overview', 'layer')}
    try:
        out['z'] = stacking.z_of(m.get('z'))
    except stacking.StackError as exc:
        raise MarkError(str(exc)) from None
    tint = _tint(m.get('tint'))
    if tint:
        out['tint'] = tint
    if kind == 'text':
        text = str(m.get('text') or '').strip()
        if not text or len(text) > TEXT_MAX:
            raise MarkError(f'A label has 1 to {TEXT_MAX} characters')
        out.update(text=text, size=_pick(m.get('size'), SIZES, 'm', 'size'), rotation=_int(m.get('rotation')) or 0)
        _scale(out, m.get('scale'))
    elif kind == 'icon':
        icon = m.get('icon')
        # An uploaded icon (floorbit/icon_library.py) by id; one removed later is simply not drawn.
        if not (isinstance(icon, str) and icon_library.ID_RE.match(icon)):
            icon = _pick(icon, tuple(ICONS), None, 'icon')
        out.update(icon=icon or _missing('icon'),
                   size=_pick(m.get('size'), SIZES, 'm', 'size'), rotation=_int(m.get('rotation')) or 0)
        _scale(out, m.get('scale'))
    elif kind == 'wall':
        out.update(x2=_pct(m.get('x2'), 'x2'), y2=_pct(m.get('y2'), 'y2'),
                   style=_pick(m.get('style'), STYLES, 'solid', 'style'))
        bends = _bends(m.get('points'))
        if bends:
            out['points'] = bends
        if (out['x'], out['y']) == (out['x2'], out['y2']) and not bends:
            raise MarkError('A wall needs two different ends')
    else:
        w, h = _pct(m.get('w'), 'w'), _pct(m.get('h'), 'h')
        if not w or not h:
            raise MarkError('A zone needs a width and a height')
        label = str(m.get('label') or '').strip()
        if len(label) > LABEL_MAX:
            raise MarkError(f'A zone label has at most {LABEL_MAX} characters')
        out.update(w=w, h=h, label=label, color=_pick(m.get('color'), COLORS, 'muted', 'color'))
        # Kept only when turned, so zones drawn before rotation existed stay as they were.
        if _int(m.get('rotation')):
            out['rotation'] = _int(m.get('rotation'))
    return out


def _tint(value):
    # A colour the crew picked, over the theme's; missing or empty keeps the theme's, light or dark.
    if value in (None, ''):
        return None
    if not isinstance(value, str) or not TINT.fullmatch(value):
        raise MarkError('tint is a colour like #3fb950')
    return value.lower()


def _bends(value):
    # Empty or missing: a straight wall. Bends sitting on top of each other are one.
    if value in (None, ''):
        return []
    if not isinstance(value, list) or len(value) > BENDS_MAX:
        raise MarkError(f'A wall has at most {BENDS_MAX} bends, each [x, y]')
    out = []
    for p in value:
        if not isinstance(p, (list, tuple)) or len(p) != 2:
            raise MarkError(f'A wall has at most {BENDS_MAX} bends, each [x, y]')
        q = [_pct(p[0], 'x'), _pct(p[1], 'y')]
        if not out or out[-1] != q:
            out.append(q)
    return out


def _scale(out, value):
    # 1 is the default and isn't stored, so marks that were never resized stay as they were.
    if value in (None, ''):
        return
    try:
        n = round(float(value), 2)
        if not SCALE[0] <= n <= SCALE[1]:   # also false for NaN
            raise ValueError(value)
    except (TypeError, ValueError):
        raise MarkError('scale is a number from {} to {}'.format(*SCALE)) from None
    if n != 1:
        out['scale'] = n


def _int(value):
    # Any whole angle (the editor's rotate handle turns freely); 360 and -90 are 0 and 270.
    try:
        return round(float(value)) % 360 if value not in (None, '') else None
    except (TypeError, ValueError, OverflowError):
        raise MarkError('rotation is a whole number of degrees') from None


def _missing(what):
    raise MarkError(f'{what} is missing')


def all_marks(data, hall_id=None):
    """The marks, each with its hall written out; with ``hall_id`` only that hall's."""
    ids = {h['id'] for h in halls.halls(data)}
    out = []
    for m in data.get(KEY) or []:
        if not isinstance(m, dict):
            continue
        hall = halls.hall_of(m, data, ids)
        if hall_id is None or hall == hall_id:
            out.append({**m, 'hall_id': hall})
    return stacking.by_z(out)


def add(data, body):
    marks = data.setdefault(KEY, [])
    if len(marks) >= MAX_MARKS:
        raise MarkError(f'At most {MAX_MARKS} marks on the plan')
    try:
        hall_id = halls.check_id(data, body.get('hall_id'))
    except halls.HallError as exc:
        raise MarkError(str(exc)) from None
    mark = {**clean(body), 'hall_id': hall_id}
    marks.append(mark)
    return mark


def change(data, mark_id, body):
    for i, old in enumerate(data.get(KEY) or []):
        if old.get('id') == mark_id:
            mark = {**clean(body, old), 'hall_id': old.get('hall_id')}
            if 'hall_id' in body:
                try:
                    mark['hall_id'] = halls.check_id(data, body['hall_id'])
                except halls.HallError as exc:
                    raise MarkError(str(exc)) from None
            data[KEY][i] = mark
            return mark
    return None


def remove(data, mark_id):
    before = len(data.get(KEY) or [])
    data[KEY] = [m for m in data.get(KEY) or [] if m.get('id') != mark_id]
    return len(data[KEY]) != before
