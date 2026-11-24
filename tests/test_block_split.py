"""Splitting a seat block at a row (floorbit/block_split.py, #1208)."""
import pytest

from floorbit.store import load_data

# One seat is 2 % of the plan across and 3.2 % down (50 x 31.25 seats).
ROWS = {"name": "", "naming": "rows", "row_start": "C", "cols": 10, "rows": 4, "x": 40, "y": 40}


def _make(client, **fields):
    made = client.post("/api/seat-blocks", json=fields)
    assert made.status_code == 201, made.get_json()
    return made.get_json()


def _split(client, block, at):
    return client.post(f"/api/seat-blocks/{block['id']}/split", json={"at": at})


def test_rows_above_stay_and_the_rest_become_a_new_block_in_place(client):
    block = _make(client, **ROWS)
    res = _split(client, block, 1)
    assert res.status_code == 201, res.get_json()
    kept, new = res.get_json()["block"], res.get_json()["new"]
    assert kept["id"] == block["id"] and new["id"] != block["id"]
    assert len(kept["rows"]) == 1 and len(new["rows"]) == 3 and new["rows"][0]["gap"] == 0
    # Every row keeps its letter, so no seat changes its name.
    assert kept["row_letters"] == ["C"] and new["row_letters"] == ["D", "E", "F"]
    # Four rows of one seat, 4 seats high: the top row's middle is 1.5 seats up, the rest's 0.5 down.
    assert (kept["x"], kept["y"]) == (40, pytest.approx(40 - 1.5 * 3.2))
    assert (new["x"], new["y"]) == (40, pytest.approx(40 + 0.5 * 3.2))
    stored = {b["id"]: b for b in load_data()["seat_blocks"]}
    assert set(stored) == {kept["id"], new["id"]} and stored[new["id"]]["hall_id"] == block["hall_id"]


def test_a_turned_block_splits_along_its_own_rows(client):
    block = _make(client, **{**ROWS, "rotation": 90})
    res = _split(client, block, 2)
    assert res.status_code == 201, res.get_json()
    kept, new = res.get_json()["block"], res.get_json()["new"]
    # A quarter turn clockwise puts the block's top rows on the right; the letters still follow the rows.
    assert kept["x"] > 40 > new["x"] and kept["y"] == new["y"] == 40
    assert sorted(kept["row_letters"] + new["row_letters"]) == ["C", "D", "E", "F"]
    assert set(kept["row_letters"]) == set(block["row_letters"][:2])


def test_a_named_block_gives_the_new_part_the_next_free_name(client):
    _make(client, name="B", cols=4, rows=1, x=10, y=10)
    block = _make(client, name="A", cols=6, rows=3, x=40, y=40)
    res = _split(client, block, 2)
    assert res.status_code == 201, res.get_json()
    kept, new = res.get_json()["block"], res.get_json()["new"]
    assert kept["name"] == "A" and new["name"] == "C"
    assert new["seat_rows"][0][0] == "C-1"
    worded = _make(client, name="Gaming", cols=6, rows=2, x=40, y=80)
    assert _split(client, worded, 1).get_json()["new"]["name"] == "Gaming 2"


@pytest.mark.parametrize("at", [0, 4, "2", None, True])
def test_the_row_must_be_inside_the_block(client, at):
    block = _make(client, **ROWS)
    res = _split(client, block, at)
    assert res.status_code == 400
    assert len(load_data()["seat_blocks"]) == 1


def test_split_then_merge_gives_the_block_back(client):
    block = _make(client, **ROWS)
    parts = _split(client, block, 2).get_json()
    merged = client.post("/api/seat-blocks/merge", json={"ids": [parts["new"]["id"], parts["block"]["id"]]})
    assert merged.status_code == 200, merged.get_json()
    back = merged.get_json()["block"]
    assert back["id"] == block["id"] and back["row_letters"] == block["row_letters"]
    assert (back["x"], back["y"]) == (pytest.approx(block["x"]), pytest.approx(block["y"]))


def test_unknown_block(client):
    assert client.post("/api/seat-blocks/nope/split", json={"at": 1}).status_code == 404
