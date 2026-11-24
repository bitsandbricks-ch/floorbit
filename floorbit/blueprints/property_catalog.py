"""Known inventory properties and their types (floorbit/property_catalog.py, issue #879).

- ``GET /api/inventory/properties``: every known property, built-in ones first, and the types.
- ``POST /api/inventory/properties`` ``{"key", "label"?, "type"?, "unit"?, "choices"?, "roles"?, "hint"?}``,
  ``PATCH /api/inventory/properties/<key>``, ``DELETE /api/inventory/properties/<key>``: custom ones,
  admins (``settings.manage``), since a type decides what everyone may type in.
"""
from flask import Blueprint, g, jsonify, request

from integrations import events

from .. import audit, property_catalog
from ..store import load_data
from .inventory_groups import _saved

bp = Blueprint('property_catalog', __name__)


def _changed(what, key):
    audit.record('inventory', what, user=g.get('audit_user'), target=key[:120])
    events.publish('inventory.changed', {})


@bp.route('/api/inventory/properties', methods=['GET'])
def list_properties():
    return jsonify({'properties': property_catalog.catalog(load_data()), 'types': list(property_catalog.TYPES)})


@bp.route('/api/inventory/properties', methods=['POST'])
def create_property():
    body = request.get_json(silent=True) or {}
    found, err = _saved(lambda data: property_catalog.save(data, body))
    if err:
        return err
    _changed('Defined an inventory property', found['key'])
    return jsonify(found), 201


@bp.route('/api/inventory/properties/<key>', methods=['PATCH'])
def update_property(key):
    body = request.get_json(silent=True) or {}
    found, err = _saved(lambda data: property_catalog.save(data, body, key))
    if err:
        return err
    _changed('Changed an inventory property', found['key'])
    return jsonify(found)


@bp.route('/api/inventory/properties/<key>', methods=['DELETE'])
def delete_property(key):
    _, err = _saved(lambda data: property_catalog.delete(data, key))
    if err:
        return err
    _changed('Removed an inventory property', key)
    return jsonify({'ok': True})
