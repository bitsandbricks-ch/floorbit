"""Load test for an event-sized network (issue #473): how long Floorbit's own work takes at N seats.

Everything is in this process with fake switches; nothing talks to LibreNMS, NetBox or Redis.
It times the parts that grow with the seat count:

- the MAC-table read behind "Unmatched clients" (``port_clients.find``), with a pretend LibreNMS
  delay per switch (``--fdb-ms``),
- the patch plan check (``patch_check.check``),
- every seat checking in once (``checkin.check_in``) and reading the check-in history back.

    python scripts/load_test.py                       # 4000 seats, files
    python scripts/load_test.py --seats 4000 --database sqlite --fdb-ms 1000

The numbers in docs/sizing.md come from this script.
"""
import argparse
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class FakeSwitches:
    """A monitoring source with one PC on every seat port, plus one unplanned and one swapped."""

    def __init__(self, cables, seat_ips, fdb_ms):
        self.fdb_ms = fdb_ms
        self.fdb = {}
        self.arp_rows = []
        for n, cable in enumerate(cables):
            mac = f'02:00:00:{n >> 16 & 255:02x}:{n >> 8 & 255:02x}:{n & 255:02x}'
            self.fdb.setdefault(cable['switch'], []).append({'port': cable['port'], 'mac': mac})
            self.arp_rows.append({'mac_address': mac, 'ipv4_address': seat_ips[cable['seat']]})
        first = cables[0]['switch']
        self.fdb[first].append({'port': 'Gi1/0/49', 'mac': '02:ff:00:00:00:01'})   # no cable says what this is
        a, b = self.arp_rows[0], self.arp_rows[1]
        a['ipv4_address'], b['ipv4_address'] = b['ipv4_address'], a['ipv4_address']   # two players swapped

    def enabled(self):
        return True

    def port_clients(self, switch):
        time.sleep(self.fdb_ms / 1000)
        return self.fdb.get(switch, [])

    def arp(self, net):
        return self.arp_rows


def build(seats, ports):
    """Seat blocks of ``ports`` seats, one access switch each, a cable per seat."""
    blocks, cables, seat_ips = [], [], {}
    for b in range((seats + ports - 1) // ports):
        name = f'B{b + 1:03d}'
        count = min(ports, seats - b * ports)
        blocks.append({'id': f'blk-{b}', 'name': name, 'cols': count, 'rows': 1, 'x': 0, 'y': b * 40})
        for i in range(1, count + 1):
            seat = f'{name}-{i}'
            n = b * ports + i
            seat_ips[seat] = f'10.{n >> 16 & 255}.{n >> 8 & 255}.{n & 255}'
            cables.append({'id': f'c{n}', 'label': f'C-{n:05d}', 'switch': f'sw-{b + 1:03d}',
                           'port': f'Gi1/0/{i}', 'seat': seat, 'block': f'blk-{b}', 'kind': 'copper'})
    return {'seat_blocks': blocks, 'cables': cables}, seat_ips


def timed(label, fn, results, per=None):
    start = time.perf_counter()
    value = fn()
    took = time.perf_counter() - start
    results.append((label, took, per))
    return value


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--seats', type=int, default=4000)
    ap.add_argument('--ports', type=int, default=48, help='seat ports per access switch')
    ap.add_argument('--database', choices=('files', 'sqlite'), default='files')
    ap.add_argument('--fdb-ms', type=float, default=0, help='pretend LibreNMS time per MAC table read')
    args = ap.parse_args(argv)

    tmp = tempfile.mkdtemp(prefix='floorbit-load-')
    os.environ['CHECKIN_FILE'] = os.path.join(tmp, 'checkins.json')
    os.environ.pop('CHECKIN_ALLOWED_NETWORKS', None)
    if args.database == 'sqlite':
        os.environ['FLOORBIT_DATABASE_URL'] = f'sqlite:///{tmp}/floorbit.db'
    else:
        os.environ.pop('FLOORBIT_DATABASE_URL', None)

    from floorbit import cables as cables_mod
    from floorbit import patch_check, port_clients, store
    from floorbit.syslog import canonical_port
    from integrations import checkin, history

    store.DATA_FILE = os.path.join(tmp, 'data.json')
    data, seat_ips = build(args.seats, args.ports)
    data[cables_mod.KEY] = data.pop('cables')
    cables = data[cables_mod.KEY]
    monitor = FakeSwitches(cables, seat_ips, args.fdb_ms)
    seat_map = {seat: {'ip_address': ip} for seat, ip in seat_ips.items()}
    results = []

    found = timed('Unmatched clients: read every seat switch', lambda: port_clients.find(monitor, data, seat_map),
                  results)
    assert found['unplanned']['count'] == 1 and found['moved']['count'] == 2, found
    reads = {(c['switch'].lower(), canonical_port(c['port'])): {'state': 'up'} for c in cables}
    switches = {c['switch'].lower() for c in cables}
    checked = timed('Patch plan check', lambda: patch_check.check(reads, switches, data), results)
    assert sum(b['up'] for b in checked['blocks']) == args.seats

    def check_everyone():
        for n, cable in enumerate(cables):
            mac = monitor.arp_rows[n]['mac_address']
            checkin.check_in(cable['seat'], f'player{n}', seat_ips[cable['seat']], lambda: data, mac=mac)
    timed(f'Check-in: {args.seats} seats, one after the other', check_everyone, results, per=args.seats)
    rows = timed('Check-in history: read back', history.read_all, results)
    assert len(rows) == args.seats, len(rows)

    print(f'{args.seats} seats, {len(switches)} switches, {args.database}, '
          f'{args.fdb_ms:g} ms per MAC table read')
    for label, took, per in results:
        each = f'  ({took / per * 1000:.1f} ms each)' if per else ''
        print(f'  {label:<48} {took:8.2f} s{each}')
    return results


if __name__ == '__main__':
    main()
