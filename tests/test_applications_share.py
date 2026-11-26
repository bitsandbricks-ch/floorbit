"""Sharing applications between events (issue #1612): another Floorbit's export comes in as the
event's own applications, keeping ids, and adds to built-in ones what they don't have yet."""
import json

from floorbit import applications
from tests.test_ports import audit_lines, sign_in


def by_id(rows):
    return {r["id"]: r for r in rows}


def export(*apps):
    return json.dumps({"version": 1, "applications": list(apps)})


def test_an_export_comes_in_with_its_ids(app_module, client):
    raw = export(
        {"id": "example-arena", "name": "Example Arena", "kind": "game", "part_of": "steam",
         "sites": ["arena.example.com"], "ports": ["udp/7777"]},
        {"id": "steam", "name": "Steam", "kind": "launcher", "sites": ["steampowered.com", "example.net"]},
    )
    resp = client.post("/api/applications/import", json={"file": raw})
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json() == {"added": 1, "changed": 1}
    apps = by_id(applications.listing())
    arena = apps["example-arena"]
    assert arena["builtin"] is False and arena["part_of"] == "steam" and arena["sites"] == ["example.com"]
    # The built-in Steam keeps what it shipped and gets only what it lacked.
    assert apps["steam"]["added"]["sites"] == ["example.net"]
    # Importing the same file again changes nothing and adds nothing new.
    assert client.post("/api/applications/import", json={"file": raw}).get_json() == {"added": 0, "changed": 2}
    assert len([a for a in applications.listing() if a["id"].startswith("example-arena")]) == 1
    actions = [line["action"] for line in audit_lines() if line.get("area") == "applications"]
    assert actions[-1] == "Imported applications"


def test_a_bad_export_is_refused_and_says_why(app_module, client):
    for body, status in [({}, 400), ({"file": "not json"}, 400), ({"file": "[1]"}, 400),
                         ({"file": export({"id": "x", "name": "X", "ports": ["udp/99999"]})}, 400)]:
        assert client.post("/api/applications/import", json=body).status_code == status
    # A name another application already has stops there, saying how many came in before.
    raw = export({"id": "ok-one", "name": "Ok One"}, {"id": "dupe", "name": "Steam"})
    resp = client.post("/api/applications/import", json={"file": raw})
    assert resp.status_code == 400 and "(1 taken before it.)" in resp.get_json()["error"]
    assert "ok-one" in by_id(applications.listing())


def test_importing_is_for_admins(app_module, client):
    viewer = sign_in(app_module, "watcher", "viewer")
    assert viewer.post("/api/applications/import", json={"file": export()}).status_code == 403
