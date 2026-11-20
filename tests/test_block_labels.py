"""A block named by its rows has no name of its own: pickers and power feeds showed a dash and "?"
(Mike, 2026-11-19). They show the block's row letters instead."""
from floorbit import power, seat_names


def _rows_block(**extra):
    return {'id': 'b1', 'name': '', 'naming': 'rows', 'row_start': 'C', 'rows': 2, 'cols': 4, **extra}


def test_a_block_named_by_rows_is_called_by_its_row_letters():
    assert seat_names.label(_rows_block()) == 'C\u2013D'
    assert seat_names.label(_rows_block(rows=1)) == 'C'
    assert seat_names.label(_rows_block(rotation=180)) == 'C\u2013D'             # turned: still C to D
    assert seat_names.label({'name': 'A', 'rows': 2, 'cols': 4}) == 'A'
    assert seat_names.row_names(_rows_block()) == ['C', 'D']
    assert seat_names.row_names({'name': 'A', 'rows': 3}) == ['1', '2', '3']


def test_power_feeds_name_the_rows_not_a_question_mark():
    blocks = {'b1': _rows_block(), 'b2': {'id': 'b2', 'name': 'A', 'rows': 2, 'cols': 4}}
    assert power._feed_label({'block': 'b1', 'rows': [2]}, blocks) == 'row D'
    assert power._feed_label({'block': 'b1', 'rows': []}, blocks) == 'rows C\u2013D'
    assert power._feed_label({'block': 'b2', 'rows': [1, 2]}, blocks) == 'block A rows 1, 2'
    assert power._feed_label({'block': 'gone'}, blocks) == 'a removed block'


def test_the_blocks_api_gives_each_block_a_label(client):
    client.post('/api/seat-blocks', json={'name': '', 'naming': 'rows', 'row_start': 'E', 'x': 20, 'y': 20,
                                          'cols': 4, 'rows': 3})
    got = client.get('/api/seat-blocks').get_json()
    assert [(b['label'], b['row_names']) for b in got] == [('E\u2013G', ['E', 'F', 'G'])]


def test_rows_from_two_blocks_are_listed_by_name_and_patched_together(client):
    """A block lists its rows by name, and the crew patches rows, whichever block they are in."""
    hall_id = client.get("/api/halls").get_json()
    hall_id = (hall_id.get("halls") if isinstance(hall_id, dict) else hall_id)[0]["id"]
    for start, x in (("C", 0), ("E", 300)):
        r = client.post("/api/seat-blocks", json={"x": x, "y": 0, "cols": 2, "rows": 2, "naming": "rows",
                                                  "row_start": start, "hall_id": hall_id})
        assert r.status_code in (200, 201), r.get_json()
    rows = client.get("/api/seat-rows").get_json()
    assert [r["name"] for r in rows] == ["C", "D", "E", "F"]
    assert rows[0]["block_label"] == "C\u2013D" and rows[0]["seat_count"] == 2 and rows[0]["naming"] == "rows"
    by_name = {r["name"]: r["id"] for r in rows}
    plan = client.post("/api/cables/block", json={"rows": [by_name["D"], by_name["E"]], "switch": "sw-1",
                                                  "first_port": "Gi1/0/1", "dry_run": True}).get_json()
    assert plan["rows"] == ["D", "E"]
    assert [(c["seat"], c["port"]) for c in plan["cables"]] == [
        ("D-1", "Gi1/0/1"), ("D-2", "Gi1/0/2"), ("E-1", "Gi1/0/3"), ("E-2", "Gi1/0/4")]
    walk = client.get(f"/api/seat-walk?rows={by_name['F']}").get_json()
    assert walk["row_names"] == ["F"] and [s["seat"] for s in walk["seats"]] == ["F-1", "F-2"]
    check = client.get("/api/cables/check").get_json()
    assert "rows" in check
