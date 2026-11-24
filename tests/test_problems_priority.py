"""Priorities, raising by hand, and the hall and tags of each problem (issue #1364)."""
import pytest

from floorbit import problems
from floorbit.store import load_data, save_data

pytestmark = pytest.mark.usefixtures("lan_here")


def _down(dev_id, name, since):
    return {"id": f"switch:{dev_id}", "kind": "switch", "level": "down", "title": f"{name} is offline",
            "where": name, "since": since, "link": "", "switch_id": dev_id, "mute_id": dev_id, "name": name,
            "muted": None}


@pytest.fixture(autouse=True)
def floor(monkeypatch, app_module):
    data = load_data()
    data["halls"] = [{"id": "h1", "name": "Hall 1", "background": None},
                     {"id": "h2", "name": "Hall 2", "background": None}]
    data["inventory"] = [
        {"id": "acc1", "name": "sw-a-01", "role": "access", "hall_id": "h1", "tags": ["row-a"]},
        {"id": "core1", "name": "core-01", "role": "core", "hall_id": "h2", "tags": ["stage", "core"]},
    ]
    data["seat_blocks"] = [{"id": "b1", "name": "B", "cols": 2, "rows": 1, "hall_id": "h2"}]
    save_data(data)
    # The access switch went down first: by age alone it would come first.
    monkeypatch.setattr(problems, "_switches",
                        lambda muted: [_down("acc1", "sw-a-01", 100), _down("core1", "core-01", 200)])
    monkeypatch.setattr(problems, "_reach", lambda items, data: None)
    port = {"id": "attention:errors:x", "kind": "errors", "level": "warn", "title": "Errors rising", "where": "B-1",
            "since": 1, "link": "", "seat": "B-1"}
    monkeypatch.setattr(problems, "_attention", lambda: [dict(port)])
    yield
    data = load_data()
    for key in ("halls", "inventory", "seat_blocks", problems.RAISED):
        data.pop(key, None)
    save_data(data)


def _get(client, pid):
    body = client.get("/api/problems").get_json()
    return body, next(p for p in body["problems"] + body["attention"] if p["id"] == pid)


def test_a_core_switch_down_ranks_above_an_access_switch(client):
    body, core = _get(client, "switch:core1")
    access = next(p for p in body["problems"] if p["id"] == "switch:acc1")
    assert (core["priority"], access["priority"]) == (1, 2)
    ids = [p["id"] for p in body["problems"]]
    assert ids.index("switch:core1") < ids.index("switch:acc1")


def test_hall_and_tags_come_from_the_switch_or_the_seat(client):
    body, core = _get(client, "switch:core1")
    assert core["hall"] == "Hall 2" and core["tags"] == ["stage", "core"]
    port = next(p for p in body["attention"] if p["id"] == "attention:errors:x")
    assert port["hall"] == "Hall 2" and port["priority"] == 3


def test_raise_by_hand_and_take_it_back(client):
    r = client.post("/api/alerts/raised", json={"problem_id": "switch:acc1"})
    assert r.status_code == 201, r.get_json()
    body, access = _get(client, "switch:acc1")
    assert access["priority"] == 1 and access["raised"]["by"]
    # Raised and older than the core switch's: now it comes first.
    assert body["problems"][0]["id"] == "switch:acc1"
    assert client.delete("/api/alerts/raised/switch:acc1").status_code == 200
    assert _get(client, "switch:acc1")[1]["priority"] == 2
    assert client.delete("/api/alerts/raised/switch:acc1").status_code == 404


def test_only_problems_on_the_list_can_be_raised(client):
    r = client.post("/api/alerts/raised", json={"problem_id": "nope"})
    assert r.status_code == 400


def test_viewers_cannot_raise(client, app_module):
    app_module.app.extensions["auth"].users.add("viewer1", "viewer-password-1", role="viewer")
    other = app_module.app.test_client()
    other.post("/login", data={"username": "viewer1", "password": "viewer-password-1"})
    assert other.post("/api/alerts/raised", json={"problem_id": "switch:acc1"}).status_code == 403
