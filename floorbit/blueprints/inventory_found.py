"""Inventory > Discovery (issues #891, #968): what discovery found that the inventory doesn't have.
Rules in floorbit/inventory_found.py.

- ``GET /api/inventory/found``: devices LLDP/CDP sees that match no inventory device, and links
  between inventory devices that no planned link explains. Viewers and up.
- ``POST /api/inventory/found/ignore`` ``{"kind": "device"|"link", "key", "ignored": true|false}``:
  leave one out, or take it back. Editors and up (``/api/inventory`` WRITE), audit-logged.

Adding a device goes through ``POST /api/inventory``, confirming a link through ``POST /api/links``.
"""
from flask import Blueprint, g, jsonify, request

from .. import audit, inventory_found
from ..store import load_data, save_data
from .inventory import data_lock

bp = Blueprint('inventory_found', __name__)


@bp.route('/api/inventory/found', methods=['GET'])
def found():
    return jsonify(inventory_found.collect(load_data()))


@bp.route('/api/inventory/found/ignore', methods=['POST'])
def ignore():
    body = request.get_json(silent=True) or {}
    kind, key = body.get('kind'), body.get('key')
    if kind not in ('device', 'link') or not isinstance(key, str) or not key.strip():
        return jsonify({'error': 'Send the kind (device or link) and the key'}), 400
    on = body.get('ignored', True) is not False
    with data_lock:
        data = load_data()
        inventory_found.set_ignored(data, kind, key, on)
        save_data(data)
    what = 'a found device' if kind == 'device' else 'a found link'
    audit.record('inventory', f'Ignored {what}' if on else f'Stopped ignoring {what}',
                 user=g.get('audit_user'), target=key.strip()[:80])
    return jsonify({'ok': True})
