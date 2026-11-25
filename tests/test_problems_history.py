"""What happened at a problem's or an incident's place, from the event changelog (issues #882, #913)."""
import time

import pytest

from floorbit import problems, timeline
from integrations import events
from tests.test_rbac import sign_in_as

pytestmark = pytest.mark.usefixtures("lan_here")


@pytest.fixture(autouse=True)
def journal(tmp_path, monkeypatch):
    monkeypatch.setenv("TIMELINE_FILE", str(tmp_path / "timeline.jsonl"))
    events.subscribe_once("*", timeline.on_event)


@pytest.fixture
def place(client, app_module, monkeypatch):
    sw = client.post("/api/inventory", json={"name": "sw-a-01", "role": "switch"}).get_json()
    now = time.time()
    item = {"id": "attention:errors:x", "kind": "errors", "level": "warn", "title": "Errors rising on Gi1/0/9",
            "where": "sw-a-01 Gi1/0/9", "since": now - 60, "link": "/plan?switch=sw-a-01", "switch_id": sw["id"]}
    monkeypatch.setattr(problems, "_attention", lambda: [dict(item)])
    stats = app_module.app.extensions["floorbit_stats"]
    stats.new_event()
    stats.record_switch({"id": sw["id"], "name": "sw-a-01", "status": "offline", "since": now - 600})
    stats.record_switch({"id": sw["id"], "name": "sw-a-01", "status": "online", "since": now - 300})
    stats.record_switch({"id": "s2", "name": "sw-a-010", "status": "offline", "since": now - 200})
    events.publish("logs.alert", {"device": "sw-a-01", "port": "Gi1/0/9", "title": "Port flapping"})
    events.publish("security.finding", {"id": "f1", "kind": "rogue_dhcp", "severity": "down", "switch": "sw-a-01",
                                        "port": "Gi1/0/3", "seat": "A-3"})
    return sw


def titles(entries):
    return [(e["kind"], e["title"]) for e in entries]


def test_a_problem_page_has_its_place_history(client, place):
    got = titles(client.get("/api/problems/attention:errors:x").get_json()["history"])
    assert ("outage", "Switch went offline") in got and ("outage", "Switch back online after 5 min") in got
    assert ("alert", "Log alert: Port flapping") in got
    assert ("alert", "Security: rogue dhcp (seat A-3)") in got
    # Exactly that switch: not sw-a-010, and never the audit log.
    assert len([k for k, _ in got if k == "outage"]) == 2
    assert all(k in ("outage", "incident", "alert") for k, _ in got)


def test_seats_stay_out_for_who_may_not_see_them(client, place, app_module):
    viewer = sign_in_as(app_module, "vic", "viewer")
    got = titles(viewer.get("/api/problems/attention:errors:x").get_json()["history"])
    assert ("alert", "Log alert: Port flapping") in got
    assert not any("seat" in title for _, title in got)


def test_an_incident_has_its_place_history(client, place):
    client.post("/api/seat-blocks", json={"name": "A", "x": 10, "y": 10, "cols": 2, "rows": 2})
    made = client.post("/api/incidents", json={"switch_id": place["id"], "title": "Uplink flaps"}).get_json()
    other = client.post("/api/incidents", json={"seat": "A-3", "title": "No internet"}).get_json()
    body = client.get(f"/api/incidents/{made['id']}/history").get_json()
    got = titles(body["entries"])
    assert ("outage", "Switch went offline") in got and ("alert", "Log alert: Port flapping") in got
    assert ("incident", "Incident opened: Uplink flaps") not in got   # not itself
    seat = titles(client.get(f"/api/incidents/{other['id']}/history").get_json()["entries"])
    assert ("alert", "Security: rogue dhcp (seat A-3)") in seat
    assert client.get("/api/incidents/nope/history").status_code == 404


def test_the_incident_history_needs_the_board(client, place, app_module):
    made = client.post("/api/incidents", json={"switch_id": place["id"], "title": "Uplink flaps"}).get_json()
    viewer = sign_in_as(app_module, "vic", "viewer")
    assert viewer.get(f"/api/incidents/{made['id']}/history").status_code == 403
