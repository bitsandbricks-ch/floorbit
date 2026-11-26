"""Rule sources for the applications (issue #1503): fetched on a schedule, checked, the last good
copy kept, their order, and the freeze. Nothing here fetches for real: ``fetch`` is a stand-in."""
import json

import pytest

from floorbit import application_sources as sources
from floorbit import applications
from tests.test_ports import audit_lines, sign_in

GOOD = json.dumps({"version": 1, "applications": [
    {"id": "valorant", "name": "Valorant (synced)", "kind": "game", "part_of": "riot",
     "sites": ["valorant.example.net"], "ports": ["udp/7000-7500"]},
    {"id": "example-arena", "name": "Example Arena", "kind": "game", "sites": ["arena.example.com"]},
]}).encode()


def by_id(rows):
    return {r["id"]: r for r in rows}


def add(client, **body):
    body = {"name": "Ours", "url": "https://example.com/rules.json", **body}
    resp = client.post("/api/applications/sources", json=body)
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()


def test_a_good_file_adds_and_replaces_applications(app_module, client):
    src = add(client)
    row = sources.sync(src["id"], now=1000, fetch=lambda url: GOOD)
    assert row["ok"] is True and row["count"] == 2 and row["changed_at"] == 1000
    apps = by_id(applications.listing())
    assert apps["example-arena"]["kind"] == "game" and apps["example-arena"]["builtin"] is True
    # The source wins over the shipped entry, which keeps its LAN cache ids.
    assert apps["valorant"]["name"] == "Valorant (synced)" and apps["valorant"]["sites"] == ["example.net"]
    assert apps["valorant"]["source"] == f"source:{src['id']}"
    rules = {r["name"]: r for r in applications.flow_rules()}
    assert rules["Valorant (synced)"]["ports"] == ["udp/7000-7500"]
    # The event's own changes still come first, and hiding works on a synced one.
    client.put("/api/applications/example-arena", json={"sites": ["extra.example.org"]})
    assert by_id(applications.listing())["example-arena"]["sites"] == ["example.com", "example.org"]
    # The page lists the source by name, without its URL.
    answer = client.get("/api/applications").get_json()
    assert answer["synced"][0]["name"] == "Ours" and "url" not in answer["synced"][0]


@pytest.mark.parametrize("raw", [
    b"<html>not a list</html>{",
    b'{"version": 2, "applications": []}',
    json.dumps({"version": 1, "applications": [{"id": "Bad Id", "name": "X"}]}).encode(),
    json.dumps({"version": 1, "applications": [{"id": "x", "name": "X", "ports": ["udp/99999"]}]}).encode(),
    json.dumps({"version": 1, "applications": [{"id": "x", "name": "X", "kind": "virus"}]}).encode(),
    b"[1, 2, 3]",
])
def test_a_bad_file_is_kept_out_and_the_last_good_copy_stays(app_module, client, raw):
    src = add(client)
    sources.sync(src["id"], now=1000, fetch=lambda url: GOOD)
    row = sources.sync(src["id"], now=2000, fetch=lambda url: raw)
    assert row["ok"] is False and row["error"] and row["count"] == 2 and row["changed_at"] == 1000
    assert "example-arena" in by_id(applications.listing())


def test_a_fetch_that_fails_keeps_the_copy_and_says_why(app_module, client):
    src = add(client)
    sources.sync(src["id"], now=1000, fetch=lambda url: GOOD)

    def away(url):
        raise sources.SourceError("Could not fetch it: ConnectionError.")
    row = sources.sync(src["id"], now=2000, fetch=away)
    assert row["error"] == "Could not fetch it: ConnectionError." and row["count"] == 2


def test_a_plain_domain_list_is_one_site_group(app_module, client):
    src = add(client, name="Tournament CDN")
    text = (b"# cache-domains style\n*.cdn.example.com\nexample.org\n\n"
            b"domain:example.net @ads\nfull:www.example.info\ninclude:other\nregexp:^ad\n")
    row = sources.sync(src["id"], now=1000, fetch=lambda url: text)
    assert row["ok"] is True and row["count"] == 1
    group = by_id(applications.listing())[f"src-{src['id']}"]
    assert group["name"] == "Tournament CDN" and group["kind"] == "sitegroup"
    assert group["sites"] == ["example.com", "example.info", "example.net", "example.org"]


def test_the_higher_source_wins(app_module, client):
    low = add(client, name="Low")
    high = add(client, name="High")
    one = {"version": 1, "applications": [{"id": "example-arena", "name": "Arena", "kind": "game"}]}
    sources.sync(low["id"], now=1, fetch=lambda url: json.dumps(one).encode())
    one["applications"][0]["name"] = "Arena from High"
    sources.sync(high["id"], now=1, fetch=lambda url: json.dumps(one).encode())
    assert by_id(applications.listing())["example-arena"]["name"] == "Arena"           # first in the list wins
    assert client.put(f"/api/applications/sources/{high['id']}", json={"position": 0}).status_code == 200
    assert by_id(applications.listing())["example-arena"]["name"] == "Arena from High"
    # Switched off, a source counts for nothing; removed, its copy goes too.
    client.put(f"/api/applications/sources/{high['id']}", json={"on": False})
    assert by_id(applications.listing())["example-arena"]["name"] == "Arena"
    assert client.delete(f"/api/applications/sources/{low['id']}").status_code == 200
    assert "example-arena" not in by_id(applications.listing())


def test_the_schedule_and_the_freeze(app_module, client):
    src = add(client, every_hours=6)
    calls = []

    def fetch(url):
        calls.append(url)
        return GOOD
    assert sources.tick(now=1000, fetch=fetch) == [src["id"]]
    assert sources.tick(now=1000 + 3600, fetch=fetch) == []               # not due for six hours
    assert sources.tick(now=1000 + 6 * 3600, fetch=fetch) == [src["id"]]
    resp = client.put("/api/applications/sources-frozen", json={"frozen": True})
    assert resp.status_code == 200 and resp.get_json()["frozen"] is True
    assert sources.tick(now=1000 + 60 * 3600, fetch=fetch) == []
    assert client.post(f"/api/applications/sources/{src['id']}/sync").status_code == 409
    assert len(calls) == 2
    # A failed fetch is tried again sooner than the interval.
    client.put("/api/applications/sources-frozen", json={"frozen": False})

    def away(url):
        raise sources.SourceError("Could not fetch it: Timeout.")
    sources.tick(now=10**6, fetch=away)
    assert sources.tick(now=10**6 + sources.RETRY_AFTER, fetch=fetch) == [src["id"]]
    actions = [line["action"] for line in audit_lines() if line.get("area") == "applications"]
    assert actions == ["Added a rule source", "Froze the rule sources", "Unfroze the rule sources"]


@pytest.mark.parametrize("body", [
    {"name": "", "url": "https://example.com/x.json"},
    {"name": "X", "url": "http://example.com/x.json"},
    {"name": "X", "url": "https://user:pw@example.com/x.json"},
    {"name": "X", "url": "https://example.com/x.json", "every_hours": 0},
    {"name": "X", "url": "https://example.com/x.json", "every_hours": "24"},
])
def test_a_source_is_checked(app_module, client, body):
    assert client.post("/api/applications/sources", json=body).status_code == 400


def test_the_sources_are_for_admins(app_module, client):
    add(client)
    viewer = sign_in(app_module, "watcher", "viewer")
    assert viewer.get("/api/applications/sources").status_code == 403
    body = {"name": "X", "url": "https://example.com/x"}
    assert viewer.post("/api/applications/sources", json=body).status_code == 403
    assert viewer.put("/api/applications/sources-frozen", json={"frozen": True}).status_code == 403
    assert viewer.get("/api/applications").status_code == 200
