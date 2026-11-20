"""Seats whose PC got an address from another switch stack's range (issue #1062).

Ranges follow the switch stacks (sets of them by colour), not the seat blocks."""
import pytest

from floorbit import firewalls, seat_ranges
from floorbit.store import load_data, save_data
from integrations import seat_sources

pytestmark = pytest.mark.usefixtures("lan_here")

GREEN, RED = "192.0.2.0/26", "192.0.2.64/26"


def seat(n, ip, switch="sw-g1"):
    return {"ip_address": ip, "switch": switch, "port": f"Gi1/0/{n}"}


@pytest.fixture
def hall(client, monkeypatch):
    mapping = {}
    monkeypatch.setattr(seat_sources, "load", lambda *a, **k: mapping)
    groups = {}
    for name in ("Green", "Red"):
        r = client.post("/api/inventory/groups", json={"name": name})
        assert r.status_code == 201, r.data
        groups[name] = r.get_json()["id"]
    devices = {}
    for name, group in (("sw-g1", "Green"), ("sw-g2", "Green"), ("sw-r1", "Red")):
        r = client.post("/api/inventory", json={"name": name, "role": "switch", "group_id": groups[group]})
        assert r.status_code in (200, 201), r.data
        devices[name] = r.get_json()["id"]
    for name in ("fw-01", "fw-02"):
        assert client.post("/api/inventory", json={"name": name, "role": "firewall"}).status_code in (200, 201)
    firewalls.health.reset()
    yield {"groups": groups, "devices": devices, "mapping": mapping}
    firewalls.health.reset()


def _range(client, cidr, fw, switches=()):
    r = client.post("/api/firewalls/ranges", json={"cidr": cidr, "firewalls": [fw], "switches": list(switches)})
    assert r.status_code == 201, r.data
    return r.get_json()


def test_a_switchs_range_is_guessed_from_its_seats(client, hall):
    """Zero setup: four of sw-g1's five PCs are in the green range, so that is sw-g1's range."""
    _range(client, GREEN, "fw-01")
    _range(client, RED, "fw-02")
    m = hall["mapping"]
    m.update({"A-1": seat(1, "192.0.2.11"), "A-2": seat(2, "192.0.2.70"), "A-3": seat(3, "192.0.2.13"),
              "A-4": seat(4, "192.0.2.14"), "A-5": seat(5, "192.0.2.15"),
              "A-6": seat(6, "203.0.113.6")})                      # in no range: not judged on a guess
    found = seat_ranges.misplaced(load_data(), m)
    assert [(f["seat"], f["actual"], f["guessed"]) for f in found] == [("A-2", RED, True)]
    [item] = seat_ranges.items(load_data(), m)
    assert item["title"] == f"Seat A-2 is in the range {RED}"
    assert item["where"] == f"Gi1/0/2: most of sw-g1 is in {GREEN}"
    # No IP ever: the seat's address is not in what the crew sees.
    assert "192.0.2.70" not in str(item)


def test_a_mixed_or_small_switch_stays_quiet(client, hall):
    _range(client, GREEN, "fw-01")
    _range(client, RED, "fw-02")
    m = hall["mapping"]
    m.update({"A-1": seat(1, "192.0.2.11"), "A-2": seat(2, "192.0.2.70")})
    assert seat_ranges.misplaced(load_data(), m) == []             # two PCs: too few to tell
    m.update({"A-3": seat(3, "192.0.2.13"), "A-4": seat(4, "192.0.2.14"),
              "A-5": seat(5, "192.0.2.75"), "A-6": seat(6, "192.0.2.76")})
    assert seat_ranges.misplaced(load_data(), m) == []             # 3 and 3: DHCP that ignores switches


def test_a_range_can_name_a_switch_group(client, hall):
    """Green's range is for every switch in the Green group; a red seat on a green stack shows."""
    _range(client, GREEN, "fw-01", [hall["groups"]["Green"]])
    _range(client, RED, "fw-02", [hall["devices"]["sw-r1"]])
    m = hall["mapping"]
    m.update({"A-1": seat(1, "192.0.2.11"), "A-2": seat(2, "192.0.2.70", "sw-g2"),
              "A-3": seat(3, "203.0.113.5", "sw-g2"), "B-1": seat(1, "192.0.2.10", "sw-r1")})
    found = {f["seat"]: f for f in seat_ranges.misplaced(load_data(), m)}
    assert set(found) == {"A-2", "A-3", "B-1"}
    assert found["A-2"]["actual_for"] == "sw-r1" and found["B-1"]["actual_for"] == "Green"
    assert found["A-3"]["actual"] is None
    items = {i["id"]: i for i in seat_ranges.items(load_data(), m)}
    assert items["range:seat:A-2"]["title"] == f"Seat A-2 is in the range {RED} of sw-r1"
    assert items["range:seat:A-2"]["where"] == f"Gi1/0/2: sw-g2 uses {GREEN}"
    assert items["range:seat:A-3"]["title"] == "Seat A-3 has an address outside every planned range"


def test_several_seats_behind_one_switch_are_one_item(client, hall):
    _range(client, GREEN, "fw-01", [hall["groups"]["Green"]])
    m = hall["mapping"]
    m.update({f"A-{n}": seat(n, f"192.0.2.{n}") for n in range(1, 9)})
    m.update({f"A-{n}": seat(n, f"192.0.2.{70 + n}") for n in (1, 2, 3)})
    [item] = seat_ranges.items(load_data(), m)
    assert item["id"] == "range:switch:sw-g1"
    assert item["title"] == "3 seats on sw-g1 are outside its range"
    assert item["where"] == "Seats A-1, A-2, A-3: check the switch's VLAN"


def test_most_of_a_named_switch_off_means_the_range_is_set_wrong(client, hall):
    _range(client, GREEN, "fw-01", [hall["devices"]["sw-r1"]])     # green's range given to a red stack
    m = hall["mapping"]
    m.update({f"B-{n}": seat(n, f"192.0.2.{70 + n}", "sw-r1") for n in range(1, 6)})
    [item] = seat_ranges.items(load_data(), m)
    assert (item["id"], item["title"]) == ("range:plan:sw-r1", "sw-r1: 5 of 5 seats are outside its ranges")
    link = next(p for p in client.get("/api/problems").get_json()["attention"] if p["kind"] == "range")["link"]
    assert link == "/firewalls"


def test_problems_list_them_under_attention_in_german_too(client, hall):
    _range(client, GREEN, "fw-01", [hall["groups"]["Green"]])
    m = hall["mapping"]
    m.update({"A-1": seat(1, "192.0.2.11"), "A-3": seat(3, "203.0.113.5")})
    body = client.get("/api/problems").get_json()
    mine = [p for p in body["attention"] if p["kind"] == "range"]
    assert [p["id"] for p in mine] == ["range:seat:A-3"]
    assert mine[0]["level"] == "warn" and mine[0]["link"] == "/plan?seat=A-3"
    de = client.get("/api/problems", headers={"Accept-Language": "de-CH"}).get_json()
    [item] = [p for p in de["attention"] if p["kind"] == "range"]
    assert item["title"] == "Platz A-3 hat eine Adresse ausserhalb aller geplanten Bereiche"
    assert item["where"] == f"Gi1/0/3: sw-g1 nutzt {GREEN}"


def test_switches_are_checked_and_kept_on_an_imported_range(client, hall):
    green, red = hall["groups"]["Green"], hall["groups"]["Red"]
    assert client.post("/api/firewalls/ranges", json={"cidr": GREEN, "firewalls": ["fw-01"],
                                                      "switches": ["nope"]}).status_code == 400
    row = _range(client, GREEN, "fw-01", [green, green])
    assert row["switches"] == [green]
    # An imported range takes its switches in Floorbit, but nothing else.
    data = load_data()
    data["firewalls"]["ranges"][0]["source"] = "import"
    save_data(data)
    assert client.put(f"/api/firewalls/ranges/{row['id']}", json={"name": "x"}).status_code == 409
    r = client.put(f"/api/firewalls/ranges/{row['id']}", json={"switches": [red]})
    assert r.status_code == 200 and r.get_json()["switches"] == [red]
    assert client.get("/api/firewalls").get_json()["ranges"][0]["switches"] == [red]
