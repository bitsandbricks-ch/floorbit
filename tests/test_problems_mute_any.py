"""Mute for every kind of problem (issue #887): by its own id, with a time limit."""
import pytest

from floorbit import problems

pytestmark = pytest.mark.usefixtures("lan_here")


@pytest.fixture(autouse=True)
def port_trouble(monkeypatch):
    item = {"id": "attention:errors:x", "kind": "errors", "level": "warn", "title": "Errors rising on Gi1/0/9",
            "where": "sw-a-01 Gi1/0/9", "since": 1, "link": "/plan?switch=sw-a-01"}
    monkeypatch.setattr(problems, "_attention", lambda: [dict(item)])


def _body(client):
    client.put("/api/settings/plugins/demo", json={"enabled": True})
    return client.get("/api/problems").get_json()


def _one(body):
    """A problem with no mute of its own (not a switch, service or access point)."""
    every = body["problems"] + body["attention"]
    return next(p for p in every if str(p.get("mute_id", "")).startswith("problem:"))


def test_every_problem_can_be_muted(client):
    body = _body(client)
    assert all(p.get("mute_id") or p["kind"] == "switch" for p in body["problems"] + body["attention"])


def test_a_muted_problem_stays_listed_and_leaves_the_counts(client):
    body = _body(client)
    p = _one(body)
    r = client.post("/api/alerts/mutes", json={"problem_id": p["id"], "minutes": 30, "reason": "known"})
    assert r.status_code == 201, r.get_json()
    after = client.get("/api/problems").get_json()
    again = next(x for x in after["problems"] + after["attention"] if x["id"] == p["id"])
    assert again["muted"]["reason"] == "known"
    assert after["counts"]["total"] == body["counts"]["total"] - 1
    assert after["counts"]["muted"] == body["counts"]["muted"] + 1
    mute = next(m for m in after["mutes"] if m["switch_id"] == p["mute_id"])
    assert mute["kind"] == "problem"
    # Ending it brings the problem back into the counts.
    assert client.delete(f"/api/alerts/mutes/{p['mute_id']}").status_code == 200
    assert client.get("/api/problems").get_json()["counts"]["total"] == body["counts"]["total"]


def test_only_problems_on_the_list_can_be_muted(client):
    _body(client)
    r = client.post("/api/alerts/mutes", json={"problem_id": "nope", "minutes": 30})
    assert r.status_code == 400
    assert r.get_json()["error"] == "There is no such problem."
