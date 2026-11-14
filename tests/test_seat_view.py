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


def test_editor_has_the_seat_states_layer(client):
    page = client.get("/").get_data(as_text=True)
    assert 'id="btn-seat-states"' in page and "/static/js/editor/seat-states.js" in page
    assert page.index("editor/seat-states.js") < page.index("editor/main.js")


def test_notifications_script_is_on_the_editor(client):
    page = client.get("/").get_data(as_text=True)
    assert "/static/js/notify.js" in page


def test_inspector_link_history(client, app_module):
    """Issue #167: the seat's link over the last hours, from the changes the replay keeps."""
    stats = app_module.app.extensions["floorbit_stats"]
    stats.reset()
    now = time.time()
    dev = {"id": "s1", "name": "sw-d-01"}

    def read(t, up):
        port = {"name": "Gi1/0/6", "state": "up" if up else "down", "download_bps": 1e6 if up else 0}
        stats.record([(dev, port, "D-6")], ["sw-d-01"], now=t)

    for minutes, up in ((400, True), (300, False), (90, True), (60, False), (30, True)):
        read(now - minutes * 60, up)
    hist = stats.seat_history("D-6", now - 6 * 3600)
    # The read 400 minutes ago is before the window: it only sets the starting state.
    assert hist["start"] is True and hist["from"] == pytest.approx(now - 6 * 3600)
    assert [on for _, on in hist["changes"]] == [0, 1, 0, 1]
    assert [round((now - t) / 60) for t, _ in hist["changes"]] == [300, 90, 60, 30]
    assert stats.seat_history("D-99", now - 3600)["changes"] == []


def test_inspector_details_carry_history(client, hall):
    d = client.get("/api/plan/seats/D-6").get_json()
    # One read so far: the history starts there, online, with no change yet.
    assert d["history"]["start"] is True and d["history"]["changes"] == []
    assert d["history"]["to"] >= d["history"]["from"]


def test_changed_lately(client, app_module):
    """Issue #171: seats whose link changed in the last minutes, but not the first read."""
    client.post("/api/seat-blocks", json={"name": "D", "x": 40, "y": 50, "cols": 4, "rows": 2})
    stats = app_module.app.extensions["floorbit_stats"]
    stats.reset()
    now = time.time()
    dev = {"id": "s1", "name": "sw-d-01"}

    def port(name, up):
        return {"name": name, "state": "up" if up else "down", "download_bps": 1e6 if up else 0}

    def read(t, up6, up7):
        stats.record([(dev, port("Gi1/0/6", up6), "D-6"), (dev, port("Gi1/0/7", up7), "D-7")], ["sw-d-01"], now=t)

    read(now - 3600, True, True)
    assert stats.changed_since(now - 7200) == {}
    read(now - 1800, True, False)   # D-7 down half an hour ago
    read(now - 240, False, False)   # D-6 down four minutes ago
    assert stats.changed_since(now - 900) == {"D-6": pytest.approx(now - 240)}
    assert set(stats.changed_since(now - 7200)) == {"D-6", "D-7"}
    seats = client.get("/api/plan").get_json()["seats"]
    assert seats["D-6"]["changed"] == pytest.approx(now - 240) and "changed" not in seats["D-7"]


def test_block_panel(client, hall):
    """Issue #174: one block's states, problem seats and the switches that serve it."""
    client.post("/api/incidents", json={"title": "No link", "seat": "D-7"})
    b = client.get("/api/plan/blocks/D").get_json()
    assert (b["seats"], b["online"], b["offline"], b["unknown"]) == (8, 1, 1, 6)
    assert b["bps"] == 6_000_000
    assert [p["seat"] for p in b["problems"]] == ["D-7"]
    assert b["switches"] == [{"name": "sw-d-01", "seats": 2, "online": 1, "status": "unknown"}]
    assert b["no_port"] == 6
    assert "player-six" not in str(b) and "198.51.100.7" not in str(b)
    assert client.get("/api/plan/blocks/Z").status_code == 404


def test_switch_panel(client, hall):
    """Issue #176: one switch's status and the seats it serves, port by port."""
    s = client.get("/api/plan/switches/sw-d-01").get_json()
    assert [(r["seat"], r["port"], r["state"]) for r in s["seats"]] == [
        ("D-6", "Gi1/0/6", "online"), ("D-7", "Gi1/0/7", "offline")]
    assert s["online"] == 1 and s["status"] == "unknown"
    assert "player-six" not in str(s) and "198.51.100.7" not in str(s)
    assert client.get("/api/plan/switches/sw-z-99").status_code == 404


def test_port_order():
    from floorbit.seat_view import _port_key
    assert sorted(["Gi1/0/10", "Gi1/0/2", "Gi1/0/1"], key=_port_key) == ["Gi1/0/1", "Gi1/0/2", "Gi1/0/10"]


def test_crew_notes_on_a_seat(client, app_module, hall):
    got = client.put("/api/plan/seats/d-6/note", json={"text": "  Cable swapped at 14:20  "}).get_json()
    assert got["note"]["text"] == "Cable swapped at 14:20" and got["note"]["at"]
    details = client.get("/api/plan/seats/D-6").get_json()
    assert details["crew"] is True and details["note"]["text"] == "Cable swapped at 14:20"
    assert client.get("/api/plan").get_json()["seats"]["D-6"]["note"] is True
    assert client.put("/api/plan/seats/Z-1/note", json={"text": "x"}).status_code == 404
    assert client.put("/api/plan/seats/D-6/note", json={"text": 5}).status_code == 400
    assert len(client.put("/api/plan/seats/D-1/note", json={"text": "x" * 900}).get_json()["note"]["text"]) == 500

    # The kiosk sees that there is a note, not what it says, and can't write one.
    app_module.app.extensions["auth"].users.add("kim", "kim-password-1", role="kiosk")
    kiosk = app_module.app.test_client()
    kiosk.post("/login", data={"username": "kim", "password": "kim-password-1"})
    seen = kiosk.get("/api/plan/seats/D-6").get_json()
    assert seen["crew"] is False and "note" not in seen
    assert kiosk.get("/api/plan").get_json()["seats"]["D-6"]["note"] is True
    assert kiosk.put("/api/plan/seats/D-6/note", json={"text": "hi"}).status_code == 403

    # Empty text removes it; a new event clears the rest.
    assert client.put("/api/plan/seats/D-6/note", json={"text": ""}).get_json()["note"] is None
    assert "note" not in client.get("/api/plan").get_json()["seats"]["D-6"]
    client.post("/api/report/new-event")
    assert "note" not in client.get("/api/plan").get_json()["seats"]["D-1"]
