"""Discovery areas from plugins (issue #968, docs/plugin-spec.md#discovery).

A plugin lists areas under ``discovery:`` (floorbit/plugins/discovery.py). Each one is a discovery
action like the built-in ones (inventory_discovery.ACTIONS), with the id ``<plugin>.<area>``: its
own schedule an admin can change, Run now, and its last run. A run asks the plugin's agent part
``discover(area, devices)`` through the agent, checks what comes back (shape, size, privacy) and
puts it where the built-in areas put theirs:

- ``identity``: the device's fields, by discovery's fill rules (hand values win), its reading
  next to the field, and drift where the device and the inventory disagree.
- ``networks``, ``optics``, ``poe``, ``routes``: the device's discovered VLANs, networks,
  transceivers, PoE budget and routes, where the monitoring source has none, and the entries.
- an area of the plugin's own: ``auto.<area>.<field>`` properties of the device.

Which source decides when the monitoring source and a plugin both read an area is #965's.
"""
from __future__ import annotations

import json

from . import inventory_discovery

KEY = 'inventory_plugin_facts'          # {device id: {area id: {facts, at}}}
BATCH = 25                              # devices per call: a call has CALL_TIMEOUT seconds
DEVICE_MAX_BYTES = 64 * 1024            # one device's facts for one area, as JSON
VALUE_MAX = 200
LIST_MAX = 100
# Built-in area: the keys it keeps per device (inventory_discovery's record).
KEYS = {'networks': ('vlans', 'networks', 'svis'), 'optics': ('transceivers',), 'poe': ('poe',),
        'routes': ('routes',), 'identity': ()}


def _registry():
    from . import agent_plugins
    return agent_plugins._registry()


def _specs(registry=None):
    from . import agent_plugins
    try:
        return [s for s in agent_plugins.agent_specs(registry) if s.manifest.get('discovery')]
    except Exception as exc:  # noqa: BLE001 - no plugin areas is safe: the built-in ones still run
        print(f'[discovery] plugin areas: {exc}')
        return []


def areas(registry=None):
    """Every area the plugins that are on add, in plugin order."""
    out = []
    for spec in _specs(registry):
        for entry in spec.manifest.get('discovery') or []:
            out.append({'id': f"{spec.id}.{entry['area']}", 'plugin': spec.id, 'plugin_name': spec.name,
                        'area': entry['area'], 'name': entry['name'], 'builtin': entry['builtin'],
                        'roles': tuple(entry['roles']), 'platforms': tuple(entry.get('platforms') or ()),
                        'fields': tuple(entry.get('fields') or ()), 'minutes': entry['minutes'],
                        'privacy': entry['privacy'], 'keys': KEYS.get(entry['area'], ())})
    return out


def area(area_id, registry=None):
    return next((a for a in areas(registry) if a['id'] == area_id), None)


def applies(a, dev):
    """Whether the area is about this device: its role, and its platform when the area names some."""
    if (dev.get('role') or 'switch') not in a['roles']:
        return False
    if not a['platforms']:
        return True
    platform = f"{dev.get('platform') or ''} {dev.get('os') or ''}".lower()
    return any(p in platform for p in a['platforms'])


# ── what comes back ─────────────────────────────────────────────────────────────────────────

def _scalar(value):
    if isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        text = ' '.join(value.split())
        return text[:VALUE_MAX] if text else None
    return None


def _own(a, raw):
    """An area of the plugin's own: a flat mapping of its fields to a value or a list of values."""
    out = {}
    for key, value in raw.items():
        key = str(key)
        if a['fields'] and key not in a['fields']:
            continue
        from .plugins.discovery import FIELD_RE
        if not FIELD_RE.match(key):
            continue
        if isinstance(value, list):
            items = [v for v in (_scalar(v) for v in value[:LIST_MAX]) if v is not None]
            if items:
                out[key] = items
        else:
            value = _scalar(value)
            if value is not None:
                out[key] = value
    return out


def clean(a, dev, raw):
    """What one device's facts become for an area, or (None, why) when they are refused."""
    if not isinstance(raw, dict):
        return None, 'not a mapping'
    try:
        size = len(json.dumps(raw, default=str))
    except (TypeError, ValueError):
        return None, 'not JSON'
    if size > DEVICE_MAX_BYTES:
        return None, f'larger than {DEVICE_MAX_BYTES // 1024} KB'
    if a['privacy'] == 'aggregate':
        from .plugins.agent import personal_data
        if personal_data(raw):
            return None, 'holds an address but the area is aggregate'
    row = {'facts': raw}
    kind = a['area'] if a['builtin'] else None
    if kind == 'identity':
        return {'fields': inventory_discovery.fields_of(row),
                'descr': ' '.join(str(raw.get('descr') or '').split())[:300]}, ''
    if kind == 'networks':
        return inventory_discovery.networks_of(row), ''
    if kind == 'optics':
        return {'transceivers': inventory_discovery.optics_of(row, dev['name'])}, ''
    if kind == 'poe':
        return {'poe': inventory_discovery.poe_of(row)}, ''
    if kind == 'routes':
        return {'routes': inventory_discovery.routes_of(row)}, ''
    return {'values': _own(a, raw)}, ''


# ── a run ────────────────────────────────────────────────────────────────────────────────────

def _ask(a, ids):
    """{device id: raw facts} from the agents, and the first error when none answered."""
    from . import agent_plugins
    from .plugins.base import PluginError
    spec = next((s for s in _specs() if s.id == a['plugin']), None)
    if spec is None:
        return {}, 'The plugin is off.'
    found, error = {}, ''
    for start in range(0, len(ids), BATCH):
        part = ids[start:start + BATCH]
        try:
            answers = agent_plugins.ask(spec, 'call', 'discover',
                                        {'area': a['area'], 'devices': part, 'privacy': a['privacy']})
        except PluginError as exc:
            return found, str(exc)[:300]
        answered = False
        for answer in answers:
            facts = (answer.get('result') or {}).get('facts') if isinstance(answer.get('result'), dict) else None
            if not isinstance(facts, dict):
                error = error or str(answer.get('error') or 'The agent sent no facts.')[:300]
                continue
            answered = True
            # Several agents (two in a hall): the first that read a device.
            for dev_id in part:
                if dev_id not in found and isinstance(facts.get(dev_id), dict) and facts[dev_id]:
                    found[dev_id] = facts[dev_id]
        if answered:
            error = ''
    return found, error


def run(only=None, device_ids=None, registry=None):
    """Run the plugin areas ``only`` names (all when None), on every device they are about or only
    on ``device_ids``. Returns ``{at, areas: {id: {devices, changed, error?, refused?}}}``."""
    from . import inventory
    from .blueprints.inventory import data_lock
    from .store import load_data, save_data
    todo = [a for a in areas(registry) if only is None or a['id'] in only]
    report = {'at': inventory.now(), 'areas': {}}
    if not todo:
        return report
    data = load_data()
    asked = {}
    for a in todo:
        devs = [d for d in inventory.devices(data) if applies(a, d) and (device_ids is None or d['id'] in device_ids)]
        done = report['areas'][a['id']] = {'devices': 0, 'changed': 0}
        if not devs:
            continue
        # Outside the lock: a call through the agent takes seconds.
        found, error = _ask(a, [d['id'] for d in devs])
        if error and not found:
            done['error'] = error
        asked[a['id']] = (a, found)
    with data_lock:
        data = load_data()
        now = report['at']
        store = data.get(KEY) if isinstance(data.get(KEY), dict) else {}
        store = {i: v for i, v in store.items() if isinstance(v, dict) and inventory.find(data, i) is not None}
        entries = False
        for area_id, (a, found) in asked.items():
            done = report['areas'][area_id]
            for dev_id, raw in found.items():
                dev = inventory.find(data, dev_id)
                if dev is None:
                    continue
                facts, why = clean(a, dev, raw)
                if facts is None:
                    done.setdefault('refused', []).append({'device': dev['name'], 'why': why})
                    continue
                done['devices'] += 1
                record = store.setdefault(dev_id, {})
                if (record.get(area_id) or {}).get('facts') != facts:
                    done['changed'] += 1
                    entries = entries or a['area'] in ('networks', 'optics')
                record[area_id] = {'facts': facts, 'at': now}
                if a['area'] == 'identity' and a['builtin']:
                    _identity(data, dev, a, facts, now)
            if done.get('refused'):
                done['refused'] = done['refused'][:20]
        data[KEY] = store
        if entries:
            inventory_discovery._entries(data, inventory_discovery.found_records(data), report)
        if device_ids is None:
            # Each area's last run moves its clock, as the built-in actions' do; a run for a few doesn't.
            runs = data.setdefault(inventory_discovery.RUNS, {})
            for area_id, done in report['areas'].items():
                runs[area_id] = {'at': now, 'devices': done['devices'], 'changed': done['changed'],
                                 **({'error': done['error']} if done.get('error') else {})}
        save_data(data)
    for area_id, done in report['areas'].items():
        if done.get('error'):
            print(f"[discovery] {area_id}: {done['error']}")
    return report


def _identity(data, dev, a, facts, now):
    """The plugin's reading of the device: its fields by the fill rules, the reading next to each
    field, and drift where they disagree."""
    from . import inventory, inventory_properties
    values = facts.get('fields') or {}
    inventory_properties.record_readings(data, dev['id'], a['plugin'], values, {'sysDescr': facts.get('descr')}, now)
    changed, _kept = inventory_discovery.fill(dev, values, inventory_discovery.fed_key(a['plugin']))
    if changed:
        dev['updated_at'] = inventory.now()
    rows = [{'kind': 'field', 'field': f, 'configured': dev.get(f), 'actual': values[f], 'source': a['plugin']}
            for f in inventory_discovery.FIELDS
            if values.get(f) and dev.get(f) and not inventory_discovery._same(f, dev.get(f), values[f])]
    drift = data.get('inventory_drift') if isinstance(data.get('inventory_drift'), dict) else {}
    old = [r for r in drift.get(dev['id']) or [] if isinstance(r, dict)]
    mine = inventory_discovery._since(rows, [r for r in old if r.get('source') == a['plugin']], now)
    rest = [r for r in old if r.get('source') != a['plugin']]
    if mine or rest:
        drift[dev['id']] = rest + mine
    else:
        drift.pop(dev['id'], None)
    data['inventory_drift'] = drift


# ── what the device page shows ──────────────────────────────────────────────────────────────

def facts_of(data, device_id):
    """{area id: {facts, at}} the plugins read from one device."""
    store = data.get(KEY) if isinstance(data.get(KEY), dict) else {}
    found = store.get(device_id)
    return found if isinstance(found, dict) else {}


def builtin_fill(data, device_id, record):
    """The built-in keys the monitoring source has none of, from the plugins that read them (in
    plugin order). ``record``: discovery's own for the device."""
    out = dict(record)
    for area_id, got in sorted(facts_of(data, device_id).items()):
        area_name = area_id.split('.', 1)[-1]
        facts = got.get('facts') if isinstance(got, dict) else None
        if area_name not in KEYS or area_name == 'identity' or not isinstance(facts, dict):
            continue
        for key in KEYS[area_name]:
            if not out.get(key) and facts.get(key):
                out[key] = facts[key]
                out['at'] = out.get('at') or got.get('at')
    return out


def own_properties(data, device_id):
    """``auto.<area>.<field>``: what the plugins' own areas read, {key: {value, source, seen}}."""
    out = {}
    for area_id, got in sorted(facts_of(data, device_id).items()):
        plugin, _, area_name = area_id.partition('.')
        facts = got.get('facts') if isinstance(got, dict) else None
        if area_name in KEYS or not isinstance(facts, dict):
            continue
        for field, value in sorted((facts.get('values') or {}).items()):
            out.setdefault(f'auto.{area_name}.{field}', {'value': value, 'source': plugin, 'seen': got.get('at')})
    return out
