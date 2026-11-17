"""Inventory types: cables, power, panels and stored entries with fields, groups and tags."""
from conftest import stored

ONE = {"switch": "sw-a-01", "port": "Gi1/0/3", "panel": "PP-A", "panel_port": "3", "seat": "a-3"}


def test_types_list_the_built_in_ones_with_counts(client):
    client.post("/api/inventory", json={"name": "sw-a-01", "role": "switch"})
    body = client.get("/api/inventory/types").get_json()
    by_id = {t["id"]: t for t in body["types"]}
    builtin = {"device", "cable", "circuit", "power-board", "patch-panel", "rack", "transceiver", "vlan", "item"}
    assert builtin <= set(by_id)
    assert by_id["device"]["count"] == 1 and by_id["rack"]["fields"][0]["key"] == "height_u"
    assert "link" in body["field_kinds"]


def test_cables_and_power_are_entries_that_keep_their_pages(client):
    client.post("/api/inventory", json={"name": "sw-a-01", "role": "switch"})
    cable = client.post("/api/cables", json=ONE).get_json()
    board = client.post("/api/power/boards", json={"name": "DB-1"}).get_json()
    group = client.post("/api/inventory/groups", json={"name": "Hall A"}).get_json()
    tag = client.post("/api/inventory/tags", json={"name": "spare"}).get_json()

    [entry] = client.get("/api/inventory/entries?type=cable").get_json()["entries"]
    assert entry["name"] == cable["label"] and "sw-a-01 Gi1/0/3" in entry["summary"]
    r = client.patch(f"/api/inventory/entries/cable/{cable['id']}",
                     json={"group_id": group["id"], "tags": [tag["id"]], "properties": {"colour": "blue"},
                           "icon": "cable"})
    assert r.status_code == 200, r.get_json()
    detail = client.get(f"/api/inventory/entries/cable/{cable['id']}").get_json()
    assert detail["resolved"]["group_path"] == [{"id": group["id"], "name": "Hall A"}]
    assert "credentials" not in detail["resolved"]
    # The cable page still has the cable as it was.
    assert client.get(f"/api/cables?q={cable['label']}").get_json()["cables"][0]["seat"] == "A-3"
    # Removing the group and tag takes them off the entry too.
    client.delete(f"/api/inventory/groups/{group['id']}")
    client.delete(f"/api/inventory/tags/{tag['id']}")
    entry = client.get(f"/api/inventory/entries/cable/{cable['id']}").get_json()
    assert entry["group_id"] is None and entry["tags"] == []
    # Linked entries are made and removed on their own page.
    assert client.post("/api/inventory/entries/cable", json={"name": "x"}).status_code == 409
    assert client.delete(f"/api/inventory/entries/power-board/{board['id']}").status_code == 409
    assert [e["name"] for e in client.get("/api/inventory/entries?type=power-board").get_json()["entries"]] == ["DB-1"]


def test_stored_entries_check_their_fields(client):
    client.post("/api/inventory", json={"name": "core-01", "role": "router"})
    r = client.post("/api/inventory/entries/transceiver", json={"name": "SFP 1", "fields": {
        "device": "CORE-01", "port": "Te1/0/1", "form": "sfp+", "speed": "10G"}})
    assert r.status_code == 201, r.get_json()
    sfp = r.get_json()
    assert sfp["fields"] == {"device": "core-01", "port": "Te1/0/1", "form": "SFP+", "speed": "10G"}
    for bad in ({"device": "nowhere"}, {"form": "floppy"}, {"nope": "1"}):
        assert client.patch(f"/api/inventory/entries/transceiver/{sfp['id']}", json={"fields": bad}).status_code == 400
    rack = client.post("/api/inventory/entries/rack", json={"name": "R1"}).get_json()
    fields = {f["key"]: f for f in client.get(f"/api/inventory/entries/rack/{rack['id']}").get_json()["field_values"]}
    assert fields["height_u"]["value"] == "42" and fields["height_u"]["is_default"] is True
    tall = client.patch(f"/api/inventory/entries/rack/{rack['id']}", json={"fields": {"height_u": "abc"}})
    assert tall.status_code == 400
    assert client.post("/api/inventory/entries/rack", json={"name": "r1"}).status_code == 409
    assert client.delete(f"/api/inventory/entries/rack/{rack['id']}").status_code == 200


def test_admins_add_types_and_fields_that_devices_and_entries_use(client):
    r = client.post("/api/inventory/types", json={"name": "Screen"})
    assert r.status_code == 201
    screen = r.get_json()
    r = client.patch(f"/api/inventory/types/{screen['id']}", json={"fields": [
        {"label": "Size (inch)", "kind": "number", "default": "55"},
        {"label": "Mount", "kind": "choice", "choices": ["Wall", "Stand"]},
        {"label": "Touch", "kind": "bool"}], "properties": {"owner": "AV"}, "icon": "screen"})
    assert r.status_code == 200, r.get_json()
    assert [f["key"] for f in r.get_json()["fields"]] == ["size_inch", "mount", "touch"]
    tv = client.post(f"/api/inventory/entries/{screen['id']}",
                     json={"name": "Stage left", "fields": {"touch": "true"}}).get_json()
    detail = client.get(f"/api/inventory/entries/{screen['id']}/{tv['id']}").get_json()
    assert detail["resolved"]["properties"]["owner"]["from"]["type"] == "type"
    assert detail["resolved"]["look"]["icon"]["value"] == "screen"
    assert {f["key"]: f["value"] for f in detail["field_values"]} == {"size_inch": "55", "mount": "", "touch": "yes"}
    assert client.delete(f"/api/inventory/types/{screen['id']}").status_code == 409     # it has entries
    # A field on devices, typed in on the device.
    client.patch("/api/inventory/types/device", json={"fields": [{"label": "Asset tag"}]})
    dev = client.post("/api/inventory", json={"name": "sw-a-01", "fields": {"asset_tag": "A-0001"}}).get_json()
    assert dev["fields"] == {"asset_tag": "A-0001"}
    assert client.patch("/api/inventory/types/cable", json={"name": "Wire"}).get_json()["name"] == "Cable"
    assert client.delete("/api/inventory/types/cable").status_code == 409
    for bad in ([{"label": ""}], [{"label": "A", "kind": "choice"}], [{"label": "A"}, {"label": "a"}],
                [{"label": "port"}]):
        target = "transceiver" if bad == [{"label": "port"}] else screen["id"]
        assert client.patch(f"/api/inventory/types/{target}", json={"fields": bad}).status_code == 400, bad
    assert stored("inventory_types")


def test_only_admins_change_types(app_module, client):
    from tests.test_rbac import sign_in_as
    lead = sign_in_as(app_module, "le7", "lead")
    assert lead.get("/api/inventory/types").status_code == 200
    assert lead.post("/api/inventory/types", json={"name": "Screen"}).status_code == 403
    assert lead.post("/api/inventory/entries/item", json={"name": "Ladder"}).status_code == 201
