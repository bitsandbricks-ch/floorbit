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
from . import options
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
    out['runs_here'] = runs_here(data, dev)
    out['connected'] = connected(data, dev)
    from .. import inventory_discovery
    out['drift'] = inventory_discovery.drift_of(data, dev['id'])
    out['discovered'] = inventory_discovery.discovered_of(data, dev['id'])
    from .. import inventory_properties
    out['property_view'] = inventory_properties.view(data, dev, resolved)
    return out


def connected(data, dev):
    """What is wired to the device, from the pages that keep it: cables on its ports (by name),
    circuits that feed it (by id) and internet lines that come in on it (by name)."""
    from .. import cables, power, services
    name = dev['name'].lower()
    wired = [{'id': c.get('id'), 'label': c.get('label') or '', 'port': c.get('port') or '',
              'panel': c.get('panel') or '', 'panel_port': c.get('panel_port') or '', 'seat': c.get('seat') or '',
              'type': c.get('type') or '', 'speed': c.get('speed')}
             for c in cables.all_cables(data) if str(c.get('switch') or '').lower() == name]
    boards, circuits = power._stored(data)
    board_names = {b.get('id'): b.get('name') or '' for b in boards}
    fed = [{'id': c.get('id'), 'name': c.get('name') or '', 'board': board_names.get(c.get('board'), ''),
            'phase': c.get('phase') or '', 'rating_a': c.get('rating_a')}
           for c in circuits if dev['id'] in (c.get('switches') or [])]
    lines = [{'id': u.get('id'), 'name': u.get('name') or '', 'port': u.get('port') or '',
              'capacity_mbps': u.get('capacity_mbps')}
             for u in services._stored(data)['uplinks'] if str(u.get('device') or '').lower() == name]
    wired.sort(key=lambda c: options._natural(c['port']))
    from .. import inventory_types
    return {'cables': wired, 'circuits': fed, 'uplinks': lines,
            'entries': inventory_types.linked_to(data, dev['name'])}


def runs_here(data, dev):
    """What goes down with this device: VMs whose host it is, and game servers that run on it or
    on one of those VMs."""
    name = dev['name'].lower()
    vms = [d for d in inventory.devices(data) if (d.get('host') or '').lower() == name and d['id'] != dev['id']]
    on = {name} | {v['name'].lower() for v in vms}
    games = [s for s in data.get('game_servers') or [] if (s.get('runs_on') or '').lower() in on]
    return ([{'kind': 'device', 'id': v['id'], 'name': v['name'], 'role': v.get('role') or ''} for v in vms]
            + [{'kind': 'game-server', 'id': s.get('id'), 'name': s.get('name'), 'via': s.get('runs_on')}
               for s in games])


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
