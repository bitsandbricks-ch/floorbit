"""Tournament awareness (issue #31): match seats."""
import pytest

from floorbit import ports, sources
from tests.test_attention import Monitoring, port


@pytest.fixture(autouse=True)
def fresh_ports():
    for state in (ports._last, ports._failures, ports._busy):
        state.clear()


@pytest.fixture
def floor(client):
    client.post("/api/seat-blocks", json={"name": "A", "x": 10, "y": 10, "cols": 4, "rows": 1})
    client.post("/api/seat-blocks", json={"name": "B", "x": 60, "y": 10, "cols": 4, "rows": 1})
    return client


def test_zones_take_blocks_seats_and_ranges(floor):
    resp = floor.post("/api/tournament/zones", json={"name": "Stage", "seats": "b, a-1 .. a-2", "note": "Finals"})
    assert resp.status_code == 201, resp.get_json()
    zone = resp.get_json()
    assert zone["blocks"] == ["B"] and zone["seats"] == ["A-1", "A-2"]
    seats = floor.get("/api/tournament/seats").get_json()
    assert sorted(seats) == ["A-1", "A-2", "B-1", "B-2", "B-3", "B-4"] and seats["B-3"] == "Stage"
    overview = floor.get("/api/tournament").get_json()
    assert overview["plans"][0]["match"] == 6
    # Bad input says what is wrong.
    bad = floor.post("/api/tournament/zones", json={"name": "X", "seats": "A-1, Z-9"})
    assert bad.status_code == 400 and "Z-9" in bad.get_json()["error"]
    assert floor.post("/api/tournament/zones", json={"name": "", "seats": "A"}).status_code == 400
    assert floor.post("/api/tournament/zones", json={"name": "X", "seats": ""}).status_code == 400
    changed = floor.patch(f"/api/tournament/zones/{zone['id']}", json={"name": "Main stage"}).get_json()
    assert changed["name"] == "Main stage" and changed["blocks"] == ["B"]
    assert floor.patch(f"/api/tournament/zones/{zone['id']}", json={"seats": "A-4"}).get_json()["blocks"] == []
    assert floor.delete(f"/api/tournament/zones/{zone['id']}").status_code == 200
    assert floor.get("/api/tournament/seats").get_json() == {}


def test_only_leads_change_zones(floor, app_module):
    app_module.app.extensions["auth"].users.add("vic", "vic-password-1", role="viewer")
    viewer = app_module.app.test_client()
    viewer.post("/login", data={"username": "vic", "password": "vic-password-1"})
    assert viewer.get("/api/tournament").status_code == 200
    assert viewer.post("/api/tournament/zones", json={"name": "X", "seats": "A"}).status_code == 403


def test_match_seats_go_first_on_the_board_and_problems(floor, app_module, monkeypatch):
    floor.post("/api/tournament/zones", json={"name": "Stage", "seats": "B"})
    floor.post("/api/incidents", json={"seat": "A-1", "title": "Slow"})
    floor.post("/api/incidents", json={"seat": "B-2", "title": "No link"})
    floor.post("/api/incidents", json={"seat": "A-3", "title": "Newest"})
    board = floor.get("/api/incidents").get_json()["incidents"]
    assert [i["title"] for i in board] == ["No link", "Newest", "Slow"]
    assert board[0]["match"] == "Stage" and board[1]["match"] is None

    mon = Monitoring()
    monkeypatch.setattr(sources, "monitoring", lambda: mon)
    floor.post("/api/switches", json={"name": "sw-a-01", "x": 10, "y": 5})
    watch = app_module.app.extensions["floorbit_attention"]
    watch.reset()
    mon.set("sw-a-01", port("Gi1/0/1", duplex="half", description="Seat B-1"))
    with app_module.app.app_context():
        watch.poll_once(now=1000)
    mon.set("sw-a-01", port("Gi1/0/2", duplex="half", description="Seat A-2"))
    with app_module.app.app_context():
        watch.poll_once(now=2000)
    body = floor.get("/api/problems").get_json()
    assert [a["match"] for a in body["attention"]] == ["Stage", None]   # older, but a match seat
    assert body["counts"]["match"] == 1


def test_qos_hints_list_the_ports_behind_match_seats(floor, monkeypatch):
    mon = Monitoring()
    monkeypatch.setattr(sources, "monitoring", lambda: mon)
    floor.post("/api/switches", json={"name": "sw-b-01", "x": 60, "y": 5})
    floor.post("/api/switches", json={"name": "sw-a-01", "x": 10, "y": 5})
    mon.set("sw-b-01", port("Gi1/0/1", description="Seat B-1"), port("Gi1/0/2", description="B-2 desk"),
            port("Te1/1/1", description="Uplink to dist-01"))
    mon.set("sw-a-01", port("Gi1/0/1", description="Seat A-1"))
    assert floor.get("/api/tournament/qos").get_json()["switches"] == []
    floor.post("/api/tournament/zones", json={"name": "Stage", "seats": "B-1..B-3"})
    hints = floor.get("/api/tournament/qos").get_json()
    assert hints["available"] is True and hints["missing"] == ["B-3"]
    (sw,) = hints["switches"]
    assert sw["switch"] == "sw-b-01" and sw["uplinks"] == ["Te1/1/1"]
    assert [(p["port"], p["seat"]) for p in sw["ports"]] == [("Gi1/0/1", "B-1"), ("Gi1/0/2", "B-2")]


def test_port_actions_on_match_seats_ask_twice(floor, monkeypatch):
    floor.post("/api/inventory", json={"name": "sw-a-01", "mgmt_ip": "198.51.100.4", "role": "switch"})
    floor.put("/api/settings/plugins/demo", json={"enabled": True})
    from integrations import seat_sources
    monkeypatch.setattr(seat_sources, "load", lambda *a, **k: {"A-1": {"ip_address": "192.0.2.10"}})
    floor.post("/api/tournament/zones", json={"name": "Stage", "seats": "A-1"})
    first = floor.post("/api/ports/bounce", json={"seat": "A-1"})
    assert first.status_code == 409
    assert first.get_json()["match_seat"] == "Stage" and "match seat" in first.get_json()["error"]
    again = floor.post("/api/ports/bounce", json={"seat": "A-1", "confirm_match": True})
    assert again.status_code == 200, again.get_json()
