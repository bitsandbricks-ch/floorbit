"""Which machine is on which seat port, and the ones the patch plan doesn't explain (issue #473).

The switches' MAC tables (``port_clients`` of the monitoring plugin, LibreNMS FDB) say which MAC is
on which port; the ARP table says that MAC's IP. Put next to the cables and the seat mapping, two
kinds of client stand out:

- ``unplanned``: a client on a seat switch's port that no cable explains (a seat the plan missed,
  a crew laptop, a rogue switch).
- ``moved``: a client on seat A's port whose IP the seat mapping gives to seat B (players swapped
  seats, or the cables at the switch are swapped).
- ``shared``: a seat port with more than one machine on it, a desk switch or router when it has
  many (issue #1119). Those are where loops, a home router's DHCP and a lost seat start. Only the
  count of MACs is kept, never which.

Two more lists catch PCs that never check in (issue #949):

- ``no_port``: an IP in the seat networks that ARP knows but no seat-switch edge port carries yet
  (the gateways and the inventory's own boxes left out).
- ``empty``: a seat cabled to a port with no machine on it; only once check-ins have started, so
  the list isn't every seat before the doors open.

A MAC the crew marked as ignored (a printer, a crew PC) leaves every list.

Ports with many MACs are uplinks or a switch under a desk, and ports cabled without a seat are
infrastructure: neither is a client. Reading every seat switch is many calls at 4000 seats, so a
read runs in the background, at most every two minutes, and the page shows the last one.
"""
import ipaddress
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from . import cables as cables_mod
from . import sources
from .dhcp_leases import leases
from .edge_ports import EDGE_PORT_MACS
from .store import load_data

MAX_LISTED = 200
UPLINK_MACS = EDGE_PORT_MACS     # more MACs than this on one port: not a seat (floorbit/edge_ports.py)
MIN_AGE = 120            # seconds between reads: LibreNMS itself refreshes MAC tables only when it polls
EVERY = 300              # the background read (issue #949): LibreNMS polls the switches anyway
IGNORED = 'port_clients_ignored'   # {mac: {by, at, note}} in the event's data
WORKERS = 4              # switches read side by side: LibreNMS answers one FDB in about a second


def _listed(rows):
    return {'count': len(rows), 'rows': rows[:MAX_LISTED]}


def _seat_ips(seats):
    """{ip: seat} from the seat mapping, for the IPs that parse."""
    out = {}
    for seat, entry in (seats or {}).items():
        ip = str((entry or {}).get('ip_address') or '').strip()
        try:
            out[str(ipaddress.ip_address(ip))] = str(seat).upper()
        except ValueError:
            continue
    return out


def networks(ips):
    """The /24s (IPv4) the seat IPs are in, merged: one ARP query each, not one per seat."""
    nets = set()
    for ip in ips:
        addr = ipaddress.ip_address(ip)
        if addr.version == 4:
            nets.add(ipaddress.ip_network(f'{addr}/24', strict=False))
    return [str(n) for n in ipaddress.collapse_addresses(nets)]


def _arp(monitor, nets):
    """{mac: ip} from ARP, by network."""
    out = {}
    for net in nets:
        for entry in monitor.arp(net) or []:
            mac = sources.normalise_mac(entry.get('mac_address'))
            if mac and entry.get('ipv4_address'):
                out[mac] = entry['ipv4_address']
    return out


def _learned_cables():
    """The seat ports check-ins found (integrations/checkin.py), shaped like cables, so a seat
    nobody patched by plan still shows the MAC and IP on its port."""
    from integrations import checkin
    try:
        rows = checkin.learned_ports()
    except Exception:  # noqa: BLE001  # the patch plan alone still answers
        return []
    return [{'switch': r['switch'], 'port': r['port'], 'seat': seat, 'label': 'check-in'}
            for seat, r in rows.items() if r.get('switch') and r.get('port')]


def _hand_ports(data):
    """The switch ports typed in on the Seat mapping page, shaped like cables."""
    from . import seatmap
    return [{'switch': e['switch'], 'port': e['port'], 'seat': seat, 'label': 'seat mapping'}
            for seat, e in seatmap.entries(data).items() if e.get('switch') and e.get('port')]


def ignored(data):
    raw = data.get(IGNORED)
    return {str(k): v for k, v in raw.items() if isinstance(v, dict)} if isinstance(raw, dict) else {}


def set_ignored(data, mac, on, by=None, note='', now=None):
    """Marks a MAC as not a seat PC (or not any more); ValueError for something that isn't a MAC."""
    mac = sources.normalise_mac(mac)
    if not mac:
        raise ValueError('That is not a MAC address.')
    rows = ignored(data)
    if on:
        rows[mac] = {'by': by, 'at': time.time() if now is None else now, 'note': str(note or '').strip()[:80]}
    else:
        rows.pop(mac, None)
    data[IGNORED] = rows
    return mac


def _infra_ips(data):
    from . import inventory
    return {d['mgmt_ip'] for d in inventory.devices(data) if d.get('mgmt_ip')}


def _gateway(ip):
    """The .1 of a /24 is the seat network's gateway, not a PC: left out of ``no_port``."""
    try:
        return ipaddress.ip_address(ip).packed[-1] == 1
    except ValueError:
        return False


def _checkins_started():
    from integrations import checkin
    try:
        return bool(checkin.load_all())
    except Exception:  # noqa: BLE001
        return False


def find(monitor, data, seats):
    """One read: ``{"unplanned", "moved", "no_port", "empty", "switches", "failed", "clients"}``."""
    from .syslog import canonical_port  # syslog reads attention, which reads cables: late
    all_cables = cables_mod.all_cables(data) + _hand_ports(data) + _learned_cables()
    by_port = {}
    for c in all_cables:   # a patched cable comes first and wins over a port a check-in found
        by_port.setdefault((c['switch'].lower(), canonical_port(c['port'])), c)
    switches = sorted({c['switch'] for c in all_cables if c.get('seat')}, key=str.lower)
    ip_seat = _seat_ips(seats)

    def read(switch):
        try:
            return switch, monitor.port_clients(switch), None
        except Exception as exc:  # noqa: BLE001  # one switch failing must not hide the rest
            return switch, None, str(exc)[:200]

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        reads = list(pool.map(read, switches))
    failed = [{'switch': s, 'error': err or 'No MAC table'} for s, rows, err in reads if rows is None]
    per_port = {}
    for switch, rows, _err in reads:
        for row in rows or []:
            mac = sources.normalise_mac(row.get('mac'))
            if mac and row.get('port'):
                per_port.setdefault((switch, row['port']), set()).add(mac)
    mac_ip = _arp(monitor, networks(ip_seat)) if per_port else {}

    skip = ignored(data)
    unplanned, moved, shared, clients, seat_ips, seat_macs = [], [], [], 0, {}, {}
    on_edge = set()
    for (switch, port), macs in sorted(per_port.items(), key=lambda kv: (kv[0][0].lower(), canonical_port(kv[0][1]))):
        if len(macs) <= UPLINK_MACS:
            on_edge |= macs
        cable = by_port.get((switch.lower(), canonical_port(port)))
        if cable and not cable.get('seat'):
            continue
        # A MAC the crew ignored (their own laptop during the seat walk) doesn't make a port shared.
        if cable and len(macs - skip.keys()) > 1:
            shared.append({'switch': switch, 'port': port, 'seat': cable['seat'], 'cable': cable['label'],
                           'macs': len(macs - skip.keys()), 'desk_switch': len(macs) > UPLINK_MACS})
        if len(macs) > UPLINK_MACS:
            continue
        for mac in sorted(macs):
            if mac in skip:
                continue
            clients += 1
            # A laptop the ARP poll hasn't seen yet may already have its DHCP lease (dhcp_leases.py).
            ip = mac_ip.get(mac) or leases.ip_for_mac(mac) or ''
            row = {'switch': switch, 'port': port, 'mac': mac, 'ip': ip, 'ip_seat': ip_seat.get(ip, '')}
            if cable is None:
                unplanned.append(row)
                continue
            if ip:
                seat_ips[ip] = cable['seat'].upper()
            if len(macs) == 1:      # two machines on one seat port: say nothing rather than guess
                seat_macs[cable['seat']] = {'mac_address': mac, 'ip_address': ip}
            if row['ip_seat'] and row['ip_seat'] != cable['seat'].upper():
                moved.append({**row, 'seat': cable['seat'], 'cable': cable['label']})
    # Desk switches first: they are the ones that loop or hand out addresses.
    shared.sort(key=lambda r: (not r['desk_switch'], -r['macs']))
    # Only from a full read: a switch that didn't answer would make all its PCs look portless.
    no_port, empty = [], []
    if not failed:
        infra = _infra_ips(data)
        for mac, ip in sorted(mac_ip.items(), key=lambda kv: _ip_key(kv[1])):
            if mac in on_edge or mac in skip or ip in infra or _gateway(ip):
                continue
            no_port.append({'mac': mac, 'ip': ip, 'ip_seat': ip_seat.get(ip, '')})
    if _checkins_started():
        read_ok = {s for s, rows, _err in reads if rows is not None}
        busy = {(sw.lower(), canonical_port(p)) for (sw, p) in per_port}
        seen = set()
        for c in all_cables:
            key = (c['switch'].lower(), canonical_port(c['port']))
            if not c.get('seat') or c['switch'] not in read_ok or key in busy or c['seat'] in seen:
                continue
            seen.add(c['seat'])
            empty.append({'seat': c['seat'].upper(), 'switch': c['switch'], 'port': c['port']})
    return {'unplanned': _listed(unplanned), 'moved': _listed(moved), 'shared': _listed(shared),
            'no_port': _listed(no_port),
            'empty': _listed(sorted(empty, key=lambda r: _seat_key(r['seat']))), 'switches': len(switches),
            'failed': failed, 'clients': clients, 'seat_ips': seat_ips, 'seat_macs': seat_macs}


def _ip_key(ip):
    try:
        return (0, ipaddress.ip_address(ip))
    except ValueError:
        return (1, ip)


def _seat_key(seat):
    from .page_index import _seat_key as key
    return key(seat)


def _start(work):
    threading.Thread(target=work, name='port-clients', daemon=True).start()


def without_cabled(state, data=None):
    """The last read, less the unplanned clients whose port got a cable since (patched to a seat,
    or marked as infrastructure), so the list shrinks as the crew works through it."""
    from .syslog import canonical_port
    cabled = {(c['switch'].lower(), canonical_port(c['port'])) for c in cables_mod.all_cables(data)}
    rows = state['unplanned']['rows']
    left = [r for r in rows if (r['switch'].lower(), canonical_port(r['port'])) not in cabled]
    # The rough area the crew gave for that port narrows where to walk (floorbit/port_areas.py).
    from . import port_areas
    areas = port_areas.all_areas(data)
    left = [{**r, 'area': port_areas.hint(r['switch'], r['port'], areas)} for r in left]
    out = {**state, 'unplanned': {'count': state['unplanned']['count'] - (len(rows) - len(left)), 'rows': left}}
    # Marked as ignored since the read: gone from the lists now, not at the next read.
    skip = ignored(data if data is not None else load_data())
    for key in ('unplanned', 'no_port'):
        rows = out.get(key) or {'count': 0, 'rows': []}
        kept = [r for r in rows['rows'] if r.get('mac') not in skip]
        out[key] = {'count': rows['count'] - (len(rows['rows']) - len(kept)), 'rows': kept}
    out['ignored'] = len(skip)
    return out


class Finder:
    """The last read, and a background thread that makes the next one."""

    def __init__(self, app=None):
        self.app = app
        self.result = None
        self.seat_ips = {}     # {ip: seat} on cabled seat ports, last read: the captive answer (captive.py)
        self.seat_macs = {}    # {seat: {mac_address, ip_address}}: the seat mapping's "network" source
        self.as_of = None
        self.error = None
        self._lock = threading.Lock()
        self._running = False

    def run(self, now=None):
        """Read now, in this thread."""
        monitor = sources.monitoring()
        try:
            if not monitor.enabled():
                raise RuntimeError('No monitoring source is set up')
            from integrations import seat_sources
            result = find(monitor, load_data(), seat_sources.load())
            error = None
        except Exception as exc:  # noqa: BLE001  # shown on the page; the last read stays
            result, error = None, str(exc)[:300]
        with self._lock:
            if result is not None:
                self.seat_ips = result.pop('seat_ips', {})
                self.seat_macs = result.pop('seat_macs', {})
                self.result, self.as_of = result, time.time() if now is None else now
            self.error = error
            self._running = False

    def request(self):
        """Start a read in the background unless one is running or the last is fresh."""
        with self._lock:
            if self._running or (self.as_of and 0 <= time.time() - self.as_of < MIN_AGE):
                return False
            self._running = True

        def work():
            if self.app is None:
                self.run()
                return
            with self.app.app_context():
                self.run()

        _start(work)
        return True

    def state(self):
        with self._lock:
            return {'as_of': self.as_of, 'reading': self._running, 'error': self.error,
                    **(self.result or {'unplanned': _listed([]), 'moved': _listed([]), 'shared': _listed([]),
                                       'no_port': _listed([]), 'empty': _listed([]), 'switches': 0,
                                       'failed': [], 'clients': 0})}

    def reset(self):
        with self._lock:
            self.result = self.as_of = self.error = None
            self.seat_ips, self.seat_macs = {}, {}
            self._running = False


SHARED_ONE_LINE = 5     # more shared seat ports than this: one line in Problems, the list is on Cables


def problems(state):
    """Problems' attention items for the seat ports with more than one machine (issue #1119)."""
    rows = (state.get('shared') or {}).get('rows') or []
    count = (state.get('shared') or {}).get('count', len(rows))
    if not rows:
        return []
    desks = [r for r in rows if r['desk_switch']]
    if count > SHARED_ONE_LINE:
        title = f'{count} seat ports have more than one machine'
        looks = 'looks' if len(desks) == 1 else 'look'
        where = f'{len(desks)} {looks} like a desk switch or router' if desks else 'Check them under Cables'
        return [{'id': 'shared:all', 'title': title, 'where': where, 'seat': None, 'switch': None}]
    out = []
    for r in rows:
        if r['desk_switch']:
            title = f"Seat {r['seat']}: a switch or router on the seat port ({r['macs']} machines)"
        else:
            title = f"Seat {r['seat']}: {r['macs']} machines on one seat port"
        out.append({'id': f"shared:{r['switch']}:{r['port']}", 'title': title, 'where': f"{r['switch']} {r['port']}",
                    'seat': r['seat'], 'switch': r['switch']})
    return out


_finder = None


def seat_clients():
    """{seat: {mac_address, ip_address}} from the last read, for the seat mapping."""
    finder = _finder
    if finder is None:
        return {}
    with finder._lock:
        return {seat: dict(v) for seat, v in finder.seat_macs.items()}


def last_read():
    """The last read as the page sees it, without starting a new one."""
    return _finder.state() if _finder is not None else None


def _every(finder, stop):
    """Reads every five minutes while a monitoring source is set up (issue #949), so the lists are
    ready when the crew looks, not only once someone opens the cables page."""
    while not stop.wait(EVERY):
        try:
            with finder.app.app_context():
                if sources.monitoring().enabled():
                    finder.request()
        except Exception as exc:  # noqa: BLE001  # keep the thread alive
            print(f'[port-clients] background read failed: {exc}')


def init_app(app, start_background=True):
    global _finder
    _finder = app.extensions['floorbit_port_clients'] = Finder(app)
    started, stop = threading.Event(), threading.Event()

    @app.before_request
    def start_port_clients_once():
        if start_background and not started.is_set():
            started.set()
            threading.Thread(target=_every, args=(_finder, stop), name='port-clients-every', daemon=True).start()
