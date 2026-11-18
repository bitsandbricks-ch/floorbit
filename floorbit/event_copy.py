"""Copying one event's floor plan into a new or an existing event (issue #466, docs/tenancy.md).

Only what is planned is copied, in parts the crew picks. What happened at an event (check-ins,
incidents, handover, logs, history) never is. Tenant-wide parts (accounts, settings, dashboards,
runbooks) aren't either: every event already shares them.

Into an existing event, each part is either replaced or merged: lists of things with an ``id``
are joined by id (the copied one wins), other values are taken from the source when the target has
none. ``preview`` says what would change without saving.
"""
import os
import shutil

from . import store, tenancy

# part -> the data.json keys it covers. Halls also carry their background pictures.
PARTS = {
    'halls': ('halls',),
    'seats': ('seat_blocks', 'seats'),
    'inventory': ('inventory', 'plan_groups', 'plan_marks', 'port_areas', 'links'),
    'cables': ('cables', 'cable_routes', 'patch_panels'),
    'power': ('power',),
    'services': ('firewalls', 'services', 'game_servers'),
    'schedule': ('schedule', 'tournament', 'brackets'),
}
MODES = ('replace', 'merge')


class CopyError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def _parts(parts):
    if parts is None:
        return list(PARTS)
    if not isinstance(parts, list) or not parts or any(p not in PARTS for p in parts):
        raise CopyError(f"Pick what to copy: {', '.join(PARTS)}.")
    return parts


def _ids(value):
    if isinstance(value, list) and all(isinstance(x, dict) and 'id' in x for x in value):
        return {str(x['id']): x for x in value}
    return None


def _merge(target, source):
    """(merged value, added, changed)."""
    t_ids, s_ids = _ids(target), _ids(source)
    if t_ids is not None and s_ids is not None:
        added = [k for k in s_ids if k not in t_ids]
        changed = [k for k in s_ids if k in t_ids and t_ids[k] != s_ids[k]]
        merged = [s_ids.get(str(x['id']), x) for x in target] + [s_ids[k] for k in added]
        return merged, len(added), len(changed)
    if target in (None, [], {}):
        return source, (len(source) if isinstance(source, (list, dict)) else 1), 0
    if isinstance(target, dict) and isinstance(source, dict):
        merged = {**target, **{k: v for k, v in source.items() if k not in target}}
        return merged, len(merged) - len(target), 0
    return target, 0, 0


def _count(value):
    return len(value) if isinstance(value, (list, dict)) else (0 if value is None else 1)


def _plan(source, target, parts, mode):
    """(the target's new data.json parts, what changes per part)."""
    with tenancy.using_event(source):
        src = store.load_data()
    with tenancy.using_event(target):
        dst = store.load_data()
    out, changes = {}, {}
    for part in parts:
        summary = {'added': 0, 'changed': 0, 'removed': 0}
        for key in PARTS[part]:
            if key not in src:
                continue
            if mode == 'replace':
                summary['removed'] += _count(dst.get(key))
                summary['added'] += _count(src[key])
                out[key] = src[key]
            else:
                out[key], added, changed = _merge(dst.get(key), src[key])
                summary['added'] += added
                summary['changed'] += changed
        changes[part] = summary
    return out, changes


def _event(event_id):
    event = tenancy.find(event_id) if isinstance(event_id, str) else None
    if event is None:
        raise CopyError('No such event.', 404)
    return event


def preview(source_id, target_id, parts=None, mode='merge'):
    source, target = _event(source_id), _event(target_id)
    if source['id'] == target['id']:
        raise CopyError('Pick two different events.')
    if mode not in MODES:
        raise CopyError('Copy with replace or merge.')
    return _plan(source, target, _parts(parts), mode)[1]


def copy(source_id, target_id, parts=None, mode='merge'):
    """Copy the parts into the target event and save it. Returns what changed per part."""
    source, target = _event(source_id), _event(target_id)
    if source['id'] == target['id']:
        raise CopyError('Pick two different events.')
    if mode not in MODES:
        raise CopyError('Copy with replace or merge.')
    parts = _parts(parts)
    out, changes = _plan(source, target, parts, mode)
    with tenancy.using_event(source):
        pictures = store.event_path('halls')
    with tenancy.using_event(target):
        data = store.load_data()
        data.update(out)
        store.save_data(data)
        if 'halls' in parts and os.path.isdir(pictures):   # background pictures are files
            shutil.copytree(pictures, store.event_path('halls'), dirs_exist_ok=True)
    return changes
