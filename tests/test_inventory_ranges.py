"""A firewall range is an inventory item (Mike, 2026-11-24): a linked type next to cables and power."""
import pytest

pytestmark = pytest.mark.usefixtures("lan_here")


def _firewalls(client, *names):
    for name in names:
        assert client.post("/api/inventory", json={"name": name, "role": "firewall"}).status_code in (200, 201)


def test_ranges_are_entries_with_groups_and_tags_that_keep_their_page(client):
    _firewalls(client, "fw-01", "fw-02", "fw-03")
    hall = client.post("/api/firewalls/ranges",
                       json={"cidr": "192.0.2.0/25", "firewalls": ["fw-01", "fw-02"], "fallback": ["fw-03"],
                             "name": "Hall A"}).get_json()
    bare = client.post("/api/firewalls/ranges", json={"cidr": "192.0.2.128/27", "firewalls": ["fw-03"]}).get_json()
    types = {t["id"]: t for t in client.get("/api/inventory/types").get_json()["types"]}
    assert types["firewall-range"]["sort"] == "linked" and types["firewall-range"]["count"] == 2

    entries = {e["id"]: e for e in client.get("/api/inventory/entries?type=firewall-range").get_json()["entries"]}
    assert entries[hall["id"]]["name"] == "Hall A"
    assert entries[hall["id"]]["summary"] == "192.0.2.0/25 → fw-01, fw-02"
    assert entries[hall["id"]]["link"] == "/firewalls?q=192.0.2.0"
    assert entries[bare["id"]]["name"] == "192.0.2.128/27"            # no name: its addresses

    group = client.post("/api/inventory/groups", json={"name": "Hall A"}).get_json()
    tag = client.post("/api/inventory/tags", json={"name": "seats"}).get_json()
    r = client.patch(f"/api/inventory/entries/firewall-range/{hall['id']}",
                     json={"group_id": group["id"], "tags": [tag["id"]], "notes": "Core VRF seats"})
    assert r.status_code == 200, r.get_json()
    detail = client.get(f"/api/inventory/entries/firewall-range/{hall['id']}").get_json()
    assert detail["resolved"]["group_path"] == [{"id": group["id"], "name": "Hall A"}]
    assert detail["notes"] == "Core VRF seats"
    # The firewall plan is the same as before, and ranges are made and removed on the Firewalls page.
    assert client.get("/api/firewalls").get_json()["ranges"][0]["firewalls"] == ["fw-01", "fw-02"]
    assert client.post("/api/inventory/entries/firewall-range", json={"name": "x"}).status_code == 409
    assert client.delete(f"/api/inventory/entries/firewall-range/{hall['id']}").status_code == 409

    # Removing the range takes its inventory settings with it.
    assert client.delete(f"/api/firewalls/ranges/{hall['id']}").status_code in (200, 204)
    from floorbit.store import load_data
    assert f"firewall-range:{hall['id']}" not in (load_data().get("inventory_items") or {})
    left = client.get("/api/inventory/entries?type=firewall-range").get_json()["entries"]
    assert [e["id"] for e in left] == [bare["id"]]
