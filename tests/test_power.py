"""Electrics (issue #45): boards, circuits, load, power incidents and the floor plan layer."""
import pytest

from floorbit import power
from integrations import events


def sign_in_as(app_module, username, role, teams=None):
    app_module.app.extensions["auth"].users.add(username, "role-password-1", role=role)
    from auth import teams as team_store
    for team, team_role in (teams or {}).items():
        team_store.set_member(username, team, team_role)
    c = app_module.app.test_client()
    assert c.post("/login", data={"username": username, "password": "role-password-1"}).status_code == 302
    return c


@pytest.fixture
def registry(app_module):
    return app_module.app.extensions["floorbit_plugins"]


@pytest.fixture
def watch(app_module):
    w = app_module.app.extensions["floorbit_power"]
    w.stop()
    w.reset()
    yield w
    w.reset()


@pytest.fixture
def floor(client, watch):
    """Block A (3 x 2 seats), one switch and board DB-1."""
    block = client.post("/api/seat-blocks", json={"name": "A", "x": 10, "y": 10, "cols": 3, "rows": 2}).get_json()
    sw = client.post("/api/switches", json={"name": "sw-a-01", "x": 20, "y": 20}).get_json()
    board = client.post("/api/power/boards", json={"name": "DB-1", "x": 5, "y": 40}).get_json()
    return {"block": block["id"], "switch": sw["id"], "board": board["id"]}


def add_circuit(client, floor, **extra):
    body = {"board": floor["board"], "name": "A row 2", "phase": "L2", "rating_a": 16,
            "blocks": [{"block": floor["block"], "rows": [2]}], "switches": [floor["switch"]], **extra}
    resp = client.post("/api/power/circuits", json=body)
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()


def test_power_is_a_plugin_area():
    from floorbit.plugins import AREA_METHODS, EVENTS
    assert AREA_METHODS["power"] == ("power_readings",) and "power.alert" in EVENTS


def test_rows_follow_the_editor_numbering():
    block = {"name": "a", "cols": 3, "rows": 2}
    assert power.block_rows(block) == [["A-1", "A-2", "A-3"], ["A-4", "A-5", "A-6"]]
    assert power.block_rows({**block, "rotation": 180}) == [["A-6", "A-5", "A-4"], ["A-3", "A-2", "A-1"]]
    assert power.block_rows({**block, "rotation": 90}) == [["A-3", "A-2", "A-1"], ["A-6", "A-5", "A-4"]]
    assert power.block_rows({**block, "reverse_numbers": True})[0] == ["A-6", "A-5", "A-4"]


def test_a_circuit_feeds_rows_and_switches(client, floor):
    add_circuit(client, floor)
    body = client.get("/api/power").get_json()
    c = body["circuits"][0]
    assert c["fed"]["seats"] == ["A-4", "A-5", "A-6"]
    assert c["fed"]["switches"] == [{"id": floor["switch"], "name": "sw-a-01"}]
    assert c["state"] == "unknown" and c["feeds_label"] == "block A row 2"
    assert body["can_edit"] and body["blocks"] == [{"id": floor["block"], "name": "A", "rows": 2}]


def test_circuits_are_checked(client, floor):
    bad = [({"board": "nope"}, "board"), ({"phase": "L4"}, "Phase"), ({"rating_a": 0}, "between"),
           ({"name": ""}, "name"), ({"blocks": [{"block": "gone"}]}, "seat blocks"), ({"meter": "a;b"}, "meter")]
    for extra, words in bad:
        resp = client.post("/api/power/circuits", json={"board": floor["board"], "name": "X", **extra})
        assert resp.status_code == 400 and words in resp.get_json()["error"], extra
    # A board with circuits stays until they are gone.
    c = add_circuit(client, floor)
    assert client.delete(f"/api/power/boards/{floor['board']}").status_code == 409
    assert client.delete(f"/api/power/circuits/{c['id']}").status_code == 200
    assert client.delete(f"/api/power/boards/{floor['board']}").status_code == 200


def test_load_turns_amber_then_red_and_files_one_incident(client, floor, watch, monkeypatch):
    c = add_circuit(client, floor)
    monkeypatch.setattr(events, "_subscribers", list(events._subscribers))   # this listener leaves with the test
    seen = []
    events.subscribe("power.alert", lambda ev: seen.append(ev["data"]))
    ok = client.post(f"/api/power/circuits/{c['id']}/reading", json={"amps": 8}).get_json()
    assert ok["alerts"] == []
    client.post(f"/api/power/circuits/{c['id']}/reading", json={"watts": 3036})   # 13.2 A at 230 V
    got = client.get("/api/power").get_json()["circuits"][0]
    assert got["state"] == "warn" and got["load_pct"] == 82.5 and got["reading"]["by"] == "tester"
    red = client.post(f"/api/power/circuits/{c['id']}/reading", json={"amps": 15.5}).get_json()
    assert [a["state"] for a in red["alerts"]] == ["crit"]
    assert seen[-1]["seats"] == 3 and seen[-1]["switches"] == ["sw-a-01"]
    board = client.get("/api/incidents").get_json()["incidents"]
    assert len(board) == 1
    incident = board[0]
    assert incident["circuit_id"] == c["id"] and incident["team"] == "electrics" and incident["source"] == "power"
    assert "A-4 to A-6" in incident["notes"][0]["text"] and "sw-a-01" in incident["notes"][0]["text"]
    # Staying red, or tripping, while it is open files nothing new.
    client.post(f"/api/power/circuits/{c['id']}/reading", json={"amps": 15.9})
    client.post(f"/api/power/circuits/{c['id']}/trip", json={"tripped": True})
    assert len(client.get("/api/incidents").get_json()["incidents"]) == 1
    assert seen[-1]["state"] == "tripped"


def test_a_trip_pages_and_marks_the_floor_plan(client, floor, watch):
    c = add_circuit(client, floor)
    resp = client.post(f"/api/power/circuits/{c['id']}/trip", json={"tripped": True}).get_json()
    assert resp["alerts"][0]["state"] == "tripped"
    marks = client.get("/api/power/markers").get_json()
    assert marks["seats"]["A-5"]["state"] == "tripped" and "A-1" not in marks["seats"]
    assert marks["switches"][floor["switch"]]["circuit"] == "A row 2"
    assert marks["boards"] == [{"id": floor["board"], "name": "DB-1", "x": 5.0, "y": 40.0, "state": "tripped"}]
    assert client.get("/api/incidents").get_json()["incidents"][0]["title"] == "Breaker tripped: A row 2"
    client.post(f"/api/power/circuits/{c['id']}/trip", json={"tripped": False})
    assert client.get("/api/power/markers").get_json()["seats"]["A-5"]["state"] == "unknown"


def test_what_is_red_at_start_pages_nobody_again(client, floor, watch):
    c = add_circuit(client, floor)
    client.post(f"/api/power/circuits/{c['id']}/reading", json={"amps": 15.5})
    watch.reset()     # a restart
    other = add_circuit(client, floor, name="A row 1", blocks=[{"block": floor["block"], "rows": [1]}])
    resp = client.post(f"/api/power/circuits/{other['id']}/reading", json={"amps": 3}).get_json()
    assert resp["alerts"] == []


def test_who_may_change_power(app_module, client, floor):
    c = add_circuit(client, floor)
    viewer = sign_in_as(app_module, "watcher", "viewer")
    assert viewer.get("/api/power").status_code == 200       # no personal data in it
    assert viewer.get("/api/power").get_json()["can_edit"] is False
    assert viewer.post(f"/api/power/circuits/{c['id']}/reading", json={"amps": 3}).status_code == 403
    # A tech in Electrics types readings and trips in, but leaves the circuits alone.
    sparky = sign_in_as(app_module, "sparky", "viewer", teams={"electrics": "tech"})
    assert sparky.post(f"/api/power/circuits/{c['id']}/reading", json={"amps": 3}).status_code == 200
    assert sparky.patch(f"/api/power/circuits/{c['id']}", json={"rating_a": 10}).status_code == 403
    # A network tech is not on the Electrics team.
    tech = sign_in_as(app_module, "netty", "tech", teams={"infra": "tech"})
    assert tech.post(f"/api/power/circuits/{c['id']}/trip", json={"tripped": True}).status_code == 403
    lead = sign_in_as(app_module, "boss", "lead")
    assert lead.patch(f"/api/power/circuits/{c['id']}", json={"rating_a": 10}).status_code == 200
    assert viewer.post("/api/power/check").status_code == 403


def test_the_layer_can_be_switched_off(client, floor, monkeypatch):
    monkeypatch.setenv("POWER_ENABLED", "0")
    assert client.get("/api/power/markers").get_json() == {"enabled": False, "seats": {}, "switches": {},
                                                           "boards": [], "counts": {}}
    assert client.post("/api/power/boards", json={"name": "DB-2"}).status_code == 409
    assert b'href="/power"' not in client.get("/").data


def test_demo_meters_feed_the_circuits(client, watch):
    client.put("/api/settings/plugins/demo", json={"enabled": True})
    assert client.post("/api/demo/layout").get_json()["blocks"] == 4
    body = client.post("/api/power/check").get_json()
    assert body["plugins"] == 1 and len(body["boards"]) == 2 and len(body["circuits"]) == 9
    by_name = {c["name"]: c for c in body["circuits"]}
    assert by_name["B row 2"]["state"] == "warn" and by_name["B row 2"]["reading"]["source"] == "plugin"
    assert by_name["Network rack"]["fed"]["switches"][0]["name"] == "core-01"
    assert len(by_name["A row 1"]["fed"]["seats"]) == 12


def test_discord_power_message():
    from integrations.discord import DiscordNotifier
    msg = DiscordNotifier().build_power_message({"id": "c1", "name": "A row 2", "board": "DB-1", "phase": "L2",
                                                 "state": "tripped", "rating_a": 16, "seats": 12,
                                                 "switches": ["sw-a-01"]}, now=1000)
    embed = msg["embeds"][0]
    assert embed["title"] == "⚡ Breaker tripped: A row 2"
    assert {"name": "Feeds", "value": "12 seats and sw-a-01", "inline": False} in embed["fields"]
    assert DiscordNotifier().build_power_message({"state": "warn"}) is None
