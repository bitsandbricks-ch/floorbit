"""Smoke tests: the pages render and the floor plan API keeps what it is given."""


def test_index_renders(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"<html" in resp.data.lower()


def test_config_without_integrations(client):
    resp = client.get("/api/config")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["netbox_enabled"] is False
    assert body["librenms_enabled"] is False


def test_switch_lifecycle(client):
    assert client.get("/api/switches").get_json() == []

    resp = client.post("/api/switches", json={"name": "sw-test-01", "x": 10, "y": 20})
    assert resp.status_code == 201
    switch = resp.get_json()
    assert switch["name"] == "sw-test-01"
    assert switch["source"] == "manual"

    resp = client.put(f"/api/switches/{switch['id']}", json={"x": 30, "y": 40})
    assert resp.status_code == 200
    assert (resp.get_json()["x"], resp.get_json()["y"]) == (30, 40)

    assert [s["id"] for s in client.get("/api/switches").get_json()] == [switch["id"]]

    assert client.delete(f"/api/switches/{switch['id']}").status_code == 200
    assert client.get("/api/switches").get_json() == []


def test_switch_needs_coordinates(client):
    resp = client.post("/api/switches", json={"name": "no-position"})
    assert resp.status_code == 400


def test_unknown_switch_is_404(client):
    assert client.put("/api/switches/does-not-exist", json={"name": "x"}).status_code == 404


def test_seat_block_lifecycle(client):
    resp = client.post("/api/seat-blocks", json={"name": "A", "x": 5, "y": 5, "cols": 8, "rows": 2})
    assert resp.status_code == 201
    block = resp.get_json()
    assert (block["cols"], block["rows"]) == (8, 2)

    resp = client.put(f"/api/seat-blocks/{block['id']}", json={"rotation": 90})
    assert resp.get_json()["rotation"] == 90

    assert client.delete(f"/api/seat-blocks/{block['id']}").status_code == 200
    assert client.get("/api/seat-blocks").get_json() == []


def test_settings_round_trip(client):
    resp = client.put("/api/settings", json={"hide_labels": True})
    assert resp.status_code == 200
    assert client.get("/api/settings").get_json()["hide_labels"] is True
