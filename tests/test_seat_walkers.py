"""Several crew members walk the hall at once (issue #1000): each claims rows, says where they are,
and the overview shows every row with its progress and walker. Demo hall only."""
import time

from floorbit import seat_walkers
from tests.test_rbac import sign_in_as
from tests.test_seat_walk import hall  # noqa: F401  # the demo hall fixture


def _rows(client):
    return {r["name"] if r["naming"] == "rows" else f"{r['block_label']} {r['name']}": r["id"]
            for r in client.get("/api/seat-rows").get_json()}


def test_two_walkers_take_different_rows_and_the_hall_shows_both(hall, app_module):  # noqa: F811
    rows = _rows(hall)
    a1, a2, b1 = rows["A 1"], rows["A 2"], rows["B 1"]
    me = hall.post("/api/seat-walk/walkers", json={"rows": [a1, a2]})
    assert me.status_code == 201, me.get_json()
    other = sign_in_as(app_module, "walker2", "lead")
    them = other.post("/api/seat-walk/walkers", json={"rows": [b1]}).get_json()
    # A row someone walks is theirs until they stop, unless taken over on purpose.
    clash = other.post("/api/seat-walk/walkers", json={"rows": [a2]})
    assert clash.status_code == 409 and clash.get_json()["held"]

    assert hall.put(f"/api/seat-walk/walkers/{me.get_json()['id']}", json={"seat": "a-3"}).status_code == 200
    by_row = {r["id"]: r for r in hall.get("/api/seat-walk").get_json()["hall"]}
    assert by_row[a1]["walker"]["seat"] == "A-3" and by_row[a1]["seats"] > 0
    assert by_row[b1]["walker"]["id"] == them["id"] and by_row[rows["C 1"]]["walker"] is None

    taken = other.post("/api/seat-walk/walkers", json={"rows": [a2], "take": True})
    assert taken.status_code == 201
    by_row = {r["id"]: r for r in hall.get("/api/seat-walk").get_json()["hall"]}
    assert by_row[a2]["walker"]["id"] == taken.get_json()["id"] and by_row[a1]["walker"]["id"] == me.get_json()["id"]

    assert hall.delete(f"/api/seat-walk/walkers/{me.get_json()['id']}").status_code == 200
    by_row = {r["id"]: r for r in hall.get("/api/seat-walk").get_json()["hall"]}
    assert by_row[a1]["walker"] is None
    assert hall.put(f"/api/seat-walk/walkers/{me.get_json()['id']}", json={"seat": "A-4"}).status_code == 404


def test_a_walker_nobody_heard_from_lets_go(hall, monkeypatch):  # noqa: F811
    row = _rows(hall)["C 1"]
    assert hall.post("/api/seat-walk/walkers", json={"rows": [row]}).status_code == 201
    later = time.time() + seat_walkers.IDLE + 1
    monkeypatch.setattr(seat_walkers.time, "time", lambda: later)
    assert hall.post("/api/seat-walk/walkers", json={"rows": [row]}).status_code == 201


def test_bad_claims(hall, app_module):  # noqa: F811
    assert hall.post("/api/seat-walk/walkers", json={"rows": []}).status_code == 400
    assert hall.post("/api/seat-walk/walkers", json={"rows": ["nope:1"]}).status_code == 404
    viewer = sign_in_as(app_module, "watcher", "tech")      # sees the walk, may not walk
    assert viewer.post("/api/seat-walk/walkers", json={"rows": [_rows(hall)["A 1"]]}).status_code == 403
    assert viewer.get("/api/seat-walk").status_code == 200
