"""Discovery: inventory devices filled from what the monitoring source polls (docs/inventory.md#discovery).

Telemetry asks each device what it is every few minutes (SNMP: sysDescr, sysLocation, ENTITY-MIB,
HOST-RESOURCES-MIB; floorbit/telemetry/state.py ``Device.summary``), and LibreNMS knows the same
of its devices. Discovery takes that into the inventory devices the source knows, with their ports
as interfaces, every ``DISCOVERY_MINUTES`` (15 by default) and with **Sync now**.

It only fills in, so nothing anyone set is lost:

- A field gets the discovered value when it is empty, or still holds what discovery put there
  last (kept in ``fed['discovery']``). A value typed by hand or fed by another plugin (NetBox)
  stays, and the report counts it as kept.
- It never adds or deletes devices and never changes a name, role, address or status.
- Interfaces go through the same merge as **Take from monitoring** (inventory_interfaces.merge_feed).

What it keeps instead of overwriting is **drift** (issue #918): per device, each field, the
hostname, the management address and each interface where the inventory and the device disagree,
with what is configured, what is actual and since when (``inventory_drift``; drift() below).
"""
import ipaddress
import re
import threading
import time

from integrations import config

PLUGIN = 'discovery'
NAME = 'Discovery'
DEFAULT_MINUTES = 15
MIN_MINUTES = 5
MAX_MINUTES = 24 * 60
# What discovery may fill; everything else on a device is someone's decision.
FIELDS = ('model', 'serial', 'platform', 'os', 'cpu', 'cores', 'memory_mb', 'disk_gb', 'location')
# LibreNMS's ``os`` names, as the platform field writes them.
OS_NAMES = {'ios': 'Cisco IOS', 'iosxe': 'Cisco IOS-XE', 'nxos': 'Cisco NX-OS', 'linux': 'Linux',
            'opnsense': 'OPNsense', 'pfsense': 'pfSense', 'freebsd': 'FreeBSD', 'windows': 'Windows',
            'proxmox': 'Proxmox VE', 'vmware': 'VMware ESXi', 'junos': 'Junos', 'arubaos': 'ArubaOS',
            'routeros': 'RouterOS', 'edgeos': 'EdgeOS', 'unifi': 'UniFi'}
_VERSION = re.compile(r'\bVersion:?\s+([^\s,]+)', re.I)

# One run at a time from this process; the button and the schedule can meet.
running = threading.Lock()


def every_minutes():
    """Minutes between runs, or 0 when off."""
    minutes = config.get_int('DISCOVERY_MINUTES', DEFAULT_MINUTES, minimum=0)
    if minutes <= 0:
        return 0
    return min(max(minutes, MIN_MINUTES), MAX_MINUTES)


# ── what a device said, as inventory fields ──────────────────────────────────────────────────

def software(descr, rev=''):
    """(platform, os) from a sysDescr: ``('Cisco IOS', 'Cisco IOS 15.2(7)E8')``. Unknown text
    gives no platform and the start of the text as the OS."""
    text = ' '.join(str(descr or '').split())
    low = text.lower()
    version = ''
    m = _VERSION.search(text)
    if m:
        version = m.group(1)
    platform = ''
    if 'nx-os' in low:
        platform = 'Cisco NX-OS'
    elif 'ios-xe' in low or 'iosxe' in low or 'ios xe' in low:
        platform = 'Cisco IOS-XE'
    elif 'cisco ios' in low or 'ios (tm)' in low:
        platform = 'Cisco IOS'
    elif low.startswith('linux '):
        platform = 'Linux'
        version = text.split()[2] if len(text.split()) > 2 else ''
    elif low.startswith('freebsd '):
        platform = 'FreeBSD'
        version = text.split()[2] if len(text.split()) > 2 else ''
    elif 'windows' in low:
        platform = 'Windows'
        m = re.search(r'Windows Version ([\d.]+)', text)
        version = m.group(1) if m else ''
    version = version or str(rev or '').strip()
    if platform:
        return platform, f'{platform} {version}'.strip()
    return '', text[:80]


def fields_of(row):
    """Inventory fields from one row of ``monitoring().devices()``: telemetry's ``facts``, or
    LibreNMS's own keys (hardware, serial, os, version, location)."""
    facts = row.get('facts') if isinstance(row.get('facts'), dict) else None
    out = {}
    if facts is not None:
        out['model'] = facts.get('model')
        out['serial'] = facts.get('serial')
        out['platform'], out['os'] = software(facts.get('descr'), facts.get('software'))
        if not facts.get('descr') and facts.get('software'):
            out['os'] = facts['software']
        out['location'] = facts.get('location')
        for key in ('cores', 'memory_mb', 'disk_gb', 'cpu'):
            out[key] = facts.get(key)
    else:
        out['model'] = row.get('hardware')
        out['serial'] = row.get('serial')
        out['location'] = row.get('location')
        os_name = str(row.get('os') or '').strip()
        if os_name:
            out['platform'] = OS_NAMES.get(os_name.lower(), os_name)
            out['os'] = f"{out['platform']} {row.get('version') or ''}".strip()
        elif row.get('sysDescr'):
            out['platform'], out['os'] = software(row['sysDescr'])
    from . import inventory
    clean = {}
    for field, value in out.items():
        if value in (None, '') or isinstance(value, bool):
            continue
        if field in inventory.NUMBERS:
            if not isinstance(value, (int, float)) or value <= 0:
                continue
            value = round(value)
        try:
            value = inventory.clean_field(field, value)
        except inventory.InventoryError:
            continue
        if value:
            clean[field] = value
    return clean


def match(devices, rows):
    """[(inventory device, row)] for the rows that name an inventory device, by name (short
    name too, case-insensitive) or management address."""
    def short(name):
        return str(name or '').strip().lower().split('.')[0]

    by_name, by_ip = {}, {}
    for d in devices:
        by_name.setdefault(str(d['name']).strip().lower(), d)
        by_name.setdefault(short(d['name']), d)
        if d.get('mgmt_ip'):
            by_ip.setdefault(d['mgmt_ip'], d)
    out, taken = [], set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        dev = None
        for key in (row.get('hostname'), row.get('display'), row.get('sysName')):
            if key:
                dev = by_name.get(str(key).strip().lower()) or by_name.get(short(key))
                if dev:
                    break
        dev = dev or by_ip.get(row.get('ip'))
        if dev is not None and dev['id'] not in taken:
            taken.add(dev['id'])
            out.append((dev, row))
    return out


def fill(dev, values):
    """Put discovered values on one device by the rules at the top. Returns (changed, kept)."""
    before = (dev.get('fed') or {}).get(PLUGIN) or {}
    owned = {}
    changed, kept = [], 0
    for field in FIELDS:
        value = values.get(field)
        if not value:
            continue
        current = dev.get(field) or ''
        if field in (dev.get('locked') or []) or (current and current != before.get(field)):
            kept += current != value
            continue
        owned[field] = value
        if current != value:
            dev[field] = value
            changed.append(field)
    # Only what discovery owns: a hand edit later doesn't lock against it, it just stops it.
    dev.setdefault('fed', {})[PLUGIN] = owned
    return changed, kept


# ── actions (issue #919) ─────────────────────────────────────────────────────────────────────

# What discovery does, per kind of device, each on its own clock. ``minutes`` None: every
# DISCOVERY_MINUTES. ``keys``: what it keeps in ``inventory_discovered``.
ACTIONS = (
    {'id': 'identity', 'name': 'Model, serial and software', 'minutes': 60, 'keys': (),
     'roles': ('switch', 'router', 'firewall', 'access-point', 'server', 'vm', 'pdu', 'other')},
    {'id': 'interfaces', 'name': 'Interfaces', 'minutes': None, 'keys': (),
     'roles': ('switch', 'router', 'firewall', 'access-point', 'server', 'pdu')},
    {'id': 'networks', 'name': 'VLANs and networks', 'minutes': None, 'keys': ('vlans', 'networks'),
     'roles': ('switch', 'router', 'firewall', 'server', 'vm')},
    {'id': 'optics', 'name': 'Transceivers', 'minutes': 60, 'keys': ('transceivers',),
     'roles': ('switch', 'router', 'firewall')},
    {'id': 'poe', 'name': 'PoE budget', 'minutes': None, 'keys': ('poe',), 'roles': ('switch',)},
    {'id': 'routes', 'name': 'Routes', 'minutes': None, 'keys': ('routes',), 'roles': ('firewall',)},
)
ACTION_IDS = tuple(a['id'] for a in ACTIONS)
SCHEDULES = 'inventory_discovery_schedules'      # {action: minutes} set by an admin, 0 = off
RUNS = 'inventory_discovery_runs'                # {action: {at, devices, changed}}


def action(action_id):
    return next((a for a in ACTIONS if a['id'] == action_id), None)


def action_minutes(data, action_id):
    """Minutes between runs of one action, or 0 when off. Discovery off (DISCOVERY_MINUTES 0)
    turns every action off."""
    every = every_minutes()
    if every <= 0:
        return 0
    saved = (data.get(SCHEDULES) or {}) if isinstance(data.get(SCHEDULES), dict) else {}
    if isinstance(saved.get(action_id), int) and not isinstance(saved.get(action_id), bool):
        return 0 if saved[action_id] <= 0 else min(max(saved[action_id], MIN_MINUTES), MAX_MINUTES)
    return action(action_id)['minutes'] or every


def actions(data):
    """Every action with its schedule and its last run, for the API."""
    saved = (data.get(SCHEDULES) or {}) if isinstance(data.get(SCHEDULES), dict) else {}
    runs = (data.get(RUNS) or {}) if isinstance(data.get(RUNS), dict) else {}
    return [{'id': a['id'], 'name': a['name'], 'roles': list(a['roles']), 'minutes': action_minutes(data, a['id']),
             'custom': a['id'] in saved, 'last': runs.get(a['id'])} for a in ACTIONS]


def set_minutes(data, action_id, minutes):
    """An admin's schedule for one action: minutes (0 = off), or None for the default. Returns
    what is wrong with it, or None when it is saved (a fixed text: nothing of the request echoes)."""
    if action(action_id) is None:
        return 'No such discovery action.'
    if not isinstance(data.get(SCHEDULES), dict):
        data[SCHEDULES] = {}
    saved = data[SCHEDULES]
    if minutes is None:
        saved.pop(action_id, None)
        return None
    if isinstance(minutes, bool) or not isinstance(minutes, int) or minutes < 0 or minutes > MAX_MINUTES:
        return f'Minutes are a whole number from 0 (off) to {MAX_MINUTES}.'
    if 0 < minutes < MIN_MINUTES:
        return f'Discovery runs at most every {MIN_MINUTES} minutes.'
    saved[action_id] = minutes
    return None


def due_actions(data, now):
    from . import inventory_schedule
    runs = (data.get(RUNS) or {}) if isinstance(data.get(RUNS), dict) else {}
    return [a['id'] for a in ACTIONS
            if inventory_schedule.due(now, inventory_schedule._at(runs.get(a['id']) or {}),
                                      action_minutes(data, a['id']))]


# ── a run ────────────────────────────────────────────────────────────────────────────────────

def run(only=None, device_ids=None):
    """Run the actions ``only`` names (all when None) on the inventory devices the monitoring
    source knows, or only on ``device_ids``. Returns the report (also kept as
    ``inventory_discovery`` for the Inventory page) with what each action did."""
    from . import inventory, sources
    from .blueprints.inventory import data_lock
    from .blueprints.inventory_interfaces import sync_from_monitoring
    from .store import load_data, save_data
    todo = [a for a in ACTIONS if only is None or a['id'] in only]
    report = {'plugin': PLUGIN, 'at': inventory.now(), 'received': 0, 'updated': 0, 'unchanged': 0,
              'locked': 0, 'added': 0, 'gone': 0, 'interfaces': 0, 'actions': {a['id']: {'devices': 0, 'changed': 0}
                                                                                 for a in todo}}
    if device_ids is not None:
        report['devices'] = sorted(device_ids)
    mon = sources.monitoring()
    if not getattr(mon, 'name', '') or mon.name == 'none' or not mon.enabled():
        report['error'] = 'No monitoring source is set up, so there is nothing to discover.'
        return _keep(report)
    try:
        rows = mon.devices() or []
    except Exception as exc:  # noqa: BLE001 - the source's own error, shown on the Inventory page
        report['error'] = f'The monitoring source did not answer: {exc}'[:300]
        return _keep(report)
    ran = {a['id'] for a in todo}

    def does(action_id, dev):
        return action_id in ran and dev.get('role', 'switch') in action(action_id)['roles']

    found = {}
    with data_lock:
        data = load_data()
        pairs = [(d, r) for d, r in match(inventory.devices(data), rows) if device_ids is None or d['id'] in device_ids]
        report['received'] = len(pairs)
        for dev, row in pairs:
            values = fields_of(row)
            found[dev['id']] = (values, row)
            if not does('identity', dev):
                continue
            report['actions']['identity']['devices'] += 1
            changed, kept = fill(dev, values)
            report['locked'] += kept
            if changed:
                dev['updated_at'] = inventory.now()
                report['updated'] += 1
                report['actions']['identity']['changed'] += 1
            else:
                report['unchanged'] += 1
        save_data(data)
    polled = {dev['id'] for dev, row in pairs if does('interfaces', dev) and row.get('status', 1)}
    ports_ok = False
    if polled:
        ports = sync_from_monitoring([dev['name'] for dev, _row in pairs if dev['id'] in polled])
        if ports.get('error'):
            report['actions']['interfaces']['error'] = ports['error']
        else:
            ports_ok = True
            report['interfaces'] = ports['added'] + ports['updated']
            report['added'] = ports['added']
            report['gone'] = ports['gone']
            report['actions']['interfaces'].update(devices=len(polled), changed=report['interfaces'])
    with data_lock:
        data = load_data()
        now_text = inventory.now()
        before = data.get('inventory_drift') if isinstance(data.get('inventory_drift'), dict) else {}
        # What this run didn't look at stays as the last run left it.
        out = {i: rows for i, rows in before.items() if i not in found and inventory.find(data, i) is not None}
        for dev_id, (values, row) in found.items():
            dev = inventory.find(data, dev_id)
            if dev is None:
                continue
            old = [r for r in before.get(dev_id) or [] if isinstance(r, dict)]
            rows = drift(dev, values, row, mon.name if ports_ok and dev_id in polled else None)
            if not does('identity', dev):
                rows = [r for r in rows if r['kind'] == 'interface'] + [r for r in old if r.get('kind') != 'interface']
            if not (ports_ok and dev_id in polled):
                rows = [r for r in rows if r['kind'] != 'interface'] + [r for r in old if r.get('kind') == 'interface']
            rows = _since(rows, old, now_text)
            if rows:
                out[dev_id] = rows
        data['inventory_drift'] = out
        report['drift'] = len(out)
        last_seen = data.get('inventory_discovered') if isinstance(data.get('inventory_discovered'), dict) else {}
        # A device that didn't answer keeps what it said last: its optics and VLANs aren't gone.
        kept = {i: n for i, n in last_seen.items() if isinstance(n, dict) and inventory.find(data, i) is not None}
        for dev_id, (_values, row) in found.items():
            dev = inventory.find(data, dev_id)
            if dev is None:
                continue
            fresh = {**networks_of(row), 'transceivers': optics_of(row, dev['name']), 'poe': poe_of(row),
                     'routes': routes_of(row)}
            record = dict(kept.get(dev_id) or {})
            for a in todo:
                if not a['keys'] or not does(a['id'], dev):
                    continue
                report['actions'][a['id']]['devices'] += 1
                for key in a['keys']:
                    if record.get(key) != fresh[key]:
                        report['actions'][a['id']]['changed'] += 1
                    record[key] = fresh[key]
                record['at'] = now_text
            if any(record.get(k) for k in ('vlans', 'networks', 'transceivers', 'poe', 'routes')):
                kept[dev_id] = record
            else:
                kept.pop(dev_id, None)
        data['inventory_discovered'] = kept
        if ran & {'networks', 'optics'}:
            _entries(data, list(kept.values()), report)
        save_data(data)
    return _keep(report)


# ── networks and VLANs (issue #919) ──────────────────────────────────────────────────────────

def networks_of(row):
    """The VLANs ({id: name}) a device knows and the networks on its interfaces, from telemetry's facts."""
    facts = row.get('facts') if isinstance(row.get('facts'), dict) else {}
    vlans = facts.get('vlans') if isinstance(facts.get('vlans'), dict) else {}
    out = {'vlans': [], 'networks': []}
    for vid, name in vlans.items():
        if str(vid).isdigit() and 1 <= int(vid) <= 4094:
            out['vlans'].append({'id': int(vid), 'name': ' '.join(str(name or '').split())[:64]})
    out['vlans'] = sorted(out['vlans'], key=lambda v: v['id'])[:4094]
    for net in facts.get('networks') or []:
        try:
            out['networks'].append(str(ipaddress.ip_network(str(net), strict=False)))
        except ValueError:
            continue
    out['networks'] = sorted(set(out['networks']))[:256]
    return out


# ── transceivers (issue #919) ───────────────────────────────────────────────────────────────

def _optic_form(text):
    if re.search(r'TWINAX|(?<![A-Z])(DAC|CU)\d?(?![A-Z])', text):
        return 'DAC'
    if re.search(r'(?<![A-Z])AOC', text):
        return 'AOC'
    if 'QSFP' in text:
        return 'QSFP28' if re.search(r'(?<!\d)100G', text) else 'QSFP+'
    if 'SFP' in text or 'GLC-' in text:            # GLC-: Cisco's 1G SFPs
        if re.search(r'SFP28|(?<!\d)25G', text):
            return 'SFP28'
        if re.search(r'SFP\+|(?<!\d)10G', text):
            return 'SFP+'
        return 'SFP'
    return ''


def _optic_speed(text):
    for speed in ('100G', '40G', '25G', '10G'):
        if re.search(rf'(?<!\d){speed}', text):
            return speed
    if re.search(r'1000BASE|(?<!\d)1G(?!\d)|GLC-|GBIC', text):
        return '1G'
    return ''


def _optic_media(text, form):
    if form == 'DAC' or re.search(r'BASE-?T(?![A-Z])|GLC-T', text):
        return 'Copper'
    for media, pattern in (('BiDi', r'BIDI|(?<![A-Z])BX'), ('ER', r'(?<![A-Z])(ER|ZX|EX|ZR)\d?(?![A-Z])'),
                           ('LR', r'(?<![A-Z])(LR|LX|LH)\d?(?![A-Z])'), ('SR', r'(?<![A-Z])(SR|SX)\d?(?![A-Z])')):
        if re.search(pattern, text):
            return media
    return ''


def optic(model, descr=''):
    """Form factor, media and speed read from an optic's model and description, in the
    Transceiver type's choices; '' where it doesn't say."""
    text = f'{model} {descr}'.upper()
    form = _optic_form(text)
    return {'form': form, 'media': _optic_media(text, form), 'speed': _optic_speed(text)}


def optics_of(row, device_name):
    """The transceivers a device reports (telemetry's facts), as entries' fields."""
    facts = row.get('facts') if isinstance(row.get('facts'), dict) else {}
    out = []
    for o in facts.get('transceivers') or []:
        if not isinstance(o, dict) or not str(o.get('serial') or '').strip():
            continue
        model = ' '.join(str(o.get('model') or '').split())[:80]
        out.append({'serial': ' '.join(str(o['serial']).split())[:64], 'model': model,
                    'port': str(o.get('port') or '')[:64], 'device': device_name,
                    **optic(model, str(o.get('descr') or ''))})
    return out[:500]


def routes_of(row):
    """A firewall's routes: [{network, next_hop, interface, proto}], the default route first."""
    facts = row.get('facts') if isinstance(row.get('facts'), dict) else {}
    out = []
    for r in facts.get('routes') or []:
        if not isinstance(r, dict):
            continue
        try:
            net = str(ipaddress.ip_network(str(r.get('network')), strict=False))
            hop = str(ipaddress.ip_address(r['next_hop'])) if r.get('next_hop') else ''
        except ValueError:
            continue
        out.append({'network': net, 'next_hop': hop, 'interface': str(r.get('interface') or '')[:64],
                    'proto': str(r.get('proto') or 'other')[:16]})
    return out[:2000]


def poe_of(row):
    """A switch's PoE budget and what it gives now, in watts: {budget_w, used_w}, or None."""
    facts = row.get('facts') if isinstance(row.get('facts'), dict) else {}
    poe = facts.get('poe') if isinstance(facts.get('poe'), dict) else {}
    try:
        return {'budget_w': float(poe['budget_w']), 'used_w': float(poe.get('used_w') or 0)} if poe.get('budget_w') \
            else None
    except (TypeError, ValueError):
        return None


def _entries(data, found, report):
    """Every VLAN, network and transceiver the devices know, as inventory entries (the same rules
    as a plugin's: hand changes win, nothing is deleted)."""
    from . import inventory_scope, inventory_types
    vlans, networks, optics = {}, set(), {}
    for n in found:
        for v in n.get('vlans') or []:
            if v['name'] or v['id'] not in vlans:
                vlans[v['id']] = v['name'] or vlans.get(v['id']) or ''
        networks.update(n.get('networks') or [])
        for o in n.get('transceivers') or []:
            optics[o['serial'].lower()] = o          # an optic moved to another switch: where it is now
    if not vlans and not networks and not optics:
        return
    feed = {'vlan': [{'ref': f'vlan-{vid}', 'name': name or f'VLAN {vid}', 'fields': {'vlan_id': vid}}
                     for vid, name in sorted(vlans.items())]
            + [{'ref': f'prefix-{net}', 'name': net, 'fields': {'prefix': net}} for net in sorted(networks)]}
    if optics:
        feed['transceiver'] = [
            {'ref': f'optic-{key}', 'name': f'{o["model"] or "Transceiver"} {o["serial"]}',
             'fields': {k: o[k] for k in ('device', 'port', 'form', 'media', 'speed', 'serial') if o[k]}}
            for key, o in sorted(optics.items())]
    try:
        clean, skipped = inventory_types.clean_feed(feed)
        result = inventory_types.sync_entries(data, PLUGIN, clean, skipped)
    except inventory_scope.ScopeError as exc:
        report['entries_error'] = str(exc)[:300]
        return
    report['entries'] = {k: result[k] for k in ('added', 'updated', 'gone')}


def discovered_of(data, device_id):
    found = data.get('inventory_discovered') if isinstance(data.get('inventory_discovered'), dict) else {}
    return {'vlans': [], 'networks': [], 'transceivers': [], 'poe': None, 'routes': [], 'at': None,
            **(found.get(device_id) or {})}


# ── drift ────────────────────────────────────────────────────────────────────────────────────

def _same(field, a, b):
    from . import inventory
    a, b = str(a or '').strip(), str(b or '').strip()
    if field in inventory.NUMBERS and a.isdigit() and b.isdigit():
        # What a device reports is usable memory or formatted disk: a few percent off isn't drift.
        big = max(int(a), int(b))
        return big == 0 or abs(int(a) - int(b)) / big <= 0.1
    return ' '.join(a.lower().split()) == ' '.join(b.lower().split())


def _short(name):
    return str(name or '').strip().lower().split('.')[0]


def drift(dev, values, row, port_source=None):
    """Where the inventory device and what the device reports disagree: [{kind, field, configured,
    actual}]. ``port_source``: the monitoring plugin whose ports were just merged, for the
    interfaces (None: they weren't polled this time, so nothing is said about them)."""
    out = []
    for field in FIELDS:
        actual, configured = values.get(field), dev.get(field)
        if actual and configured and not _same(field, configured, actual):
            out.append({'kind': 'field', 'field': field, 'configured': configured, 'actual': actual})
    sys_name = row.get('sysName')
    if sys_name and _short(sys_name) != _short(dev['name']) and _short(sys_name) != _short(row.get('hostname')):
        out.append({'kind': 'hostname', 'field': 'name', 'configured': dev['name'],
                    'actual': str(sys_name)[:80]})
    ip = str(row.get('ip') or '').strip()
    natted = (dev.get('properties') or {}).get('telemetry_address')     # reached elsewhere on purpose
    if ip and dev.get('mgmt_ip') and ip != dev['mgmt_ip'] and not natted:
        out.append({'kind': 'address', 'field': 'mgmt_ip', 'configured': dev['mgmt_ip'], 'actual': ip})
    if port_source:
        out += _interface_drift(dev, port_source)
    return out


def _interface_drift(dev, source):
    out = []
    for iface in dev.get('interfaces') or []:
        name = iface['name']
        reported = source in (iface.get('refs') or {}) and source not in (iface.get('gone') or [])
        if not reported:
            if not iface.get('hidden'):
                # Made by hand or by another plugin, or gone from the device: it isn't there.
                out.append({'kind': 'interface', 'field': name, 'configured': 'present', 'actual': 'missing'})
            continue
        if iface.get('hidden'):
            out.append({'kind': 'interface', 'field': name, 'configured': 'hidden', 'actual': 'present'})
            continue
        fed = (iface.get('fed') or {}).get(source) or {}
        for field in iface.get('locked') or []:
            if field in fed and fed[field] not in (None, '') and iface.get(field) != fed[field]:
                out.append({'kind': 'interface', 'field': f'{name} {field}', 'configured': iface.get(field),
                            'actual': fed[field]})
    return out[:200]


def _since(rows, before, at):
    """Each row with the time it was first seen, carried over from the last run."""
    seen = {(r.get('kind'), r.get('field'), str(r.get('actual'))): r.get('since')
            for r in before if isinstance(r, dict)}
    return [{**r, 'since': seen.get((r['kind'], r['field'], str(r['actual']))) or at} for r in rows]


def drift_of(data, device_id):
    found = data.get('inventory_drift') if isinstance(data.get('inventory_drift'), dict) else {}
    return list(found.get(device_id) or [])


def _keep(report):
    from .blueprints.inventory import data_lock
    from .store import load_data, save_data
    with data_lock:
        data = load_data()
        data['inventory_discovery'] = report
        if report.get('actions') and 'devices' not in report:
            # Each action's last run, failed or not, moves its clock; a run for a few devices doesn't.
            if not isinstance(data.get(RUNS), dict):
                data[RUNS] = {}
            for action_id, done in report['actions'].items():
                data[RUNS][action_id] = {'at': report['at'], **done,
                                         **({'error': report['error']} if report.get('error') else {})}
        save_data(data)
    if report.get('error'):
        print(f"[discovery] {report['error']}")
    else:
        print('[discovery] {received} devices: {updated} updated, {locked} fields kept as set, '
              '{interfaces} interfaces added or updated'.format(**report))
    return report


def last(data):
    report = data.get('inventory_discovery')
    return report if isinstance(report, dict) else None


def available():
    """Whether there is a monitoring source to discover from."""
    from . import sources
    try:
        mon = sources.monitoring()
        return bool(getattr(mon, 'name', '')) and mon.name != 'none' and bool(mon.enabled())
    except Exception:  # noqa: BLE001
        return False


def tick(now=None):
    """One look at the schedule (inventory_schedule's loop): runs the actions that are due.
    Returns the report, or None."""
    from .store import load_data
    now = time.time() if now is None else now
    due = due_actions(load_data(), now)
    if not due or not available() or not running.acquire(blocking=False):
        return None
    try:
        return run(set(due))
    finally:
        running.release()
