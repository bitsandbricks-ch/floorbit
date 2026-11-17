"""Inventory groups, tags, defaults, credentials and login blocks (floorbit/inventory_scope.py).

- ``GET /api/inventory/groups``: groups, tags, defaults and the features a device can have.
- ``POST /api/inventory/groups``, ``PATCH`` / ``DELETE /api/inventory/groups/<id>``: editors.
- ``POST /api/inventory/tags``, ``PATCH`` / ``DELETE /api/inventory/tags/<id>``: editors.
- ``PATCH /api/inventory/defaults``: properties and features for every device. Editors.
- ``GET /api/inventory/credentials``: what is set where, never a secret. Editors.
- ``PUT /api/inventory/credentials``: set or replace one; ``DELETE /api/inventory/credentials/<id>``.
  Admins (``settings.manage``), like stored switch logins.
- ``GET /api/inventory/blocks``: devices blocked after a failed login. ``POST /api/inventory/blocks/clear``
  ``{"device_id", "credential_id"?}``: techs (``ports.act``).

Every change is audit-logged and tells the agents their plugins' devices may have changed.
"""
from flask import Blueprint, g, jsonify, request

from integrations import events

from .. import audit, inventory, inventory_scope, vault
from ..store import load_data, save_data
from .inventory import data_lock

bp = Blueprint('inventory_groups', __name__)


def _registry():
    return inventory_scope._registry()


def _feature_catalog():
    registry = _registry()
    specs = getattr(registry, 'specs', {}) or {}
    out = [{'id': f, 'core': True, 'name': f, 'default': True} for f in inventory_scope.CORE_FEATURES]
    for pid in inventory_scope.known_features(registry):
        if pid in inventory_scope.CORE_FEATURES:
            continue
        spec = specs.get(pid)
        out.append({'id': pid, 'core': False, 'name': getattr(spec, 'name', pid), 'default': False,
                    'agent': bool(getattr(spec, 'agent', None))})
    return out


def overview(data):
    counts = {}
    for dev in inventory.devices(data):
        counts[dev.get('group_id')] = counts.get(dev.get('group_id'), 0) + 1
    tag_counts = {}
    for holder in [*inventory.devices(data), *inventory_scope.groups(data)]:
        for t in holder.get('tags') or []:
            tag_counts[t] = tag_counts.get(t, 0) + 1
    creds = {}
    for c in inventory_scope.credential_listing(data):
        creds.setdefault((c['owner_type'], c['owner_id']), []).append(c['kind'])
    return {
        'groups': [{**g, 'devices': counts.get(g['id'], 0), 'credentials': creds.get(('group', g['id']), [])}
                   for g in inventory_scope.groups(data)],
        'tags': [{**t, 'used': tag_counts.get(t['id'], 0), 'credentials': creds.get(('tag', t['id']), [])}
                 for t in inventory_scope.tags(data)],
        'defaults': {**inventory_scope.defaults(data), 'credentials': creds.get(('defaults', 'defaults'), [])},
        'features': _feature_catalog(),
        'icons': list(inventory.ICONS),
        'credential_kinds': list(inventory_scope.KINDS),
        'auth_protocols': list(inventory_scope.AUTH_PROTOCOLS),
        'priv_protocols': list(inventory_scope.PRIV_PROTOCOLS),
        'ungrouped': counts.get(None, 0),
    }


def _changed(what, name, changed):
    if changed:
        audit.record('inventory', what, user=g.get('audit_user'), target=f"{name} ({', '.join(changed)})"[:120])
        events.publish('inventory.changed', {})
        inventory_scope.reload_agents()


def _saved(fn, *args):
    """Run a change on data.json under the lock; (result, None) or (None, error response)."""
    with data_lock:
        data = load_data()
        try:
            result = fn(data, *args)
        except KeyError:
            return None, (jsonify({'error': 'Not found.'}), 404)
        except (inventory_scope.ScopeError, inventory.InventoryError) as exc:
            return None, (jsonify({'error': str(exc)}), getattr(exc, 'status', 400))
        except vault.VaultError as exc:
            return None, (jsonify({'error': str(exc)}), 500)
        save_data(data)
    return result, None


@bp.route('/api/inventory/groups', methods=['GET'])
def list_groups():
    return jsonify(overview(load_data()))


@bp.route('/api/inventory/groups', methods=['POST'])
def create_group():
    body = request.get_json(silent=True) or {}
    result, err = _saved(lambda d: inventory_scope.save_group(d, body, None, _registry()))
    if err:
        return err
    grp = result[0]
    _changed('Added an inventory group', grp['name'], ['added'])
    return jsonify(grp), 201


@bp.route('/api/inventory/groups/<group_id>', methods=['PATCH'])
def update_group(group_id):
    body = request.get_json(silent=True) or {}
    result, err = _saved(lambda d: inventory_scope.save_group(d, body, group_id, _registry()))
    if err:
        return err
    grp, changed = result
    _changed('Changed an inventory group', grp['name'], changed)
    return jsonify({**grp, 'changed': changed})


@bp.route('/api/inventory/groups/<group_id>', methods=['DELETE'])
def delete_group(group_id):
    result, err = _saved(lambda d: inventory_scope.delete_group(d, group_id))
    if err:
        return err
    grp, moved = result
    _changed('Removed an inventory group', grp['name'], ['removed'])
    return jsonify({'ok': True, 'moved': moved})


@bp.route('/api/inventory/tags', methods=['POST'])
def create_tag():
    body = request.get_json(silent=True) or {}
    result, err = _saved(lambda d: inventory_scope.save_tag(d, body, None, _registry()))
    if err:
        return err
    tag = result[0]
    _changed('Added an inventory tag', tag['name'], ['added'])
    return jsonify(tag), 201


@bp.route('/api/inventory/tags/<tag_id>', methods=['PATCH'])
def update_tag(tag_id):
    body = request.get_json(silent=True) or {}
    result, err = _saved(lambda d: inventory_scope.save_tag(d, body, tag_id, _registry()))
    if err:
        return err
    tag, changed = result
    _changed('Changed an inventory tag', tag['name'], changed)
    return jsonify({**tag, 'changed': changed})


@bp.route('/api/inventory/tags/<tag_id>', methods=['DELETE'])
def delete_tag(tag_id):
    tag, err = _saved(lambda d: inventory_scope.delete_tag(d, tag_id))
    if err:
        return err
    _changed('Removed an inventory tag', tag['name'], ['removed'])
    return jsonify({'ok': True})


@bp.route('/api/inventory/defaults', methods=['PATCH'])
def update_defaults():
    body = request.get_json(silent=True) or {}
    result, err = _saved(lambda d: inventory_scope.save_defaults(d, body, _registry()))
    if err:
        return err
    current, changed = result
    _changed('Changed the inventory defaults', 'All devices', changed)
    return jsonify({**current, 'changed': changed})


@bp.route('/api/inventory/credentials', methods=['GET'])
def list_credentials():
    return jsonify({'credentials': inventory_scope.credential_listing(load_data())})


@bp.route('/api/inventory/credentials', methods=['PUT'])
def set_credential():
    body = request.get_json(silent=True) or {}
    cred, err = _saved(lambda d: inventory_scope.set_credential(d, body, g.get('audit_user')))
    if err:
        return err
    names = {c['id']: c['owner_name'] for c in inventory_scope.credential_listing(load_data())}
    where = f"{cred['owner_type']} {names.get(cred['id'], '?')}"
    audit.record('credentials', f"Set the {cred['kind']} credential on {where}",
                 user=g.get('audit_user'), target=cred['username'] or cred['kind'])
    events.publish('inventory.changed', {})
    inventory_scope.reload_agents()
    return jsonify(cred)


@bp.route('/api/inventory/credentials/<cred_id>', methods=['DELETE'])
def delete_credential(cred_id):
    names = {c['id']: c['owner_name'] for c in inventory_scope.credential_listing(load_data())}
    cred, err = _saved(lambda d: inventory_scope.delete_credential(d, cred_id))
    if err:
        return err
    where = f"{cred['owner_type']} {names.get(cred_id, '?')}"
    audit.record('credentials', f"Removed the {cred['kind']} credential on {where}",
                 user=g.get('audit_user'), target=cred['username'] or cred['kind'])
    events.publish('inventory.changed', {})
    inventory_scope.reload_agents()
    return jsonify({'ok': True})


@bp.route('/api/inventory/blocks', methods=['GET'])
def list_blocks():
    return jsonify({'blocks': inventory_scope.blocks(load_data())})


@bp.route('/api/inventory/blocks/clear', methods=['POST'])
def clear_block():
    body = request.get_json(silent=True) or {}
    if not body.get('device_id'):
        return jsonify({'error': 'Say which device.'}), 400
    try:
        cleared = inventory_scope.clear_block(str(body['device_id']), body.get('credential_id') or None,
                                              g.get('audit_user'))
    except KeyError:
        return jsonify({'error': 'No such device.'}), 404
    return jsonify({'cleared': cleared})
