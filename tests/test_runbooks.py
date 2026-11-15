"""Runbooks for incident types (issue #102)."""
import pytest

from floorbit import runbooks


def _login(app_module, name, role):
    app_module.app.extensions["auth"].users.add(name, f"{name}-password-1", role=role)
    c = app_module.app.test_client()
    assert c.post("/login", data={"username": name, "password": f"{name}-password-1"}).status_code == 302
    return c


@pytest.fixture
def floor(client, app_module):
    client.post("/api/seat-blocks", json={"name": "A", "x": 10, "y": 50, "cols": 4, "rows": 2})
    return {"ana": _login(app_module, "ana", "tech"), "vic": _login(app_module, "vic", "viewer")}


def test_starters_until_the_crew_saves_one(client):
    books = client.get("/api/runbooks").get_json()["runbooks"]
    assert [b["kinds"] for b in books] == [["no-internet"], ["slow"], ["power"], ["switch-down"]]
    assert all(b["starter"] for b in books)


def test_kind_of_an_incident():
    assert runbooks.kind_of({"problem": "slow", "seat": "A-1"}) == "slow"
    assert runbooks.kind_of({"circuit_id": "c1"}) == "power"
    assert runbooks.kind_of({"switch_id": "s1"}) == "switch-down"
    assert runbooks.kind_of({"seat": "A-1", "switch_id": "s1"}) == "other"


def test_crud_and_order(client):
    r = client.post("/api/runbooks", json={"title": "Seat checklist", "kinds": ["no-internet", "other"],
                                           "body": "1. Check the cable"})
    assert r.status_code == 201
    book = r.get_json()
    assert client.post("/api/runbooks", json={"title": "x", "body": "y", "kinds": ["bogus"]}).status_code == 400
    assert client.post("/api/runbooks", json={"title": "", "body": "y"}).status_code == 400
    books = client.get("/api/runbooks").get_json()["runbooks"]
    assert len(books) == 5 and books[-1]["id"] == book["id"]
    # The first for a kind wins: move ours above the starter for no internet.
    for _ in range(4):
        assert client.post(f"/api/runbooks/{book['id']}/move", json={"step": -1}).status_code == 200
    assert client.get("/api/runbooks").get_json()["runbooks"][0]["id"] == book["id"]
    r = client.patch(f"/api/runbooks/{book['id']}", json={"body": "1. Swap the cable"})
    assert r.get_json()["body"] == "1. Swap the cable" and r.get_json()["title"] == "Seat checklist"
    assert client.delete(f"/api/runbooks/{book['id']}").status_code == 200
    assert client.delete(f"/api/runbooks/{book['id']}").status_code == 404


def test_incident_and_job_link_the_runbook(client, floor):
    inc = client.post("/api/incidents", json={"seat": "A-1", "title": "Slow", "problem": "slow"}).get_json()
    board = client.get("/api/incidents").get_json()["incidents"]
    assert next(i for i in board if i["id"] == inc["id"])["runbook"]["title"] == "Slow connection"
    floor["ana"].put("/api/jobs/me", json={"on_duty": True, "at": "A-2"})
    assert client.post(f"/api/incidents/{inc['id']}/dispatch").get_json()["assignee"] == "ana"
    job = floor["ana"].get("/api/jobs").get_json()["jobs"][0]
    assert job["runbook"]["title"] == "Slow connection" and "speed test" in job["runbook"]["body"]


def test_incident_without_a_runbook(client, floor):
    inc = client.post("/api/incidents", json={"seat": "A-1", "title": "Odd"})
    assert inc.status_code == 201
    assert client.get("/api/incidents").get_json()["incidents"][0]["runbook"] is None


def test_roles(floor):
    assert floor["ana"].get("/api/runbooks").status_code == 200
    assert floor["ana"].post("/api/runbooks", json={"title": "x", "body": "y"}).status_code == 403
    assert floor["vic"].get("/api/runbooks").status_code == 403
