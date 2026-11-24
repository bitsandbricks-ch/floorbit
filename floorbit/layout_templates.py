"""The floor plan template library (issue #48): a layout saved as it is, to start from later.

A template is a snapshot of the floor plan, of every hall or of one: the halls with their background
images, where the switches are, and the seat blocks. Never event data: no check-ins, nicks, IPs, MACs,
serials, secrets or accounts. A snapshot only ever copies the fields listed here, and an imported
file is cut down to them too (what was dropped is reported), so a shared template can't carry them.

Each template is a JSON file in ``layout-templates/`` next to data.json (images make them too big for
data.json, which is read on every request), with its last ``MAX_VERSIONS`` versions.

Starting from a template replaces the floor plan, or one hall's, like restoring a backup. Switches
are matched to the inventory by name: a known one is placed where the template has it, an unknown
one is added by hand. Switches the template doesn't have are taken off the plan, not deleted.
"""
import os
import re
import time
import uuid

from . import halls, inventory, plan_marks, seat_layout, seat_rows, store

FORMAT = 'floorbit-template'
FORMAT_VERSION = 1
MAX_VERSIONS = 10
MAX_TEMPLATES = 200
NAME_MAX, DESCRIPTION_MAX = 80, 500
BLOCK_KEYS = ('name', 'x', 'y', 'rows', 'seat_width', 'seat_height', 'spacing_x', 'spacing_y',
              'rotation', 'reverse_numbers', 'naming', 'row_start', 'row_labels', 'seat_at', 'hall_id')
# What templates saved before blocks had rows (floorbit/seat_rows.py from_grid moves them).
GRID_KEYS = ('cols', 'col_gaps', 'row_gaps')
SWITCH_KEYS = ('name', 'role', 'model', 'x', 'y', 'hall_id')
_ID = re.compile(r'[a-f0-9]{12}')


class TemplateError(ValueError):
    """Raised with one of the fixed messages below. The API answers with ``public(exc)``, never with the
    exception's own text, so no detail of a failure reaches the answer."""


NO_HALL = 'That hall does not exist'
UNKNOWN_NAMING = 'A seat block has a naming that Floorbit does not know'
NOT_A_NUMBER = 'The template has a value that is not a number'
OUT_OF_RANGE = 'The template has a value that is out of range'
BAD_ROWS = 'A seat block in the template has rows that are not valid'
NO_LAYOUT = 'The template has no layout'
HALL_COUNT = f'A template has 1 to {halls.MAX_HALLS} halls'
HALL_NOT_OBJECT = 'A hall is not an object'
BAD_HALL_ID = 'A hall id is not valid or used twice'
BAD_HALL = 'A hall in the template is not valid'
BLOCK_NOT_OBJECT = 'A seat block is not an object'
BLOCK_TWICE = 'A seat block name is in the template twice'
SWITCH_NOT_OBJECT = 'A switch is not an object'
SWITCH_NO_NAME = 'A switch has no name'
BAD_MARK = 'A mark on the plan is not valid'
NEEDS_NAME = 'A template needs a name'
TOO_MANY = f'At most {MAX_TEMPLATES} templates'
NO_VERSION = 'This version of the template does not exist'
NOT_A_TEMPLATE = 'This is not a Floorbit template file'
UNSUPPORTED = 'This template format is not supported'
ONE_HALL_ONLY = 'Only a template of one hall can go into one hall'
NAME_CLASH = 'Another hall already has seat blocks with these names'
_MESSAGES = {m: m for m in (NO_HALL, UNKNOWN_NAMING, NOT_A_NUMBER, OUT_OF_RANGE, BAD_ROWS, NO_LAYOUT, HALL_COUNT,
                            HALL_NOT_OBJECT, BAD_HALL_ID, BAD_HALL, BLOCK_NOT_OBJECT, BLOCK_TWICE, SWITCH_NOT_OBJECT,
                            SWITCH_NO_NAME, BAD_MARK, NEEDS_NAME, TOO_MANY, NO_VERSION, NOT_A_TEMPLATE, UNSUPPORTED,
                            ONE_HALL_ONLY, NAME_CLASH)}


def public(exc):
    """The answer for ``exc``: its fixed message, looked up rather than read from the exception."""
    return _MESSAGES.get(exc.args[0] if exc.args else None, 'The template is not valid')


# ── Snapshots ────────────────────────────────────────────────────────────────────────────

def snapshot(data, hall_id=None):
    """The layout of every hall, or of one, with nothing but layout in it."""
    chosen = [h for h in halls.halls(data) if hall_id is None or h['id'] == hall_id]
    if not chosen:
        raise TemplateError(NO_HALL)
    ids = {h['id'] for h in halls.halls(data)}
    wanted = {h['id'] for h in chosen}
    blocks = [{k: b.get(k) for k in BLOCK_KEYS if k != 'hall_id'} | {'hall_id': halls.hall_of(b, data, ids)}
              for b in data.get('seat_blocks') or [] if halls.hall_of(b, data, ids) in wanted]
    switches = [{k: d.get(k) for k in SWITCH_KEYS if k != 'hall_id'} | {'hall_id': halls.hall_of(d, data, ids)}
                for d in inventory.devices(data) if d.get('x') is not None and halls.hall_of(d, data, ids) in wanted]
    marks = [{k: v for k, v in m.items() if k != 'id'} for m in plan_marks.all_marks(data) if m['hall_id'] in wanted]
    return {
        'halls': [{'id': h['id'], 'name': h['name'], 'background': halls.background_data_url(h), **_placing(h)}
                  for h in chosen],
        'switches': switches,
        'seat_blocks': blocks,
        'plan_marks': marks,
    }


def _placing(h):
    """Where a hall's background sits and the hall's scale, the parts that are set."""
    bg = h.get('background') or {}
    found = {'frame': bg.get('frame'), 'opacity': bg.get('opacity'), 'seat_m': h.get('seat_m')}
    return {k: v for k, v in found.items() if v is not None}


def _put_placing(hall, h):
    """Puts a template hall's background placement and scale on ``hall`` (checked by halls.py)."""
    halls.set_scale(hall, h.get('seat_m'))
    if hall.get('background'):
        halls.place_background(hall, {k: h[k] for k in ('frame', 'opacity') if h.get(k) is not None})


def _naming(b, what):
    """A template block's naming fields (floorbit/seat_names.py), checked."""
    from . import seat_names
    naming = b.get('naming') or 'block'
    start = str(b.get('row_start') or 'A').upper()
    labels = b.get('row_labels') or 'start'
    known = naming in seat_names.NAMINGS and labels in seat_names.ROW_LABELS
    if not known or not seat_names.LETTERS_RE.match(start):
        raise TemplateError(UNKNOWN_NAMING)
    return {'naming': naming, 'row_start': start, 'row_labels': labels}


def _num(value, lo, hi, what, cast=float):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TemplateError(NOT_A_NUMBER)
    value = cast(value)
    if not lo <= value <= hi:
        raise TemplateError(OUT_OF_RANGE)
    return value


def _places(b, what):
    """A block's rows and freely placed seats (floorbit/seat_rows.py, seat_layout.py), checked. A
    template saved before blocks had rows is read as its grid."""
    b = seat_rows.from_grid(dict(b))
    try:
        rows = seat_rows.clean(b.get('rows'))
        return {'rows': rows, 'seat_at': seat_layout.clean(b.get('seat_at'), rows)}
    except (seat_rows.RowError, seat_layout.LayoutError):
        raise TemplateError(BAD_ROWS) from None


def clean_layout(layout):
    """A layout from a file, cut down to the template fields and checked. Returns (layout, dropped),
    ``dropped`` the names of the fields that were taken out."""
    if not isinstance(layout, dict):
        raise TemplateError(NO_LAYOUT)
    dropped = set(layout) - {'halls', 'switches', 'seat_blocks', 'plan_marks'}
    raw_halls = layout.get('halls')
    if not isinstance(raw_halls, list) or not raw_halls or len(raw_halls) > halls.MAX_HALLS:
        raise TemplateError(HALL_COUNT)
    out_halls, ids = [], set()
    for h in raw_halls:
        if not isinstance(h, dict):
            raise TemplateError(HALL_NOT_OBJECT)
        dropped |= set(h) - {'id', 'name', 'background', 'frame', 'opacity', 'seat_m'}
        hid = str(h.get('id') or '')[:40]
        if not re.fullmatch(r'[\w-]{1,40}', hid) or hid in ids:
            raise TemplateError(BAD_HALL_ID)
        ids.add(hid)
        try:
            if h.get('background'):
                halls.decode_image(h['background'])
            placing = {k: h[k] for k in ('frame', 'opacity', 'seat_m') if h.get(k) is not None}
            _put_placing({'background': {'stand-in': True}}, placing)   # checked now, put on when applied
            out_halls.append({'id': hid, 'name': halls.clean_name(h.get('name')),
                              'background': h.get('background') or None, **placing})
        except halls.HallError:
            raise TemplateError(BAD_HALL) from None

    blocks, names = [], set()
    for b in layout.get('seat_blocks') or []:
        if not isinstance(b, dict):
            raise TemplateError(BLOCK_NOT_OBJECT)
        dropped |= set(b) - set(BLOCK_KEYS) - set(GRID_KEYS)
        name = str(b.get('name') or '')[:40]
        if name.upper() in names:
            raise TemplateError(BLOCK_TWICE)
        names.add(name.upper())
        what = f'Block "{name}"'
        blocks.append({
            'name': name,
            'x': _num(b.get('x'), 0, 100, f'{what} x'), 'y': _num(b.get('y'), 0, 100, f'{what} y'),
            'seat_width': _num(b.get('seat_width', 3), 0.1, 50, f'{what} seat_width'),
            'seat_height': _num(b.get('seat_height', 3), 0.1, 50, f'{what} seat_height'),
            'spacing_x': _num(b.get('spacing_x', 0.5), 0, 50, f'{what} spacing_x'),
            'spacing_y': _num(b.get('spacing_y', 1), 0, 50, f'{what} spacing_y'),
            'rotation': _num(b.get('rotation', 0) or 0, -360, 360, f'{what} rotation', int),
            'reverse_numbers': bool(b.get('reverse_numbers')),
            **_naming(b, what),
            **_places(b, what),
            'hall_id': b.get('hall_id') if b.get('hall_id') in ids else out_halls[0]['id'],
        })

    switches = []
    for s in layout.get('switches') or []:
        if not isinstance(s, dict):
            raise TemplateError(SWITCH_NOT_OBJECT)
        dropped |= set(s) - set(SWITCH_KEYS)
        name = str(s.get('name') or '').strip()[:80]
        if not name:
            raise TemplateError(SWITCH_NO_NAME)
        switches.append({
            'name': name, 'role': str(s.get('role') or 'switch')[:40], 'model': str(s.get('model') or '')[:80],
            'x': _num(s.get('x'), 0, 100, f'Switch "{name}" x'), 'y': _num(s.get('y'), 0, 100, f'Switch "{name}" y'),
            'hall_id': s.get('hall_id') if s.get('hall_id') in ids else out_halls[0]['id'],
        })
    marks = []
    for m in layout.get('plan_marks') or []:
        try:
            mark = plan_marks.clean(m)
        except plan_marks.MarkError:
            raise TemplateError(BAD_MARK) from None
        mark.pop('id', None)
        marks.append({**mark, 'hall_id': m.get('hall_id') if m.get('hall_id') in ids else out_halls[0]['id']})
    return {'halls': out_halls, 'switches': switches, 'seat_blocks': blocks, 'plan_marks': marks}, sorted(dropped)


def counts(layout):
    return {k: len(layout.get(k) or []) for k in ('halls', 'switches', 'seat_blocks')}


# ── The library ──────────────────────────────────────────────────────────────────────────

def folder():
    return store.tenant_path('layout-templates')


def _path(template_id):
    if not _ID.fullmatch(str(template_id)):
        raise KeyError(template_id)
    return os.path.join(folder(), f'{template_id}.json')


def load(template_id):
    found = store.read_json(_path(template_id))
    if found is None:
        raise KeyError(template_id)
    return found


def _save(template):
    os.makedirs(folder(), exist_ok=True)
    store.write_json(_path(template['id']), template)


def meta(template):
    """The template without its layouts, for lists."""
    return {
        'id': template['id'], 'name': template['name'], 'description': template.get('description', ''),
        'created': template['created'], 'updated': template['updated'],
        'versions': [{'n': v['n'], 'saved': v['saved'], **counts(v['layout'])} for v in template['versions']],
    }


def all_templates():
    out = []
    for name in store.list_json(folder()):
        if name.endswith('.json'):
            try:
                out.append(meta(load(name[:-5])))
            except (KeyError, ValueError, TypeError):
                continue   # a broken or foreign file doesn't take the list down
    return sorted(out, key=lambda t: t['name'].lower())


def _clean_text(value, limit, what, required=False):
    text = ' '.join(str(value or '').split())[:limit] if what == 'name' else str(value or '').strip()[:limit]
    if required and not text:
        raise TemplateError(NEEDS_NAME)
    return text


def _now():
    return time.strftime('%Y-%m-%dT%H:%M:%S%z')


def create(name, description, layout):
    if len(store.list_json(folder())) >= MAX_TEMPLATES:
        raise TemplateError(TOO_MANY)
    now = _now()
    template = {'id': uuid.uuid4().hex[:12], 'name': _clean_text(name, NAME_MAX, 'name', True),
                'description': _clean_text(description, DESCRIPTION_MAX, 'description'),
                'created': now, 'updated': now, 'versions': [{'n': 1, 'saved': now, 'layout': layout}]}
    _save(template)
    return template


def add_version(template_id, layout):
    template = load(template_id)
    n = template['versions'][-1]['n'] + 1 if template['versions'] else 1
    template['versions'] = [*template['versions'], {'n': n, 'saved': _now(), 'layout': layout}][-MAX_VERSIONS:]
    template['updated'] = _now()
    _save(template)
    return template


def change(template_id, body):
    template = load(template_id)
    if 'name' in body:
        template['name'] = _clean_text(body['name'], NAME_MAX, 'name', True)
    if 'description' in body:
        template['description'] = _clean_text(body['description'], DESCRIPTION_MAX, 'description')
    template['updated'] = _now()
    _save(template)
    return template


def duplicate(template_id):
    source = load(template_id)
    return create(f"{source['name']} (copy)"[:NAME_MAX], source.get('description', ''),
                  source['versions'][-1]['layout'])


def delete(template_id):
    if not store.delete_json(_path(template_id)):
        raise KeyError(template_id)


def version(template, n=None):
    if n in (None, ''):
        return template['versions'][-1]
    for v in template['versions']:
        if str(v['n']) == str(n):
            return v
    raise TemplateError(NO_VERSION)


def export(template, n=None):
    v = version(template, n)
    return {'format': FORMAT, 'version': FORMAT_VERSION, 'name': template['name'],
            'description': template.get('description', ''), 'saved': v['saved'], 'layout': v['layout']}


def from_file(body):
    """(name, description, layout, dropped) from an exported file."""
    if not isinstance(body, dict) or body.get('format') != FORMAT:
        raise TemplateError(NOT_A_TEMPLATE)
    if body.get('version') != FORMAT_VERSION:
        raise TemplateError(UNSUPPORTED)
    layout, dropped = clean_layout(body.get('layout'))
    dropped = sorted({*dropped, *(set(body) - {'format', 'version', 'name', 'description', 'saved', 'layout'})})
    return body.get('name') or 'Imported template', body.get('description') or '', layout, dropped


# ── Starting from a template ─────────────────────────────────────────────────────────────

def _place(data, switches, hall_map):
    """Place the template's switches: an inventory device of the same name, else a new hand-made one."""
    by_name = {}
    for d in inventory.devices(data):
        by_name.setdefault(d['name'].lower(), d)
    placed = added = 0
    for s in switches:
        dev = by_name.get(s['name'].lower())
        if dev is None:
            dev = inventory.create(data, {'name': s['name'], 'role': s['role'] or 'switch', 'model': s['model'],
                                          'x': s['x'], 'y': s['y']})
            added += 1
        else:
            dev['x'], dev['y'] = s['x'], s['y']
            dev['updated_at'] = inventory.now()
            placed += 1
        dev['hall_id'] = hall_map[s['hall_id']]
    return placed, added


def apply(data, layout, hall_id=None):
    """Replace the floor plan with the template's, or with ``hall_id`` one hall's with a one-hall
    template. Changes ``data`` and the background files; the caller saves."""
    layout, _ = clean_layout(layout)
    ids = {h['id'] for h in halls.halls(data)}
    if hall_id:
        if len(layout['halls']) != 1:
            raise TemplateError(ONE_HALL_ONLY)
        target = halls.find(data, hall_id)
        if target is None:
            raise KeyError(hall_id)
        halls.ensure(data)
        target = halls.find(data, hall_id)
        others = {str(b.get('name') or '').upper() for b in data.get('seat_blocks') or []
                  if halls.hall_of(b, data, ids) != hall_id}
        clash = sorted(b['name'] for b in layout['seat_blocks'] if b['name'].upper() in others)
        if clash:
            raise TemplateError(NAME_CLASH)
        data['seat_blocks'] = [b for b in data.get('seat_blocks') or [] if halls.hall_of(b, data, ids) != hall_id]
        data[plan_marks.KEY] = [m for m in data.get(plan_marks.KEY) or [] if halls.hall_of(m, data, ids) != hall_id]
        for d in inventory.devices(data, include_hidden=True):
            if d.get('x') is not None and halls.hall_of(d, data, ids) == hall_id:
                d['x'] = d['y'] = None
        bg = layout['halls'][0]['background']
        if bg:
            halls.set_background(target, *halls.decode_image(bg))
        else:
            halls.remove_background(target)
        _put_placing(target, layout['halls'][0])
        hall_map = {layout['halls'][0]['id']: hall_id}
    else:
        for hall in halls.halls(data):
            halls.remove_background(hall)
        data['halls'] = []
        hall_map = {}
        for h in layout['halls']:
            hall = {'id': h['id'], 'name': h['name'], 'background': None}
            if h['background']:
                halls.set_background(hall, *halls.decode_image(h['background']))
            _put_placing(hall, h)
            data['halls'].append(hall)
            hall_map[h['id']] = h['id']
        data['seat_blocks'] = []
        data[plan_marks.KEY] = []
        for d in inventory.devices(data, include_hidden=True):
            d['x'] = d['y'] = None
    from .blueprints.seat_blocks import make_block
    new_blocks = [make_block(b, hall_map[b['hall_id']]) for b in layout['seat_blocks']]
    data.setdefault('seat_blocks', []).extend(new_blocks)
    data.setdefault(plan_marks.KEY, []).extend(
        {**plan_marks.clean(m), 'hall_id': hall_map[m['hall_id']]} for m in layout.get('plan_marks') or [])
    placed, added = _place(data, layout['switches'], hall_map)
    return {'halls': len(layout['halls']), 'seat_blocks': len(new_blocks), 'switches_placed': placed,
            'switches_added': added}
