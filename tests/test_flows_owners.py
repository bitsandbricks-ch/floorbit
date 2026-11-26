"""Network owners on the Traffic page (issue #1481, A2): the iptoasn list, its lookup and the five-seat rule."""
import gzip
import os

from floorbit.flows import owners as owners_mod
from floorbit.flows.aggregate import Aggregator
from floorbit.flows.classify import BUILTIN, Classifier, compile_rules
from floorbit.flows.owners import Owners, Table

NOW = 1_800_000_000
# Real public ranges in iptoasn's layout, with made-up owners on documentation AS numbers.
LINES = [
    "1.0.0.0\t1.0.0.255\t64496\tZZ\tEXAMPLE-CDN - Example CDN\n",
    "1.0.1.0\t1.0.1.255\t64496\tZZ\tEXAMPLE-CDN - Example CDN\n",
    "1.0.4.0\t1.0.7.255\t64497\tZZ\tEXAMPLE-VIDEO\n",
    "1.0.8.0\t1.0.8.255\t0\tNone\tNot routed\n",
    "2001:4860::\t2001:4860:ffff:ffff:ffff:ffff:ffff:ffff\t64498\tZZ\tEXAMPLE-GAMES - Example Games\n",
    "broken line\n",
]


def test_table_finds_owners_and_merges_neighbours():
    table = Table.read(LINES)
    assert table.lookup("1.0.0.7") == (64496, "Example CDN")
    assert table.lookup("1.0.1.200") == (64496, "Example CDN")
    assert len(table.starts[4]) == 2                      # 1.0.0.0/24 and 1.0.1.0/24 are one range
    assert table.lookup("1.0.5.1") == (64497, "EXAMPLE-VIDEO")
    assert table.lookup("2001:4860::8888") == (64498, "Example Games")
    assert table.lookup("1.0.8.1") is None                # AS 0: not routed
    assert table.lookup("1.0.2.1") is None                # between ranges
    assert table.lookup("192.168.1.1") is None            # private addresses have no owner
    assert table.lookup("not an address") is None


def _write(path, lines):
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        fh.writelines(lines)


def test_owners_fetches_once_a_day_and_keeps_the_old_list(tmp_path):
    calls = []

    def fetch(path):
        calls.append(path)
        _write(path, LINES)
        os.utime(path, (NOW, NOW))
    owners = Owners(folder=str(tmp_path), fetch=fetch, log=lambda m: None)
    assert owners.lookup("1.0.0.7") is None               # nothing loaded yet
    owners.refresh(now=NOW, wait=True)
    assert len(calls) == 1
    assert owners.lookup("1.0.0.7") == (64496, "Example CDN")
    assert owners.status() == {"updated": NOW, "ranges": 3}
    owners.refresh(now=NOW + 3600, wait=True)              # not a day old: no fetch
    assert len(calls) == 1

    def fail(path):
        calls.append(path)
        raise OSError("offline")
    owners._fetch = fail
    owners.refresh(now=NOW + 86400, wait=True)
    assert len(calls) == 2
    assert owners.lookup("1.0.0.7") == (64496, "Example CDN")   # the old list stays in use
    owners.refresh(now=NOW + 86400 + 60, wait=True)        # a failed fetch waits an hour
    assert len(calls) == 2


def test_owners_reads_the_list_on_disk_after_a_restart(tmp_path):
    _write(tmp_path / owners_mod.FILE, LINES)
    os.utime(tmp_path / owners_mod.FILE, (NOW, NOW))
    owners = Owners(folder=str(tmp_path), fetch=lambda p: (_ for _ in ()).throw(AssertionError("fetched")))
    owners.refresh(now=NOW + 60, wait=True)
    assert owners.lookup("1.0.5.1") == (64497, "EXAMPLE-VIDEO")


def _flow(src, dst, size=1000):
    return {"src": src, "dst": dst, "sport": 443, "dport": 50000, "proto": 6, "bytes": size, "packets": 1}


def test_owners_need_five_seats_like_services():
    table = Table.read(LINES)
    seats = {f"192.0.2.{10 + i}": f"A-{i + 1}" for i in range(6)}
    agg = Aggregator(Classifier(compile_rules(BUILTIN)), owner_of=table.lookup)
    agg.set_seats(seats, dict.fromkeys(seats.values(), "A"))
    flows = [_flow("1.0.0.7", ip, 5000) for ip in seats]                       # six seats: named
    flows += [_flow("1.0.5.1", ip, 300) for ip in list(seats)[:2]]            # two seats: folded
    flows += [_flow(ip, "1.0.0.9", 100) for ip in list(seats)[:1]]            # upload to a named owner
    agg.add(flows, now=NOW)
    snap = agg.snapshot(now=NOW + 1)
    assert snap["owners"] == [{"asn": 64496, "name": "Example CDN", "bytes": 30100, "down": 30000, "up": 100,
                               "seats": 6}]
    assert snap["other_owners"] == 600
    agg.tick(now=NOW + 3600)                                                   # the hour closes
    (_, public), = agg.take_closed_hours()
    assert public["owners"] == {"64496": {"name": "Example CDN", "bytes": 30100, "down": 30000, "up": 100,
                                          "seats": 6}}
    assert public["other_owners"] == 600
