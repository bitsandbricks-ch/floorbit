"""A firewall range is an inventory prefix with firewalls set (Mike, 2026-11-24, issue #1345)."""
import pytest

from floorbit import upgrades
from floorbit.store import load_data, save_data

pytestmark = pytest.mark.usefixtures("lan_here")


def _firewalls(client, *names):
    for name in names:
        assert client.post("/api/inventory", json={"name": name, "role": "firewall"}).status_code in (200, 201)


def _prefixes(client):
    return {e["id"]: e for e in client.get("/api/inventory/entries?type=prefix").get_json()["entries"]}


def test_ranges_are_prefixes_with_groups_and_tags(client):
    _firewalls(client, "fw-01", "fw-02", "fw-03")
    hall = client.post("/api/firewalls/ranges",
                       json={"cidr": "192.0.2.0/25", "firewalls": ["fw-01", "fw-02"], "fallback": ["fw-03"],
                             "name": "Hall A"}).get_json()
    bare = client.post("/api/firewalls/ranges", json={"cidr": "192.0.2.128/27", "firewalls": ["fw-03"]}).get_json()
    types = {t["id"]: t for t in client.get("/api/inventory/types").get_json()["types"]}
    assert "firewall-range" not in types and types["prefix"]["sort"] == "stored" and types["prefix"]["count"] == 2

    entries = _prefixes(client)
    assert entries[hall["id"]]["name"] == "Hall A" and entries[hall["id"]]["fields"]["prefix"] == "192.0.2.0/25"
    assert entries[hall["id"]]["summary"] == "→ fw-01, fw-02"
    assert entries[bare["id"]]["name"] == "192.0.2.128/27"            # no name: its addresses
    assert bare["name"] == ""

    group = client.post("/api/inventory/groups", json={"name": "Hall A"}).get_json()
    tag = client.post("/api/inventory/tags", json={"name": "seats"}).get_json()
    r = client.patch(f"/api/inventory/entries/prefix/{hall['id']}",
                     json={"group_id": group["id"], "tags": [tag["id"]], "notes": "Core VRF seats",
                           "fields": {"purpose": "Seats"}})
    assert r.status_code == 200, r.get_json()
    detail = client.get(f"/api/inventory/entries/prefix/{hall['id']}").get_json()
    assert detail["resolved"]["group_path"] == [{"id": group["id"], "name": "Hall A"}]
    # The firewall plan stays as it was.
    assert client.get("/api/firewalls").get_json()["ranges"][0]["firewalls"] == ["fw-01", "fw-02"]

    # Removing a range made on the Firewalls page takes its prefix with it.
    assert client.delete(f"/api/firewalls/ranges/{hall['id']}").status_code in (200, 204)
    assert list(_prefixes(client)) == [bare["id"]]


def test_a_range_goes_on_the_prefix_the_inventory_has(client):
    _firewalls(client, "fw-01")
    seats = client.post("/api/inventory/entries/prefix",
                        json={"name": "Seats", "fields": {"prefix": "198.51.100.0/24", "vlan_id": 110}}).get_json()
    r = client.post("/api/firewalls/ranges", json={"cidr": "198.51.100.0/24", "firewalls": ["fw-01"]})
    assert r.status_code == 201 and r.get_json()["id"] == seats["id"] and r.get_json()["name"] == "Seats"
    assert list(_prefixes(client)) == [seats["id"]]
    # Taking the plan away leaves the prefix the crew wrote down.
    assert client.delete(f"/api/firewalls/ranges/{seats['id']}").status_code in (200, 204)
    assert list(_prefixes(client)) == [seats["id"]] and client.get("/api/firewalls").get_json()["ranges"] == []
    assert "plan" not in next(e for e in load_data()["inventory_entries"] if e["id"] == seats["id"])


def test_the_old_shapes_move_once(client):
    data = load_data()
    data["inventory"] = [*data.get("inventory", []), {"id": "fw1", "name": "fw-01", "role": "firewall"}]
    data["inventory_entries"] = [
        {"id": "v1", "type": "vlan", "name": "Seats A", "fields": {"vlan_id": "110", "prefix": "10.10.0.0/22",
                                                                    "lookups": "yes"}},
        {"id": "v2", "type": "vlan", "name": "Crew", "fields": {"vlan_id": "120", "gateway": "x"}},
    ]
    data["firewalls"] = {"ranges": [
        {"id": "r1", "cidr": "10.10.0.0/22", "name": "Hall", "firewalls": ["fw-01"], "fallback": [], "switches": []},
        {"id": "r2", "cidr": "192.0.2.0/27", "name": "", "firewalls": ["fw-01"], "source": "import",
         "plugin": "NetBox"}]}
    data["inventory_items"] = {"firewall-range:r2": {"notes": "from NetBox"}}
    data[upgrades.KEY] = upgrades.CURRENT - 1
    save_data(data)
    data = load_data()
    by_id = {e["id"]: e for e in data["inventory_entries"]}
    assert by_id["v1"]["type"] == "prefix" and by_id["v1"]["plan"]["firewalls"] == ["fw-01"]
    assert by_id["v2"]["type"] == "vlan" and by_id["v2"]["fields"] == {"vlan_id": "120"}
    # Seats A's VLAN 110 gets an entry of its own; Crew's 120 has one.
    assert sorted(e["fields"]["vlan_id"] for e in by_id.values() if e["type"] == "vlan") == ["110", "120"]
    assert by_id["r2"]["plan"]["source"] == "import" and by_id["r2"]["notes"] == "from NetBox"
    assert "firewalls" not in data and not data.get("inventory_items")
    rows = {r["cidr"]: r for r in client.get("/api/firewalls").get_json()["ranges"]}
    assert rows["10.10.0.0/22"]["name"] == "Seats A" and rows["192.0.2.0/27"]["source"] == "import"
    # Twice is the same as once.
    before = list(data["inventory_entries"])
    upgrades._ipam(data)
    assert data["inventory_entries"] == before
