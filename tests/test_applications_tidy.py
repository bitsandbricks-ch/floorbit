"""Around sharing (issue #1612): what a rule source's fetch changed, the busiest sites nothing names,
and an event's own additions that now ship anyway."""
import json

from floorbit import application_sources as sources
from floorbit import applications


def rules(*apps):
    return json.dumps({"version": 1, "applications": list(apps)}).encode()


ARENA = {"id": "example-arena", "name": "Example Arena", "kind": "game", "sites": ["arena.example.com"]}
OTHER = {"id": "example-other", "name": "Example Other", "kind": "game", "sites": ["other.example.org"]}


def add_source(client):
    body = {"name": "Ours", "url": "https://example.com/r.json"}
    return client.post("/api/applications/sources", json=body).get_json()


def test_a_fetch_says_what_it_changed(app_module, client):
    src = add_source(client)
    row = sources.sync(src["id"], now=1, fetch=lambda url: rules(ARENA, OTHER))
    assert row["last_change"]["added"] == {"count": 2, "names": ["Example Arena", "Example Other"]}
    changed = {**ARENA, "sites": ["arena.example.net"]}
    row = sources.sync(src["id"], now=2, fetch=lambda url: rules(changed))
    assert row["last_change"] == {"added": {"count": 0, "names": []},
                                  "changed": {"count": 1, "names": ["Example Arena"]},
                                  "removed": {"count": 1, "names": ["Example Other"]}}
    # The same file again changes nothing, so the last change stays.
    assert sources.sync(src["id"], now=3, fetch=lambda url: rules(changed))["last_change"] == row["last_change"]


def test_the_busiest_unnamed_sites(app_module):
    apps = applications.listing()
    sites = {"steampowered.com": [500, 40], "example.com": [90, 12], "example.org": [300, 12], "example.net": [5, 6]}
    got = applications.unrecognised(apps, sites, limit=2)
    assert got == [{"site": "example.org", "lookups": 300, "seats": 12},
                   {"site": "example.com", "lookups": 90, "seats": 12}]


def test_the_api_lists_them(app_module, client):
    assert client.get("/api/applications").get_json()["unrecognised"] == []


def test_an_addition_that_now_ships_is_redundant(app_module, client):
    client.put("/api/applications/steam", json={"sites": ["example.net"]})
    steam = {a["id"]: a for a in applications.listing()}["steam"]
    assert steam["redundant"] is False
    src = add_source(client)
    sources.sync(src["id"], now=1, fetch=lambda url: rules(
        {"id": "steam", "name": "Steam", "kind": "launcher", "sites": ["steampowered.com", "example.net"]}))
    steam = {a["id"]: a for a in applications.listing()}["steam"]
    assert steam["redundant"] is True and steam["added"]["sites"] == ["example.net"]
    # Hiding is a change of its own, never redundant.
    client.put("/api/applications/steam", json={"sites": ["example.net"], "hidden": True})
    assert {a["id"]: a for a in applications.listing()}["steam"]["redundant"] is False
