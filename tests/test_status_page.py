"""Public network status page (issue #101): the state, the areas hit, the crew's updates."""
import time
import xml.etree.ElementTree as ET

import pytest

from floorbit import sources, status_page

# The page reads the monitor's state: with the LAN plugins answering here, no agent call that fails
# in the background (no agent in these tests) can mark the monitoring as down mid-test.
pytestmark = pytest.mark.usefixtures("lan_here")


@pytest.fixture
def floor(client, app_module, monkeypatch):
    client.post("/api/seat-blocks", json={"name": "A", "x": 40, "y": 50, "cols": 4, "rows": 3})
    client.post("/api/seat-blocks", json={"name": "B", "x": 900, "y": 50, "cols": 4, "rows": 3})
    a = client.post("/api/switches", json={"name": "sw-a-01", "x": 60, "y": 60}).get_json()
    b = client.post("/api/switches", json={"name": "sw-b-01", "x": 920, "y": 60}).get_json()
    c = client.post("/api/switches", json={"name": "sw-c-01", "x": 500, "y": 500}).get_json()
    monitor = app_module.app.extensions["floorbit_integrations"]["monitor"]
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
    # The page is React (PublicStatus.test.tsx draws it); here only that it is served, not 404.
    assert anon_client.get("/status").status_code in (200, 503)


def test_one_switch_down_names_the_rows_not_the_switch(anon_client, floor, switched_on):
    status_page.learn_seats({("sw-a-01", "Gi1/0/1"): "A-1", ("sw-a-01", "Gi1/0/5"): "A-5",
                             ("sw-b-01", "Gi1/0/1"): "B-1"})
    _down(floor, "a")
    data = anon_client.get("/status.json").get_json()
    assert data["state"] == "degraded" and data["since"]
    assert data["areas"] == [{"hall": "", "block": "A", "rows": "1-2", "seats": 2}]
    body = anon_client.get("/status.json").get_data(as_text=True)
    assert "sw-a-01" not in body and "Gi1/0/1" not in body


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
    client.put("/api/status-page/override", json={"state": None})
    assert anon_client.get("/status.json").get_json()["state"] == "operational"
    assert client.delete(f"/api/status-page/updates/{uid}").status_code == 200
    assert client.delete(f"/api/status-page/updates/{uid}").status_code == 404
    assert anon_client.get("/status.json").get_json()["updates"] == []


def test_crew_view_names_switches(client, floor):
    _down(floor, "a")
    assert client.get("/api/status-page").get_json()["crew_areas"][0]["switches"] == ["sw-a-01"]


def test_viewer_cannot_post(app_module, anon_client, floor):
    app_module.app.extensions["auth"].users.add("watcher", "role-password-1", role="viewer")
    anon_client.post("/login", data={"username": "watcher", "password": "role-password-1"})
    assert anon_client.post("/api/status-page/updates", json={"text": "x"}).status_code == 403
    assert anon_client.get("/api/status-page").status_code == 403


def test_rows_text():
    assert status_page._rows_text({1, 2, 3, 5, 7, 8}) == "1-3, 5, 7-8"
    assert status_page._rows_text(set()) == ""


def test_recently_back_areas(anon_client, floor, switched_on):
    # Issue #394: attendees who saw the outage see that it is over.
    status_page.learn_seats({("sw-a-01", "Gi1/0/1"): "A-1"})
    sid = floor["a"]["id"]
    back = time.time() - 5 * 60
    floor["monitor"].statuses = {sid: {"id": sid, "status": "online", "since": back, "previous": "offline"}}
    data = anon_client.get("/status.json").get_json()
    assert data["state"] == "operational" and data["areas"] == []
    assert data["recovered"] == [{"hall": "", "block": "A", "rows": "1", "seats": 1}]
    assert data["recovered_at"] == back
    assert "sw-a-01" not in anon_client.get("/status.json").get_data(as_text=True)
    # Up since a restart, or back more than half an hour ago: nothing to say.
    floor["monitor"].statuses = {sid: {"id": sid, "status": "online", "since": back}}
    assert anon_client.get("/status.json").get_json()["recovered"] == []
    floor["monitor"].statuses = {sid: {"id": sid, "status": "online", "since": time.time() - 31 * 60,
                                       "previous": "offline"}}
    assert anon_client.get("/status.json").get_json()["recovered"] == []


def test_crew_view_lists_recently_back_with_switches(client, floor):
    # Issue #396: the crew page shows what the public page lists as back up, with switch names.
    sid = floor["a"]["id"]
    floor["monitor"].statuses = {sid: {"id": sid, "status": "online", "since": time.time() - 60, "previous": "offline"}}
    crew = client.get("/api/status-page").get_json()
    assert crew["crew_recovered"][0]["switches"] == ["sw-a-01"] and "switches" not in crew["recovered"][0]


def test_atom_feed_of_updates(client, anon_client, floor, switched_on):
    client.put("/api/settings", json={"integrations.public_url": "https://status.example.com/"})
    client.post("/api/status-page/updates", json={"text": "Hall B has no network <for now> & we know.",
                                                  "area": "Hall B", "state": "maintenance"})
    client.post("/api/status-page/updates", json={"text": "Hall B is back."})
    r = anon_client.get("/status.atom")
    assert r.status_code == 200 and r.mimetype == "application/atom+xml"
    ns = {"a": "http://www.w3.org/2005/Atom"}
    feed = ET.fromstring(r.data)
    entries = feed.findall("a:entry", ns)
    assert [e.find("a:content", ns).text for e in entries] == [
        "Hall B is back.", "Hall B has no network <for now> & we know."]
    assert entries[1].find("a:title", ns).text.startswith("Maintenance · Hall B: ")
    assert feed.find("a:link[@rel='self']", ns).get("href") == "https://status.example.com/status.atom"
    # Same rule as /status.json: never who posted.
    from tests.conftest import TEST_USER
    assert TEST_USER.encode() not in r.data


def test_atom_feed_off_and_empty(client, anon_client, floor):
    assert anon_client.get("/status.atom").status_code == 404
    client.put("/api/settings", json={"public.status_page": True})
    feed = ET.fromstring(anon_client.get("/status.atom").data)
    assert feed.find("{http://www.w3.org/2005/Atom}updated").text.endswith("Z")
    assert feed.findall("{http://www.w3.org/2005/Atom}entry") == []


# ── Planned maintenance (issue #422) ──────────────────────────────────────────
def test_planned_maintenance_is_announced_then_runs(client, anon_client, floor, switched_on, monkeypatch):
    now = time.time()
    plan = {"start": now + 3600, "end": now + 5400, "text": "Switch swap in hall B", "area": "Hall B"}
    item = client.post("/api/status-page/maintenance", json=plan).get_json()
    page = anon_client.get("/status.json").get_json()
    assert page["state"] == "operational" and page["maintenance_now"] is None
    assert page["planned"] == [{"id": item["id"], "start": plan["start"], "end": plan["end"],
                                "text": "Switch swap in hall B", "area": "Hall B"}]   # never who planned it

    # An hour later it runs: the page says Maintenance by itself, with the plan's text.
    monkeypatch.setattr(time, "time", lambda: now + 3700)
    page = anon_client.get("/status.json").get_json()
    assert page["state"] == "maintenance" and page["maintenance_now"]["id"] == item["id"]
    # A state set by hand still wins.
    client.put("/api/status-page/override", json={"state": "outage"})
    assert anon_client.get("/status.json").get_json()["state"] == "outage"
    client.put("/api/status-page/override", json={"state": None})

    # Once over, it is gone and the automatic state is back.
    monkeypatch.setattr(time, "time", lambda: now + 5500)
    page = anon_client.get("/status.json").get_json()
    assert page["state"] == "operational" and page["planned"] == []
    actions = {e["action"] for e in client.get("/api/settings/audit").get_json()["entries"]}
    assert "Planned maintenance" in actions


def test_planned_maintenance_checks_and_cancel(client, app_module, floor):
    now = time.time()

    def plan(**body):
        return client.post("/api/status-page/maintenance", json={"text": "Work", **body})
    assert plan(start=now + 60, end=now).status_code == 400            # ends before it starts
    assert plan(start=now - 7200, end=now - 3600).status_code == 400   # already over
    assert plan(start=now + 30 * 86400, end=now + 30 * 86400 + 60).status_code == 400   # too far ahead
    assert plan(start="soon", end=now + 60).status_code == 400
    assert client.post("/api/status-page/maintenance", json={"start": now, "end": now + 60}).status_code == 400
    item = plan(start=now + 60, end=now + 120).get_json()
    assert client.get("/api/status-page").get_json()["planned"][0]["id"] == item["id"]
    tech = app_module.app.extensions["auth"].users
    tech.add("tech-ti", "example-pass-1", role="tech")
    c = app_module.app.test_client()
    c.post("/login", data={"username": "tech-ti", "password": "example-pass-1"})
    assert c.post("/api/status-page/maintenance", json={"start": now + 60, "end": now + 120, "text": "x"},
                  headers={"X-Requested-With": "fetch"}).status_code == 403
    assert client.delete(f"/api/status-page/maintenance/{item['id']}").status_code == 200
    assert client.delete(f"/api/status-page/maintenance/{item['id']}").status_code == 404
    assert client.get("/api/status-page").get_json()["planned"] == []
