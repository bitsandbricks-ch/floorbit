"""Saved dashboard layouts (issue #103). See docs/dashboard.md.

A layout is which plugin tiles a screen shows, in which order, and how many columns: the ops desk
might show the DHCP and uplink tiles in two big columns, the NOC wall everything. Open one with
``/dashboard?layout=<id>``, add ``&screen=1`` for a kiosk. Kept in data.json under
``dashboard_layouts``. A tile is named ``<plugin>/<w or a>/<id>`` (widget or action); tiles of a
plugin that is off or that the viewer may not see are skipped, never an error.
"""
import re
import threading
import time

from .store import load_data, save_data

KEY = 'dashboard_layouts'
MAX_LAYOUTS = 30
MAX_TILES = 60
ID_RE = re.compile(r'^[a-z0-9][a-z0-9-]{0,31}$')
TILE_RE = re.compile(r'^[\w.-]{1,64}/[wa]/[\w.-]{1,64}$')
COLUMNS = (1, 2, 3, 4)
_lock = threading.Lock()


class LayoutError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def all_layouts(data=None):
    data = load_data() if data is None else data
    raw = data.get(KEY)
    return [x for x in raw if isinstance(x, dict)] if isinstance(raw, list) else []


def save(layout_id, body, by):
    layout_id = str(layout_id or '').strip().lower()
    if not ID_RE.match(layout_id):
        raise LayoutError('A layout id is up to 32 lower-case letters, digits or -, for example ops-desk.')
    name = ' '.join(str(body.get('name') or '').split())[:60]
    if not name:
        raise LayoutError('Give the layout a name.')
    tiles = body.get('tiles')
    if not isinstance(tiles, list) or not tiles or any(not isinstance(t, str) or not TILE_RE.match(t) for t in tiles):
        raise LayoutError('Pick at least one tile.')
    tiles = list(dict.fromkeys(tiles))[:MAX_TILES]
    try:
        columns = int(body.get('columns') or 3)
    except (TypeError, ValueError):
        columns = 0
    if columns not in COLUMNS:
        raise LayoutError('Columns are 1 to 4.')
    layout = {'id': layout_id, 'name': name, 'tiles': tiles, 'columns': columns, 'updated_at': time.time(), 'by': by}
    with _lock:
        data = load_data()
        layouts = all_layouts(data)
        old = next((n for n, x in enumerate(layouts) if x.get('id') == layout_id), None)
        if old is None:
            if len(layouts) >= MAX_LAYOUTS:
                raise LayoutError(f'Floorbit keeps at most {MAX_LAYOUTS} layouts.')
            layouts.append(layout)
        else:
            layouts[old] = layout
        data[KEY] = layouts
        save_data(data)
    return layout


def delete(layout_id):
    with _lock:
        data = load_data()
        layouts = all_layouts(data)
        kept = [x for x in layouts if x.get('id') != layout_id]
        if len(kept) == len(layouts):
            raise LayoutError('No such layout.', 404)
        data[KEY] = kept
        save_data(data)
