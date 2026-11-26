"""One device's properties in three levels, the way LogicMonitor shows them (issue #965):

- ``system.*``: the device's own fields. Each one is ``{value, set_by, sources}``: the value every
  view uses, who set it (``hand``, ``discovery`` or the feeding plugin, such as ``netbox``), and what
  each source last read for it, so a disagreement can be seen next to the value.
- ``auto.*``: what discovery found that has no field of its own (the VLAN and optic counts, the PoE
  budget, sysDescr, a plugin area's fields as ``auto.<area>.<field>``), each ``{value, source, seen}``.
- no prefix: the custom properties people set, each ``{value, from}``, inherited from tags, groups
  and the device type (inventory_scope.resolve).

A view only: the fields, ``fed``, ``locked``, discovery's records and the readings are where the data
lives; nothing here is stored.
"""
from . import inventory

# The fields shown as system.*: everything a device is, without its free text notes.
SYSTEM = tuple(f for f in inventory.FIELDS if f != 'notes')
MAX_READINGS = 5000


def record_readings(data, dev_id, source, values, row, at):
    """Keep what ``source`` last read for one device: its fields as discovery saw them (before the
    fill rules), the name and address it answered with, and its sysDescr."""
    if not source:
        return
    store = data.setdefault('inventory_readings', {})
    if dev_id not in store and len(store) >= MAX_READINGS:
        return
    fields = {k: v for k, v in values.items() if k in SYSTEM and v not in (None, '')}
    sys_name = str(row.get('sysName') or row.get('hostname') or '').strip()
    if sys_name:
        fields['name'] = sys_name[:inventory.LIMITS['name']]
    ip = str(row.get('ip') or '').strip()
    if ip:
        fields['mgmt_ip'] = ip[:inventory.LIMITS['mgmt_ip']]
    facts = row.get('facts') if isinstance(row.get('facts'), dict) else {}
    descr = ' '.join(str(facts.get('descr') or row.get('sysDescr') or '').split())
    store.setdefault(dev_id, {})[str(source)[:40]] = {'fields': fields, 'descr': descr[:300], 'at': at}


def forget(data, keep_ids):
    """Drop the readings of devices that are gone."""
    store = data.get('inventory_readings')
    if isinstance(store, dict):
        for dev_id in [i for i in store if i not in keep_ids]:
            store.pop(dev_id, None)


def _set_by(dev, field, value):
    if value in (None, ''):
        return ''
    if field in (dev.get('locked') or []):
        return 'hand'
    fed = dev.get('fed') or {}
    if (fed.get('discovery') or {}).get(field) == value:
        return 'discovery'
    for plugin in sorted(dev.get('refs') or {}):
        if (fed.get(plugin) or {}).get(field) == value:
            return plugin
    for key in sorted(fed):
        # A plugin's discovery area (plugin_discovery.py): named by its plugin.
        if key.startswith('discovery:') and (fed.get(key) or {}).get(field) == value:
            return key.split(':', 1)[1]
    return 'hand'


def view(data, dev, resolved=None):
    """``{system: {...}, auto: {...}, custom: {...}}`` for one device (see the top)."""
    from . import inventory_discovery, inventory_scope
    readings = ((data.get('inventory_readings') or {}).get(dev['id']) or {})
    fed = dev.get('fed') or {}
    system = {}
    for field in SYSTEM:
        value = dev.get(field)
        sources = {}
        # A feeding plugin's value (NetBox) is a reading too; discovery's own is in the readings.
        for plugin in sorted(dev.get('refs') or {}):
            if field in (fed.get(plugin) or {}):
                sources[plugin] = fed[plugin][field]
        for source, r in sorted(readings.items()):
            if field in (r.get('fields') or {}):
                sources[source] = r['fields'][field]
        system[f'system.{field}'] = {'value': value, 'set_by': _set_by(dev, field, value), 'sources': sources}
    system['system.group'] = {'value': dev.get('group_id') or '', 'set_by': 'hand' if dev.get('group_id') else '',
                              'sources': {}}
    system['system.tags'] = {'value': list(dev.get('tags') or []), 'set_by': 'hand' if dev.get('tags') else '',
                             'sources': {}}

    auto = {}
    found = inventory_discovery.discovered_of(data, dev['id'])
    at = found.get('at')

    def put(key, value, source='discovery', seen=at):
        if value not in (None, '', [], {}):
            auto[f'auto.{key}'] = {'value': value, 'source': source, 'seen': seen}

    put('vlans.count', len(found.get('vlans') or []) or None)
    put('networks.count', len(found.get('networks') or []) or None)
    put('optics.count', len(found.get('transceivers') or []) or None)
    put('routes.count', len(found.get('routes') or []) or None)
    gateway = next((r.get('next_hop') for r in found.get('routes') or []
                    if isinstance(r, dict) and r.get('network') == '0.0.0.0/0'), None)
    put('routes.default_gateway', gateway)
    poe = found.get('poe') if isinstance(found.get('poe'), dict) else {}
    put('poe.budget_w', poe.get('budget_w'))
    put('poe.used_w', poe.get('used_w'))
    put('interfaces.count', len(dev.get('interfaces') or []) or None, 'inventory', dev.get('updated_at'))
    for source, r in sorted(readings.items()):
        if r.get('descr') and 'auto.snmp.sysdescr' not in auto:
            put('snmp.sysdescr', r['descr'], source, r.get('at'))
    from . import plugin_discovery
    for key, entry in plugin_discovery.own_properties(data, dev['id']).items():
        auto.setdefault(key, entry)

    if resolved is None:
        resolved = inventory_scope.resolve(data, dev, inventory_scope._registry())
    custom = {k: {'value': v.get('value'), 'from': v.get('from')}
              for k, v in sorted((resolved.get('properties') or {}).items())}
    return {'system': system, 'auto': dict(sorted(auto.items())), 'custom': custom}
