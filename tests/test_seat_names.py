"""Seat blocks with a letter per row, several at once, turned (floorbit/seat_names.py)."""
from floorbit import seat_names
from floorbit.store import load_data

ROWS = {"name": "", "cols": 3, "rows": 2, "naming": "rows", "row_start": "C"}


def test_letters_count_on_like_spreadsheet_columns():
    assert [seat_names.row_letter(i) for i in (0, 25, 26, 27)] == ["A", "Z", "AA", "AB"]
    assert seat_names.letter_index("AA") == 26 and seat_names.letter_index("c") == 2


def test_every_row_has_its_own_letter_and_numbers():
    assert seat_names.block_rows(ROWS) == [["C-1", "C-2", "C-3"], ["D-1", "D-2", "D-3"]]
    assert seat_names.block_rows({**ROWS, "reverse_numbers": True}) == [["C-3", "C-2", "C-1"], ["D-3", "D-2", "D-1"]]


def test_turning_a_block_turns_its_numbers():
    # Upside down: the block's bottom row is read first and seat 1 is on the left as seen.
    assert seat_names.block_rows({**ROWS, "rotation": 180}) == [["D-3", "D-2", "D-1"], ["C-3", "C-2", "C-1"]]
    # A quarter clockwise: rows stand up, letters run left to right, numbers top to bottom.
    assert seat_names.block_rows({**ROWS, "rotation": 90}) == [["D-1", "D-2", "D-3"], ["C-1", "C-2", "C-3"]]
    assert seat_names.block_rows({**ROWS, "rotation": 270}) == [["C-3", "C-2", "C-1"], ["D-3", "D-2", "D-1"]]
    assert seat_names.seat_one_first(ROWS) and not seat_names.seat_one_first({**ROWS, "rotation": 180})


def test_old_blocks_keep_their_seat_names():
    old = {"name": "a", "cols": 3, "rows": 2}
    assert seat_names.block_rows(old) == [["A-1", "A-2", "A-3"], ["A-4", "A-5", "A-6"]]
    assert seat_names.row_letters(old) == []


def test_several_blocks_at_once_carry_on_the_rows(client):
    body = {**ROWS, "row_start": "A", "x": 50, "y": 10, "count": 3, "dy": 12, "row_labels": "both"}
    resp = client.post("/api/seat-blocks/many", json=body)
    assert resp.status_code == 201
    made = resp.get_json()
    assert [b["row_start"] for b in made] == ["A", "C", "E"]
    assert [b["y"] for b in made] == [10, 22, 34]
    assert made[2]["seat_rows"][1] == ["F-1", "F-2", "F-3"] and made[0]["row_letters"] == ["A", "B"]
    assert len(load_data()["seat_blocks"]) == 3


def test_blocks_named_by_letter_count_on_too(client):
    made = client.post("/api/seat-blocks/many", json={"name": "A", "cols": 2, "rows": 1, "x": 10, "y": 10,
                                                      "count": 2, "dx": 20}).get_json()
    assert [b["name"] for b in made] == ["A", "B"] and made[1]["seat_rows"] == [["B-1", "B-2"]]


def test_a_seat_name_is_never_given_twice(client):
    assert client.post("/api/seat-blocks", json={**ROWS, "x": 10, "y": 10}).status_code == 201
    resp = client.post("/api/seat-blocks", json={**ROWS, "row_start": "D", "x": 10, "y": 30})
    assert resp.status_code == 409 and resp.get_json()["seat"] == "D-1"
    # All or nothing: the second block (rows C and D) would clash, so none is added.
    many = client.post("/api/seat-blocks/many", json={**ROWS, "row_start": "A", "x": 10, "y": 40, "count": 3, "dy": 5})
    assert many.status_code == 409 and many.get_json()["seat"] == "C-1"
    assert len(load_data()["seat_blocks"]) == 1


def test_editing_checks_names_but_moving_an_old_clash_still_works(client):
    a = client.post("/api/seat-blocks", json={"name": "", "cols": 2, "rows": 1, "x": 10, "y": 10}).get_json()
    data = load_data()
    data["seat_blocks"].append({**a, "id": "twin", "y": 30})   # two unnamed blocks: seats 1 and 2 twice
    from floorbit.store import save_data
    save_data(data)
    assert client.put("/api/seat-blocks/twin", json={"x": 40}).status_code == 200
    b = client.post("/api/seat-blocks", json={**ROWS, "x": 60, "y": 60}).get_json()
    assert client.put(f"/api/seat-blocks/{b['id']}", json={"row_start": "Z"}).status_code == 200
    assert client.put(f"/api/seat-blocks/{b['id']}", json={"row_labels": "middle"}).status_code == 400
    assert client.put(f"/api/seat-blocks/{b['id']}", json={"row_start": "A1"}).status_code == 400


def test_the_plan_drawing_has_the_row_letters(client):
    from floorbit.blueprints.screen import CELL, plan
    client.post("/api/seat-blocks", json={**ROWS, "x": 50, "y": 50, "row_labels": "start"})
    drawing, _ = plan(load_data())
    rows = drawing["shapes"][0]["rows"]
    assert [r["text"] for r in rows] == ["C", "D"]
    assert rows[0]["x"] == -3 * CELL / 2 - CELL / 2


def test_csv_import_takes_the_naming_columns(client):
    from floorbit import halls
    blocks, errors = halls.parse_blocks_csv("name,x,y,cols,rows,naming,row_start\nNorth,10,10,4,2,rows,K\n")
    assert not errors and blocks[0]["naming"] == "rows" and blocks[0]["row_start"] == "K"
    _, errors = halls.parse_blocks_csv("name,x,y,cols,rows,row_labels\nN,10,10,4,2,middle\n")
    assert errors


def test_the_plan_has_no_edge(client):
    # Mike's case: more blocks than fit in the plan box. The plan grows with them.
    made = client.post("/api/seat-blocks/many", json={"name": "A", "cols": 12, "rows": 2, "x": 20, "y": 80,
                                                      "count": 4, "dy": 15})
    assert made.status_code == 201
    assert [b["y"] for b in made.get_json()] == [80, 95, 110, 125]
    left = client.post("/api/seat-blocks", json={"name": "Z", "cols": 2, "rows": 1, "x": -30, "y": 50})
    assert left.status_code == 201
    moved = client.put(f"/api/seat-blocks/{left.get_json()['id']}", json={"x": -45.5})
    assert moved.status_code == 200 and moved.get_json()["x"] == -45.5
    # Only nonsense is refused.
    for x in ("nan", "inf", 1e9):
        assert client.post("/api/seat-blocks", json={"name": "Q", "x": x, "y": 10}).status_code == 400
    # The Seats view fits its drawing around all of them.
    drawing = client.get("/api/plan").get_json()["drawing"]
    names = {s["name"] for s in drawing["shapes"]}
    assert {"A", "B", "C", "D", "Z"} <= names
