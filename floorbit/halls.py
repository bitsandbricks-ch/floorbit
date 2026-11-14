"""Halls (or floors): each has its own floor plan, background image, switches and seat blocks.

``data['halls']`` lists them in order, ``[{'id', 'name', 'background': {'type', 'version'} | None}]``.
Placed devices and seat blocks say which hall they are in with ``hall_id``. An install from before
halls has no list and no ``hall_id`` anywhere: it reads as one hall, ``main``, holding everything,
and an item without a ``hall_id`` (or with one of a hall that's gone) is in the first hall.

Seat numbers stay unique across halls (block names are), so everything that works with seats
(seat map, stats, incidents, power) works the same with more than one hall.

Background images are files next to data.json (``halls/<id>.<ext>``), not in it, because data.json is
read on every request. Backups carry them inline (floorbit/blueprints/backup.py).
"""
import base64
import binascii
import csv
import hashlib
import io
import os
import re
import uuid

from . import store

DEFAULT = {'id': 'main', 'name': 'Hall', 'background': None}
MAX_HALLS = 20
NAME_MAX = 60
IMAGE_MAX_BYTES = 5 * 1024 * 1024
IMAGE_TYPES = {'image/png': 'png', 'image/jpeg': 'jpg', 'image/webp': 'webp', 'image/svg+xml': 'svg'}
CSV_MAX_ROWS = 500
CSV_COLUMNS = ('name', 'x', 'y', 'cols', 'rows', 'rotation', 'seat_width', 'seat_height',
               'spacing_x', 'spacing_y', 'reverse_numbers')


class HallError(ValueError):
    pass


def halls(data):
    found = [h for h in data.get('halls') or [] if isinstance(h, dict) and h.get('id')]
    return found or [dict(DEFAULT)]


def ensure(data):
    """Write the implicit hall down before changing the list, so its id stays ``main``."""
    if not data.get('halls'):
        data['halls'] = [dict(DEFAULT)]
    return data['halls']


def find(data, hall_id):
    return next((h for h in halls(data) if h['id'] == hall_id), None)


def default_id(data):
    return halls(data)[0]['id']


def hall_of(item, data, ids=None):
    """The hall an item is in: its own when that hall exists, otherwise the first."""
    ids = ids if ids is not None else {h['id'] for h in halls(data)}
    hid = item.get('hall_id')
    return hid if hid in ids else default_id(data)


def check_id(data, hall_id):
    """A hall id from a request: None means the first hall."""
    if hall_id in (None, ''):
        return default_id(data)
    if find(data, str(hall_id)) is None:
        raise HallError(f'No hall "{hall_id}"')
    return str(hall_id)


def clean_name(name):
    name = ' '.join(str(name or '').split())[:NAME_MAX]
    if not name:
        raise HallError('A hall needs a name')
    return name


def create(data, name):
    items = ensure(data)
    if len(items) >= MAX_HALLS:
        raise HallError(f'At most {MAX_HALLS} halls')
    hall = {'id': uuid.uuid4().hex[:12], 'name': clean_name(name), 'background': None}
    items.append(hall)
    return hall


def rename(data, hall_id, name):
    ensure(data)
    hall = find(data, hall_id)
    if hall is None:
        raise KeyError(hall_id)
    hall['name'] = clean_name(name)
    return hall


def counts(data, hall_id):
    ids = {h['id'] for h in halls(data)}
    blocks = sum(1 for b in data.get('seat_blocks') or [] if hall_of(b, data, ids) == hall_id)
    devices = sum(1 for d in data.get('inventory') or []
                  if d.get('x') is not None and not d.get('hidden') and hall_of(d, data, ids) == hall_id)
    return {'switches': devices, 'seat_blocks': blocks}


def delete(data, hall_id):
    """Only an empty hall, and never the last one: deleting must not lose a layout by accident."""
    items = ensure(data)
    hall = find(data, hall_id)
    if hall is None:
        raise KeyError(hall_id)
    if len(items) == 1:
        raise HallError('The last hall cannot be deleted')
    if any(counts(data, hall_id).values()):
        raise HallError('Move or delete the switches and seat blocks in this hall first')
    remove_background(hall)
    data['halls'] = [h for h in items if h['id'] != hall_id]


def public(data, hall):
    bg = hall.get('background') or None
    return {'id': hall['id'], 'name': hall['name'],
            'background': f"/api/halls/{hall['id']}/background?v={bg['version']}" if bg else None,
            **counts(data, hall['id'])}


# ── Background images ─────────────────────────────────────────────────────────────────────

def _folder():
    return os.path.join(os.path.dirname(os.path.abspath(store.DATA_FILE)), 'halls')


def _path(hall):
    bg = hall.get('background') or {}
    ext = IMAGE_TYPES.get(bg.get('type'))
    if not ext or not re.fullmatch(r'[\w-]{1,40}', hall['id']):
        return None
    return os.path.join(_folder(), f"{hall['id']}.{ext}")


def decode_image(data_url):
    """(mime type, bytes) from a data URL, checked."""
    m = re.fullmatch(r'data:([\w/+.-]+);base64,(.+)', str(data_url or ''), flags=re.S)
    if not m or m.group(1) not in IMAGE_TYPES:
        raise HallError('The background must be a PNG, JPEG, WebP or SVG image')
    try:
        raw = base64.b64decode(m.group(2), validate=True)
    except (binascii.Error, ValueError):
        raise HallError('The image is not valid base64') from None
    if len(raw) > IMAGE_MAX_BYTES:
        raise HallError(f'The background is at most {IMAGE_MAX_BYTES // (1024 * 1024)} MB')
    return m.group(1), raw


def set_background(hall, mime, raw):
    remove_background(hall)
    hall['background'] = {'type': mime, 'version': hashlib.sha256(raw).hexdigest()[:12]}
    os.makedirs(_folder(), exist_ok=True)
    with open(_path(hall), 'wb') as f:
        f.write(raw)


def remove_background(hall):
    path = _path(hall)
    hall['background'] = None
    if path and os.path.exists(path):
        os.remove(path)


def read_background(hall):
    """(mime type, bytes) or None."""
    path = _path(hall)
    if not path or not os.path.exists(path):
        return None
    with open(path, 'rb') as f:
        return hall['background']['type'], f.read()


def background_data_url(hall):
    found = read_background(hall)
    if not found:
        return None
    return f'data:{found[0]};base64,' + base64.b64encode(found[1]).decode()


# ── CSV import of seat blocks ─────────────────────────────────────────────────────────────

def _number(row, key, cast, default, lo, hi):
    raw = (row.get(key) or '').strip()
    if raw == '':
        if default is None:
            raise HallError(f'"{key}" is missing')
        return default
    try:
        value = cast(float(raw.replace(',', '.'))) if cast is int else cast(raw.replace(',', '.'))
    except ValueError:
        raise HallError(f'"{key}" is not a number: {raw[:20]}') from None
    if not lo <= value <= hi:
        raise HallError(f'"{key}" must be between {lo} and {hi}')
    return value


def parse_blocks_csv(text):
    """Seat blocks from CSV text, with a header row. Returns (blocks, errors), errors as
    ``[{'line', 'error'}]``; the caller adds nothing when there is any error, so a half import can't happen.

    Columns: name, x, y (percent of the plan), cols, rows, and optionally rotation, seat_width,
    seat_height, spacing_x, spacing_y, reverse_numbers. Comma or semicolon separated.
    """
    text = text.lstrip('﻿')
    try:
        dialect = csv.Sniffer().sniff(text.split('\n', 1)[0], delimiters=',;\t')
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    header = [h.strip().lower() for h in reader.fieldnames or []]
    missing = [c for c in ('name', 'x', 'y', 'cols', 'rows') if c not in header]
    if missing:
        return [], [{'line': 1, 'error': f'The header row has no {", ".join(missing)} column'}]
    reader.fieldnames = header
    blocks, errors, names = [], [], set()
    for row in reader:
        line = reader.line_num
        if len(blocks) + len(errors) >= CSV_MAX_ROWS:
            errors.append({'line': line, 'error': f'At most {CSV_MAX_ROWS} seat blocks in one import'})
            break
        if not any((v or '').strip() for v in row.values() if isinstance(v, str)):
            continue
        try:
            name = (row.get('name') or '').strip()[:40]
            if not name:
                raise HallError('"name" is missing')
            if name.upper() in names:
                raise HallError(f'Block "{name}" is in the file twice')
            names.add(name.upper())
            blocks.append({
                'name': name,
                'x': _number(row, 'x', float, None, 0, 100), 'y': _number(row, 'y', float, None, 0, 100),
                'cols': _number(row, 'cols', int, None, 1, 200), 'rows': _number(row, 'rows', int, None, 1, 200),
                'rotation': _number(row, 'rotation', int, 0, -360, 360),
                'seat_width': _number(row, 'seat_width', float, 3, 0.1, 50),
                'seat_height': _number(row, 'seat_height', float, 3, 0.1, 50),
                'spacing_x': _number(row, 'spacing_x', float, 0.5, 0, 50),
                'spacing_y': _number(row, 'spacing_y', float, 1, 0, 50),
                'reverse_numbers': (row.get('reverse_numbers') or '').strip().lower() in ('1', 'true', 'yes', 'ja'),
            })
        except HallError as exc:
            errors.append({'line': line, 'error': str(exc)})
    if not blocks and not errors:
        errors.append({'line': 1, 'error': 'The file has no seat blocks'})
    return blocks, errors
