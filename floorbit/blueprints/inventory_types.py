"""Inventory types and entries (floorbit/inventory_types.py).

- ``GET /api/inventory/types``: every type with its fields and how many entries it has.
- ``POST /api/inventory/types`` ``{"name"}``; ``PATCH /api/inventory/types/<id>`` ``{"name"?, "fields"?,
  "icon"?, "color"?, "properties"?, "features"?}``; ``DELETE /api/inventory/types/<id>`` (custom, empty).
  Admins (``settings.manage``): a type's fields shape what everyone types in.
- ``GET /api/inventory/entries?type=``: entries of every type but devices.
- ``POST /api/inventory/entries/<type>`` (stored types), ``GET`` / ``PATCH`` / ``DELETE
  /api/inventory/entries/<type>/<id>``. Editors (``floorplan.edit``).
"""
from flask import Blueprint, g, jsonify, request

from integrations import events

from .. import audit, inventory_scope, inventory_types
from ..store import load_data
from .inventory_groups import _saved

bp = Blueprint('inventory_types', __name__)


def _changed(_area, what, name, changed):
    if changed:
        audit.record('inventory', what, user=g.get('audit_user'), target=f"{name} ({', '.join(changed)})"[:120])
        events.publish('inventory.changed', {})


@bp.route('/api/inventory/types', methods=['GET'])
def list_types():
    data = load_data()
    counts = inventory_types.counts(data)
    return jsonify({'types': [{**t, 'count': counts.get(t['id'], 0)} for t in inventory_types.types(data)],
                    'field_kinds': list(inventory_types.FIELD_KINDS)})


@bp.route('/api/inventory/types', methods=['POST'])
def create_type():
    body = request.get_json(silent=True) or {}
    result, err = _saved(lambda data: inventory_types.save_type(data, body, registry=inventory_scope._registry()))
    if err:
        return err
    t, changed = result
    _changed('types', 'Added an inventory type', t['name'], changed)
    return jsonify(t), 201


@bp.route('/api/inventory/types/<type_id>', methods=['PATCH'])
def update_type(type_id):
    body = request.get_json(silent=True) or {}
    result, err = _saved(lambda data: inventory_types.save_type(data, body, type_id, inventory_scope._registry()))
    if err:
        return err
    t, changed = result
    _changed('types', 'Changed an inventory type', t['name'], changed)
    if 'features' in changed:
        inventory_scope.reload_agents()
    return jsonify(t)


@bp.route('/api/inventory/types/<type_id>', methods=['DELETE'])
def delete_type(type_id):
    _, err = _saved(lambda data: inventory_types.delete_type(data, type_id))
    if err:
        return err
    _changed('types', 'Removed an inventory type', type_id, ['removed'])
    return jsonify({'ok': True})


@bp.route('/api/inventory/entries', methods=['GET'])
def list_entries():
    data = load_data()
    return jsonify({'entries': inventory_types.listing(data, request.args.get('type') or None)})


@bp.route('/api/inventory/entries/<type_id>', methods=['POST'])
def create_entry(type_id):
    body = request.get_json(silent=True) or {}
    entry, err = _saved(lambda data: inventory_types.create(data, type_id, body))
    if err:
        return err
    _changed('entries', 'Added an inventory entry', entry['name'], ['created'])
    return jsonify(entry), 201


@bp.route('/api/inventory/entries/<type_id>/<entry_id>', methods=['GET'])
def get_entry(type_id, entry_id):
    try:
        return jsonify(inventory_types.detail(load_data(), type_id, entry_id))
    except inventory_scope.ScopeError as exc:
        return jsonify({'error': str(exc)}), exc.status


@bp.route('/api/inventory/entries/<type_id>/<entry_id>', methods=['PATCH'])
def update_entry(type_id, entry_id):
    body = request.get_json(silent=True) or {}
    result, err = _saved(lambda data: inventory_types.update(data, type_id, entry_id, body))
    if err:
        return err
    entry, changed = result
    _changed('entries', 'Changed an inventory entry', entry['name'], changed)
    return jsonify(entry)


@bp.route('/api/inventory/entries/<type_id>/<entry_id>', methods=['DELETE'])
def delete_entry(type_id, entry_id):
    entry, err = _saved(lambda data: inventory_types.delete(data, type_id, entry_id))
    if err:
        return err
    _changed('entries', 'Removed an inventory entry', entry['name'], ['removed'])
    return jsonify({'ok': True})
