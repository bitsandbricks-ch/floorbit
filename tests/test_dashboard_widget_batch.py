"""Several dashboard tiles in one request (issue #1300): each answers as if asked on its own."""
from urllib.parse import urlencode

from tests.test_dashboard_core import _login


def _batch(c, urls, **kw):
    return c.get("/api/dashboard/widgets?" + urlencode([("u", u) for u in urls]), **kw)


def test_each_tile_answers_as_on_its_own(client):
    urls = ["/api/dashboard/floorbit/problems", "/api/dashboard/floorbit/incidents", "/api/dashboard/floorbit/nope"]
    body = _batch(client, urls).get_json()
    alone = [client.get(u) for u in urls]
    assert [r["status"] for r in body["results"]] == [a.status_code for a in alone] == [200, 200, 404]
    assert body["results"][0]["body"]["type"] == alone[0].get_json()["type"] == "stat"
    assert body["results"][2]["body"] == {"error": "No such widget"}


def test_each_tile_keeps_its_own_permission_check(app_module, client):
    viewer = _login(app_module, "vic", "viewer")
    body = _batch(viewer, ["/api/dashboard/floorbit/problems", "/api/dashboard/floorbit/incidents"]).get_json()
    assert [r["status"] for r in body["results"]] == [200, 404]


def test_signed_out_gets_nothing(anon_client):
    assert _batch(anon_client, ["/api/dashboard/floorbit/problems"]).status_code == 401


def test_only_tile_addresses(client):
    urls = ["/api/settings", "https://example.com/api/dashboard/floorbit/problems",
            "/api/dashboard/floorbit/../../settings", "/api/plugins/demo/widgets/x/../../../settings"]
    body = _batch(client, urls).get_json()
    assert [r["status"] for r in body["results"]] == [400, 400, 400, 400]
    assert _batch(client, []).status_code == 400
    assert _batch(client, ["/api/dashboard/floorbit/problems"] * 65).status_code == 400


def test_query_and_language_reach_the_tile(client):
    body = _batch(client, ["/api/dashboard/floorbit/incidents"], headers={"Accept-Language": "de-CH"}).get_json()
    assert body["results"][0]["body"]["unit"] == "offen"
    err = _batch(client, ["/api/settings"], headers={"Accept-Language": "de-CH"}).get_json()
    assert err["results"][0]["body"]["error"] == "Keine Adresse einer Kachel."


def test_the_event_picked_for_a_tile_does_not_stay(client, app_module):
    from floorbit import store
    _batch(client, ["/api/dashboard/floorbit/problems", "/api/dashboard/floorbit/seats"])
    assert store._event_dir.get() is None


def test_tiles_of_a_batch_read_a_shared_source_once(client, monkeypatch):
    stats = client.application.extensions["floorbit_stats"]
    asked = []
    real = stats.snapshot

    def counting(*a, **kw):
        asked.append(1)
        return real(*a, **kw)
    monkeypatch.setattr(stats, "snapshot", counting)
    tiles = ["/api/dashboard/floorbit/" + t for t in ("bandwidth", "peak", "ports", "uplinks", "top_ports")]
    body = _batch(client, tiles).get_json()
    assert all(r["status"] == 200 for r in body["results"]), body
    assert len(asked) == 1
    asked.clear()
    for t in tiles:                                   # on their own, each reads it
        client.get(t)
    assert len(asked) == 5
