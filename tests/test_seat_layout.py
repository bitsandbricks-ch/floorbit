"""Seats placed freely inside a block (floorbit/seat_layout.py): the admins' U round their table."""
from floorbit import seat_layout
from floorbit.blueprints.screen import CELL

ADMINS = {"name": "ADM", "cols": 4, "rows": 2, "x": 50, "y": 50}


def test_places_start_at_the_corner_and_fall_back_to_rows():
    rows = {"cols": 3, "rows": 1}
    assert seat_layout.places(rows, 3, 1) == ({(0, 0): (0, 0), (0, 1): (1, 0), (0, 2): (2, 0)}, 3, 1)
    # Seat 3 goes under seat 1: the box is two seats wide and two high.
    free = {**rows, "seat_at": {"0,2": [0, 1]}}
    assert seat_layout.places(free, 3, 1) == ({(0, 0): (0, 0), (0, 1): (1, 0), (0, 2): (0, 1)}, 2, 2)
    assert seat_layout.clean({"0,9": [1, 1], "0,1": ["2.123", 0]}, 3, 1) == {"0,1": [2.12, 0.0]}
    assert seat_layout.clean({}, 3, 1) is None
    for bad in ({"x": [1, 1]}, {"0,0": [1]}, {"0,0": [1e6, 0]}, {"0,0": [float("nan"), 0]}, [1]):
        try:
            seat_layout.clean(bad, 3, 1)
        except seat_layout.LayoutError:
            continue
        raise AssertionError(bad)


def test_a_block_keeps_its_seats_where_they_were_put(client):
    block = client.post("/api/seat-blocks", json=ADMINS).get_json()
    assert block["seat_at"] is None
    # Back row turned into the sides of a U: the first and last seat of row 2 move up beside row 1.
    u = {"1,0": [-1, -1], "1,3": [4, -1], "1,1": [1, 1], "1,2": [2, 1]}
    moved = client.put(f"/api/seat-blocks/{block['id']}", json={"seat_at": u, "x": 50, "y": 50}).get_json()
    assert moved["seat_at"]["1,0"] == [0, 0] and moved["seat_at"]["0,0"] == [1, 1]   # the box starts at 0,0
    assert moved["seat_at"]["1,3"] == [5, 0]
    assert moved["seat_rows"] == block["seat_rows"]                                    # names stay
    plan = client.get("/api/plan?hall=main").get_json()
    shape = next(s for s in plan["drawing"]["shapes"] if s["name"] == "ADM")
    assert shape["free"] and shape["rows"] == [] and (shape["w"], shape["h"]) == (6 * CELL, 3 * CELL)
    cell = next(c for c in shape["cells"] if c["seat"] == block["seat_rows"][1][0])
    assert (cell["x"], cell["y"], cell["rc"]) == (-3 * CELL, -1.5 * CELL, [1, 0])
    # Seats placed freely can't be merged; back to rows clears them.
    other = client.post("/api/seat-blocks", json={**ADMINS, "name": "ADN", "x": 70}).get_json()
    merge = client.post("/api/seat-blocks/merge", json={"ids": [block["id"], other["id"]]})
    assert merge.status_code == 400 and "freely" in merge.get_json()["error"]
    assert client.put(f"/api/seat-blocks/{block['id']}", json={"seat_at": None}).get_json()["seat_at"] is None
    bad = client.put(f"/api/seat-blocks/{block['id']}", json={"seat_at": {"0,0": [500, 0]}})
    assert bad.status_code == 400


def test_a_template_carries_the_seat_places(client):
    block = client.post("/api/seat-blocks", json=ADMINS).get_json()
    placed = {"seat_at": {"1,0": [-1, -1]}, "col_gaps": [{"after": 2, "size": 1}]}
    client.put(f"/api/seat-blocks/{block['id']}", json=placed)
    saved = client.post("/api/templates", json={"name": "U", "hall": "main"})
    assert saved.status_code in (200, 201), saved.get_json()
    tid = saved.get_json()["id"]
    client.put(f"/api/seat-blocks/{block['id']}", json={"seat_at": None, "col_gaps": []})
    assert client.post(f"/api/templates/{tid}/apply", json={"hall": "main"}).status_code == 200
    back = client.get("/api/seat-blocks").get_json()[0]
    assert back["seat_at"]["1,0"] == [0, 0] and back["col_gaps"] == [{"after": 2, "size": 1.0}]
