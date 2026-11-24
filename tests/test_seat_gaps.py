"""Gaps inside a seat block (floorbit/seat_gaps.py): room in the rows, lanes between rows."""
from floorbit import seat_gaps
from floorbit.blueprints.screen import CELL
from floorbit.store import load_data

ROW = {"name": "A", "cols": 12, "rows": 2, "x": 40, "y": 40}


def test_offsets_move_seats_apart():
    assert seat_gaps.offsets([], 3) == ([0, 1, 2], 3)
    assert seat_gaps.offsets([{"after": 2, "size": 1.5}], 4) == ([0, 1, 3.5, 4.5], 5.5)


def test_gaps_are_cleaned():
    assert seat_gaps.clean([{"after": 9, "size": 1}, {"after": 3, "size": "2"}, {"after": 3, "size": 1}], 6) == \
        [{"after": 3, "size": 1.0}]   # after the last column: dropped; the same column twice: the last wins
    for bad in ([{"after": 1}], [{"after": 1, "size": 0}], [{"after": 1, "size": 99}], "x"):
        try:
            seat_gaps.clean(bad, 6)
        except seat_gaps.GapError:
            continue
        raise AssertionError(bad)


def _rows(col_gaps=None, gap=0, seats=12):
    return [{"id": "1", "seats": seats, "col_gaps": col_gaps or []},
            {"id": "2", "seats": seats, "col_gaps": col_gaps or [], "gap": gap}]


def test_a_block_keeps_its_gaps_and_its_seat_names(client):
    made = client.post("/api/seat-blocks", json={**ROW, "rows": _rows([{"after": 6, "size": 2}])})
    assert made.status_code == 201
    block = made.get_json()
    assert block["rows"][0]["col_gaps"] == [{"after": 6, "size": 2.0}] and block["rows"][1]["gap"] == 0
    assert block["seat_rows"][0][:7] == ["A-1", "A-2", "A-3", "A-4", "A-5", "A-6", "A-7"]   # numbers carry on
    lane = client.put(f"/api/seat-blocks/{block['id']}", json={"rows": _rows([{"after": 6, "size": 2}], gap=3)})
    assert lane.get_json()["rows"][1]["gap"] == 3.0
    # Fewer seats drop the gaps that no longer fit.
    fewer = _rows([{"after": 6, "size": 2}], gap=3, seats=5)
    small = client.put(f"/api/seat-blocks/{block['id']}", json={"rows": fewer}).get_json()
    assert small["rows"][0]["col_gaps"] == [] and small["rows"][1]["gap"] == 3.0
    bad = client.put(f"/api/seat-blocks/{block['id']}", json={"rows": _rows(gap=50)})
    assert bad.status_code == 400 and "space above a row" in bad.get_json()["error"]
    assert load_data()["seat_blocks"][0]["rows"][1]["gap"] == 3.0


def test_the_seats_view_draws_the_gaps(client):
    client.post("/api/seat-blocks", json={**ROW, "rows": _rows([{"after": 6, "size": 2}], gap=3)})
    shape = client.get("/api/plan").get_json()["drawing"]["shapes"][0]
    assert shape["w"] == 14 * CELL and shape["h"] == 5 * CELL
    xs = sorted({c["x"] for c in shape["cells"]})
    assert xs[6] - xs[5] == 3 * CELL and xs[5] - xs[4] == CELL
    ys = sorted({c["y"] for c in shape["cells"]})
    assert ys[1] - ys[0] == 4 * CELL
