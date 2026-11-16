"""Things on the floor plan besides switches and seats (Mike's hall plan): text labels, walls and
lines, zones, and icons for exits, toilets, the bar and the like.

Each mark is in one hall (``hall_id``) at ``x``/``y`` in percent of the plan, like a seat block:

- ``text``: ``text``, ``size`` (s, m, l), ``rotation`` (0, 90, 180, 270);
- ``icon``: ``icon`` (one of :data:`ICONS`), ``size``, ``rotation``;
- ``wall``: a line from ``x``/``y`` to ``x2``/``y2``, ``style`` solid or dashed (a wall, a fence, a door gap);
- ``zone``: a box ``w`` by ``h`` from its top left corner ``x``/``y``, with an optional ``label`` and ``color``.

They are kept in data.json under ``plan_marks``, travel in backups and templates, and are drawn on the
floor plan editor, the Seats view and the attendee hall view. The icons are Tabler's (MIT), the same set
the React app uses, so one list serves every page.
"""
import uuid

from . import halls
from .plan_icons import ICONS

KEY = 'plan_marks'
KINDS = ('text', 'icon', 'wall', 'zone')
SIZES = ('s', 'm', 'l')
ROTATIONS = (0, 90, 180, 270)
STYLES = ('solid', 'dashed')
COLORS = ('muted', 'bit', 'trace', 'warn', 'down')
TEXT_MAX, LABEL_MAX = 60, 40
MAX_MARKS = 2000

class MarkError(ValueError):
    pass


def _pct(value, what):
    try:
        n = float(value)
    except (TypeError, ValueError):
        raise MarkError(f'{what} is a number from 0 to 100') from None
    if not 0 <= n <= 100:
        raise MarkError(f'{what} is a number from 0 to 100')
    return round(n, 3)


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
           'x': _pct(m.get('x'), 'x'), 'y': _pct(m.get('y'), 'y')}
    if kind == 'text':
        text = str(m.get('text') or '').strip()
        if not text or len(text) > TEXT_MAX:
            raise MarkError(f'A label has 1 to {TEXT_MAX} characters')
        out.update(text=text, size=_pick(m.get('size'), SIZES, 'm', 'size'),
                   rotation=_pick(_int(m.get('rotation')), ROTATIONS, 0, 'rotation'))
    elif kind == 'icon':
        out.update(icon=_pick(m.get('icon'), tuple(ICONS), None, 'icon') or _missing('icon'),
                   size=_pick(m.get('size'), SIZES, 'm', 'size'),
                   rotation=_pick(_int(m.get('rotation')), ROTATIONS, 0, 'rotation'))
    elif kind == 'wall':
        out.update(x2=_pct(m.get('x2'), 'x2'), y2=_pct(m.get('y2'), 'y2'),
                   style=_pick(m.get('style'), STYLES, 'solid', 'style'))
        if (out['x'], out['y']) == (out['x2'], out['y2']):
            raise MarkError('A wall needs two different ends')
    else:
        w, h = _pct(m.get('w'), 'w'), _pct(m.get('h'), 'h')
        if not w or not h:
            raise MarkError('A zone needs a width and a height')
        label = str(m.get('label') or '').strip()
        if len(label) > LABEL_MAX:
            raise MarkError(f'A zone label has at most {LABEL_MAX} characters')
        out.update(w=w, h=h, label=label, color=_pick(m.get('color'), COLORS, 'muted', 'color'))
    return out


def _int(value):
    try:
        return int(value) % 360 if value not in (None, '') else None
    except (TypeError, ValueError):
        raise MarkError('rotation is 0, 90, 180 or 270') from None


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
    return out


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
