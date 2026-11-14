"""The floor plan's seat view (issue #55): one state per seat, and the inspector's details."""
import time

import pytest

from integrations import seat_sources


@pytest.fixture
def hall(client, app_module, monkeypatch):
    monkeypatch.setenv("SEAT_SOURCES", "manual")
    seat_sources.invalidate()
    client.post("/api/seat-blocks", json={"name": "D", "x": 40, "y": 50, "cols": 4, "rows": 2})
    client.put("/api/seat-map/D-6", json={"ip": "198.51.100.7", "nick": "player-six"})
    stats = app_module.app.extensions["floorbit_stats"]
    stats.reset()
    dev = {"id": "s1", "name": "sw-d-01"}
    stats.record([(dev, {"name": "Gi1/0/6", "state": "up", "download_bps": 5e6, "upload_bps": 1e6}, "D-6"),
                  (dev, {"name": "Gi1/0/7", "state": "down"}, "D-7")], ["sw-d-01"], now=time.time())
    watch = app_module.app.extensions["floorbit_attention"]
    monkeypatch.setattr(watch, "port_seats", {("sw-d-01", "Gi1/0/6"): "D-6", ("sw-d-01", "Gi1/0/7"): "D-7"},
                        raising=False)
    return stats


def test_every_seat_gets_one_state(client, hall):
    client.post("/api/incidents", json={"title": "No link", "seat": "D-7"})
    out = client.get("/api/plan").get_json()
    seats = out["seats"]
    assert len(seats) == 8 and out["monitoring"] is True
    assert seats["D-6"]["state"] == "online" and seats["D-6"]["bps"] == 6_000_000 and seats["D-6"]["taken"]
    assert seats["D-7"]["state"] == "offline" and seats["D-7"]["problems"] == 1
    assert seats["D-1"] == {"state": "unknown"}   # no known port: we can't say it's down
    assert out["blocks"] == [{"name": "D", "seats": 8, "online": 1, "problems": 1}]
    assert out["drawing"]["shapes"][0]["name"] == "D" and out["size"]["cell"] == 32
    # Nothing personal in the plan itself.
    assert "198.51.100.7" not in str(out) and "player-six" not in str(out)


def test_an_old_read_says_unknown(client, hall):
    hall.last = time.time() - 3600
    out = client.get("/api/plan").get_json()
    assert out["monitoring"] is False and {s["state"] for s in out["seats"].values()} == {"unknown"}


def test_match_zone_and_checkin(client, hall, monkeypatch):
    client.post("/api/tournament/zones", json={"name": "Main stage", "seats": "D-1..D-4"})
    out = client.get("/api/plan").get_json()
    assert out["seats"]["D-2"]["match"] == "Main stage" and "match" not in out["seats"]["D-6"]
    assert out["checkin"] is False


def test_inspector_shows_people_only_with_seats_view(client, app_module, hall):
    got = client.get("/api/plan/seats/d-6").get_json()
    assert got["seat"] == "D-6" and got["block"] == "D" and got["state"] == "online"
    assert got["switch"] == "sw-d-01" and got["port"] == "Gi1/0/6"
    assert got["people"] is True and got["nick"] == "player-six" and got["ip"] == "198.51.100.7"
    assert client.get("/api/plan/seats/Z-1").status_code == 404

    app_module.app.extensions["auth"].users.add("kim", "kim-password-1", role="kiosk")
    kiosk = app_module.app.test_client()
    kiosk.post("/login", data={"username": "kim", "password": "kim-password-1"})
    seen = kiosk.get("/api/plan/seats/D-6").get_json()
    assert seen["people"] is False and "nick" not in seen and "ip" not in seen and seen["state"] == "online"


def test_page_is_the_react_app(client):
    assert client.get("/plan").status_code in (200, 503)   # 503 only when the React app isn't built


def test_a_missing_checkin_is_not_a_problem(client, app_module, hall, monkeypatch):
    watch = app_module.app.extensions["floorbit_attention"]
    items = [{"kind": "checkin", "seat": "D-6", "title": "Seat D-6 is online without a check-in", "since": 1},
             {"kind": "flapping", "seat": "D-6", "title": "Port flapping", "since": 1}]
    monkeypatch.setattr(watch, "snapshot", lambda: {"items": items})
    assert client.get("/api/plan").get_json()["seats"]["D-6"]["problems"] == 1
    assert len(client.get("/api/plan/seats/D-6").get_json()["attention"]) == 2
