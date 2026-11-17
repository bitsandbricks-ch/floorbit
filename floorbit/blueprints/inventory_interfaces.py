"""One inventory device in detail, and its interfaces (floorbit/inventory_interfaces.py).

- ``GET /api/inventory/<id>``: the device, its interfaces, and what it inherits from its group and
  tags (properties, features, credentials: which are set and from where, never a secret; the
  credentials only for editors). Viewers and up.
- ``POST /api/inventory/<id>/interfaces`` ``{"names": "Gi1/0/1-48", <fields>}``: add by hand.
- ``PATCH`` / ``DELETE /api/inventory/<id>/interfaces/<iid>``: change or remove one.
- ``POST /api/inventory/interfaces/sync``: take the ports the monitoring source (LibreNMS,
  telemetry) knows for every device, as interfaces fed by that plugin.
Changes need ``floorplan.edit``.
"""
from flask import Blueprint, g, jsonify, request

from integrations import events

from .. import audit, inventory, inventory_interfaces, inventory_scope
from ..store import load_data, save_data
from .inventory import data_lock
from .options import _can

bp = Blueprint('inventory_interfaces', __name__)

# Only ports of these get synced from the monitoring source (it has no servers' NICs).
MONITORED_ROLES = ('switch', 'router', 'firewall', 'access-point', 'server', 'pdu')


def detail(data, dev):
    out = inventory.public(dev)
    out['interfaces'] = [inventory_interfaces.public(i) for i in inventory_interfaces.listing(dev, True)]
    resolved = inventory_scope.resolve(data, dev, inventory_scope._registry())
    if not _can('floorplan.edit'):
        resolved['credentials'] = {}
    out['resolved'] = resolved
    out['own_credentials'] = inventory_scope.credentials_of(data, 'device', dev['id']) if _can('floorplan.edit') else []
    out['blocks'] = inventory_scope.blocks(data, dev['id'])
    return out


@bp.route('/api/inventory/<device_id>', methods=['GET'])
def get_device(device_id):
    data = load_data()
    dev = inventory.find(data, device_id)
    if dev is None:
        return jsonify({'error': 'No such device'}), 404
    return jsonify(detail(data, dev))


def _edit(device_id, fn):
    with data_lock:
        data = load_data()
        dev = inventory.find(data, device_id)
        if dev is None:
            return None, None, (jsonify({'error': 'No such device'}), 404)
        try:
            result = fn(dev)
        except KeyError:
            return None, None, (jsonify({'error': 'No such interface'}), 404)
        except inventory_interfaces.InterfaceError as exc:
            return None, None, (jsonify({'error': str(exc)}), 400)
        dev['updated_at'] = inventory.now()
        save_data(data)
    events.publish('inventory.changed', {})
    return dev, result, None


@bp.route('/api/inventory/<device_id>/interfaces', methods=['POST'])
def add_interfaces(device_id):
    body = request.get_json(silent=True) or {}
    dev, added, err = _edit(device_id, lambda d: inventory_interfaces.add(d, body))
    if err:
        return err
    audit.record('inventory', f'Added {len(added)} interfaces', user=g.get('audit_user'), target=dev['name'])
    return jsonify({'added': [inventory_interfaces.public(i) for i in added]}), 201


@bp.route('/api/inventory/<device_id>/interfaces/<iface_id>', methods=['PATCH'])
def update_interface(device_id, iface_id):
    body = request.get_json(silent=True) or {}
    dev, result, err = _edit(device_id, lambda d: inventory_interfaces.update(d, iface_id, body))
    if err:
        return err
    iface, changed = result
    if changed:
        audit.record('inventory', 'Changed an interface', user=g.get('audit_user'),
                     target=f"{dev['name']} {iface['name']} ({', '.join(changed)})"[:120])
    return jsonify({**inventory_interfaces.public(iface), 'changed': changed})


@bp.route('/api/inventory/<device_id>/interfaces/<iface_id>', methods=['DELETE'])
def remove_interface(device_id, iface_id):
    names = {}

    def go(d):
        iface = inventory_interfaces.find(d, iface_id)
        names['name'] = iface['name'] if iface else '?'
        return inventory_interfaces.remove(d, iface_id)

    dev, outcome, err = _edit(device_id, go)
    if err:
        return err
    audit.record('inventory', 'Removed an interface' if outcome == 'deleted' else 'Hid an interface',
                 user=g.get('audit_user'), target=f"{dev['name']} {names['name']}")
    return jsonify({'result': outcome})


def sync_from_monitoring(names=None):
    """Every device's ports from the monitoring source, merged as interfaces. Returns the report."""
    from .. import sources
    mon = sources.monitoring()
    plugin_id = getattr(mon, 'name', '') or ''
    if not plugin_id or plugin_id == 'none' or not mon.enabled():
        return {'error': 'No monitoring source is set up, so there are no ports to take.'}
    data = load_data()
    wanted = [d for d in inventory.devices(data) if d.get('role') in MONITORED_ROLES
              and (names is None or d['name'] in names)]
    ports_of = {}
    for dev in wanted:
        try:
            ports_of[dev['id']] = [inventory_interfaces.from_monitoring(p) for p in mon.device_ports(dev['name']) or []
                                   if isinstance(p, dict) and p.get('name')]
        except Exception as exc:  # noqa: BLE001 - one switch away must not stop the rest
            print(f'[inventory] ports of {dev["name"]} failed: {exc}')
    report = {'plugin': plugin_id, 'at': inventory.now(), 'devices': 0, 'added': 0, 'updated': 0, 'gone': 0}
    with data_lock:
        data = load_data()
        for dev_id, ports in ports_of.items():
            dev = inventory.find(data, dev_id)
            if dev is None or not ports:
                continue
            counts = inventory_interfaces.merge_feed(dev, plugin_id, inventory_interfaces.clean_feed(ports))
            report['devices'] += 1
            for k in ('added', 'updated', 'gone'):
                report[k] += counts[k]
            if counts['added'] or counts['updated']:
                dev['updated_at'] = inventory.now()
        save_data(data)
    return report


@bp.route('/api/inventory/interfaces/sync', methods=['POST'])
def sync_interfaces():
    body = request.get_json(silent=True) or {}
    names = body.get('devices') if isinstance(body.get('devices'), list) else None
    report = sync_from_monitoring(names)
    if report.get('error'):
        return jsonify(report), 409
    audit.record('inventory', 'Took the interfaces from the monitoring source', user=g.get('audit_user'),
                 target=f"{report['devices']} devices, {report['added']} added")
    events.publish('inventory.changed', {})
    return jsonify(report)
