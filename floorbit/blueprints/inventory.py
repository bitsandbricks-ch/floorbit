"""The inventory API and page (floorbit/inventory.py has the rules).

- ``GET /api/inventory``: every device (``?hidden=1`` includes hidden ones), the plugins that
  feed it and their last sync. Viewers and up.
- ``POST /api/inventory``, ``PATCH`` / ``DELETE /api/inventory/<id>``: editors and up.
- ``POST /api/inventory/sync``: run every inventory plugin that's on now, then discovery
  (floorbit/inventory_discovery.py). Editors and up.
- ``GET /api/inventory/log``: the last syncs. Editors and up.
"""
import threading

from flask import Blueprint, current_app, jsonify, request

from .. import agent_link, inventory, inventory_discovery, inventory_schedule, inventory_scope, inventory_types, spa
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
    # A hosted Floorbit: the agent first. A plugin it feeds (NetBox) is skipped here, since this
    # side can't reach it and would only log a failed sync every time.
    reports = _sync_from_agent() if agent_link.active() else []
    fed = {r.get('base') or r['plugin'] for r in reports if not r.get('error')}
    for spec in _feeders():
        if spec.id in fed or not agent_link.may_call_here(spec):
            continue
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
        report['entries'] = _sync_entries(registry, spec)
        reports.append(report)
    return reports


def _sync_entries(registry, spec):
    """Racks, VLANs, transceivers, power panels, ... from a plugin that has ``entries()``
    (floorbit/inventory_types.py). Its own report, or None when the plugin has none."""
    cls = spec.plugin_class()
    if cls is None or not hasattr(cls, 'entries'):
        return None
    try:
        feed, skipped = inventory_types.clean_feed(registry.call(spec, 'entries'))
    except (PluginError, inventory_scope.ScopeError) as exc:
        registry.log(spec.id, f'entries sync failed: {exc}')
        return {'error': str(exc)[:300]}
    with data_lock:
        data = load_data()
        report = inventory_types.sync_entries(data, spec.id, feed, skipped)
        save_data(data)
    registry.log(spec.id, 'entries sync: {added} added, {updated} updated, {joined} joined, '
                          '{gone} gone'.format(**report))
    return report


def _record(report):
    with data_lock:
        data = load_data()
        inventory.record_log(data, report)
        save_data(data)


def _sync_from_agent():
    """A hosted Floorbit: the local agent's inventory plugins, merged under their own ids, so
    moving from a local install to a hosted one keeps the devices (docs/agent.md)."""
    try:
        feeds = agent_link.inventory_feeds()
    except (agent_link.AgentUnavailable, agent_link.AgentError) as exc:
        report = {'plugin': 'agent', 'name': 'Local agent', 'via': 'agent', 'at': inventory.now(),
                  'error': str(exc)[:300]}
        _record(report)
        return [report]
    reports = []
    for feed in feeds:
        base = {'name': feed['name'], 'via': 'agent', 'base': feed.get('base', feed['plugin'])}
        try:
            if 'error' in feed:
                raise inventory.InventoryError(feed['error'])
            items, skipped = inventory.clean_feed(feed['items'])
        except inventory.InventoryError as exc:
            report = {'plugin': feed['plugin'], 'at': inventory.now(), 'error': str(exc)[:300], **base}
            _record(report)
            reports.append(report)
            continue
        with data_lock:
            data = load_data()
            report = inventory.sync(data, feed['plugin'], items, skipped)
            report.update(base)
            save_data(data)
        reports.append(report)
    return reports


def _sources(data):
    log = inventory.sync_log(data)
    out = []
    for spec in _feeders():
        last = next((r for r in log if r.get('plugin') == spec.id), None)
        via = ' (local agent)' if last and last.get('via') == 'agent' else ''
        out.append({'id': spec.id, 'name': spec.name + via, 'last_sync': last})
    if agent_link.active():
        known, via_agent = {o['id'] for o in out}, False
        for r in log:       # newest first: the agent's feeds as of its last sync
            if r.get('via') != 'agent' or r.get('plugin') == 'agent':
                continue
            via_agent = True
            if r.get('plugin') not in known:
                known.add(r['plugin'])
                out.append({'id': r['plugin'], 'name': f"{r.get('name') or r['plugin']} (local agent)", 'last_sync': r})
        if not via_agent:   # nothing came from it yet: show it, with its last error if any
            last = next((r for r in log if r.get('plugin') == 'agent'), None)
            out.append({'id': 'agent', 'name': 'Local agent', 'last_sync': last})
    if inventory_discovery.available():
        out.append({'id': inventory_discovery.PLUGIN, 'name': inventory_discovery.NAME,
                    'last_sync': inventory_discovery.last(data)})
    return out


@bp.route('/inventory')
@bp.route('/inventory/<path:_item>')
def inventory_page(_item=None):
    """The list, and each device's, group's, tag's and entry's own page (the React app routes them)."""
    return spa.render('Inventory')


@bp.route('/api/inventory', methods=['GET'])
def list_devices():
    data = load_data()
    hidden = request.args.get('hidden') in ('1', 'true')
    return jsonify({'devices': [inventory.public(d) for d in inventory.devices(data, include_hidden=hidden)],
                    'sources': _sources(data), 'every': inventory_schedule.every_minutes(),
                    'roles': list(inventory.ROLES), 'fields': list(inventory.FIELDS)})


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
    discover = inventory_discovery.available()
    if not _feeders() and not agent_link.active() and not discover:
        return jsonify({'error': 'No inventory source is on. Turn one on under Settings > Plugins.'}), 400
    with inventory_schedule.running:   # a scheduled sync that's under way finishes first
        reports = run_sync()
    if discover:
        with inventory_discovery.running:
            reports.append(inventory_discovery.run())
    return jsonify({'reports': reports, 'sources': _sources(load_data())})


@bp.route('/api/inventory/log', methods=['GET'])
def sync_history():
    return jsonify({'log': inventory.sync_log(load_data(), request.args.get('plugin') or None)})
