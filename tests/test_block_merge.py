"""Merging seat blocks (floorbit/block_merge.py)."""
import pytest

from floorbit.store import load_data

# One seat is 2 % of the plan across and 3.2 % down (50 x 31.25 seats).
A = {"name": "A", "cols": 12, "rows": 2, "x": 40, "y": 40}


def _make(client, **fields):
    made = client.post("/api/seat-blocks", json=fields)
    assert made.status_code == 201, made.get_json()
    return made.get_json()


def _merge(client, *blocks):
    return client.post("/api/seat-blocks/merge", json={"ids": [b["id"] for b in blocks]})


def test_blocks_side_by_side_become_one_and_numbers_carry_on(client):
    a = _make(client, **A)
    b = _make(client, **{**A, "name": "B", "cols": 6, "x": 58})   # touching on the right
    res = _merge(client, b, a)   # the order picked doesn't matter: the left one leads
    assert res.status_code == 200, res.get_json()
    body = res.get_json()
    block = body["block"]
    assert body["removed"] == [b["id"]] and block["id"] == a["id"]
    assert block["cols"] == 18 and block["rows"] == 2 and block["col_gaps"] == []
    assert (block["x"], block["y"]) == (46, 40)
    assert block["seat_rows"][0][-1] == "A-18" and block["seat_rows"][1][0] == "A-19"
    assert [x["id"] for x in load_data()["seat_blocks"]] == [a["id"]]


def test_space_between_blocks_becomes_a_gap(client):
    a = _make(client, **A)
    b = _make(client, **{**A, "name": "B", "cols": 6, "x": 64})   # 3 seats of room
    block = _merge(client, a, b).get_json()["block"]
    assert block["col_gaps"] == [{"after": 12, "size": 3.0}]
    assert block["x"] == 49


def test_stacked_rows_keep_their_row_letters(client):
    a = _make(client, **{**A, "naming": "rows", "row_start": "E"})
    b = _make(client, **{**A, "rows": 1, "naming": "rows", "row_start": "G", "y": 44.8,
                         "col_gaps": [{"after": 6, "size": 1}]})
    bad = _merge(client, a, b)
    assert bad.status_code == 400 and "columns" in bad.get_json()["error"]
    client.put(f"/api/seat-blocks/{b['id']}", json={"col_gaps": []})
    block = _merge(client, a, b).get_json()["block"]
    assert block["rows"] == 3 and block["row_letters"] == ["E", "F", "G"]
    assert block["seat_rows"][2][0] == "G-1"


def test_turned_blocks_merge_in_their_own_frame(client):
    a = _make(client, **{**A, "rows": 1, "rotation": 90})
    b = _make(client, **{**A, "name": "B", "rows": 1, "rotation": 90, "y": 78.4})   # below = to its right
    block = _merge(client, a, b).get_json()["block"]
    assert block["cols"] == 24 and block["rotation"] == 90
    assert block["x"] == pytest.approx(40) and block["y"] == pytest.approx(59.2)


@pytest.mark.parametrize("other", [
    {"rows": 3, "x": 58},             # side by side with other rows
    {"x": 50},                        # overlapping
    {"x": 58, "rotation": 90},        # turned the other way
    {"x": 58, "y": 45},               # not in line
    {"x": 120},                       # far apart
])
def test_blocks_that_do_not_fit_stay_apart(client, other):
    a = _make(client, **A)
    b = _make(client, **{**A, "name": "B", **other})
    res = _merge(client, a, b)
    assert res.status_code == 400 and res.get_json()["error"]
    assert len(load_data()["seat_blocks"]) == 2


def test_merge_needs_known_blocks(client):
    a = _make(client, **A)
    assert _merge(client, a).status_code == 400
    assert client.post("/api/seat-blocks/merge", json={"ids": [a["id"], "nope"]}).status_code == 404


def test_blocks_have_no_group_field(client):
    # Groups are plan groups (floorbit/plan_groups.py); the old field is moved there once.
    a = _make(client, **{**A, "group": "g1"})
    assert "group" not in a
    assert "group" not in client.put(f"/api/seat-blocks/{a['id']}", json={"group": "g2"}).get_json()
