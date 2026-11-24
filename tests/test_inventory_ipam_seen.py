"""IPAM: where discovery read a VLAN or a prefix (issue #1347)."""
from test_inventory_scope import add

from floorbit.store import load_data, save_data


def test_vlans_and_prefixes_say_which_devices_they_were_seen_on(client):
    a = add(client, name="sw-b-01", mgmt_ip="192.0.2.51")
    b = add(client, name="sw-a-01", mgmt_ip="192.0.2.52")
    for name, vid in (("Seats", "10"), ("Spare", "99")):
        r = client.post("/api/inventory/entries/vlan", json={"name": name, "fields": {"vlan_id": vid}})
        assert r.status_code == 201
    assert client.post("/api/inventory/entries/prefix",
                       json={"name": "Seats", "fields": {"prefix": "198.51.100.0/24"}}).status_code == 201
    data = load_data()
    data["inventory_discovered"] = {
        a["id"]: {"vlans": [{"id": 10, "name": "seats"}], "networks": ["198.51.100.0/24"]},
        b["id"]: {"vlans": [{"id": 10, "name": "seats"}]},
        "gone-device": {"vlans": [{"id": 10, "name": "seats"}]},     # a device no longer in the inventory
    }
    save_data(data)
    vlans = {e["name"]: e["seen_on"] for e in client.get("/api/inventory/entries?type=vlan").get_json()["entries"]}
    assert vlans == {"Seats": [{"id": b["id"], "name": "sw-a-01"}, {"id": a["id"], "name": "sw-b-01"}], "Spare": []}
    prefix = client.get("/api/inventory/entries?type=prefix").get_json()["entries"][0]
    assert prefix["seen_on"] == [{"id": a["id"], "name": "sw-b-01"}]
    # Other kinds of entries don't carry it.
    assert client.post("/api/inventory/entries/rack", json={"name": "R1"}).status_code == 201
    assert "seen_on" not in client.get("/api/inventory/entries?type=rack").get_json()["entries"][0]
