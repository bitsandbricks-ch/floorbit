"""Acting on several inventory devices at once (issue #980): the list's pick bar.

- ``POST /api/inventory/bulk``: ``{ids: [...], action, tag?, group_id?}`` with ``action`` one of
  ``tag-add``, ``tag-remove``, ``group`` (``group_id`` null or '' takes them out of their group),
  ``hide`` and ``show``. One request for all of them; each device that changed gets its own line in
  the audit log, as a change one by one would. Editors and up (``/api/inventory`` WRITE).
"""
from flask import Blueprint, g, jsonify, request

from .. import audit, inventory, inventory_scope
from ..store import load_data, save_data
from .inventory import data_lock

bp = Blueprint('inventory_bulk', __name__)

ACTIONS = ('tag-add', 'tag-remove', 'group', 'hide', 'show')
MAX_IDS = 1000


def _body_for(dev, action, value):
    """The PATCH body one device would get for this action, or None when nothing changes."""
    tags = list(dev.get('tags') or [])
    if action == 'tag-add':
        return None if value in tags else {'tags': [*tags, value]}
    if action == 'tag-remove':
        return {'tags': [t for t in tags if t != value]} if value in tags else None
    if action == 'group':
        return None if (dev.get('group_id') or None) == value else {'group_id': value}
    hidden = action == 'hide'
    return None if bool(dev.get('hidden')) == hidden else {'hidden': hidden}


@bp.route('/api/inventory/bulk', methods=['POST'])
def bulk():
    body = request.get_json(silent=True) or {}
    ids, action = body.get('ids'), body.get('action')
    if action not in ACTIONS:
        return jsonify({'error': 'Unknown action'}), 400
    if not isinstance(ids, list) or not ids or len(ids) > MAX_IDS or not all(isinstance(i, str) for i in ids):
        return jsonify({'error': 'Pick at least one device'}), 400
    with data_lock:
        data = load_data()
        value = None
        if action.startswith('tag-'):
            value = body.get('tag')
            if not isinstance(value, str) or inventory_scope.tag(data, value) is None:
                return jsonify({'error': 'No such tag.'}), 400
        elif action == 'group':
            value = body.get('group_id') or None
            if value is not None and inventory_scope.group(data, value) is None:
                return jsonify({'error': 'No such group.'}), 400
        found = {d['id']: d for d in data.get('inventory') or []}
        missing = [i for i in ids if i not in found]
        if missing:
            return jsonify({'error': 'No such device', 'missing': missing}), 404
        done = []
        for device_id in dict.fromkeys(ids):
            patch = _body_for(found[device_id], action, value)
            if patch is None:
                continue
            try:
                dev, changed = inventory.update(data, device_id, patch)
            except (inventory.InventoryError, inventory_scope.ScopeError) as exc:
                # Checked above, so this is a device the change can't apply to (too many tags):
                # nothing is saved, the list stays as it was.
                return jsonify({'error': str(exc), 'device': device_id}), 400
            if changed:
                done.append((dev, changed))
        if done:
            save_data(data)
    for dev, changed in done:
        audit.record('inventory', 'Changed device', user=g.get('audit_user'), target=dev['name'], fields=changed)
    return jsonify({'changed': [dev['id'] for dev, _ in done], 'unchanged': len(set(ids)) - len(done)})
