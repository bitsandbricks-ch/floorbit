"""The latest picture of each device, built from telemetry points (lineproto.Point).

This is what the telemetry monitoring source answers from (floorbit/builtin_plugins/telemetry): a
switch's ports with their state, rates and errors, its MAC table, ARP, LLDP and CDP neighbours,
and a firewall's gateways and states. Only the newest values are kept, in memory: the time series
go to storage.py, and MAC tables and ARP never do (they name the people at the seats).

Points come in several shapes, one per driver (docs/telemetry.md):

- SNMP polling, as floorbit/telemetry/telegraf.py asks Telegraf for it: ``fb_system``, ``fb_if``,
  ``fb_bridge``, ``fb_fdb``, ``fb_qfdb``, ``fb_arp``, ``fb_lldp``, ``fb_lldp_loc``, ``fb_cdp``,
  each table row with its SNMP index in the ``index`` tag.
- SNMP traps (Telegraf ``snmp_trap``): linkUp and linkDown change a port at once, between polls.
- gNMI and Cisco model-driven telemetry (NX-OS, IOS-XE): OpenConfig or native interface paths.
  Field names differ by platform and path, so the last part of each name is what counts
  (``state/counters/in-octets`` and ``in_octets`` are the same thing here).
- Our own pollers (pollers.py: NX-API, the OPNsense API) and anything else: ``fb_arp`` and
  ``fb_if`` rows keyed by name (``ip``, ``mac``, ``port`` tags) instead of an SNMP index.
- A firewall's own Telegraf (OPNsense ``os-telegraf``, the pfSense Telegraf package): ``cpu``,
  ``mem``, ``net``, ``pf``, ``system``, with the firewall in the ``host`` tag.
"""
import re
import threading
import time

from . import lineproto

EXPIRE_EVERY = 10      # seconds between passes that drop rows past TABLE_TTL
MIN_RATE_GAP = 2.0     # seconds between two counter readings worth a rate
TABLE_TTL = 600        # seconds a MAC, ARP or neighbour row lives without being seen again
STALE = 180            # a device that sent nothing for this long reads as offline
OPER = {1: 'up', 2: 'down', 3: 'testing', 4: 'unknown', 5: 'dormant', 6: 'notPresent', 7: 'lowerLayerDown'}
DUPLEX = {1: 'unknown', 2: 'halfDuplex', 3: 'fullDuplex'}
LINK_DOWN = '1.3.6.1.6.3.1.1.5.3'
LINK_UP = '1.3.6.1.6.3.1.1.5.4'
IF_INDEX_OID = '1.3.6.1.2.1.2.2.1.1'


def _key(name):
    """``state/counters/in-octets`` -> ``in_octets``: what a gNMI or MDT field means, whatever
    path prefix the platform puts in front."""
    return re.split(r'[/:]', str(name))[-1].replace('-', '_').lower()


def _num(value):
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _status(value):
    """IF-MIB numbers, OpenConfig ``UP``/``DOWN`` and NX-OS ``up``/``down`` alike."""
    if isinstance(value, bool):
        return 'up' if value else 'down'
    number = _num(value)
    if number is not None:
        return OPER.get(int(number), 'unknown')
    text = str(value or '').strip().lower()
    if text in ('up', 'down', 'testing', 'dormant', 'unknown'):
        return text
    if text in ('lower_layer_down', 'lowerlayerdown', 'link-down', 'link_down'):
        return 'down'
    if text in ('not_present', 'notpresent'):
        return 'notPresent'
    return 'unknown' if text else None


def _mac(value):
    from ..sources import normalise_mac
    return normalise_mac(value)


def _mac_from_index(parts):
    """Six decimal numbers (an SNMP MAC index) as aa:bb:cc:dd:ee:ff."""
    if len(parts) != 6:
        return None
    try:
        return ':'.join(f'{int(p):02x}' for p in parts)
    except ValueError:
        return None


class Interface:
    __slots__ = (
        '_counted',
        'admin',
        'alias',
        'duplex',
        'in_bps',
        'in_err_rate',
        'in_errors',
        'in_octets',
        'index',
        'last_change',
        'name',
        'oper',
        'out_bps',
        'out_err_rate',
        'out_errors',
        'out_octets',
        'seen',
        'speed',
    )

    def __init__(self, index=None, name=None):
        self.index = index
        self.name = name
        self.alias = None
        self.oper = self.admin = self.duplex = None
        self.speed = None                 # bits per second
        self.in_octets = self.out_octets = self.in_errors = self.out_errors = None
        self.in_bps = self.out_bps = self.in_err_rate = self.out_err_rate = None
        self.last_change = None
        self.seen = 0
        self._counted = {}                # counter -> (value, time), for rates

    def count(self, which, value, at):
        """Take a counter reading and work out its rate against the last one."""
        value = _num(value)
        if value is None:
            return None
        before = self._counted.get(which)
        if before is not None and at - before[1] < MIN_RATE_GAP:
            # Two agents polling the same hall (no VRRP, or split): the second copy lands a moment
            # after the first, or late and older. A rate over a fraction of a second jumps between
            # 0 and many times the truth (switches refresh counters every few seconds), and an
            # older reading would become the base; keep the base and wait for a real interval.
            return None
        self._counted[which] = (value, at)
        if before is None:
            return None
        delta = value - before[0]
        # A counter that went backwards was reset (reboot, clear counters): no rate this round.
        return delta / (at - before[1]) if delta >= 0 else None

    def librenms_row(self):
        """The row shape the LibreNMS plugin reads (librenms/ports.py summarize_port), so every
        page that shows a port works unchanged."""
        return {'ifName': self.name, 'ifAlias': self.alias or '', 'ifOperStatus': self.oper,
                'ifAdminStatus': self.admin, 'ifDuplex': self.duplex,
                'ifSpeed': self.speed, 'ifInOctets_rate': self.in_bps / 8 if self.in_bps is not None else None,
                'ifOutOctets_rate': self.out_bps / 8 if self.out_bps is not None else None,
                'ifInErrors_rate': self.in_err_rate, 'ifOutErrors_rate': self.out_err_rate,
                'ifInErrors': self.in_errors, 'ifOutErrors': self.out_errors,
                'poll_time': int(self.seen) if self.seen else None}


class Device:
    _cpu_rows = None

    def __init__(self, name):
        self.name = name
        self.address = None
        self.mdt_node = None
        self.driver = None
        self.kind = 'switch'
        self.sys_name = None
        self.uptime = None
        self.cpu = None
        self.mem = None
        self.states = None                # a firewall's pf states
        self.seen = 0
        self.interfaces = {}              # index or name -> Interface
        self.bridge_ports = {}            # bridge port -> ifIndex
        self.lldp_local = {}              # LLDP local port number -> port name
        self.fdb = {}                     # (mac, vlan) -> [port key, seen]
        self.arp = {}                     # ip -> [mac, port key, seen]
        self.lldp = {}                    # (local port, remote index) -> [row, seen]
        self.cdp = {}
        self.gateways = {}                # name -> {status, delay_ms, loss_pct, seen}

    # ports -----------------------------------------------------------------------------------
    def port(self, index=None, name=None):
        """The interface by SNMP index or by name, made when new. Telegraf rows carry both; gNMI,
        MDT and our pollers only the name."""
        if index is not None and str(index) in self.interfaces:
            found = self.interfaces[str(index)]
            if name and not found.name:
                found.name = name
            return found
        if name:
            for iface in self.interfaces.values():
                if iface.name and iface.name.lower() == str(name).lower():
                    if index is not None and iface.index is None:
                        iface.index = str(index)
                    return iface
        iface = Interface(str(index) if index is not None else None, name)
        self.interfaces[str(index) if index is not None else f'name:{name}'] = iface
        return iface

    def port_name(self, key):
        """A port key (ifIndex or name) as the port's name, or None."""
        if key is None:
            return None
        iface = self.interfaces.get(str(key))
        if iface is not None:
            return iface.name
        return str(key) if not str(key).isdigit() else None

    def online(self, now=None):
        return (time.time() if now is None else now) - self.seen < STALE


class State:
    """Every device's latest picture. Thread-safe: points come in on the intake thread while
    pages read."""

    def __init__(self):
        self._lock = threading.Lock()
        self.devices = {}
        # False on a standby agent (VRRP): another agent collects, this picture is not the hall's.
        self.collecting = True
        # Why devices send nothing (problems.Problems), set by the collector on the agent.
        self.problems = None
        self.points = 0
        self.unknown = 0               # points no driver here understands (kept in storage only)
        self._expired = 0.0

    def reset(self):
        with self._lock:
            self.devices.clear()
            self.points = self.unknown = 0
            self.collecting = True

    def device(self, name):
        with self._lock:
            return self.devices.get(name)

    def find(self, hostname):
        """The device for a floor plan switch name: by name, sysName or address, case-insensitive."""
        want = str(hostname or '').strip().lower()
        if not want:
            return None
        with self._lock:
            for dev in self.devices.values():
                if want in {str(x).lower() for x in (dev.name, dev.sys_name, dev.address) if x}:
                    return dev
            short = want.split('.')[0]
            for dev in self.devices.values():
                if any(str(x).lower().split('.')[0] == short for x in (dev.name, dev.sys_name) if x):
                    return dev
        return None

    def _device_for(self, tags):
        name = tags.get('device') or tags.get('host')
        if not name:
            # Traps and MDT dial-out carry no token and only say where they came from: taken only
            # from a device set up with that address or MDT node name, so a spoofed sender can't
            # add devices.
            sender = tags.get('mdt_source') or tags.get('source') or tags.get('agent_host')
            if not sender:
                return None
            known = next((d for d in self.devices.values()
                          if sender in (d.name, d.address, d.mdt_node) and (d.address or d.mdt_node)), None)
            if known is None:
                return None
            name = known.name
        dev = self.devices.get(name)
        if dev is None:
            dev = self.devices[name] = Device(name)
        if tags.get('address') or tags.get('agent_host'):
            dev.address = tags.get('address') or tags.get('agent_host')
        if tags.get('driver'):
            dev.driver = tags['driver']
        if tags.get('kind'):
            dev.kind = tags['kind']
        return dev

    def know(self, targets):
        """Make the configured devices known before they send, so traps and MDT from their address
        find them, and a device that never sent shows as offline instead of missing."""
        with self._lock:
            for t in targets:
                dev = self.devices.get(t['name'])
                if dev is None:
                    dev = self.devices[t['name']] = Device(t['name'])
                dev.address = t.get('address') or dev.address
                dev.mdt_node = t.get('mdt_node') or dev.mdt_node
                dev.kind = t.get('kind') or dev.kind
                dev.driver = dev.driver or ','.join(t.get('drivers') or [])

    def apply(self, points, now=None):
        """Take a batch of points. Returns how many were understood."""
        now = time.time() if now is None else now
        used = 0
        with self._lock:
            for point in points:
                self.points += 1
                dev = self._device_for(point.tags)
                if dev is None:
                    self.unknown += 1
                    continue
                at = point.time or now
                handler = _HANDLERS.get(point.measurement) or _generic
                if handler(dev, point, at):
                    dev.seen = max(dev.seen, min(at, now))
                    used += 1
                else:
                    self.unknown += 1
            if now - self._expired >= EXPIRE_EVERY or now < self._expired:
                # Not per post: a 2,000-switch hall posts 200 times a second, and each pass walks
                # every device's tables.
                self._expire(now)
                self._expired = now
        return used

    def apply_text(self, text, now=None):
        points, bad = lineproto.parse(text)
        return self.apply(points, now), len(points), bad

    def _expire(self, now):
        for dev in self.devices.values():
            for table in (dev.fdb, dev.arp, dev.lldp, dev.cdp):
                for key in [k for k, row in table.items() if now - row[-1] > TABLE_TTL]:
                    del table[key]


# ── one handler per shape ─────────────────────────────────────────────────────────────────────

def _index(point):
    return point.tags.get('index') or point.tags.get('ifIndex')


def _system(dev, point, at):
    f = point.fields
    dev.sys_name = f.get('sysName') or dev.sys_name
    if _num(f.get('sysUpTime')) is not None:
        dev.uptime = _num(f['sysUpTime']) / 100          # TimeTicks are hundredths
    for key in ('cpu', 'cpu_load'):
        if _num(f.get(key)) is not None:
            dev.cpu = _num(f[key])
    for key in ('mem', 'mem_percent'):
        if _num(f.get(key)) is not None:
            dev.mem = _num(f[key])
    return True


def _interface(dev, point, at):
    f, t = point.fields, point.tags
    iface = dev.port(_index(point), t.get('ifName') or f.get('ifName') or t.get('name') or t.get('interface'))
    _fill(iface, {_key(k): v for k, v in f.items()}, at)
    if f.get('ifAlias') is not None or t.get('ifAlias') is not None:
        iface.alias = str(f.get('ifAlias') or t.get('ifAlias') or '').strip() or None
    return True


# Counter fields by meaning: (names from IF-MIB, OpenConfig, NX-OS, Telegraf net), attribute, rate.
COUNTERS = (
    (('ifhcinoctets', 'in_octets', 'ifinoctets', 'eth_inbytes', 'bytes_recv'), 'in_octets', 'in_bps'),
    (('ifhcoutoctets', 'out_octets', 'ifoutoctets', 'eth_outbytes', 'bytes_sent'), 'out_octets', 'out_bps'),
    (('ifinerrors', 'in_errors', 'eth_inerr', 'err_in'), 'in_errors', 'in_err_rate'),
    (('ifouterrors', 'out_errors', 'eth_outerr', 'err_out'), 'out_errors', 'out_err_rate'),
)


def _fill(iface, f, at):
    """Interface fields by meaning, from IF-MIB, OpenConfig and NX-OS names alike."""
    for key in ('ifoperstatus', 'oper_status', 'operstatus', 'oper_state'):
        if key in f and _status(f[key]):
            iface.oper = _status(f[key])
            break
    for key in ('ifadminstatus', 'admin_status', 'adminstatus', 'admin_state'):
        if key in f and _status(f[key]):
            iface.admin = _status(f[key])
            break
    if _num(f.get('ifhighspeed')):
        iface.speed = _num(f['ifhighspeed']) * 1e6
    elif _num(f.get('ifspeed')) and not iface.speed:
        iface.speed = _num(f['ifspeed'])
    elif _num(f.get('port_speed')):                       # OpenConfig: SPEED_10GB etc. aren't numbers
        iface.speed = _num(f['port_speed'])
    elif _num(f.get('high_speed')):
        iface.speed = _num(f['high_speed']) * 1e6
    elif _num(f.get('eth_speed')):                         # NX-OS: Mbit/s
        iface.speed = _num(f['eth_speed']) * 1e6
    if _num(f.get('dot3statsduplexstatus')) is not None:
        iface.duplex = DUPLEX.get(int(_num(f['dot3statsduplexstatus'])))
    if _num(f.get('iflastchange')) is not None:
        iface.last_change = _num(f['iflastchange'])
    for names, attr, rate in COUNTERS:
        for name in names:
            if _num(f.get(name)) is not None:
                setattr(iface, attr, _num(f[name]))
                per_second = iface.count(attr, f[name], at)
                if per_second is not None:
                    setattr(iface, rate, per_second * 8 if attr.endswith('octets') else per_second)
                break
    iface.seen = at


def _cpu(dev, point, at):
    """One row per CPU (or supervisor): the busiest counts."""
    value = _num(point.fields.get('cpu'))
    if value is None:
        return False
    rows = getattr(dev, '_cpu_rows', None)
    if rows is None:
        rows = dev._cpu_rows = {}
    rows[str(_index(point))] = (value, at)
    dev.cpu = max(v for v, seen in rows.values() if at - seen < STALE)
    return True


def _bridge(dev, point, at):
    if _index(point) and _num(point.fields.get('ifIndex')) is not None:
        dev.bridge_ports[str(_index(point))] = str(int(_num(point.fields['ifIndex'])))
        return True
    return False


def _fdb_port(dev, bridge_port):
    if bridge_port is None:
        return None
    bridge_port = str(int(bridge_port))
    return dev.bridge_ports.get(bridge_port, bridge_port if not dev.bridge_ports else None)


def _fdb(dev, point, at):
    """BRIDGE-MIB dot1dTpFdbTable: the index is the MAC; the VLAN comes from the poll (Cisco
    answers it per VLAN community or context, telegraf.py asks once per VLAN)."""
    parts = str(_index(point) or '').split('.')
    mac = _mac_from_index(parts[-6:])
    port = _fdb_port(dev, _num(point.fields.get('dot1dTpFdbPort')))
    status = _num(point.fields.get('dot1dTpFdbStatus'))
    if not mac or port is None or status == 4:            # 4: self, the switch's own MAC
        return False
    dev.fdb[(mac, point.tags.get('vlan') or '')] = [port, at]
    return True


def _qfdb(dev, point, at):
    """Q-BRIDGE-MIB dot1qTpFdbTable: index is VLAN (FDB id) then the MAC."""
    parts = str(_index(point) or '').split('.')
    if len(parts) < 7:
        return False
    mac = _mac_from_index(parts[-6:])
    port = _fdb_port(dev, _num(point.fields.get('dot1qTpFdbPort')))
    status = _num(point.fields.get('dot1qTpFdbStatus'))
    if not mac or port is None or status == 4:
        return False
    dev.fdb[(mac, parts[0])] = [port, at]
    return True


def _arp(dev, point, at):
    """IP-MIB ipNetToMediaTable (index ifIndex.a.b.c.d), or a row by name from a poller."""
    t, f = point.tags, point.fields
    mac = _mac(f.get('mac') or t.get('mac') or f.get('ipNetToMediaPhysAddress'))
    ip, port = t.get('ip'), t.get('port')
    if not ip:
        parts = str(_index(point) or '').split('.')
        if len(parts) >= 5:
            port, ip = parts[0], '.'.join(parts[-4:])
    if not ip or not mac:
        return False
    dev.arp[ip] = [mac, port, at]
    return True


def _lldp(dev, point, at):
    parts = str(_index(point) or '').split('.')
    if len(parts) < 3:
        return False
    f = point.fields
    dev.lldp[(parts[1], parts[2])] = [{'local': parts[1], 'remote': f.get('lldpRemSysName'),
                                       'remote_port': f.get('lldpRemPortId') or f.get('lldpRemPortDesc'),
                                       'remote_port_desc': f.get('lldpRemPortDesc')}, at]
    return True


def _lldp_local(dev, point, at):
    if not _index(point):
        return False
    f = point.fields
    dev.lldp_local[str(_index(point))] = f.get('lldpLocPortId') or f.get('lldpLocPortDesc')
    return True


def _cdp(dev, point, at):
    parts = str(_index(point) or '').split('.')
    if len(parts) < 2:
        return False
    f = point.fields
    dev.cdp[(parts[0], parts[1])] = [{'local': parts[0], 'remote': f.get('cdpCacheDeviceId'),
                                      'remote_port': f.get('cdpCacheDevicePort')}, at]
    return True


def _trap(dev, point, at):
    """linkUp / linkDown: the port changes now, not at the next poll."""
    t, f = point.tags, point.fields
    name, oid = t.get('name') or '', t.get('oid') or ''
    if name == 'linkDown' or oid.endswith(LINK_DOWN):
        oper = 'down'
    elif name == 'linkUp' or oid.endswith(LINK_UP):
        oper = 'up'
    else:
        return True                       # another trap: the device spoke, nothing to change
    index = f.get('ifIndex')
    if index is None:
        index = next((v for k, v in f.items() if k.lstrip('.').startswith(IF_INDEX_OID) or k.endswith('ifIndex')), None)
    if index is None:
        return True
    iface = dev.port(str(int(_num(index))) if _num(index) is not None else index, f.get('ifName') or f.get('ifDescr'))
    iface.oper = oper
    iface.last_change = at
    return True


def _gateway(dev, point, at):
    f = point.fields
    name = point.tags.get('gateway')
    if not name:
        return False
    dev.kind = 'firewall'
    dev.gateways[name] = {'status': f.get('status'), 'delay_ms': _num(f.get('delay_ms')),
                          'loss_pct': _num(f.get('loss_pct')), 'seen': at}
    return True


# A firewall's own Telegraf (OPNsense os-telegraf, pfSense's package): the inputs they ship.
def _fw_cpu(dev, point, at):
    if point.tags.get('cpu', 'cpu-total') != 'cpu-total' or _num(point.fields.get('usage_idle')) is None:
        return True
    dev.cpu = round(100 - _num(point.fields['usage_idle']), 1)
    return True


def _fw_mem(dev, point, at):
    if _num(point.fields.get('used_percent')) is not None:
        dev.mem = round(_num(point.fields['used_percent']), 1)
    return True


def _fw_net(dev, point, at):
    name = point.tags.get('interface')
    if not name or name == 'all':
        return True
    _fill(dev.port(None, name), {_key(k): v for k, v in point.fields.items()}, at)
    return True


def _fw_pf(dev, point, at):
    dev.kind = 'firewall'
    if _num(point.fields.get('entries')) is not None:
        dev.states = int(_num(point.fields['entries']))
    return True


def _fw_system(dev, point, at):
    if _num(point.fields.get('uptime')) is not None:
        dev.uptime = _num(point.fields['uptime'])
    return True


def _generic(dev, point, at):
    """gNMI and MDT: anything with an interface name and interface fields."""
    t = point.tags
    name = (t.get('name') or t.get('interface_name') or t.get('interface-name') or t.get('interface')
            or t.get('if_name') or t.get('id'))
    m = point.measurement.lower()
    if not name or not ('interface' in m or 'intf' in m or 'if' in _key(m)):
        return False
    fields = {_key(k): v for k, v in point.fields.items()}
    _fill(dev.port(None, name), fields, at)
    return True


_HANDLERS = {
    'fb_system': _system, 'fb_tables': _system, 'fb_vlan': _system, 'fb_if': _interface, 'fb_cpu': _cpu,
    'fb_bridge': _bridge, 'fb_fdb': _fdb, 'fb_qfdb': _qfdb, 'fb_arp': _arp, 'fb_lldp': _lldp,
    'fb_lldp_loc': _lldp_local, 'fb_cdp': _cdp, 'snmp_trap': _trap, 'fb_gateway': _gateway,
    'cpu': _fw_cpu, 'mem': _fw_mem, 'net': _fw_net, 'pf': _fw_pf, 'system': _fw_system,
}



def register(measurement, handler, private=False):
    """Teach the picture a new measurement (docs/telemetry.md, "Extending it"). ``handler(device,
    point, at)`` updates the state.Device and returns True when it understood the point. A
    plugin's driver calls this when it starts; ``private`` keeps the measurement out of storage
    (anything naming machines: MACs, IPs, user names)."""
    global PRIVATE
    _HANDLERS[measurement] = handler
    if private:
        PRIVATE = PRIVATE | {measurement}


# Measurements that name people's machines (MACs, IPs): never stored as series (storage.py).
PRIVATE = frozenset({'fb_fdb', 'fb_qfdb', 'fb_arp', 'fb_bridge', 'fb_lldp', 'fb_lldp_loc', 'fb_cdp'})

state = State()
