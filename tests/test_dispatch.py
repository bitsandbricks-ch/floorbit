"""Tech dispatch (issue #30)."""
import pytest

from floorbit import dispatch


def _login(app_module, name, role):
    app_module.app.extensions["auth"].users.add(name, f"{name}-password-1", role=role)
    c = app_module.app.test_client()
    assert c.post("/login", data={"username": name, "password": f"{name}-password-1"}).status_code == 302
    return c


@pytest.fixture
def floor(client, app_module):
    # Block A on the left, block B far to the right, both in the main hall.
    client.post("/api/seat-blocks", json={"name": "A", "x": 10, "y": 50, "cols": 4, "rows": 2})
    client.post("/api/seat-blocks", json={"name": "B", "x": 90, "y": 50, "cols": 4, "rows": 2})
    return {"ana": _login(app_module, "ana", "tech"), "ben": _login(app_module, "ben", "tech"),
            "vic": _login(app_module, "vic", "viewer")}


def _incident(client, seat, title="No internet"):
    resp = client.post("/api/incidents", json={"seat": seat, "title": title})
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()["id"]


def test_seat_points_follow_the_block_rotation(client, app_module):
    client.post("/api/seat-blocks", json={"name": "R", "x": 50, "y": 50, "cols": 2, "rows": 1, "rotation": 90})
    with app_module.app.app_context():
        from floorbit.store import load_data
        seats, _ = dispatch.points(load_data())
    # Turned a quarter: the two seats sit above each other instead of side by side.
    (_h1, x1, y1), (_h2, x2, y2) = seats["R-1"], seats["R-2"]
    assert abs(x1 - x2) < 0.01 and abs(abs(y1 - y2) - 32) < 0.01


def test_send_goes_to_the_nearest_free_tech(client, floor):
    assert floor["ana"].put("/api/jobs/me", json={"on_duty": True, "at": "a-1"}).get_json()["at"] == "A-1"
    assert floor["ben"].put("/api/jobs/me", json={"on_duty": True, "at": "B-1"}).status_code == 200
    near_b = _incident(client, "B-6")
    sent = client.post(f"/api/incidents/{near_b}/dispatch")
    assert sent.status_code == 200 and sent.get_json()["assignee"] == "ben"
    # Ben is busy now, so the next one goes to Ana even though it is next to Ben.
    second = _incident(client, "B-7", "Slow connection")
    assert client.post(f"/api/incidents/{second}/dispatch").get_json()["assignee"] == "ana"
    # Nobody left.
    third = _incident(client, "A-2", "Needs help")
    resp = client.post(f"/api/incidents/{third}/dispatch")
    assert resp.status_code == 409 and "No free tech" in resp.get_json()["error"]
    crew = {c["username"]: c for c in client.get("/api/dispatch/crew").get_json()["crew"]}
    assert crew["ben"]["jobs"] == 1 and crew["ana"]["at"] == "A-1"


def test_tech_takes_and_finishes_a_job_from_the_phone(client, floor):
    ben = floor["ben"]
    ben.put("/api/jobs/me", json={"on_duty": True, "at": "A-1"})
    job = _incident(client, "B-6")
    client.post(f"/api/incidents/{job}/dispatch")
    mine = ben.get("/api/jobs").get_json()
    assert [j["id"] for j in mine["jobs"]] == [job]
    first = mine["jobs"][0]
    assert first["drawing"]["shapes"] and first["target"] and first["from"]
    assert first["dispatched_at"] and first["taken_at"] is None
    assert "B-6" in mine["seats"] and mine["can_dispatch"] is False
    # Someone else can't answer for Ben.
    assert floor["ana"].post(f"/api/jobs/{job}/take").status_code == 403
    assert ben.post(f"/api/jobs/{job}/take").get_json()["taken_at"]
    assert ben.post(f"/api/jobs/{job}/done", json={"note": "Cable was loose"}).get_json()["status"] == "fixed"
    assert ben.get("/api/jobs").get_json()["jobs"] == []
    # He is now where the job was.
    assert ben.get("/api/jobs").get_json()["me"]["at"] == "B-6"
    notes = next(i for i in client.get("/api/incidents").get_json()["incidents"] if i["id"] == job)["notes"]
    assert notes[-1]["text"] == "Cable was loose" and notes[-1]["by"] == "ben"
    actions = [e["action"] for e in client.get("/api/settings/audit").get_json()["entries"]]
    assert {"Sent incident to the nearest tech", "Took job", "Finished job"} <= set(actions)


def test_give_back_puts_the_job_on_the_board(client, floor):
    floor["ana"].put("/api/jobs/me", json={"on_duty": True})
    job = _incident(client, "A-3")
    assert client.post(f"/api/incidents/{job}/dispatch").get_json()["assignee"] == "ana"
    assert floor["ana"].post(f"/api/jobs/{job}/give-back", json={"note": "Need a ladder"}).status_code == 200
    board = {i["id"]: i for i in client.get("/api/incidents").get_json()["incidents"]}
    assert board[job]["status"] == "open" and board[job]["assignee"] is None and board[job]["dispatched_at"] is None


def test_off_duty_and_rights(client, floor):
    floor["ana"].put("/api/jobs/me", json={"on_duty": True, "at": "A-1"})
    floor["ana"].put("/api/jobs/me", json={"on_duty": False})
    job = _incident(client, "A-2")
    assert client.post(f"/api/incidents/{job}/dispatch").status_code == 409
    assert floor["ana"].put("/api/jobs/me", json={"at": "Z-99"}).status_code == 400
    assert floor["ana"].put("/api/jobs/me", json={"at": ""}).get_json()["at"] is None
    # Techs can't send others; viewers have no jobs page at all.
    assert floor["ana"].post(f"/api/incidents/{job}/dispatch").status_code == 403
    assert floor["ana"].get("/api/dispatch/crew").status_code == 403
    assert floor["vic"].get("/api/jobs").status_code == 403
    assert floor["vic"].put("/api/jobs/me", json={"on_duty": True}).status_code == 403
