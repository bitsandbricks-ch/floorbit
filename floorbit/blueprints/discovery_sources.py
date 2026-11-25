"""Which source decides each discovery area per kind of device, and source conflicts (issue #965,
floorbit/discovery_sources.py).

- ``GET /api/inventory/discovery/types/<role>``: "What Floorbit reads from a <role>": one row per
  area with its deciding source, the others, interval, where it goes, last run and conflicts.
- ``PUT /api/inventory/discovery/deciding`` ``{role, area, source}``: an admin picks the deciding
  source (``null`` for the default). ``settings.manage`` (auth/roles.py).
- ``POST /api/inventory/<id>/conflicts/take`` ``{field, source}``: the field takes that source's
  reading, like a hand edit. Editors and up (``floorplan.edit``).
"""
from flask import Blueprint, g, jsonify, request

from integrations import events

from .. import audit, discovery_sources, inventory
from ..store import load_data, save_data
from .inventory import data_lock

bp = Blueprint('discovery_sources', __name__)


@bp.route('/api/inventory/discovery/types/<role>', methods=['GET'])
def reads(role):
    if role not in inventory.ROLES:
        return jsonify({'error': 'No such kind of device.'}), 404
    return jsonify(discovery_sources.table(load_data(), role))


@bp.route('/api/inventory/discovery/deciding', methods=['PUT'])
def pick():
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or not isinstance(body.get('role'), str) or not isinstance(body.get('area'), str) \
            or not (body.get('source') is None or isinstance(body.get('source'), str)):
        return jsonify({'error': 'Send the kind of device, the area and the source (null for the default).'}), 400
    with data_lock:
        data = load_data()
        problem = discovery_sources.set_deciding(data, body['role'], body['area'], body.get('source'))
        if problem:
            return jsonify({'error': problem}), 400
        save_data(data)
    audit.record('inventory', 'Picked the deciding discovery source', user=g.get('audit_user'),
                 target=f"{body['role']} {body['area']}", fields={'source': body.get('source') or 'default'})
    events.publish('inventory.changed', {})
    return jsonify(discovery_sources.table(data, body['role']))


@bp.route('/api/inventory/<device_id>/conflicts/take', methods=['POST'])
def take(device_id):
    body = request.get_json(silent=True) or {}
    field, source = str(body.get('field') or ''), str(body.get('source') or '')
    with data_lock:
        data = load_data()
        dev = inventory.find(data, device_id)
        if dev is None:
            return jsonify({'error': 'No such device'}), 404
        row = next((c for c in discovery_sources.conflicts_of(data, dev)
                    if c['field'] == field and source in (c['other']['source'], c['deciding']['source'])), None)
        if row is None:
            return jsonify({'error': 'The sources agree on this now.'}), 404
        value = row['other']['value'] if row['other']['source'] == source else row['deciding']['value']
        try:
            dev, changed = inventory.update(data, device_id, {field: value})
        except inventory.InventoryError as exc:
            return jsonify({'error': str(exc)}), 400
        save_data(data)
    audit.record('inventory', "Took a discovery source's value", user=g.get('audit_user'),
                 target=f"{dev['name']} {field}", fields={field: value, 'source': source})
    events.publish('inventory.changed', {})
    return jsonify({**inventory.public(dev), 'changed': changed})
