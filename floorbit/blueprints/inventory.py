"""The inventory API and page (floorbit/inventory.py has the rules).

- ``GET /api/inventory``: every device (``?hidden=1`` includes hidden ones), the plugins that
  feed it and their last sync. Viewers and up.
- ``POST /api/inventory``, ``PATCH`` / ``DELETE /api/inventory/<id>``: editors and up.
- ``POST /api/inventory/sync``: run every inventory plugin that's on now, then discovery
  (floorbit/inventory_discovery.py). Editors and up.
- ``GET /api/inventory/log``: the last syncs. Editors and up.
- ``GET /api/inventory/drift``: where devices and the inventory disagree (discovery). Viewers and up.
- ``GET /api/inventory/discovery``: discovery's actions per kind of device, their schedules and last
  runs. Viewers and up. ``PUT /api/inventory/discovery/actions/<id>``: an action's schedule (admins).
  ``POST /api/inventory/discovery/run``: run now, all or some actions, all devices or one (editors).
"""
import threading

from flask import Blueprint, current_app, jsonify, request

from .. import (
    agent_link,
    firewalls,
    inventory,
    inventory_discovery,
    inventory_schedule,
    inventory_scope,
    inventory_types,
    seat_view,
    spa,
)
from ..plugins import PluginError
from ..store import load_data, save_data

bp = Blueprint('inventory', __name__)

# data.json is read and written whole; this keeps two inventory writes from crossing.
data_lock = threading.RLock()


def _registry():
    return current_app.extensions.get('floorbit_plugins')


def _feeders():
    """The inventory plugins that are on and set up. One that isn't set up yet is no source."""
    registry = _registry()
    return [s for s in registry.feeders('inventory') if registry.set_up(s)] if registry else []


def _not_set_up():
    registry = _registry()
    return {s.id for s in registry.feeders('inventory') if not registry.set_up(s)} if registry else set()


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
    _sync_firewall_plans(registry, reports)
    return reports


def _sync_firewall_plans(registry, reports):
    """After the prefixes came in: the firewalls NetBox names on them (custom field
    ``floorbit_firewalls``) become their plans, so IPAM needs no import of its own (issue #1347).
    The outcome goes on the reports of the sources that list ranges."""
    ids = {s.id for s in firewalls.import_sources(registry) if registry.set_up(s)}
    if not ids and not agent_link.active():
        return
    try:
        added, errors = firewalls.import_from(registry, 'inventory sync')
        outcome = {'added': added, 'errors': errors}
    except firewalls.FirewallError as exc:
        outcome = {'added': 0, 'errors': [str(exc)[:300]]}
    for report in reports:
        if not report.get('error') and (report.get('base') or report.get('plugin')) in ids:
            report['firewall_ranges'] = outcome


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
    skip = _not_set_up()
    for feed in feeds:
        base = {'name': feed['name'], 'via': 'agent', 'base': feed.get('base', feed['plugin'])}
        if 'error' in feed and base['base'] in skip:
            continue    # the agent asked a plugin that isn't set up (NetBox without a URL): not a fault
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


def _set_up(spec):
    """Whether an inventory plugin has what it needs to sync. NetBox needs its URL and token; the
    plugin spec has no "configured" for inventory plugins, so the others count once they are on."""
    if spec.id != 'netbox':
        return True
    settings = _registry().settings_of(spec)
    return bool(settings.get('url') and settings.get('token'))


def _sources(data):
    log = inventory.sync_log(data)
    out = []
    for spec in _feeders():
        last = next((r for r in log if r.get('plugin') == spec.id), None)
        if last is None and not _set_up(spec):
            continue        # NetBox without a URL: "not synced yet" would read as something to fix
        via = ' (local agent)' if last and last.get('via') == 'agent' else ''
        out.append({'id': spec.id, 'name': spec.name + via, 'last_sync': last})
    if agent_link.active():
        known, via_agent, skip = {o['id'] for o in out}, False, _not_set_up()
        for r in log:       # newest first: the agent's feeds as of its last sync
            if r.get('via') != 'agent' or r.get('plugin') == 'agent':
                continue
            via_agent = True
            if r.get('error') and (r.get('base') or r.get('plugin')) in skip:
                continue
            if r.get('plugin') not in known:
                known.add(r['plugin'])
                out.append({'id': r['plugin'], 'name': f"{r.get('name') or r['plugin']} (local agent)", 'last_sync': r})
        if not via_agent:   # nothing came from it yet: shown only when asking it failed
            last = next((r for r in log if r.get('plugin') == 'agent'), None)
            if last:
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


def _live():
    """What the list shows live per device: the status monitor's state (None before its first poll)
    and the ports up of all, from the attention watch's last read of the placed switches."""
    states = seat_view.monitor_statuses()
    watch = current_app.extensions.get('floorbit_attention')
    ports = {}
    for (switch, _port), read in (getattr(watch, 'port_reads', None) or {}).items():
        row = ports.setdefault(switch, {'up': 0, 'total': 0})
        row['total'] += 1
        row['up'] += read.get('state') in ('up', 'errors')
    return states, ports


@bp.route('/api/inventory', methods=['GET'])
def list_devices():
    data = load_data()
    hidden = request.args.get('hidden') in ('1', 'true')
    drift = data.get('inventory_drift') if isinstance(data.get('inventory_drift'), dict) else {}
    states, ports = _live()
    return jsonify({'devices': [{**inventory.public(d), 'drift': len(drift.get(d['id']) or []),
                                 'state': (states.get(d['id']) or {}).get('status') if states is not None else None,
                                 'ports': ports.get(str(d['name']).lower())}
                                for d in inventory.devices(data, include_hidden=hidden)],
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
        return jsonify({'error': 'No inventory source is set up. Set one up under Settings > Plugins.'}), 400
    with inventory_schedule.running:   # a scheduled sync that's under way finishes first
        reports = run_sync()
    if discover:
        with inventory_discovery.running:
            reports.append(inventory_discovery.run())
    return jsonify({'reports': reports, 'sources': _sources(load_data())})


@bp.route('/api/inventory/discovery', methods=['GET'])
def discovery_actions():
    """What discovery does per kind of device, each action's schedule and last run."""
    data = load_data()
    return jsonify({'available': inventory_discovery.available(), 'actions': inventory_discovery.actions(data),
                    'last_run': inventory_discovery.last(data)})


@bp.route('/api/inventory/discovery/actions/<action_id>', methods=['PUT'])
def discovery_schedule(action_id):
    """An action's schedule: ``{"minutes": 30}``, 0 for off, null for the default. Admins."""
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or 'minutes' not in body:
        return jsonify({'error': 'Send the minutes between runs (0 for off, null for the default).'}), 400
    with data_lock:
        data = load_data()
        if inventory_discovery.action(action_id) is None:
            return jsonify({'error': 'No such discovery action.'}), 404
        problem = inventory_discovery.set_minutes(data, action_id, body['minutes'])
        if problem:
            return jsonify({'error': problem}), 400
        save_data(data)
    return jsonify({'actions': inventory_discovery.actions(data)})


@bp.route('/api/inventory/discovery/run', methods=['POST'])
def discovery_run():
    """Run now: every action, or ``{"actions": [...]}``, on every device or ``{"device": id}``."""
    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict):
        return jsonify({'error': 'Send an object.'}), 400
    wanted = body.get('actions')
    if wanted is not None and (not isinstance(wanted, list) or not wanted
                               or any(inventory_discovery.action(a) is None for a in wanted)):
        return jsonify({'error': 'No such discovery action.'}), 400
    devices = None
    if body.get('device') is not None:
        if inventory.find(load_data(), str(body['device'])) is None:
            return jsonify({'error': 'No such device'}), 404
        devices = {str(body['device'])}
    if not inventory_discovery.available():
        return jsonify({'error': 'No monitoring source is set up, so there is nothing to discover.'}), 400
    with inventory_discovery.running:
        report = inventory_discovery.run(set(wanted) if wanted else None, devices)
    return jsonify({'report': report, 'actions': inventory_discovery.actions(load_data())})


@bp.route('/api/inventory/drift', methods=['GET'])
def drift_list():
    """Where devices and the inventory disagree, from the last discovery run (inventory_discovery.py)."""
    data = load_data()
    names = {d['id']: d['name'] for d in inventory.devices(data, include_hidden=True)}
    found = data.get('inventory_drift') if isinstance(data.get('inventory_drift'), dict) else {}
    return jsonify({'devices': [{'id': i, 'name': names[i], 'drift': rows} for i, rows in sorted(found.items())
                                if i in names],
                    'last_run': inventory_discovery.last(data)})


@bp.route('/api/inventory/log', methods=['GET'])
def sync_history():
    return jsonify({'log': inventory.sync_log(load_data(), request.args.get('plugin') or None)})
