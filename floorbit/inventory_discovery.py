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


# ── a run ────────────────────────────────────────────────────────────────────────────────────

def run():
    """Fill every inventory device the monitoring source knows. Returns the report (also kept as
    ``inventory_discovery`` for the Inventory page)."""
    from . import inventory, sources
    from .blueprints.inventory import data_lock
    from .blueprints.inventory_interfaces import MONITORED_ROLES, sync_from_monitoring
    from .store import load_data, save_data
    report = {'plugin': PLUGIN, 'at': inventory.now(), 'received': 0, 'updated': 0, 'unchanged': 0,
              'locked': 0, 'added': 0, 'gone': 0, 'interfaces': 0}
    mon = sources.monitoring()
    if not getattr(mon, 'name', '') or mon.name == 'none' or not mon.enabled():
        report['error'] = 'No monitoring source is set up, so there is nothing to discover.'
        return _keep(report)
    try:
        rows = mon.devices() or []
    except Exception as exc:  # noqa: BLE001 - the source's own error, shown on the Inventory page
        report['error'] = f'The monitoring source did not answer: {exc}'[:300]
        return _keep(report)
    found = {}
    with data_lock:
        data = load_data()
        pairs = match(inventory.devices(data), rows)
        report['received'] = len(pairs)
        for dev, row in pairs:
            values = fields_of(row)
            found[dev['id']] = (values, row)
            changed, kept = fill(dev, values)
            report['locked'] += kept
            if changed:
                dev['updated_at'] = inventory.now()
                report['updated'] += 1
            else:
                report['unchanged'] += 1
        save_data(data)
    polled = {dev['id'] for dev, row in pairs if dev.get('role') in MONITORED_ROLES and row.get('status', 1)}
    ports_ok = False
    if polled:
        ports = sync_from_monitoring([dev['name'] for dev, _row in pairs if dev['id'] in polled])
        if not ports.get('error'):
            ports_ok = True
            report['interfaces'] = ports['added'] + ports['updated']
            report['added'] = ports['added']
            report['gone'] = ports['gone']
    with data_lock:
        data = load_data()
        before = data.get('inventory_drift') if isinstance(data.get('inventory_drift'), dict) else {}
        now_text = inventory.now()
        out = {}
        for dev_id, (values, row) in found.items():
            dev = inventory.find(data, dev_id)
            if dev is None:
                continue
            port_source = mon.name if ports_ok and dev_id in polled else None
            rows = _since(drift(dev, values, row, port_source), before.get(dev_id) or [], now_text)
            if rows:
                out[dev_id] = rows
        data['inventory_drift'] = out
        report['drift'] = len(out)
        seen = {}
        for dev_id, (_values, row) in found.items():
            dev = inventory.find(data, dev_id)
            seen[dev_id] = {**networks_of(row), 'transceivers': optics_of(row, dev['name'] if dev else '')}
        last = data.get('inventory_discovered') if isinstance(data.get('inventory_discovered'), dict) else {}
        # A device that didn't answer this time keeps what it said last: its optics and VLANs aren't gone.
        kept = {dev_id: n for dev_id, n in last.items()
                if dev_id not in seen and isinstance(n, dict) and inventory.find(data, dev_id) is not None}
        data['inventory_discovered'] = {
            **kept, **{dev_id: {**n, 'at': now_text} for dev_id, n in seen.items()
                       if n['vlans'] or n['networks'] or n['transceivers']}}
        _entries(data, list(data['inventory_discovered'].values()), report)
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
    return {'vlans': [], 'networks': [], 'transceivers': [], 'at': None, **(found.get(device_id) or {})}


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
    """One look at the schedule (inventory_schedule's loop). Returns the report, or None."""
    from . import inventory_schedule
    from .store import load_data
    now = time.time() if now is None else now
    previous = last(load_data())
    if not inventory_schedule.due(now, inventory_schedule._at(previous or {}), every_minutes()):
        return None
    if not available() or not running.acquire(blocking=False):
        return None
    try:
        return run()
    finally:
        running.release()
