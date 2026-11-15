"""Floorbit's own dashboard tiles (issue #302): problems and incidents with no plugin set up."""

from floorbit import dashboard_core
from floorbit.plugins import validate
from tests.conftest import TEST_USER


def _login(app_module, name, role):
    app_module.app.extensions["auth"].users.add(name, f"{name}-password-1", role=role)
    c = app_module.app.test_client()
    assert c.post("/login", data={"username": name, "password": f"{name}-password-1"}).status_code == 302
    return c


def test_the_tiles_come_first_and_work_like_plugin_widgets(client):
    tiles = client.get("/api/dashboard").get_json()["tiles"]
    core = [t for t in tiles if t["plugin"] == "floorbit"]
    assert [t["id"] for t in core][:2] == ["problems", "incidents"] and tiles[:4] == core
    assert core[0]["url"] == "/api/dashboard/floorbit/problems" and core[0]["plugin_name"] == "Floorbit"
    body = client.get(core[0]["url"]).get_json()
    assert body["type"] == "stat" and body["link"] == "/problems" and body["unit"] == "down"
    assert "port trouble" in body["sub"] and "muted" in body["sub"]
    assert client.get("/api/dashboard/floorbit/nope").status_code == 404


def test_the_incident_tile_counts_open_and_waiting(client):
    client.post("/api/seat-blocks", json={"name": "A", "x": 10, "y": 10, "cols": 4, "rows": 1})
    old = client.post("/api/incidents", json={"seat": "A-1", "title": "No link"}).get_json()
    client.post("/api/incidents", json={"seat": "A-2", "title": "Slow"})
    taken = client.post("/api/incidents", json={"seat": "A-3", "title": "Power"}).get_json()
    client.patch(f"/api/incidents/{taken['id']}", json={"assignee": TEST_USER})
    body = client.get("/api/dashboard/floorbit/incidents").get_json()
    assert body["value"] == 2 and body["tone"] == "" and body["sub"] == "0 waiting 10+ min · 1 being worked"
    with client.application.app_context():
        later = dashboard_core.incidents_widget("en", now=old["created_at"] + 11 * 60)
    assert later["tone"] == "warn" and later["sub"].startswith("2 waiting")


def test_texts_follow_the_browser_language(client):
    tiles = client.get("/api/dashboard", headers={"Accept-Language": "de-CH,de;q=0.9"}).get_json()["tiles"]
    assert [t["label"] for t in tiles[:4]] == ["Probleme jetzt", "Störungen", "Switches", "Plätze online"]
    body = client.get("/api/dashboard/floorbit/incidents", headers={"Accept-Language": "de-CH"}).get_json()
    assert body["unit"] == "offen" and "in Arbeit" in body["sub"]


def test_only_people_who_see_the_board_get_the_incident_tile(app_module, client):
    viewer = _login(app_module, "vic", "viewer")
    tiles = viewer.get("/api/dashboard").get_json()["tiles"]
    assert [t["id"] for t in tiles if t["plugin"] == "floorbit"] == ["problems", "switches", "seats"]
    assert viewer.get("/api/dashboard/floorbit/incidents").status_code == 404
    assert viewer.get("/api/dashboard/floorbit/problems").status_code == 200


def test_no_plugin_may_take_the_id():
    assert "taken" in validate({"id": "floorbit", "uses": ["widgets"]})


def test_switch_and_seat_tiles(client):
    ids = [t["id"] for t in client.get("/api/dashboard").get_json()["tiles"] if t["plugin"] == "floorbit"]
    assert ids == ["problems", "incidents", "switches", "seats"]
    assert dashboard_core.switches_widget("en", {"online": 40, "offline": 2, "unknown": 1}) == {
        "type": "stat", "value": 40, "unit": "of 43 up", "tone": "err", "sub": "2 offline · 1 not known",
        "link": "/problems"}
    assert dashboard_core.switches_widget("en", {"online": 3, "offline": 0, "unknown": 0})["tone"] == "ok"
    assert dashboard_core.switches_widget("de", {"online": 0, "offline": 0, "unknown": 0})["unit"] == "von 0 online"
    unknown = dashboard_core.seats_widget("en", None, 120)
    assert unknown["value"] == "?" and unknown["unit"] == "of 120" and "Not known" in unknown["sub"]
    assert dashboard_core.seats_widget("en", 87, 120)["value"] == 87
    for tile in ("switches", "seats"):
        assert client.get(f"/api/dashboard/floorbit/{tile}").get_json()["type"] == "stat"
