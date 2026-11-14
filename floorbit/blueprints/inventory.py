"""The inventory API and page (floorbit/inventory.py has the rules).

- ``GET /api/inventory``: every device (``?hidden=1`` includes hidden ones), the plugins that
  feed it and their last sync. Viewers and up.
- ``POST /api/inventory``, ``PATCH`` / ``DELETE /api/inventory/<id>``: editors and up.
- ``POST /api/inventory/sync``: run every inventory plugin that's on now. Editors and up.
- ``GET /api/inventory/log``: the last syncs. Editors and up.
"""
import threading

from flask import Blueprint, current_app, jsonify, request

from .. import inventory, spa
from ..plugins import PluginError
from ..store import load_data, save_data

bp = Blueprint('inventory', __name__)

# data.json is read and written whole; this keeps two inventory writes from crossing.
data_lock = threading.RLock()


def _registry():
    return current_app.extensions.get('floorbit_plugins')


def _feeders():
    registry = _registry()
    return registry.feeders('inventory') if registry else []


def run_sync():
    """Every inventory plugin that's on, one after the other. Returns their reports."""
    registry = _registry()
    reports = []
    for spec in _feeders():
        try:
            items, skipped = inventory.clean_feed(registry.call(spec, 'inventory'))
        except (PluginError, inventory.InventoryError) as exc:
            report = {'plugin': spec.id, 'at': inventory.now(), 'error': str(exc)[:300]}
            registry.log(spec.id, f'inventory sync failed: {exc}')
            with data_lock:
                data = load_data()
                inventory.record_log(data, report)
                save_data(data)
            reports.append(report)
            continue
        with data_lock:
            data = load_data()
            report = inventory.sync(data, spec.id, items, skipped)
            save_data(data)
        registry.log(spec.id, 'inventory sync: {added} added, {updated} updated, {joined} joined, '
                              '{gone} gone, {locked} locked fields kept'.format(**report))
        reports.append(report)
    return reports


def _sources(data):
    log = inventory.sync_log(data)
    out = []
    for spec in _feeders():
        last = next((r for r in log if r.get('plugin') == spec.id), None)
        out.append({'id': spec.id, 'name': spec.name, 'last_sync': last})
    return out


@bp.route('/inventory')
def inventory_page():
    return spa.render('Inventory')


@bp.route('/api/inventory', methods=['GET'])
def list_devices():
    data = load_data()
    hidden = request.args.get('hidden') in ('1', 'true')
    return jsonify({'devices': [inventory.public(d) for d in inventory.devices(data, include_hidden=hidden)],
                    'sources': _sources(data), 'roles': list(inventory.ROLES), 'fields': list(inventory.FIELDS)})


@bp.route('/api/inventory', methods=['POST'])
def create_device():
    body = request.get_json(silent=True) or {}
    body.pop('hall_id', None)   # placing in a hall goes through /api/switches, which checks the hall
    with data_lock:
        data = load_data()
        try:
            dev = inventory.create(data, body)
        except inventory.InventoryError as exc:
            return jsonify({'error': str(exc)}), 400
        save_data(data)
    return jsonify(inventory.public(dev)), 201


@bp.route('/api/inventory/<device_id>', methods=['PATCH'])
def update_device(device_id):
    body = request.get_json(silent=True) or {}
    body.pop('hall_id', None)   # see create_device
    if not isinstance(body.get('unlock', []), list):
        return jsonify({'error': 'unlock must be a list of field names'}), 400
    with data_lock:
        data = load_data()
        try:
            dev, changed = inventory.update(data, device_id, body)
        except KeyError:
            return jsonify({'error': 'No such device'}), 404
        except inventory.InventoryError as exc:
            return jsonify({'error': str(exc)}), 400
        save_data(data)
    return jsonify({**inventory.public(dev), 'changed': changed})


@bp.route('/api/inventory/<device_id>', methods=['DELETE'])
def delete_device(device_id):
    with data_lock:
        data = load_data()
        try:
            outcome = inventory.delete(data, device_id)
        except KeyError:
            return jsonify({'error': 'No such device'}), 404
        save_data(data)
    return jsonify({'result': outcome})


@bp.route('/api/inventory/sync', methods=['POST'])
def sync_now():
    if not _feeders():
        return jsonify({'error': 'No inventory source is on. Turn one on under Settings > Plugins.'}), 400
    reports = run_sync()
    return jsonify({'reports': reports, 'sources': _sources(load_data())})


@bp.route('/api/inventory/log', methods=['GET'])
def sync_history():
    return jsonify({'log': inventory.sync_log(load_data(), request.args.get('plugin') or None)})
