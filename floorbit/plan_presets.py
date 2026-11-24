"""Plan presets: items of the floor plan kept together under a name, to place again in any hall.

A preset is a selection from the editor: seat blocks (with their rows), walls, zones, text, icons,
patch panels and power boards, as the editor copies them (frontend ``pages/plan/edit/clipboard.ts``).
An admin zone with its blocks and its walls is one preset. Placing one posts each item again, like a
paste, with free row letters and names; each item's own API checks it then.

No switches and no cables (a switch is one device, a port has one cable), and nothing about the event.
Presets live in ``plan-presets.json`` next to the templates (floorbit/layout_templates.py), for the
whole tenant, so a preset made at one event can be placed at the next.
"""
import json
import threading
import time
import uuid

from . import store

MAX_PRESETS = 100
MAX_ITEMS = 200
MAX_BYTES = 512 * 1024      # icons and paths stay small; background images never go in
NAME_MAX = 60
KINDS = ('block', 'mark', 'panel', 'board')
# Never kept: what ties an item to one plan, and anything an item shouldn't carry to another event.
SKIP = {'id', 'hall_id', 'locked', 'group'}

_lock = threading.Lock()


class PresetError(ValueError):
    pass


def _path():
    return store.tenant_path('plan-presets.json')


def all_presets():
    found = store.read_json(_path(), {})
    presets = found.get('presets')
    return [p for p in presets if isinstance(p, dict) and p.get('id')] if isinstance(presets, list) else []


def counts(items):
    """How many of each kind, for the list: ``{'block': 2, 'mark': 3}``."""
    out = {}
    for item in items:
        out[item['kind']] = out.get(item['kind'], 0) + 1
    return out


def clean_items(items):
    if not isinstance(items, list) or not items:
        raise PresetError('A preset holds at least one item')
    if len(items) > MAX_ITEMS:
        raise PresetError(f'A preset holds at most {MAX_ITEMS} items')
    out = []
    for item in items:
        if not isinstance(item, dict) or item.get('kind') not in KINDS or not isinstance(item.get('body'), dict):
            raise PresetError('A preset holds seat blocks, marks, patch panels and power boards')
        out.append({'kind': item['kind'], 'body': {k: v for k, v in item['body'].items() if k not in SKIP}})
    if len(json.dumps(out)) > MAX_BYTES:
        raise PresetError(f'A preset is at most {MAX_BYTES // 1024} kB')
    return out


def add(name, items):
    name = str(name or '').strip()
    if not name:
        raise PresetError('A preset needs a name')
    if len(name) > NAME_MAX:
        raise PresetError(f'A preset name is at most {NAME_MAX} characters')
    items = clean_items(items)
    with _lock:
        presets = all_presets()
        if len(presets) >= MAX_PRESETS:
            raise PresetError(f'At most {MAX_PRESETS} presets: delete one first')
        if any(str(p.get('name', '')).lower() == name.lower() for p in presets):
            raise PresetError('A preset with this name exists already')
        preset = {'id': uuid.uuid4().hex[:12], 'name': name, 'saved': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
                  'counts': counts(items), 'items': items}
        store.write_json(_path(), {'presets': [*presets, preset]})
    return preset


def delete(preset_id):
    with _lock:
        presets = all_presets()
        left = [p for p in presets if p['id'] != preset_id]
        if len(left) == len(presets):
            raise KeyError(preset_id)
        store.write_json(_path(), {'presets': left})
