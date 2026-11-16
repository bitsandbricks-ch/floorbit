"""Cables drawn on the floor plan (floorbit/cable_plan.py)."""
import pytest

from floorbit import cable_plan
from floorbit.store import load_data

# One seat is 2 % of the plan across and 3.2 % down: block A's seats sit at x 29..51, its rows at y 38.4 and 41.6.
A = {"name": "A", "cols": 12, "rows": 2, "x": 40, "y": 40}


@pytest.fixture(autouse=True)
def _no_port_watch(monkeypatch):
    # What another test's port watch read must not draw cables here.
    monkeypatch.setattr(cable_plan, '_live_port_seats', dict)


def _floor(client, auto=True):
    client.put("/api/settings", json={"cabling.auto": auto})
    block = client.post("/api/seat-blocks", json=A).get_json()
    sw = client.post("/api/switches", json={"name": "sw-a-01", "x": 10, "y": 20}).get_json()
    return block, sw


def _drawn(client, kind=None):
    body = client.get("/api/cable-plan").get_json()
    return [c for c in body["cables"] if kind is None or c["kind"] == kind]


def test_a_seat_cable_runs_along_its_block_into_the_row(client):
    _floor(client)
    assert client.post("/api/cables", json={"switch": "sw-a-01", "port": "Gi1/0/1", "seat": "A-14",
                                            "type": "fiber-sm", "speed": 10}).status_code == 201
    (cable,) = _drawn(client, "lan")
    # A-14 is row 2, column 2. The switch is left of the block: the run is one seat left of it.
    assert cable["points"] == [[10, 20], [27, 20], [27, 41.6], [31, 41.6]]
    assert cable["layer"] == "network" and cable["media"] == "fiber" and cable["speed"] == 10
    assert cable["manual"] is False and cable["key"] == "lan:sw-a-01|gi1/0/1"


def test_bends_the_crew_placed_pin_the_route(client):
    _floor(client)
    client.post("/api/cables", json={"switch": "sw-a-01", "port": "Gi1/0/1", "seat": "A-1"})
    key = "lan:sw-a-01|gi1/0/1"
    res = client.put("/api/cable-plan/routes", json={"routes": {key: {"points": [[15, 30]], "corners": "round"}}})
    assert res.status_code == 200, res.get_json()
    (cable,) = _drawn(client, "lan")
    assert cable["points"] == [[10, 20], [15, 30], [29, 38.4]]
    assert cable["manual"] is True and cable["corners"] == "round"
    # The seat behind the port changes: the bends stay, the end follows.
    cid = client.get("/api/cables").get_json()["cables"][0]["id"]
    client.patch(f"/api/cables/{cid}", json={"seat": "A-2"})
    (cable,) = _drawn(client, "lan")
    assert cable["points"][1] == [15, 30] and cable["points"][-1] == [31, 38.4]
    # Back to the automatic route.
    client.put("/api/cable-plan/routes", json={"routes": {key: None}})
    assert _drawn(client, "lan")[0]["manual"] is False


def test_bad_routes_are_refused(client):
    for routes in ({"nope": None}, {"lan:a|b": {"points": [["x", 1]]}}, {"lan:a|b": {"corners": "wavy"}},
                   {"lan:a|b": {"points": [[1, 1]] * 51}}, {}):
        res = client.put("/api/cable-plan/routes", json={"routes": routes})
        assert res.status_code == 400, routes


def test_automatic_cabling_off_draws_only_the_drawn_cables(client):
    _floor(client, auto=False)
    client.post("/api/cables", json={"switch": "sw-a-01", "port": "Gi1/0/1", "seat": "A-1"})
    client.post("/api/cables", json={"switch": "sw-a-01", "port": "Gi1/0/2", "seat": "A-2"})
    body = client.get("/api/cable-plan").get_json()
    assert body["auto"] is False and body["cables"] == []
    client.put("/api/cable-plan/routes", json={"routes": {"lan:sw-a-01|gi1/0/2": {"points": None}}})
    assert [c["ref"]["seat"] for c in _drawn(client)] == ["A-2"]


def test_ports_the_watch_read_are_drawn_with_automatic_cabling(client, app_module):
    _floor(client)
    data = load_data()
    drawn = cable_plan.plan(data, live={("sw-a-01", "Gi1/0/9"): "A-3"}, auto=True)["cables"]
    assert [(c["ref"]["seat"], c["ref"]["source"]) for c in drawn] == [("A-3", "watch")]
    assert cable_plan.plan(data, live={("sw-a-01", "Gi1/0/9"): "A-3"}, auto=False)["cables"] == []


def test_a_cable_through_a_placed_patch_panel(client):
    _floor(client)
    client.post("/api/cables", json={"switch": "sw-a-01", "port": "Gi1/0/1", "panel": "PP-1", "panel_port": "1",
                                     "seat": "A-1"})
    assert client.put("/api/cable-plan/panels/PP-1", json={"x": 20, "y": 30}).status_code == 200
    body = client.get("/api/cable-plan").get_json()
    assert body["panels"] == [{"name": "PP-1", "x": 20, "y": 30}] and body["panel_names"] == ["PP-1"]
    (cable,) = body["cables"]
    assert cable["via"] == "PP-1" and [20, 30] in cable["points"]
    assert client.delete("/api/cable-plan/panels/PP-1").status_code == 200
    assert client.delete("/api/cable-plan/panels/PP-1").status_code == 404


def test_uplinks_and_power_are_drawn_on_their_layers(client):
    block, sw = _floor(client)
    client.post("/api/switches", json={"name": "dist-01", "x": 10, "y": 60})
    assert client.post("/api/links", json={"a": "sw-a-01", "a_port": "Te1/1/1", "b": "dist-01",
                                           "b_port": "Te1/0/1", "type": "dac", "speed": 10}).status_code == 201
    board = client.post("/api/power/boards", json={"name": "DB-1", "x": 5, "y": 40}).get_json()
    client.post("/api/power/circuits", json={"board": board["id"], "name": "A row", "blocks": [{"block": block["id"]}],
                                             "switches": [sw["id"]]})
    (up,) = _drawn(client, "uplink")
    assert up["points"] == [[10, 20], [10, 60]] and up["media"] == "dac"
    feeds = _drawn(client, "power")
    assert {c["layer"] for c in feeds} == {"electrical"} and len(feeds) == 2
    to_block = next(c for c in feeds if "block" in c["ref"])
    assert to_block["points"][0] == [5, 40] and to_block["points"][-1] == [28, 40]   # the block's near edge


def test_turned_blocks_keep_their_seats_in_place(client):
    data = {"seat_blocks": [{**A, "id": "b1", "rotation": 90, "naming": "block"}]}
    seats, boxes = cable_plan.geometry(data, "main")
    assert boxes["b1"]["sideways"] is True
    x, y, _ = seats["A-1"]
    # Turned a quarter clockwise, the first row runs down the right-hand side, numbered from the bottom.
    assert (round(x, 2), round(y, 2)) == (41, 57.6)
