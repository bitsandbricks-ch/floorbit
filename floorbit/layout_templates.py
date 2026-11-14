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

from . import halls, inventory, store

FORMAT = 'floorbit-template'
FORMAT_VERSION = 1
MAX_VERSIONS = 10
MAX_TEMPLATES = 200
NAME_MAX, DESCRIPTION_MAX = 80, 500
BLOCK_KEYS = ('name', 'x', 'y', 'cols', 'rows', 'seat_width', 'seat_height', 'spacing_x', 'spacing_y',
              'rotation', 'reverse_numbers', 'hall_id')
SWITCH_KEYS = ('name', 'role', 'model', 'x', 'y', 'hall_id')
_ID = re.compile(r'[a-f0-9]{12}')


class TemplateError(ValueError):
    pass


# ── Snapshots ────────────────────────────────────────────────────────────────────────────

def snapshot(data, hall_id=None):
    """The layout of every hall, or of one, with nothing but layout in it."""
    chosen = [h for h in halls.halls(data) if hall_id is None or h['id'] == hall_id]
    if not chosen:
        raise TemplateError(f'No hall "{hall_id}"')
    ids = {h['id'] for h in halls.halls(data)}
    wanted = {h['id'] for h in chosen}
    blocks = [{k: b.get(k) for k in BLOCK_KEYS if k != 'hall_id'} | {'hall_id': halls.hall_of(b, data, ids)}
              for b in data.get('seat_blocks') or [] if halls.hall_of(b, data, ids) in wanted]
    switches = [{k: d.get(k) for k in SWITCH_KEYS if k != 'hall_id'} | {'hall_id': halls.hall_of(d, data, ids)}
                for d in inventory.devices(data) if d.get('x') is not None and halls.hall_of(d, data, ids) in wanted]
    return {
        'halls': [{'id': h['id'], 'name': h['name'], 'background': halls.background_data_url(h)} for h in chosen],
        'switches': switches,
        'seat_blocks': blocks,
    }


def _num(value, lo, hi, what, cast=float):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TemplateError(f'{what} is not a number')
    value = cast(value)
    if not lo <= value <= hi:
        raise TemplateError(f'{what} is out of range')
    return value


def clean_layout(layout):
    """A layout from a file, cut down to the template fields and checked. Returns (layout, dropped),
    ``dropped`` the names of the fields that were taken out."""
    if not isinstance(layout, dict):
        raise TemplateError('The template has no layout')
    dropped = set(layout) - {'halls', 'switches', 'seat_blocks'}
    raw_halls = layout.get('halls')
    if not isinstance(raw_halls, list) or not raw_halls or len(raw_halls) > halls.MAX_HALLS:
        raise TemplateError(f'A template has 1 to {halls.MAX_HALLS} halls')
    out_halls, ids = [], set()
    for h in raw_halls:
        if not isinstance(h, dict):
            raise TemplateError('A hall is not an object')
        dropped |= set(h) - {'id', 'name', 'background'}
        hid = str(h.get('id') or '')[:40]
        if not re.fullmatch(r'[\w-]{1,40}', hid) or hid in ids:
            raise TemplateError(f'Hall id "{hid}" is not valid or used twice')
        ids.add(hid)
        try:
            if h.get('background'):
                halls.decode_image(h['background'])
            out_halls.append({'id': hid, 'name': halls.clean_name(h.get('name')),
                              'background': h.get('background') or None})
        except halls.HallError as exc:
            raise TemplateError(f'Hall "{hid}": {exc}') from None

    blocks, names = [], set()
    for b in layout.get('seat_blocks') or []:
        if not isinstance(b, dict):
            raise TemplateError('A seat block is not an object')
        dropped |= set(b) - set(BLOCK_KEYS)
        name = str(b.get('name') or '')[:40]
        if name.upper() in names:
            raise TemplateError(f'Block "{name}" is in the template twice')
        names.add(name.upper())
        what = f'Block "{name}"'
        blocks.append({
            'name': name,
            'x': _num(b.get('x'), 0, 100, f'{what} x'), 'y': _num(b.get('y'), 0, 100, f'{what} y'),
            'cols': _num(b.get('cols', 1), 1, 200, f'{what} cols', int),
            'rows': _num(b.get('rows', 1), 1, 200, f'{what} rows', int),
            'seat_width': _num(b.get('seat_width', 3), 0.1, 50, f'{what} seat_width'),
            'seat_height': _num(b.get('seat_height', 3), 0.1, 50, f'{what} seat_height'),
            'spacing_x': _num(b.get('spacing_x', 0.5), 0, 50, f'{what} spacing_x'),
            'spacing_y': _num(b.get('spacing_y', 1), 0, 50, f'{what} spacing_y'),
            'rotation': _num(b.get('rotation', 0) or 0, -360, 360, f'{what} rotation', int),
            'reverse_numbers': bool(b.get('reverse_numbers')),
            'hall_id': b.get('hall_id') if b.get('hall_id') in ids else out_halls[0]['id'],
        })

    switches = []
    for s in layout.get('switches') or []:
        if not isinstance(s, dict):
            raise TemplateError('A switch is not an object')
        dropped |= set(s) - set(SWITCH_KEYS)
        name = str(s.get('name') or '').strip()[:80]
        if not name:
            raise TemplateError('A switch has no name')
        switches.append({
            'name': name, 'role': str(s.get('role') or 'switch')[:40], 'model': str(s.get('model') or '')[:80],
            'x': _num(s.get('x'), 0, 100, f'Switch "{name}" x'), 'y': _num(s.get('y'), 0, 100, f'Switch "{name}" y'),
            'hall_id': s.get('hall_id') if s.get('hall_id') in ids else out_halls[0]['id'],
        })
    return {'halls': out_halls, 'switches': switches, 'seat_blocks': blocks}, sorted(dropped)


def counts(layout):
    return {k: len(layout.get(k) or []) for k in ('halls', 'switches', 'seat_blocks')}


# ── The library ──────────────────────────────────────────────────────────────────────────

def folder():
    return os.path.join(os.path.dirname(os.path.abspath(store.DATA_FILE)), 'layout-templates')


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
    if not os.path.isdir(folder()):
        return []
    out = []
    for name in sorted(os.listdir(folder())):
        if name.endswith('.json'):
            try:
                out.append(meta(load(name[:-5])))
            except (KeyError, ValueError, TypeError):
                continue   # a broken or foreign file doesn't take the list down
    return sorted(out, key=lambda t: t['name'].lower())


def _clean_text(value, limit, what, required=False):
    text = ' '.join(str(value or '').split())[:limit] if what == 'name' else str(value or '').strip()[:limit]
    if required and not text:
        raise TemplateError(f'A template needs a {what}')
    return text


def _now():
    return time.strftime('%Y-%m-%dT%H:%M:%S%z')


def create(name, description, layout):
    if os.path.isdir(folder()) and len([n for n in os.listdir(folder()) if n.endswith('.json')]) >= MAX_TEMPLATES:
        raise TemplateError(f'At most {MAX_TEMPLATES} templates')
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
    path = _path(template_id)
    if not os.path.exists(path):
        raise KeyError(template_id)
    os.remove(path)


def version(template, n=None):
    if n in (None, ''):
        return template['versions'][-1]
    for v in template['versions']:
        if str(v['n']) == str(n):
            return v
    raise TemplateError(f'No version {n}')


def export(template, n=None):
    v = version(template, n)
    return {'format': FORMAT, 'version': FORMAT_VERSION, 'name': template['name'],
            'description': template.get('description', ''), 'saved': v['saved'], 'layout': v['layout']}


def from_file(body):
    """(name, description, layout, dropped) from an exported file."""
    if not isinstance(body, dict) or body.get('format') != FORMAT:
        raise TemplateError('This is not a Floorbit template file')
    if body.get('version') != FORMAT_VERSION:
        raise TemplateError(f'Template format {body.get("version")!r} is not supported (expected {FORMAT_VERSION})')
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
            raise TemplateError('Only a template of one hall can go into one hall')
        target = halls.find(data, hall_id)
        if target is None:
            raise KeyError(hall_id)
        halls.ensure(data)
        target = halls.find(data, hall_id)
        others = {str(b.get('name') or '').upper() for b in data.get('seat_blocks') or []
                  if halls.hall_of(b, data, ids) != hall_id}
        clash = sorted(b['name'] for b in layout['seat_blocks'] if b['name'].upper() in others)
        if clash:
            raise TemplateError(f'Another hall already has block(s) {", ".join(clash)}')
        data['seat_blocks'] = [b for b in data.get('seat_blocks') or [] if halls.hall_of(b, data, ids) != hall_id]
        for d in inventory.devices(data, include_hidden=True):
            if d.get('x') is not None and halls.hall_of(d, data, ids) == hall_id:
                d['x'] = d['y'] = None
        bg = layout['halls'][0]['background']
        if bg:
            halls.set_background(target, *halls.decode_image(bg))
        else:
            halls.remove_background(target)
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
            data['halls'].append(hall)
            hall_map[h['id']] = h['id']
        data['seat_blocks'] = []
        for d in inventory.devices(data, include_hidden=True):
            d['x'] = d['y'] = None
    from .blueprints.seat_blocks import make_block
    new_blocks = [make_block(b, hall_map[b['hall_id']]) for b in layout['seat_blocks']]
    data.setdefault('seat_blocks', []).extend(new_blocks)
    placed, added = _place(data, layout['switches'], hall_map)
    return {'halls': len(layout['halls']), 'seat_blocks': len(new_blocks), 'switches_placed': placed,
            'switches_added': added}
