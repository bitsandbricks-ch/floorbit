"""Groups of any items on the floor plan (floorbit/plan_groups.py)."""
import pytest

from floorbit.store import load_data


def members(*ids):
    return [{"kind": k, "id": i} for k, i in ids]


def post(client, **body):
    return client.post("/api/plan-groups", json=body)


def test_groups_are_made_changed_and_removed(client):
    made = post(client, name=" Stage ", members=members(("mark", "m1"), ("switch", "sw1"), ("mark", "m1")))
    assert made.status_code == 201
    group = made.get_json()
    assert group["name"] == "Stage" and group["hall_id"] and len(group["members"]) == 2
    renamed = client.put(f"/api/plan-groups/{group['id']}", json={"name": "Front"}).get_json()
    assert renamed["name"] == "Front" and renamed["members"] == group["members"]
    listed = client.get(f"/api/plan-groups?hall={group['hall_id']}").get_json()["groups"]
    assert [g["id"] for g in listed] == [group["id"]]
    assert client.get("/api/plan-groups?hall=elsewhere").get_json()["groups"] == []
    assert client.delete(f"/api/plan-groups/{group['id']}").status_code == 200
    assert client.delete(f"/api/plan-groups/{group['id']}").status_code == 404


def test_an_item_is_in_one_group(client):
    first = client.post("/api/plan-groups", json={"members": members(("mark", "a"), ("mark", "b"))}).get_json()
    other = post(client, members=members(("mark", "c"), ("block", "d"), ("board", "e"))).get_json()
    client.post("/api/plan-groups", json={"members": members(("mark", "b"), ("block", "d"))})
    groups = {g["id"]: g for g in load_data()["plan_groups"]}
    assert first["id"] not in groups   # left with one item, it went
    assert groups[other["id"]]["members"] == members(("mark", "c"), ("board", "e"))


def test_undo_can_bring_a_group_back_with_its_id(client):
    group = post(client, id="g-keep", members=members(("mark", "a"), ("mark", "b"))).get_json()
    assert group["id"] == "g-keep"
    again = post(client, id="g-keep", members=members(("mark", "x"), ("mark", "y"))).get_json()
    assert again["id"] != "g-keep"


def test_a_halls_groups_are_set_at_once(client):
    client.post("/api/plan-groups", json={"id": "old", "members": members(("mark", "a"), ("mark", "b"))})
    body = {"groups": [{"id": "g1", "name": "One", "members": members(("mark", "a"), ("switch", "s"))},
                       {"id": "g2", "members": members(("block", "b"), ("panel", "PP-1"))}]}
    out = client.put("/api/plan-groups", json=body).get_json()["groups"]
    assert [(g["id"], g["name"]) for g in out] == [("g1", "One"), ("g2", "")]
    assert client.put("/api/plan-groups", json={"groups": []}).get_json()["groups"] == []
    assert client.put("/api/plan-groups", json={"groups": "x"}).status_code == 400


@pytest.mark.parametrize("bad", [
    {"members": members(("mark", "a"))},
    {"members": members(("cable", "a"), ("mark", "b"))},
    {"members": "a,b"},
    {"members": members(("mark", "a"), ("mark", "b")), "name": "x" * 41},
    {"members": members(("mark", "a"), ("mark", "b")), "hall_id": "nowhere"},
])
def test_bad_groups_are_refused(client, bad):
    assert client.post("/api/plan-groups", json=bad).status_code == 400


def test_only_editors_group(app_module, client):
    from tests.test_rbac import sign_in_as
    viewer = sign_in_as(app_module, "vg9", "viewer")
    assert viewer.get("/api/plan-groups").status_code == 200
    assert viewer.post("/api/plan-groups", json={"members": members(("mark", "a"), ("mark", "b"))}).status_code == 403
