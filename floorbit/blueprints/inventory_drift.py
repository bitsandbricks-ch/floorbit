"""Fix drift from the device page (issue #918): take what the device reports into the inventory.

- ``POST /api/inventory/<id>/drift/take`` ``{field}``: the inventory field takes the value discovery
  saw last (``inventory_drift``, floorbit/inventory_discovery.py), like a hand edit, so a value fed by
  NetBox is then locked against it. The row is gone at once instead of at the next discovery run.
  Editors and up (``floorplan.edit``, auth/roles.py).

Only fields and the management address: renaming a device moves its seats, links and history, so a
different hostname is shown, never taken in one click, and interfaces have their own panel.
"""
from flask import Blueprint, g, jsonify, request

from integrations import events

from .. import audit, inventory
from ..store import load_data, save_data
from .inventory import data_lock

bp = Blueprint('inventory_drift', __name__)

TAKES = ('field', 'address')


@bp.route('/api/inventory/<device_id>/drift/take', methods=['POST'])
def take(device_id):
    field = str((request.get_json(silent=True) or {}).get('field') or '')
    with data_lock:
        data = load_data()
        found = data.get('inventory_drift') if isinstance(data.get('inventory_drift'), dict) else {}
        rows = list(found.get(device_id) or [])
        row = next((r for r in rows if r.get('kind') in TAKES and r.get('field') == field), None)
        if row is None:
            return jsonify({'error': 'The device and the inventory agree on this now.'}), 404
        try:
            dev, changed = inventory.update(data, device_id, {field: row['actual']})
        except KeyError:
            return jsonify({'error': 'No such device'}), 404
        except inventory.InventoryError as exc:
            return jsonify({'error': str(exc)}), 400
        rest = [r for r in rows if r is not row]
        if rest:
            found[device_id] = rest
        else:
            found.pop(device_id, None)
        data['inventory_drift'] = found
        save_data(data)
    audit.record('inventory', "Took the device's value", user=g.get('audit_user'), target=f"{dev['name']} {field}",
                 fields={field: row['actual']})
    events.publish('inventory.changed', {})
    return jsonify({**inventory.public(dev), 'changed': changed, 'drift': rest})
