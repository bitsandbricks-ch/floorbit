"""Which source decides each discovery area, per kind of device, and where sources disagree (issue #965).

An area (identity, networks, routes, ... or a plugin's own, plugin_discovery.py) can be read by
several sources: the monitoring source (telemetry or LibreNMS) and plugins that feed it. Per kind of
device one of them **decides**:

- By default the first in a fixed order: the monitoring source, then the plugins in id order.
- An admin picks another per kind of device ("routes on firewalls come from the OPNsense plugin"),
  kept as ``discovery_deciding`` ``{role: {area: source}}``.
- Hand values and NetBox still beat every source (the fill rules, inventory_discovery.fill).

The others still count: a field the deciding source doesn't read is filled from them, and a list
it has nothing in is theirs. Where a non-deciding source reads a different value for a field,
that's a **source conflict**, shown next to drift with both sources and both values (conflicts_of,
a view over the readings: nothing extra is stored).
"""
from __future__ import annotations

MONITORING = 'monitoring'
KEY = 'discovery_deciding'
# Where an area's facts go, for the "What Floorbit reads" table.
GOES_TO = {'identity': 'fields', 'interfaces': 'interfaces', 'networks': 'discovered.networks',
           'optics': 'discovered.transceivers', 'poe': 'discovered.poe', 'routes': 'discovered.routes'}


def _monitoring():
    """(id, name) of the monitoring source, or None when there is none."""
    from . import inventory_discovery, sources
    if not inventory_discovery.available():
        return None
    mon = sources.monitoring()
    spec = (getattr(sources.registry, 'specs', None) or {}).get(mon.name) if sources.registry else None
    return mon.name, (spec.name if spec else mon.name)


def sources_for(role, area, mon=None, areas=None):
    """The sources that read ``area`` on devices of ``role``, in the default order:
    ``[{id, name, action}]``; ``action`` is the discovery action that runs it."""
    from . import inventory_discovery, plugin_discovery
    mon = _monitoring() if mon is None else mon
    areas = plugin_discovery.areas() if areas is None else areas
    out = []
    builtin = next((a for a in inventory_discovery.ACTIONS if a['id'] == area), None)
    if builtin and mon and role in builtin['roles']:
        out.append({'id': MONITORING, 'name': mon[1], 'action': area})
    for a in areas:
        if a['area'] == area and role in a['roles']:
            out.append({'id': a['plugin'], 'name': a['plugin_name'], 'action': a['id']})
    return out


def deciding(data, role, area, listed=None):
    """``(source id, why)``: the source that decides, and ``admin``, ``default`` or ``only``;
    ``(None, 'none')`` when nothing reads the area on such devices."""
    listed = sources_for(role, area) if listed is None else listed
    if not listed:
        return None, 'none'
    if len(listed) == 1:
        return listed[0]['id'], 'only'
    picked = ((data.get(KEY) or {}).get(role) or {}).get(area) if isinstance(data.get(KEY), dict) else None
    if picked and any(s['id'] == picked for s in listed):
        return picked, 'admin'
    return listed[0]['id'], 'default'


def decides(data, role, area, source):
    """Whether ``source`` decides ``area`` on devices of ``role`` (the monitoring source when no
    plugin reads the area there)."""
    who, _why = deciding(data, role or 'switch', area)
    return who == source or (who is None and source == MONITORING)


def set_deciding(data, role, area, source):
    """An admin's pick; None goes back to the default. Returns what's wrong, or None when saved."""
    from . import inventory
    if role not in inventory.ROLES:
        return 'No such kind of device.'
    listed = sources_for(role, area)
    if source is not None and not any(s['id'] == source for s in listed):
        return 'That source does not read this area on such devices.'
    saved = data.get(KEY) if isinstance(data.get(KEY), dict) else {}
    mine = saved.setdefault(role, {})
    if source is None:
        mine.pop(area, None)
    else:
        mine[area] = source
    if not mine:
        saved.pop(role, None)
    data[KEY] = saved
    return None


# ── readings and conflicts ───────────────────────────────────────────────────────────────────

def _plugin_ids(areas=None):
    from . import plugin_discovery
    return {a['plugin'] for a in (plugin_discovery.areas() if areas is None else areas)}


def readings_by_source(data, dev_id, plugins=None):
    """``{source id: (reading name, fields, at)}`` of one device: the monitoring source's (telemetry
    first, then LibreNMS) under MONITORING, each plugin's under its id."""
    plugins = _plugin_ids() if plugins is None else plugins
    readings = ((data.get('inventory_readings') or {}).get(dev_id) or {})
    out = {}
    order = sorted(readings, key=lambda s: (s != 'telemetry', s))
    for name in order:
        r = readings[name] if isinstance(readings[name], dict) else {}
        key = name if name in plugins else MONITORING
        if key == MONITORING and key in out:
            # A second monitoring source fills what the first didn't read.
            first = out[key]
            out[key] = (first[0], {**r.get('fields', {}), **first[1]}, first[2])
            continue
        out[key] = (name, dict(r.get('fields') or {}), r.get('at'))
    return out


def deciders_reading(data, dev, source):
    """The fields the deciding source of the device's identity read, when another source asks
    which fields it may fill (``source`` itself: all of them)."""
    who, _why = deciding(data, dev.get('role') or 'switch', 'identity')
    if who is None or who == source:
        return None
    return (readings_by_source(data, dev['id']).get(who) or (None, {}, None))[1]


def conflicts_of(data, dev, names=None):
    """Where a non-deciding source read another value than the deciding one: ``[{field, deciding:
    {source, name, value}, other: {source, name, value}, since}]``."""
    from . import inventory_discovery
    role = dev.get('role') or 'switch'
    listed = sources_for(role, 'identity')
    who, why = deciding(data, role, 'identity', listed)
    names = {s['id']: s['name'] for s in listed} if names is None else names
    got = {k: v for k, v in readings_by_source(data, dev['id']).items() if k in names}
    if who not in got:
        return []
    _name, mine, _at = got[who]
    out = []
    for source, (_n, fields, at) in sorted(got.items()):
        if source == who:
            continue
        for field in inventory_discovery.FIELDS:
            a, b = mine.get(field), fields.get(field)
            if a and b and not inventory_discovery._same(field, a, b):
                out.append({'kind': 'conflict', 'field': field, 'why': why,
                            'deciding': {'source': who, 'name': names.get(who, who), 'value': a},
                            'other': {'source': source, 'name': names.get(source, source), 'value': b},
                            'since': at})
    return out


# ── the "What Floorbit reads" table ──────────────────────────────────────────────────────────

def table(data, role):
    """One row per area that devices of ``role`` can have: who decides and why, who else reads
    it, how often, where it goes, the last run and the open conflicts."""
    from . import inventory, inventory_discovery, plugin_discovery
    mon = _monitoring()
    areas = plugin_discovery.areas()
    runs = data.get(inventory_discovery.RUNS) if isinstance(data.get(inventory_discovery.RUNS), dict) else {}
    devices = [d for d in inventory.devices(data) if (d.get('role') or 'switch') == role]
    names = [a['id'] for a in inventory_discovery.ACTIONS] + \
        [a['area'] for a in areas if not a['builtin'] and role in a['roles']]
    rows = []
    for area in dict.fromkeys(names):
        listed = sources_for(role, area, mon, areas)
        builtin = next((a for a in inventory_discovery.ACTIONS if a['id'] == area), None)
        if builtin and role not in builtin['roles']:
            continue
        who, why = deciding(data, role, area, listed)
        lead = next((s for s in listed if s['id'] == who), None)
        own = next((a for a in areas if a['area'] == area and not a['builtin']), None)
        conflicts = 0
        if area == 'identity' and len(listed) > 1:
            by = {s['id']: s['name'] for s in listed}
            conflicts = sum(len(conflicts_of(data, d, by)) for d in devices)
        action = lead['action'] if lead else (area if builtin else None)
        rows.append({
            'area': area, 'name': builtin['name'] if builtin else (own or {}).get('name', area),
            'builtin': bool(builtin),
            'sources': [{'id': s['id'], 'name': s['name']} for s in listed],
            'deciding': who, 'why': why,
            'minutes': inventory_discovery.action_minutes(data, action) if action and lead else None,
            'action': action if lead else None,
            'goes_to': GOES_TO.get(area) or f'auto.{area}.*',
            'last': runs.get(action) if action and lead else None,
            'conflicts': conflicts,
        })
    return {'role': role, 'devices': len(devices), 'monitoring': mon[1] if mon else None, 'rows': rows}
