"""Seats whose machine is in another block's firewall range (issue #1062). No network: the IPs
come from a fake history, the blocks and ranges from data."""
import pytest

from floorbit import range_drift

RANGES = {"ranges": [
    {"id": "r1", "cidr": "192.0.2.0/26", "name": "Block A", "firewalls": ["fw-01"]},
    {"id": "r2", "cidr": "192.0.2.64/26", "name": "", "firewalls": ["fw-02"]},
    {"id": "r3", "cidr": "198.51.100.0/24", "name": "Crew", "firewalls": ["fw-01"]},
]}


def _data(**extra):
    return {"firewalls": RANGES,
            "seat_blocks": [{"id": "a", "name": "A", "cols": 4, "rows": 2},
                            {"id": "b", "name": "B", "cols": 4, "rows": 1}],
            **extra}


def test_a_seat_in_another_blocks_range_is_flagged():
    ips = {"A-1": "192.0.2.10", "A-2": "192.0.2.11", "A-3": "192.0.2.12", "A-4": "192.0.2.13",
           "A-5": "192.0.2.70",                       # in B's range
           "B-1": "192.0.2.65", "B-2": "192.0.2.66", "B-3": "192.0.2.67"}
    assert range_drift.find(_data(), ips) == [
        {"block": "A", "expected": "192.0.2.0/26 (Block A)", "found": "192.0.2.64/26", "seats": ["A-5"]}]


def test_several_seats_of_a_block_in_one_range_are_one_finding_in_seat_order():
    ips = {**{f"A-{i}": f"192.0.2.{i}" for i in range(1, 7)}, "A-8": "198.51.100.8", "A-7": "198.51.100.7"}
    [f] = range_drift.find(_data(), ips)
    assert f["seats"] == ["A-7", "A-8"] and f["found"] == "198.51.100.0/24 (Crew)"


@pytest.mark.parametrize("ips", [
    {"A-1": "192.0.2.1", "A-2": "192.0.2.70"},                                              # too few PCs to say
    {"A-1": "192.0.2.1", "A-2": "192.0.2.2", "A-3": "192.0.2.3",
     "A-4": "192.0.2.65", "A-5": "192.0.2.66", "A-6": "192.0.2.67"},                          # a mixed block
    {"A-1": "192.0.2.1", "A-2": "192.0.2.2", "A-3": "192.0.2.3", "A-4": "203.0.113.9"},        # no range covers it
    {"A-1": "192.0.2.1", "A-2": "192.0.2.2", "A-3": "192.0.2.3", "Z-9": "192.0.2.70", "A-4": "not an ip"},
])
def test_no_finding_without_a_clear_picture(ips):
    assert range_drift.find(_data(), ips) == []


def test_nothing_without_firewall_ranges():
    assert range_drift.find({"seat_blocks": _data()["seat_blocks"]}, {"A-1": "192.0.2.70"}) == []


def test_the_history_gives_the_seats_now(tmp_path):
    from floorbit import database, endpoints
    sql = database.Sql(f"sqlite:///{tmp_path / 'ep.db'}", str(tmp_path))
    try:
        h = endpoints.History(sql)
        h.db.run("INSERT INTO floorbit_endpoints (mac, ip, device, port_key, first_seen, port, seat, vlan, last_seen) "
                 "VALUES ('020000000001', '192.0.2.1', 'sw-a-01', 'gi1/0/1', 100, 'Gi1/0/1', 'A1', 10, 1000), "
                 "('020000000002', '192.0.2.70', 'sw-a-01', 'gi1/0/1', 100, 'Gi1/0/1', 'A1', 10, 1100), "
                 "('020000000003', '192.0.2.3', 'sw-a-01', 'gi1/0/3', 100, 'Gi1/0/3', 'A3', 10, 10), "
                 "('020000000004', '', 'sw-a-01', 'gi1/0/4', 100, 'Gi1/0/4', 'A4', 10, 1000)")
        # The newest per seat; gone for longer than the gap or without an IP: left out.
        assert h.at_seats_now(now=1200) == {"A1": "192.0.2.70"}
    finally:
        sql.close()


def test_it_shows_on_the_problems_page(client, monkeypatch):
    from floorbit import store
    data = store.load_data()
    data.update(_data())
    store.save_data(data)
    ips = {"A-1": "192.0.2.1", "A-2": "192.0.2.2", "A-3": "192.0.2.3", "A-4": "192.0.2.70", "A-5": "192.0.2.71"}
    from types import SimpleNamespace

    from floorbit import endpoints
    monkeypatch.setattr(endpoints, "history", lambda: SimpleNamespace(at_seats_now=lambda: ips))
    range_drift.reset()
    try:
        [p] = [p for p in client.get("/api/problems").get_json()["problems"] if p["kind"] == "range"]
        assert p["title"] == "2 seats of block A are in 192.0.2.64/26, not 192.0.2.0/26 (Block A)"
        assert p["where"] == "A-4, A-5" and p["level"] == "warn" and p["link"] == "/plan?seat=A-4"
        german = client.get("/api/problems", headers={"Accept-Language": "de-CH"}).get_json()["problems"]
        assert any(g["title"].startswith("2 Plätze von Block A") for g in german)
    finally:
        range_drift.reset()

