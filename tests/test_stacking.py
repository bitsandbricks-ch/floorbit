"""Which seat block or mark is drawn over which (floorbit/stacking.py)."""
from floorbit import stacking

BLOCK = {"cols": 2, "rows": 1, "x": 40, "y": 40}


def test_items_go_bottom_up_by_z():
    items = [{"id": "a", "z": 2}, {"id": "b"}, {"id": "c", "z": -1}, {"id": "d", "z": 0}]
    assert [i["id"] for i in stacking.by_z(items)] == ["c", "b", "d", "a"]
    assert stacking.z_of(None) == 0 and stacking.z_of("3") == 3
    for bad in ("x", 2_000_000):
        try:
            stacking.z_of(bad)
        except stacking.StackError:
            continue
        raise AssertionError(bad)


def test_blocks_keep_their_z_and_every_view_draws_in_that_order(client):
    a = client.post("/api/seat-blocks", json={**BLOCK, "name": "A"}).get_json()
    b = client.post("/api/seat-blocks", json={**BLOCK, "name": "B", "x": 41}).get_json()
    assert a["z"] == 0
    assert client.put(f"/api/seat-blocks/{a['id']}", json={"z": 5}).get_json()["z"] == 5
    assert [x["name"] for x in client.get("/api/seat-blocks").get_json()] == ["B", "A"]
    shapes = client.get("/api/plan").get_json()["drawing"]["shapes"]
    assert [s["name"] for s in shapes] == ["B", "A"]
    bad = client.put(f"/api/seat-blocks/{b['id']}", json={"z": "top"})
    assert bad.status_code == 400 and "z" in bad.get_json()["error"]


def test_marks_keep_their_z(client):
    low = client.post("/api/plan-marks", json={"kind": "text", "x": 10, "y": 10, "text": "Low", "z": -2}).get_json()
    client.post("/api/plan-marks", json={"kind": "text", "x": 10, "y": 10, "text": "Mid"})
    assert low["z"] == -2
    client.put(f"/api/plan-marks/{low['id']}", json={"z": 9})
    assert [m["text"] for m in client.get("/api/plan-marks").get_json()["marks"]] == ["Mid", "Low"]
