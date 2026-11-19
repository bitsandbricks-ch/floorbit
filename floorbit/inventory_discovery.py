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
"""
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
    with data_lock:
        data = load_data()
        pairs = match(inventory.devices(data), rows)
        report['received'] = len(pairs)
        for dev, row in pairs:
            changed, kept = fill(dev, fields_of(row))
            report['locked'] += kept
            if changed:
                dev['updated_at'] = inventory.now()
                report['updated'] += 1
            else:
                report['unchanged'] += 1
        save_data(data)
    names = [dev['name'] for dev, row in pairs if dev.get('role') in MONITORED_ROLES and row.get('status', 1)]
    if names:
        ports = sync_from_monitoring(names)
        if not ports.get('error'):
            report['interfaces'] = ports['added'] + ports['updated']
            report['added'] = ports['added']
            report['gone'] = ports['gone']
    return _keep(report)


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
