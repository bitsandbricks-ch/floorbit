"""Which machine is on which seat port, and the ones the patch plan doesn't explain (issue #473).

The switches' MAC tables (``port_clients`` of the monitoring plugin, LibreNMS FDB) say which MAC is
on which port; the ARP table says that MAC's IP. Put next to the cables and the seat mapping, two
kinds of client stand out:

- ``unplanned``: a client on a seat switch's port that no cable explains (a seat the plan missed,
  a crew laptop, a rogue switch).
- ``moved``: a client on seat A's port whose IP the seat mapping gives to seat B (players swapped
  seats, or the cables at the switch are swapped).

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
from .store import load_data

MAX_LISTED = 200
UPLINK_MACS = 4          # more MACs than this on one port: an uplink or a desk switch, not a seat
MIN_AGE = 120            # seconds between reads: LibreNMS itself refreshes MAC tables only when it polls
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


def find(monitor, data, seats):
    """One read: ``{"unplanned", "moved", "switches", "failed", "clients"}``."""
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

    unplanned, moved, clients, seat_ips, seat_macs = [], [], 0, {}, {}
    for (switch, port), macs in sorted(per_port.items(), key=lambda kv: (kv[0][0].lower(), canonical_port(kv[0][1]))):
        if len(macs) > UPLINK_MACS:
            continue
        cable = by_port.get((switch.lower(), canonical_port(port)))
        if cable and not cable.get('seat'):
            continue
        for mac in sorted(macs):
            clients += 1
            ip = mac_ip.get(mac) or ''
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
    return {'unplanned': _listed(unplanned), 'moved': _listed(moved), 'switches': len(switches),
            'failed': failed, 'clients': clients, 'seat_ips': seat_ips, 'seat_macs': seat_macs}


def _start(work):
    threading.Thread(target=work, name='port-clients', daemon=True).start()


def without_cabled(state, data=None):
    """The last read, less the unplanned clients whose port got a cable since (patched to a seat,
    or marked as infrastructure), so the list shrinks as the crew works through it."""
    from .syslog import canonical_port
    cabled = {(c['switch'].lower(), canonical_port(c['port'])) for c in cables_mod.all_cables(data)}
    rows = state['unplanned']['rows']
    left = [r for r in rows if (r['switch'].lower(), canonical_port(r['port'])) not in cabled]
    return {**state, 'unplanned': {'count': state['unplanned']['count'] - (len(rows) - len(left)), 'rows': left}}


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
            if self._running or (self.as_of and time.time() - self.as_of < MIN_AGE):
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
                    **(self.result or {'unplanned': _listed([]), 'moved': _listed([]), 'switches': 0,
                                       'failed': [], 'clients': 0})}

    def reset(self):
        with self._lock:
            self.result = self.as_of = self.error = None
            self.seat_ips, self.seat_macs = {}, {}
            self._running = False


_finder = None


def seat_clients():
    """{seat: {mac_address, ip_address}} from the last read, for the seat mapping."""
    finder = _finder
    if finder is None:
        return {}
    with finder._lock:
        return {seat: dict(v) for seat, v in finder.seat_macs.items()}


def init_app(app):
    global _finder
    _finder = app.extensions['floorbit_port_clients'] = Finder(app)
