"""Taking the device's value from the drift list (issue #918)."""
from floorbit.store import load_data, save_data


def _device(client, **fields):
    r = client.post("/api/inventory", json={"name": "sw-a-01", "role": "switch", **fields})
    assert r.status_code == 201
    return r.get_json()["id"]


def _drift(dev_id, *rows):
    data = load_data()
    data["inventory_drift"] = {dev_id: [{**r, "since": "2026-11-24T10:00:00Z"} for r in rows]}
    save_data(data)


def test_the_device_value_goes_into_the_inventory(client):
    dev = _device(client, model="C9200", mgmt_ip="192.0.2.10")
    _drift(dev, {"kind": "field", "field": "model", "configured": "C9200", "actual": "C9300-48P"},
           {"kind": "address", "field": "mgmt_ip", "configured": "192.0.2.10", "actual": "192.0.2.11"},
           {"kind": "hostname", "field": "name", "configured": "sw-a-01", "actual": "core-x"})
    r = client.post(f"/api/inventory/{dev}/drift/take", json={"field": "model"})
    assert r.status_code == 200 and r.get_json()["model"] == "C9300-48P"
    assert [x["field"] for x in r.get_json()["drift"]] == ["mgmt_ip", "name"]
    took = client.post(f"/api/inventory/{dev}/drift/take", json={"field": "mgmt_ip"}).get_json()
    assert took["mgmt_ip"] == "192.0.2.11"
    detail = client.get(f"/api/inventory/{dev}").get_json()
    assert [x["kind"] for x in detail["drift"]] == ["hostname"]


def test_a_hostname_or_a_value_that_agrees_now_is_not_taken(client):
    dev = _device(client)
    _drift(dev, {"kind": "hostname", "field": "name", "configured": "sw-a-01", "actual": "core-x"})
    assert client.post(f"/api/inventory/{dev}/drift/take", json={"field": "name"}).status_code == 404
    assert client.post(f"/api/inventory/{dev}/drift/take", json={"field": "serial"}).status_code == 404
    assert client.get(f"/api/inventory/{dev}").get_json()["name"] == "sw-a-01"


def test_viewers_cannot_take(client, kiosk_client):
    dev = _device(client)
    _drift(dev, {"kind": "field", "field": "model", "configured": "a", "actual": "b"})
    assert kiosk_client.post(f"/api/inventory/{dev}/drift/take", json={"field": "model"}).status_code in (401, 403)


def test_a_platform_with_its_vendor_in_front_is_no_drift():
    from floorbit.inventory_discovery import _same
    assert _same("platform", "NX-OS", "Cisco NX-OS") and _same("platform", "Cisco IOS-XE", "ios-xe")
    assert not _same("platform", "IOS", "Cisco IOS-XE") and not _same("model", "C9300", "Cisco C9300")
