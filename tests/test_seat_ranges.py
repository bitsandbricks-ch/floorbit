"""Seats whose PC got an address from another block's range (issue #1062)."""
import pytest

from floorbit import firewalls, seat_ranges
from floorbit.store import load_data
from integrations import seat_sources

pytestmark = pytest.mark.usefixtures("lan_here")

MAPPING = {
    "A-1": {"ip_address": "192.0.2.10", "switch": "sw-a", "port": "Gi1/0/1"},     # in A's range
    "A-2": {"ip_address": "192.0.2.70", "switch": "sw-a", "port": "Gi1/0/2"},     # in B's range
    "A-3": {"ip_address": "203.0.113.5", "switch": "sw-a", "port": "Gi1/0/3"},    # in no range: own router
    "A-4": {"ip_address": "not an ip"},
    "B-1": {"ip_address": "192.0.2.10", "switch": "sw-b", "port": "Gi1/0/1"},     # in A's range
}


@pytest.fixture
def hall(client, monkeypatch):
    mapping = dict(MAPPING)
    monkeypatch.setattr(seat_sources, "load", lambda *a, **k: mapping)
    ids = {}
    for name, x in (("A", 10), ("B", 200)):
        block = {"name": name, "x": x, "y": 10, "cols": 4, "rows": 2}
        ids[name] = client.post("/api/seat-blocks", json=block).get_json()["id"]
    for name in ("fw-01", "fw-02"):
        assert client.post("/api/inventory", json={"name": name, "role": "firewall"}).status_code in (200, 201)
    firewalls.health.reset()
    yield ids, mapping
    firewalls.health.reset()


def _range(client, cidr, fw, blocks=()):
    r = client.post("/api/firewalls/ranges", json={"cidr": cidr, "firewalls": [fw], "blocks": list(blocks)})
    assert r.status_code == 201, r.data
    return r.get_json()


def test_nothing_is_flagged_until_a_range_names_its_blocks(client, hall):
    _range(client, "192.0.2.0/26", "fw-01")
    _range(client, "192.0.2.64/26", "fw-02")
    assert seat_ranges.misplaced(load_data(), MAPPING) == []   # DHCP that mixes ranges: nobody sets blocks


def test_a_seat_outside_its_blocks_ranges_is_flagged_with_the_range_it_is_in(client, hall):
    ids, _ = hall
    _range(client, "192.0.2.0/26", "fw-01", [ids["A"]])
    _range(client, "192.0.2.64/26", "fw-02", [ids["B"]])
    found = {m["seat"]: m for m in seat_ranges.misplaced(load_data(), MAPPING)}
    assert set(found) == {"A-2", "A-3", "B-1"}
    assert found["B-1"]["actual_blocks"] == ["A"]
    assert found["A-2"]["actual"] == "192.0.2.64/26" and found["A-2"]["actual_blocks"] == ["B"]
    assert found["A-2"]["expected"] == ["192.0.2.0/26"]
    assert found["A-3"]["actual"] is None
    titles = {i["id"]: i for i in seat_ranges.items(load_data(), MAPPING)}
    assert titles["range:seat:A-2"]["title"] == "Seat A-2 is in block B's range 192.0.2.64/26"
    assert titles["range:seat:A-2"]["where"] == "sw-a Gi1/0/2: block A uses 192.0.2.0/26"
    assert titles["range:seat:A-3"]["title"] == "Seat A-3 has an address outside every planned range"
    # No IP ever: the seat's address is not in what the crew sees.
    assert "203.0.113.5" not in str(titles) and "192.0.2.70" not in str(titles)


def test_several_seats_behind_one_switch_are_one_item(client, hall):
    ids, mapping = hall
    _range(client, "192.0.2.0/26", "fw-01", [ids["A"]])
    mapping.update({"A-1": {**MAPPING["A-1"], "ip_address": "192.0.2.71"},
                    "A-4": {"ip_address": "192.0.2.72", "switch": "SW-A", "port": "Gi1/0/4"}})
    mapping.update({f"A-{n}": {"ip_address": f"192.0.2.{n}", "switch": "sw-a2", "port": f"Gi1/0/{n}"}
                    for n in range(5, 9)})
    items = seat_ranges.items(load_data(), mapping)
    assert [i["id"] for i in items] == ["range:switch:sw-a"]
    assert items[0]["title"] == "4 seats on sw-a are outside their block's range"
    assert items[0]["where"] == "Seats A-1, A-2, A-3, A-4: check the switch's VLAN"


def test_most_of_a_block_off_means_the_plan_is_wrong_not_the_seats(client, hall):
    ids, mapping = hall
    _range(client, "192.0.2.0/26", "fw-01", [ids["A"]])
    # DHCP that doesn't hand out per block: most of A is elsewhere.
    mapping.update({f"A-{n}": {"ip_address": f"192.0.2.{100 + n}", "switch": "sw-a", "port": f"Gi1/0/{n}"}
                    for n in range(1, 8)})
    items = seat_ranges.items(load_data(), mapping)
    assert [(i["id"], i["title"]) for i in items] == [("range:block:A", "Block A: 7 of 7 seats are outside its ranges")]
    link = next(p for p in client.get("/api/problems").get_json()["attention"] if p["kind"] == "range")["link"]
    assert link == "/firewalls"


def test_problems_list_them_under_attention_in_german_too(client, hall):
    ids, _ = hall
    _range(client, "192.0.2.0/26", "fw-01", [ids["A"]])
    body = client.get("/api/problems").get_json()
    mine = [p for p in body["attention"] if p["kind"] == "range"]
    assert {p["id"] for p in mine} == {"range:seat:A-2", "range:seat:A-3"}
    assert all(p["level"] == "warn" and p["link"].startswith("/plan?seat=") for p in mine)
    de = client.get("/api/problems", headers={"Accept-Language": "de-CH"}).get_json()
    titles = {p["title"] for p in de["attention"] if p["kind"] == "range"}
    assert "Platz A-3 hat eine Adresse ausserhalb aller geplanten Bereiche" in titles


def test_blocks_are_checked_and_kept_on_an_imported_range(client, hall):
    ids, _ = hall
    assert client.post("/api/firewalls/ranges", json={"cidr": "192.0.2.0/26", "firewalls": ["fw-01"],
                                                      "blocks": ["nope"]}).status_code == 400
    row = _range(client, "192.0.2.0/26", "fw-01", [ids["A"], ids["A"]])
    assert row["blocks"] == [ids["A"]]
    # An imported range takes its blocks in Floorbit, but nothing else.
    data = load_data()
    data["firewalls"]["ranges"][0]["source"] = "import"
    from floorbit.store import save_data
    save_data(data)
    assert client.put(f"/api/firewalls/ranges/{row['id']}", json={"name": "x"}).status_code == 409
    r = client.put(f"/api/firewalls/ranges/{row['id']}", json={"blocks": [ids["B"]]})
    assert r.status_code == 200 and r.get_json()["blocks"] == [ids["B"]]
    listed = client.get("/api/firewalls").get_json()["ranges"]
    assert listed[0]["blocks"] == [ids["B"]]
