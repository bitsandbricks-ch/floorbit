"""Public network status page (issue #101): the state, the areas hit, the crew's updates."""
import time

import pytest

from floorbit import sources, status_page


@pytest.fixture
def floor(client, app_module, monkeypatch):
    client.post("/api/seat-blocks", json={"name": "A", "x": 40, "y": 50, "cols": 4, "rows": 3})
    client.post("/api/seat-blocks", json={"name": "B", "x": 900, "y": 50, "cols": 4, "rows": 3})
    a = client.post("/api/switches", json={"name": "sw-a-01", "x": 60, "y": 60}).get_json()
    b = client.post("/api/switches", json={"name": "sw-b-01", "x": 920, "y": 60}).get_json()
    c = client.post("/api/switches", json={"name": "sw-c-01", "x": 500, "y": 500}).get_json()
    monitor = app_module.app.extensions["lal_integrations"]["monitor"]
    monkeypatch.setattr(monitor, "last_poll", time.time())
    monkeypatch.setattr(monitor, "statuses", {})
    monkeypatch.setattr(status_page, "_seats_of", {})
    sources.mark_ok("test")
    return {"monitor": monitor, "a": a, "b": b, "c": c}


def _down(floor, *names):
    floor["monitor"].statuses = {
        floor[n]["id"]: {"id": floor[n]["id"], "status": "offline", "since": time.time() - 120} for n in names}


@pytest.fixture
def switched_on(client):
    assert client.put("/api/settings", json={"public.status_page": True}).status_code == 200


def test_off_by_default(anon_client, floor):
    assert anon_client.get("/status").status_code == 404
    assert anon_client.get("/status.json").status_code == 404


def test_all_running(anon_client, floor, switched_on):
    data = anon_client.get("/status.json").get_json()
    assert data["state"] == "operational" and data["areas"] == [] and data["since"] is None
    assert "All systems running" in anon_client.get("/status").get_data(as_text=True)


def test_one_switch_down_names_the_rows_not_the_switch(anon_client, floor, switched_on):
    status_page.learn_seats({("sw-a-01", "Gi1/0/1"): "A-1", ("sw-a-01", "Gi1/0/5"): "A-5",
                             ("sw-b-01", "Gi1/0/1"): "B-1"})
    _down(floor, "a")
    data = anon_client.get("/status.json").get_json()
    assert data["state"] == "degraded" and data["since"]
    assert data["areas"] == [{"hall": "", "block": "A", "rows": "1-2", "seats": 2}]
    for path in ("/status", "/status.json"):
        body = anon_client.get(path).get_data(as_text=True)
        assert "sw-a-01" not in body and "Gi1/0/1" not in body
    assert "Seat block A" in anon_client.get("/status").get_data(as_text=True)


def test_switch_without_seats_counts_for_the_nearest_block(anon_client, floor, switched_on):
    _down(floor, "b")
    assert anon_client.get("/status.json").get_json()["areas"] == [
        {"hall": "", "block": "B", "rows": "", "seats": None}]


def test_admin_can_show_switch_names(client, anon_client, floor, switched_on):
    client.put("/api/settings", json={"public.status_switch_names": True})
    _down(floor, "a")
    assert anon_client.get("/status.json").get_json()["areas"][0]["switches"] == ["sw-a-01"]


def test_half_down_is_an_outage(anon_client, floor, switched_on):
    _down(floor, "a", "b")
    assert anon_client.get("/status.json").get_json()["state"] == "outage"


def test_core_device_down_is_an_outage(app_module, monkeypatch):
    devices = [{"id": "r", "name": "core", "role": "router", "x": 1, "y": 1},
               {"id": "s1", "name": "s1", "role": "switch", "x": 2, "y": 2},
               {"id": "s2", "name": "s2", "role": "switch", "x": 3, "y": 3}]
    monkeypatch.setattr(status_page.inventory, "devices", lambda data: devices)
    out = status_page.current({}, {"r": {"status": "offline"}}, True)
    assert out["state"] == "outage"
    assert status_page.current({}, {"s1": {"status": "offline"}}, True)["state"] == "degraded"
    assert status_page.current({}, {}, False)["state"] == "unknown"


def test_monitoring_unreachable_is_unknown(anon_client, floor, switched_on):
    sources.mark_failed("test", "timeout")
    try:
        assert anon_client.get("/status.json").get_json()["state"] == "unknown"
    finally:
        sources.mark_ok("test")


def test_crew_updates_and_override(client, anon_client, floor, switched_on):
    r = client.post("/api/status-page/updates", json={"text": "Hall B is back.", "area": "Hall B"})
    assert r.status_code == 201
    uid = r.get_json()["id"]
    assert client.post("/api/status-page/updates", json={"text": "  "}).status_code == 400
    assert client.put("/api/status-page/override", json={"state": "bogus"}).status_code == 400
    r = client.put("/api/status-page/override", json={"state": "maintenance", "note": "Core swap"})
    assert r.status_code == 200
    public = anon_client.get("/status.json").get_json()
    assert public["state"] == "maintenance" and "override" not in public
    assert public["updates"][0]["text"] == "Hall B is back." and "by" not in public["updates"][0]
    crew = client.get("/api/status-page").get_json()
    assert crew["auto_state"] == "operational" and crew["override"]["note"] == "Core swap" and crew["public"]
    page = anon_client.get("/status").get_data(as_text=True)
    assert "Maintenance" in page and "Hall B is back." in page
    client.put("/api/status-page/override", json={"state": None})
    assert anon_client.get("/status.json").get_json()["state"] == "operational"
    assert client.delete(f"/api/status-page/updates/{uid}").status_code == 200
    assert client.delete(f"/api/status-page/updates/{uid}").status_code == 404
    assert anon_client.get("/status.json").get_json()["updates"] == []


def test_update_text_is_escaped(client, anon_client, floor, switched_on):
    client.post("/api/status-page/updates", json={"text": "<script>alert(1)</script>"})
    page = anon_client.get("/status").get_data(as_text=True)
    assert "<script>alert(1)" not in page and "&lt;script&gt;" in page


def test_crew_view_names_switches(client, floor):
    _down(floor, "a")
    assert client.get("/api/status-page").get_json()["crew_areas"][0]["switches"] == ["sw-a-01"]


def test_viewer_cannot_post(app_module, anon_client, floor):
    app_module.app.extensions["auth"].users.add("watcher", "role-password-1", role="viewer")
    anon_client.post("/login", data={"username": "watcher", "password": "role-password-1"})
    assert anon_client.post("/api/status-page/updates", json={"text": "x"}).status_code == 403
    assert anon_client.get("/api/status-page").status_code == 403


def test_german(anon_client, floor, switched_on):
    page = anon_client.get("/status", headers={"Accept-Language": "de"}).get_data(as_text=True)
    assert "Alles läuft" in page and 'lang="de"' in page


def test_rows_text():
    assert status_page._rows_text({1, 2, 3, 5, 7, 8}) == "1-3, 5, 7-8"
    assert status_page._rows_text(set()) == ""
