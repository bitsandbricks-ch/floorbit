"""The latest picture of each device, built from telemetry points (lineproto.Point).

This is what the telemetry monitoring source answers from (floorbit/builtin_plugins/telemetry): a
switch's ports with their state, rates and errors, its MAC table, ARP, LLDP and CDP neighbours,
and a firewall's gateways and states. Only the newest values are kept, in memory: the time series
go to storage.py, and MAC tables and ARP never do (they name the people at the seats).

Points come in several shapes, one per driver (docs/telemetry.md):

- SNMP polling, as floorbit/telemetry/telegraf.py asks Telegraf for it: ``fb_system``, ``fb_if``,
  ``fb_bridge``, ``fb_fdb``, ``fb_qfdb``, ``fb_arp``, ``fb_lldp``, ``fb_lldp_loc``, ``fb_cdp``,
  ``fb_mem``, each table row with its SNMP index in the ``index`` tag; and, every few minutes, what
  the device is: ``fb_facts``, ``fb_entity``, ``fb_storage``, ``fb_hrdevice`` (Device.summary).
- SNMP traps (Telegraf ``snmp_trap``): linkUp and linkDown change a port at once, between polls.
- gNMI and Cisco model-driven telemetry (NX-OS, IOS-XE): OpenConfig or native interface paths.
  Field names differ by platform and path, so the last part of each name is what counts
  (``state/counters/in-octets`` and ``in_octets`` are the same thing here).
- Our own pollers (pollers.py: NX-API, the OPNsense API) and anything else: ``fb_arp`` and
  ``fb_if`` rows keyed by name (``ip``, ``mac``, ``port`` tags) instead of an SNMP index.
- A firewall's own Telegraf (OPNsense ``os-telegraf``, the pfSense Telegraf package): ``cpu``,
  ``mem``, ``net``, ``pf``, ``system``, with the firewall in the ``host`` tag.
- A wireless controller's access points: ``fb_wlc_ap`` (each joined access point), ``fb_wlc_radio``
  (its radios' channel and width) and ``fb_wlc_rrm`` (each radio's load and clients), keyed by the
  AP's MAC and the radio slot (Device.wifi_aps): a Catalyst 9800 over MDT (tags), an AireOS
  controller over SNMP (AIRESPACE-WIRELESS-MIB, MAC and slot in the index). Counts only: the
  controller's client list is never asked for, and storage.py drops it if a device sends it anyway.
"""
import ipaddress
import re
import threading
import time

from . import lineproto

EXPIRE_EVERY = 10      # seconds between passes that drop rows past TABLE_TTL
MIN_RATE_GAP = 2.0     # seconds between two counter readings worth a rate
TABLE_TTL = 600        # seconds a MAC, ARP or neighbour row lives without being seen again
MAX_ENTITY = 2000      # ENTITY-MIB rows kept per device: a big chassis lists every optic and sensor
MAX_OPTICS = 500       # transceivers reported per device
# An optic by its model, description or name: SFP-10G-SR, GLC-LH-SMD, "1000BaseSX SFP", QSFP-40G-SR4, ...
OPTIC = re.compile(r'SFP|GBIC|XFP|CFP|TRANSCEIVER|GLC-|BASE-?[A-Z]{1,3}\d?\b|TWINAX', re.I)
STALE = 180            # a device that sent nothing for this long reads as offline
AP_TTL = 86400         # an AP the controller stopped naming stays listed (down) this long
MAX_APS = 4000         # access points kept per wireless controller
OPER = {1: 'up', 2: 'down', 3: 'testing', 4: 'unknown', 5: 'dormant', 6: 'notPresent', 7: 'lowerLayerDown'}
DUPLEX = {1: 'unknown', 2: 'halfDuplex', 3: 'fullDuplex'}
LINK_DOWN = '1.3.6.1.6.3.1.1.5.3'
LINK_UP = '1.3.6.1.6.3.1.1.5.4'
IF_INDEX_OID = '1.3.6.1.2.1.2.2.1.1'
IF_NAME_OID = '1.3.6.1.2.1.31.1.1.1.1'
IF_DESCR_OID = '1.3.6.1.2.1.2.2.1.2'


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

    def merge(self, other):
        """Take what another record of this same port knows and this one doesn't yet."""
        for slot in self.__slots__:
            if slot in ('_counted', 'index', 'name', 'seen'):
                continue
            if getattr(self, slot) is None:
                setattr(self, slot, getattr(other, slot))
        self.seen = max(self.seen, other.seen)
        self._counted = {**other._counted, **self._counted}

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
        self.polled = None                # the first full SNMP port poll: before it, ports are partial
        self.snmp = False                 # set up to be polled by SNMP (know())
        self.temps = {}                   # sensor -> (degrees C, seen)
        self.interfaces = {}              # index or name -> Interface
        self.bridge_ports = {}            # bridge port -> ifIndex
        self.lldp_local = {}              # LLDP local port number -> port name
        self.fdb = {}                     # (mac, vlan) -> [port key, seen]
        self.arp = {}                     # ip -> [mac, port key, seen]
        self.lldp = {}                    # (local port, remote index) -> [row, seen]
        self.cdp = {}
        self.gateways = {}                # name -> {status, delay_ms, loss_pct, seen}
        self.facts = {}                   # what it is, for discovery: see facts()
        self._entity = {}                 # ENTITY-MIB index -> row: the chassis, modules, optics
        self._entity_if = {}              # ENTITY-MIB index -> ifIndex (entAliasMappingTable)
        self._storage = {}                # hrStorage index -> (kind, bytes)
        self._processors = {}             # hrDevice index -> description
        self.if_facts = {}                # ifIndex -> {mac, ips {address: prefix}, vlan, mode}
        self.vlans = {}                   # VLAN id -> name
        self.routes = {}                  # 'dest/len via next hop' -> {network, next_hop, ifindex, proto}
        self.poe = {}                     # 'group.port' -> POWER-ETHERNET-MIB (+ Cisco) fields
        self.pse = {}                     # PoE group (a stack member) -> {budget_w, used_w, on}
        self.aps = {}                     # a wireless controller's APs: AP MAC -> {name, model, radios, ...}

    # ports -----------------------------------------------------------------------------------
    def port(self, index=None, name=None):
        """The interface by SNMP index or by name, made when new. Telegraf rows carry both; gNMI,
        MDT and our pollers only the name."""
        key = str(index) if index is not None else None
        by_index = self.interfaces.get(key) if key is not None else None
        by_name = None
        if name and (by_index is None or not by_index.name):
            want = str(name).lower()
            by_name = next((i for i in self.interfaces.values() if i.name and i.name.lower() == want), None)
        if by_index is not None:
            if by_name is not None and by_name is not by_index and by_name.index is None:
                # The same port seen twice before its rows met (a firewall's own Telegraf names igb0,
                # an SNMP row gave only its index): one port, or pickers list it twice (#972).
                by_index.merge(by_name)
                self._drop(by_name)
            if name and not by_index.name:
                by_index.name = name
            return by_index
        if by_name is not None:
            if key is not None and by_name.index is None:
                by_name.index = key
                self._drop(by_name)
                self.interfaces[key] = by_name   # found by its index from now on
            return by_name
        iface = Interface(key, name)
        self.interfaces[key if key is not None else f'name:{name}'] = iface
        return iface

    def _drop(self, iface):
        for k in [k for k, v in self.interfaces.items() if v is iface]:
            del self.interfaces[k]

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

    def temperature(self, now=None):
        """The hottest sensor heard lately (degrees C), or None: the one that trips first matters."""
        now = time.time() if now is None else now
        fresh = [v for v, seen in self.temps.values() if now - seen < STALE]
        return max(fresh) if fresh else None

    def waiting(self):
        """Polled by SNMP but its port table isn't in yet: a trap or a stream may have named a few
        ports, which would read as the switch's port count."""
        return self.snmp and self.polled is None

    def poe_ports(self):
        """PoE per ifIndex: {ifIndex: {state, class, draw_w, allocated_w}}. Cisco names each row's
        ENTITY-MIB port, which the alias table maps to its interface; elsewhere the port number is
        the ifIndex (HPE/Aruba, most others) when the switch has one PoE group."""
        out = {}
        groups = {key.split('.')[0] for key in self.poe}
        for key, f in self.poe.items():
            if 'cpeExtPsePortEntPhyIndex' in f:
                index = self._entity_if.get(str(int(_num(f['cpeExtPsePortEntPhyIndex']) or 0)))
            else:
                index = key.split('.')[-1] if len(groups) == 1 else None
            if index is None or str(index) not in self.interfaces:
                continue
            admin, found = _num(f.get('pethPsePortAdminEnable')), _num(f.get('pethPsePortDetectionStatus'))
            row = {'state': 'off' if admin == 2 else POE_STATE.get(int(found or 0), 'unknown')}
            klass = _num(f.get('pethPsePortPowerClassifications'))
            if klass and row['state'] == 'delivering':
                row['class'] = int(klass) - 1
            for field, name in (('cpeExtPsePortPwrConsumption', 'draw_w'),
                                ('cpeExtPsePortPwrAllocated', 'allocated_w')):
                if _num(f.get(field)) is not None:
                    row[name] = round(_num(f[field]) / 1000, 1)
            out[str(index)] = row
        return out

    def port_facts(self, iface, poe=None):
        """What discovery knows of one port: mac, ips ['a.b.c.d/nn'], vlan, mode, and its PoE
        (``poe``: poe_ports(), worked out once for all ports)."""
        facts = self.if_facts.get(str(iface.index)) if iface.index is not None else None
        power = (poe if poe is not None else self.poe_ports()).get(str(iface.index)) if self.poe else None
        if not facts:
            return {'poe': power} if power else {}
        out = {k: facts[k] for k in ('mac', 'vlan', 'mode') if facts.get(k)}
        if power:
            out['poe'] = power
        if facts.get('ips'):
            out['ips'] = [f'{ip}/{prefix}' for ip, prefix in sorted(facts['ips'].items())]
        return out

    def transceivers(self):
        """The optics ENTITY-MIB lists, for discovery: [{port, model, descr, serial}]. An optic is a
        module or port row with a serial whose name, model or description reads like one."""
        out = []
        for index, row in sorted(self._entity.items(), key=lambda kv: _natural_index(kv[0])):
            if _num(row.get('entPhysicalClass')) not in (9, 10):              # module, port
                continue
            serial = _text(row.get('entPhysicalSerialNum'))
            model, descr = _text(row.get('entPhysicalModelName')), _text(row.get('entPhysicalDescr'))
            name = _text(row.get('entPhysicalName'))
            if not serial or not OPTIC.search(f'{model} {descr} {name}'):
                continue
            out.append({'port': self._entity_port(index, name), 'model': model[:80], 'descr': descr[:120],
                        'serial': serial[:64]})
            if len(out) >= MAX_OPTICS:
                break
        return out

    def _entity_port(self, index, name):
        """The interface an optic sits in: its own alias mapping, its parent's (Cisco maps the port
        row, not the module in it), or an interface of the same name."""
        seen = set()
        while index and index not in seen and len(seen) < 4:
            seen.add(index)
            if index in self._entity_if:
                port = self.port_name(self._entity_if[index])
                if port:
                    return port
            parent = _num((self._entity.get(index) or {}).get('entPhysicalContainedIn'))
            index = str(int(parent)) if parent else None
        wanted = str(name or '').lower()
        return next((i.name for i in self.interfaces.values() if wanted and (i.name or '').lower() == wanted), '')

    def wifi_aps(self, now=None):
        """A wireless controller's access points as the Wi-Fi view takes them (floorbit/wifi.py
        clean_ap): name, model, up or down, and per radio its band, channel, width, load and clients.
        An AP the controller hasn't named for STALE seconds has left it: down."""
        now = time.time() if now is None else now
        out = []
        for ap in self.aps.values():
            if not ap.get('name'):
                continue
            joined = now - ap['seen'] < STALE and ap.get('up', True)
            radios = []
            for slot, r in sorted(ap['radios'].items()):
                band = r.get('band') or _band_of(None, r.get('channel'), slot)
                if not band or now - r['seen'] > STALE or r.get('up') is False:
                    continue
                radios.append({'band': band, 'channel': r.get('channel'), 'width': r.get('width'),
                               'utilization': r.get('utilization'), 'clients': r.get('clients') or 0})
            out.append({'name': ap['name'], 'model': ap.get('model') or '', 'status': 'up' if joined else 'down',
                        'radios': radios if joined else [], 'controller': self.name})
        return out

    def summary(self):
        """What the device said it is (``fb_facts`` and its tables), as discovery takes it: model,
        serial, software, descr, location, memory_mb, disk_gb, cores, cpu. Only what it said."""
        out = {k: v for k, v in self.facts.items() if v not in (None, '')}
        chassis = [row for _i, row in sorted(self._entity.items(), key=lambda kv: _natural_index(kv[0]))
                   if _num(row.get('entPhysicalClass')) == 3]
        if chassis:
            # A stack answers one chassis per member: the first is the one in charge.
            for field, key in (('entPhysicalModelName', 'model'), ('entPhysicalSerialNum', 'serial'),
                               ('entPhysicalSoftwareRev', 'software')):
                value = _text(chassis[0].get(field))
                if value:
                    out[key] = value
        ram = sum(b for kind, b in self._storage.values() if kind == 'ram')
        if ram and 'memory_mb' not in out:
            out['memory_mb'] = round(ram / 2 ** 20)
        disk = sum(b for kind, b in self._storage.values() if kind == 'disk')
        if disk:
            out['disk_gb'] = round(disk / 1e9)
        if self.vlans:
            out['vlans'] = {str(v): name for v, name in sorted(self.vlans.items())}
        networks, svis = set(), []
        from ..segments import vlan_of_interface
        for if_index, facts in self.if_facts.items():
            vlan = vlan_of_interface(self.port_name(if_index) or facts.get('name'))
            for ip, prefix in (facts.get('ips') or {}).items():
                if prefix < 32:
                    network = str(ipaddress.ip_network(f'{ip}/{prefix}', strict=False))
                    networks.add(network)
                    # A VLAN interface with an address: a segment (floorbit/segments.py), and the
                    # ifIndex an IP's ARP entry is asked under (issue #947).
                    if vlan and len(svis) < 256:
                        svis.append({'vlan': vlan, 'network': network, 'if_index': int(if_index)})
        if networks:
            out['networks'] = sorted(networks)
        if svis:
            out['svis'] = sorted(svis, key=lambda v: (v['vlan'], v['network']))
        if self.pse:
            on = [g for g in self.pse.values() if g.get('on') and g.get('budget_w')]
            if on:
                out['poe'] = {'budget_w': sum(g['budget_w'] for g in on),
                              'used_w': sum(g.get('used_w') or 0 for g in on)}
        if self.routes:
            out['routes'] = [{**{k: v for k, v in r.items() if k != 'ifindex'},
                              'interface': self.port_name(r['ifindex']) or ''}
                             for _k, r in sorted(self.routes.items(), key=lambda kv: _route_order(kv[1]))]
        optics = self.transceivers()
        if optics:
            out['transceivers'] = optics
        if self._processors:
            out['cores'] = len(self._processors)
            names = [d for d in self._processors.values() if d]
            if names:
                out['cpu'] = names[0]
        return out


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
        # Traps and streams from addresses no device here has: listed as unknown senders (#1443).
        from ..unknown_senders import Seen
        self.senders = Seen()
        self._expired = 0.0

    def reset(self):
        with self._lock:
            self.devices.clear()
            self.points = self.unknown = 0
            self.collecting = True
            self.senders.clear()

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
        if name and not tags.get('device') and name not in self.devices:
            # A firewall's own Telegraf names itself by its host name, often the full one
            # (fw-01.example.org); the device set up here is fw-01.
            short = name.split('.')[0]
            if short in self.devices:
                name = short
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

    def _unknown_sender(self, point, now):
        tags = point.tags
        sender = tags.get('mdt_source') or tags.get('source') or tags.get('agent_host')
        if not sender or tags.get('device') or tags.get('host'):
            return
        kind = 'trap' if 'trap' in point.measurement else 'stream'
        self.senders.note(kind, sender, name=tags.get('sysName') or tags.get('sys_name') or '', now=now)

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
                # poll_ports is False while LibreNMS polls the ports (polling.apply): no poll to wait for.
                dev.snmp = 'snmp' in (t.get('drivers') or []) and t.get('poll_ports', True) is not False

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
                    self._unknown_sender(point, now)
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
            for key in [k for k, ap in dev.aps.items() if now - ap['seen'] > AP_TTL]:
                del dev.aps[key]


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


def _text(value):
    """A string from SNMP as Telegraf sends it: escaped line breaks become spaces."""
    if value is None or isinstance(value, bool):
        return ''
    text = str(value).replace('\\r', ' ').replace('\\n', ' ').replace('\r', ' ').replace('\n', ' ')
    return ' '.join(text.split())[:500]


def _natural_index(index):
    return [int(p) if p.isdigit() else p for p in str(index).split('.')]


def _facts(dev, point, at):
    """sysDescr, sysLocation and hrMemorySize, with the tables below: what the device is."""
    f = point.fields
    for field, key in (('sysDescr', 'descr'), ('sysLocation', 'location')):
        if field in f:
            dev.facts[key] = _text(f[field])
    if _num(f.get('hrMemorySize')):
        dev.facts['memory_mb'] = round(_num(f['hrMemorySize']) / 1024)
    return True


def _entity(dev, point, at):
    if not _index(point):
        return False
    index = str(_index(point))
    if index not in dev._entity and len(dev._entity) >= MAX_ENTITY:
        return True
    dev._entity.setdefault(index, {}).update(point.fields)
    return True


def _entalias(dev, point, at):
    """entAliasMappingTable: which ifIndex an ENTITY-MIB row is. The value is the OID of ifIndex.N,
    numeric or named as Telegraf's gosmi writes it without MIBs (``iso.3.6.1...``)."""
    parts = str(_index(point) or '').split('.')
    value = str(point.fields.get('entAliasMappingIdentifier') or '')
    match = re.search(r'(?:^|\.)(?:3\.6\.1\.2\.1\.2\.2\.1\.1|ifIndex)\.(\d+)$', value)
    if not parts[0] or not match:
        return bool(parts[0])
    if parts[0] in dev._entity_if or len(dev._entity_if) < MAX_ENTITY:
        dev._entity_if[parts[0]] = match.group(1)
    return True


MAX_ROUTES = 2000
ROUTE_PROTO = {1: 'other', 2: 'connected', 3: 'static', 8: 'rip', 9: 'isis', 13: 'ospf', 14: 'bgp'}


def _route_order(r):
    net = ipaddress.ip_network(r['network'])
    return (net.prefixlen != 0, int(net.network_address), net.prefixlen)


def _route(dev, point, at):
    """ipCidrRouteTable: index dest(4).mask(4).tos.next hop(4)."""
    parts = str(_index(point) or '').split('.')
    if len(parts) != 13:
        return False
    f = point.fields
    try:
        net = ipaddress.ip_network(f"{'.'.join(parts[0:4])}/{'.'.join(parts[4:8])}", strict=False)
    except ValueError:
        return False
    hop = '.'.join(parts[9:13])
    key = f'{net} via {hop}'
    if key not in dev.routes and len(dev.routes) >= MAX_ROUTES:
        return True
    proto = _num(f.get('ipCidrRouteProto'))
    dev.routes[key] = {'network': str(net), 'next_hop': '' if hop == '0.0.0.0' else hop,
                       'ifindex': str(int(_num(f['ipCidrRouteIfIndex']))) if _num(f.get('ipCidrRouteIfIndex'))
                       else None,
                       'proto': ROUTE_PROTO.get(int(proto or 0), 'other')}
    return True


POE_STATE = {1: 'off', 2: 'searching', 3: 'delivering', 4: 'fault', 5: 'test', 6: 'fault'}


def _poe(dev, point, at):
    """pethPsePortTable and Cisco's extension of it, both indexed group.port: one row each."""
    index = str(_index(point) or '')
    if index.count('.') != 1:
        return False
    if index in dev.poe or len(dev.poe) < MAX_IF_FACTS:
        dev.poe.setdefault(index, {}).update(point.fields)
    return True


def _pse(dev, point, at):
    """pethMainPseTable: each PoE group's (stack member's) budget and what it gives now."""
    f = point.fields
    if not _index(point):
        return False
    if len(dev.pse) < 64 or str(_index(point)) in dev.pse:
        dev.pse[str(_index(point))] = {'budget_w': _num(f.get('pethMainPsePower')),
                                      'used_w': _num(f.get('pethMainPseConsumptionPower')),
                                      'on': _num(f.get('pethMainPseOperStatus')) == 1}
    return True


STORAGE_KINDS = {'25.2.1.2': 'ram', '25.2.1.4': 'disk'}     # hrStorageRam, hrStorageFixedDisk


def _storage(dev, point, at):
    f = point.fields
    kind = next((k for oid, k in STORAGE_KINDS.items() if str(f.get('hrStorageType') or '').endswith(oid)), None)
    size, unit = _num(f.get('hrStorageSize')), _num(f.get('hrStorageAllocationUnits'))
    if not _index(point) or kind is None or not size or not unit:
        return bool(_index(point))
    dev._storage[str(_index(point))] = (kind, size * unit)
    return True


def _hrdevice(dev, point, at):
    """hrDeviceTable: the processor rows say how many cores and which CPU."""
    f = point.fields
    if not _index(point):
        return False
    if str(f.get('hrDeviceType') or '').endswith('25.3.1.3'):        # hrDeviceProcessor
        # net-snmp writes "GenuineIntel: Intel(R) Xeon(R) ...": the vendor prefix says nothing more.
        dev._processors[str(_index(point))] = _text(f.get('hrDeviceDescr')).split(': ', 1)[-1]
    return True


MAX_IF_FACTS = 5000


def _if_fact(dev, index):
    index = str(index)
    if index not in dev.if_facts and len(dev.if_facts) >= MAX_IF_FACTS:
        return {}
    return dev.if_facts.setdefault(index, {})


def _ifmac(dev, point, at):
    if not _index(point):
        return False
    mac = _mac(point.fields.get('ifPhysAddress'))
    if mac:
        _if_fact(dev, _index(point))['mac'] = mac
    name = _text(point.fields.get('ifName'))
    if name:
        _if_fact(dev, _index(point))['name'] = name[:64]
    return True


def _ip(dev, point, at):
    """ipAddrTable: one row per IPv4 address, the address in the index."""
    if_index = _num(point.fields.get('ipAdEntIfIndex'))
    try:
        address = ipaddress.ip_address(str(_index(point) or ''))
        prefix = ipaddress.ip_network(f"0.0.0.0/{point.fields.get('ipAdEntNetMask') or '255.255.255.255'}").prefixlen
    except ValueError:
        return False
    if if_index is None or address.is_loopback:
        return bool(if_index is not None)
    ips = _if_fact(dev, int(if_index)).setdefault('ips', {})
    if len(ips) < 16:
        ips[str(address)] = prefix
    return True


def _vlan_name(dev, vlan, name):
    if vlan is not None and 1 <= vlan <= 4094 and len(dev.vlans) < 4094:
        dev.vlans[vlan] = _text(name)[:64]


def _vtp(dev, point, at):
    parts = str(_index(point) or '').split('.')
    if not parts[-1].isdigit():
        return False
    _vlan_name(dev, int(parts[-1]), point.fields.get('vtpVlanName'))
    return True


def _qvlan(dev, point, at):
    index = str(_index(point) or '').split('.')[-1]
    if not index.isdigit():
        return False
    _vlan_name(dev, int(index), point.fields.get('dot1qVlanStaticName'))
    return True


def _ifvlan(dev, point, at):
    """Cisco: an access port's VLAN (vmVlan) and whether a port trunks."""
    if not _index(point):
        return False
    facts = _if_fact(dev, _index(point))
    vlan = _num(point.fields.get('vmVlan'))
    trunk = _num(point.fields.get('vlanTrunkPortDynamicStatus'))
    if trunk == 1:
        facts['mode'] = 'trunk'
    elif vlan:
        facts['mode'] = 'access'
    if vlan and 1 <= vlan <= 4094 and trunk != 1:
        facts['vlan'] = int(vlan)
    return True


def _pvid(dev, point, at):
    """Q-BRIDGE: the VLAN untagged frames on a bridge port land in."""
    if_index = dev.bridge_ports.get(str(_index(point)))
    vlan = _num(point.fields.get('dot1qPvid'))
    if not if_index or not vlan or not 1 <= vlan <= 4094:
        return bool(_index(point))
    _if_fact(dev, if_index)['vlan'] = int(vlan)
    return True


def _mem(dev, point, at):
    """CISCO-MEMORY-POOL-MIB: pool 1 is the processor's."""
    used, free = _num(point.fields.get('memUsed')), _num(point.fields.get('memFree'))
    if used is None or free is None:
        return False
    if str(_index(point)) == '1' and used + free > 0:
        dev.mem = round(100 * used / (used + free), 1)
        dev.facts['memory_mb'] = round((used + free) / 2 ** 20)
    return True


def _interface(dev, point, at):
    f, t = point.fields, point.tags
    if dev.polled is None:
        dev.polled = at               # fb_if comes from a full SNMP walk of the port table
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


def _envtemp(dev, point, at):
    """CISCO-ENVMON-MIB (Catalyst, IOS-XE): one row per sensor, already in degrees C."""
    value = _num(point.fields.get('tempValue'))
    if value is None:
        return False
    # Some sensors read 0 when absent (an empty slot); a switch room is never at 0 °C.
    if 0 < value < 150:
        dev.temps[f'envmon:{_index(point)}'] = (value, at)
    return True


def _sensor(dev, point, at):
    """ENTITY-SENSOR-MIB (NX-OS and others): only the celsius sensors (type 8), in units (scale 9),
    with their precision as decimals."""
    f = point.fields
    kind, scale, value = _num(f.get('sensorType')), _num(f.get('sensorScale')), _num(f.get('sensorValue'))
    if value is None:
        return False
    if kind == 8 and scale in (None, 9):
        value = value / 10 ** int(_num(f.get('sensorPrecision')) or 0)
        if 0 < value < 150:
            dev.temps[f'sensor:{_index(point)}'] = (value, at)
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


def _numeric(key):
    """A trap varbind's name as a dotted OID: Telegraf's gosmi translator names an OID it has no
    MIB for ``iso.3.6.1...``, older setups ``.1.3.6.1...``; a name from a MIB stays as it is."""
    key = str(key).lstrip('.')
    return '1.' + key[4:] if key.startswith('iso.') else key


def _varbind(fields, name, oid):
    """A varbind by its MIB name or, without MIBs, by its OID (``<oid>.<row>``)."""
    if name in fields:
        return fields[name]
    return next((v for k, v in fields.items() if _numeric(k).startswith(oid + '.')), None)


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
    index = _varbind(f, 'ifIndex', IF_INDEX_OID)
    if index is None:
        return True
    label = _varbind(f, 'ifName', IF_NAME_OID) or _varbind(f, 'ifDescr', IF_DESCR_OID)
    iface = dev.port(str(int(_num(index))) if _num(index) is not None else index, label)
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


# A Catalyst 9800's wireless MDT (Cisco-IOS-XE-wireless-access-point-oper, -rrm-oper). The field
# names below are the YANG leaves' last parts; Telegraf keeps the path before them.

def _tag(tags, *names):
    """A tag by what it means, whatever spelling Telegraf gave its key (wtp-mac, wtp_mac, .../wtp-mac)."""
    by = {_key(k): v for k, v in tags.items()}
    return next((by[n] for n in names if by.get(n) not in (None, '')), None)


# What a controller calls a band: the GHz first (dot11ax runs on every band), then the old letters.
_BAND_PATTERNS = (('2.4', r'2(?:-dot-|[.-])?4-?ghz|band-?24\b'), ('6', r'(?<![\d.])6-?ghz|band-?6\b'),
                  ('5', r'(?<![\d.])5-?ghz|band-?5\b'), ('2.4', r'type-bg?\b|dot11-?[bg]\b'),
                  ('5', r'type-a\b|dot11-?a\b'))


def _band_of(text, channel=None, slot=None):
    """A radio's band from what the controller calls it, else from its channel (1-14 is 2.4 GHz),
    else from its slot (0 is 2.4 GHz and 1 is 5 GHz on Cisco APs)."""
    t = str(text or '').lower().replace('_', '-').replace(' ', '-')
    for band, pattern in _BAND_PATTERNS:
        if re.search(pattern, t):
            return band
    if channel:
        return '2.4' if channel <= 14 else '5'
    return {'0': '2.4', '1': '5'}.get(str(slot)) if slot is not None else None


def _width_of(value):
    """``chan-width-80-mhz``, ``80`` or ``CHAN_WIDTH_80MHZ`` -> 80."""
    m = re.search(r'(20|40|80|160|320)', str(value or ''))
    return int(m.group(1)) if m else None


def _ap_index(point):
    """(AP MAC, radio slot) of a row: MDT names them in tags, AireOS SNMP in the index (MAC as six
    numbers, then the slot)."""
    mac = _mac(_tag(point.tags, 'wtp_mac', 'ap_mac'))
    slot = _tag(point.tags, 'radio_slot_id', 'slot_id', 'slot')
    if mac is None and point.tags.get('index'):
        parts = str(point.tags['index']).split('.')
        mac = _mac_from_index(parts[:6])
        slot = parts[6] if len(parts) == 7 else None
    return mac, slot


def _ap_row(dev, point):
    mac = _ap_index(point)[0]
    if not mac:
        return None
    ap = dev.aps.get(mac)
    if ap is None:
        if len(dev.aps) >= MAX_APS:
            return None
        ap = dev.aps[mac] = {'name': None, 'model': None, 'radios': {}, 'seen': 0.0}
    dev.kind = 'wlc'
    return ap


def _wlc_ap(dev, point, at):
    """capwap-data: one row per joined AP, with its name and model."""
    ap = _ap_row(dev, point)
    if ap is None:
        return False
    f = {_key(k): v for k, v in point.fields.items()}
    name = ' '.join(str(f.get('name') or f.get('bsnapname') or _tag(point.tags, 'name') or '').split())[:80]
    if name:
        ap['name'] = name
    model = f.get('model') or f.get('bsnapmodel')
    if model:
        ap['model'] = ' '.join(str(model).split())[:60]
    if f.get('bsnapoperationstatus') is not None:
        ap['up'] = _num(f['bsnapoperationstatus']) == 1         # associated
    else:
        oper = str(f.get('ap_operation_state') or '').lower()
        admin = str(f.get('ap_admin_state') or '').lower()
        ap['up'] = not ('disabled' in admin or (oper and 'registered' not in oper))
    ap['seen'] = max(ap['seen'], at)
    return True


def _radio_row(dev, point, at):
    ap = _ap_row(dev, point)
    slot = _ap_index(point)[1]
    if ap is None or slot is None or not str(slot).isdigit() or int(slot) > 7:
        return None
    radio = ap['radios'].setdefault(str(slot), {'seen': 0.0})
    radio['seen'] = max(radio['seen'], at)
    # A radio row keeps the AP listed between capwap-data samples.
    ap['seen'] = max(ap['seen'], at)
    return radio


def _wlc_radio(dev, point, at):
    """radio-oper-data: a radio's band, channel and width, and whether it is on."""
    radio = _radio_row(dev, point, at)
    if radio is None:
        return False
    f = {_key(k): v for k, v in point.fields.items()}
    channel = next((_num(f[k]) for k in ('curr_freq', 'channel', 'bsnapifphychannelnumber')
                    if f.get(k) is not None), None)
    radio['channel'] = int(channel) if channel and 1 <= channel <= 233 else None
    radio['width'] = _width_of(f.get('chan_width')) or radio.get('width')
    slot = _ap_index(point)[1]
    if f.get('bsnapiftype') is not None:      # AireOS: dot11b(1) is 2.4 GHz, dot11a(2) 5 GHz
        radio['band'] = {1: '2.4', 2: '5'}.get(_num(f['bsnapiftype'])) or _band_of(None, radio['channel'], slot)
        radio['up'] = _num(f.get('bsnapifoperstatus')) != 1
        return True
    words = ' '.join(str(f.get(k) or '') for k in ('current_active_band', 'current_band_id', 'radio_type', 'band'))
    radio['band'] = _band_of(words, radio['channel'], slot)
    oper, admin = str(f.get('oper_state') or '').lower(), str(f.get('admin_state') or '').lower()
    radio['up'] = not ('down' in oper or 'disabled' in admin)
    return True


def _wlc_rrm(dev, point, at):
    """rrm-measurement: a radio's channel utilization and how many clients it has."""
    radio = _radio_row(dev, point, at)
    if radio is None:
        return False
    f = {_key(k): v for k, v in point.fields.items()}
    util = _num(f.get('cca_util_percentage') if f.get('cca_util_percentage') is not None
                else f.get('bsnapifloadchannelutilization'))
    if util is not None and 0 <= util <= 100:
        radio['utilization'] = round(util)
    clients = _num(f.get('stations') if f.get('stations') is not None else f.get('bsnapifloadnumofclients'))
    if clients is not None and 0 <= clients <= 10000:
        radio['clients'] = int(clients)
    return True


_HANDLERS = {
    'fb_system': _system, 'fb_tables': _system, 'fb_vlan': _system, 'fb_if': _interface, 'fb_cpu': _cpu,
    'fb_bridge': _bridge, 'fb_fdb': _fdb, 'fb_qfdb': _qfdb, 'fb_arp': _arp, 'fb_lldp': _lldp,
    'fb_lldp_loc': _lldp_local, 'fb_cdp': _cdp, 'snmp_trap': _trap, 'fb_gateway': _gateway,
    'cpu': _fw_cpu, 'mem': _fw_mem, 'net': _fw_net, 'pf': _fw_pf, 'system': _fw_system,
    'fb_poe': _poe, 'fb_pse': _pse, 'fb_route': _route,
    'fb_facts': _facts, 'fb_entity': _entity, 'fb_entalias': _entalias, 'fb_storage': _storage,
    'fb_hrdevice': _hrdevice, 'fb_mem': _mem, 'fb_envtemp': _envtemp, 'fb_sensor': _sensor,
    'fb_ifmac': _ifmac, 'fb_ip': _ip, 'fb_vtp': _vtp, 'fb_qvlan': _qvlan, 'fb_ifvlan': _ifvlan, 'fb_pvid': _pvid,
    'fb_wlc_ap': _wlc_ap, 'fb_wlc_radio': _wlc_radio, 'fb_wlc_rrm': _wlc_rrm,
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
# The facts are text that never changes: not series either.
PRIVATE = frozenset({'fb_fdb', 'fb_qfdb', 'fb_arp', 'fb_bridge', 'fb_lldp', 'fb_lldp_loc', 'fb_cdp',
                     'fb_facts', 'fb_entity', 'fb_entalias', 'fb_route', 'fb_storage', 'fb_hrdevice', 'fb_ifmac',
                     'fb_ip', 'fb_vtp', 'fb_qvlan', 'fb_ifvlan', 'fb_pvid'})
# A wireless controller's client list (who is on which AP), should one stream it anyway: its
# Cisco path or an alias someone gave it. Never stored, never understood.
CLIENT_LISTS = re.compile(r'client-oper|client_oper|wireless-client|dot11-client', re.I)


def private(measurement):
    """Is this measurement kept out of storage (MACs, IPs, people)?"""
    return measurement in PRIVATE or bool(CLIENT_LISTS.search(str(measurement)))

state = State()
