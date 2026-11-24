"""Smoke tests: the pages render and the floor plan API keeps what it is given."""


def test_the_classic_editor_opens_the_plans_editor(client):
    # Retired (Mike: not kept in sync); old bookmarks land in the plan's editor on the same hall.
    resp = client.get("/editor/classic?hall=main")
    assert resp.status_code == 302 and resp.headers["Location"] == "/plan?edit=1&hall=main"
    assert client.get("/editor/classic").headers["Location"] == "/plan?edit=1"


def test_kiosk_opens_the_kiosk_dashboard(client):
    """The old big-screen page moved into the ready-made Kiosk dashboard; screens that open /kiosk follow."""
    assert client.get("/kiosk").headers["Location"] == "/dashboards/kiosk"
    moved = client.get("/kiosk?hall=hall-2&theme=ops&title=x").headers["Location"]
    assert moved == "/dashboards/kiosk?hall=hall-2&theme=ops"
    heat = client.get("/kiosk?view=heat&hall=hall-2").headers["Location"]
    assert heat == "/plan?screen=1&layers=marks%2Cstatus&hall=hall-2"


def test_config_without_integrations(lan_here, client):
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
    assert [r["seats"] for r in block["rows"]] == [8, 8]

    resp = client.put(f"/api/seat-blocks/{block['id']}", json={"rotation": 90})
    assert resp.get_json()["rotation"] == 90

    assert client.delete(f"/api/seat-blocks/{block['id']}").status_code == 200
    assert client.get("/api/seat-blocks").get_json() == []
    assert client.delete(f"/api/seat-blocks/{block['id']}").status_code == 404


def test_deleting_a_seat_block_on_a_fresh_install_is_a_404(client):
    # A fresh data file has no seat block list at all: the delete was a KeyError, a 500.
    assert client.delete("/api/seat-blocks/nope").status_code == 404


def test_settings_round_trip(client):
    resp = client.put("/api/settings", json={"display.hide_labels": True})
    assert resp.status_code == 200
    saved = client.get("/api/settings").get_json()["values"]["display.hide_labels"]
    assert saved == {"source": "saved", "value": True}


def test_settings_reject_unknown_keys(client):
    assert client.put("/api/settings", json={"hide_labels": True}).status_code == 400


def test_the_old_editor_address_opens_the_floor_plan(client):
    """``/`` is the React floor plan now; old links keep what they pointed at, in Edit mode."""
    assert client.get("/").headers["Location"] == "/plan"
    assert client.get("/?seat=A-1&hall=main").headers["Location"] == "/plan?seat=A-1&hall=main&edit=1"
