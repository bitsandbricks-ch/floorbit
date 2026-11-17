"""Big-screen rotation and the "find your seat" page (issue #18)."""
import pytest

from floorbit.blueprints import screen
from integrations import seat_sources


@pytest.fixture
def hall(client, monkeypatch):
    monkeypatch.setenv("SEAT_SOURCES", "manual")
    seat_sources.invalidate()
    screen._lookups.clear()
    client.post("/api/seat-blocks", json={"name": "D", "x": 40, "y": 50, "cols": 4, "rows": 2})
    client.put("/api/seat-map/D-6", json={"ip": "198.51.100.7", "nick": "player-six"})
    seat_sources.invalidate()


def _find(client, q, **kw):
    return client.get("/api/seat-finder", query_string={"q": q}, **kw)


def test_find_a_seat_by_number_without_an_account(anon_client, hall, app_module, monkeypatch):
    monkeypatch.setattr(app_module.app.extensions["auth"], "public_read", False)
    assert anon_client.get("/find").status_code in (200, 503)   # React: PublicFind.tsx
    assert anon_client.get("/api/seat-finder").get_json() == {"nicks": False}
    resp = _find(anon_client, "d-6")
    body = resp.get_json()
    assert resp.status_code == 200 and body["found"] == {"seat": "D-6", "block": "D", "row": 2, "rows": 2, "col": 2,
                                                         "hall": ""}
    assert [c["seat"] for b in body["drawing"]["shapes"] for c in b["cells"] if c["hit"]] == ["D-6"]
    assert "player-six" not in resp.get_data(as_text=True)


def test_unknown_seat(anon_client, hall):
    resp = _find(anon_client, "Z-99")
    assert resp.status_code == 404 and resp.get_json()["code"] == "none"


@pytest.mark.parametrize("typed", ["d6", "D 6", " d-06 ", "d_6"])
def test_a_seat_is_found_as_people_type_it(anon_client, hall, typed):
    resp = _find(anon_client, typed)
    assert resp.status_code == 200 and resp.get_json()["found"]["seat"] == "D-6"


def test_nicks_find_nothing_unless_switched_on(anon_client, hall, monkeypatch):
    assert _find(anon_client, "player-six").status_code == 404
    monkeypatch.setenv("SEAT_FINDER_NICKS", "true")
    assert anon_client.get("/api/seat-finder").get_json() == {"nicks": True}
    assert _find(anon_client, "PLAYER-SIX").get_json()["found"]["seat"] == "D-6"
    assert _find(anon_client, "player").status_code == 404   # only the exact nick


def test_finder_can_be_switched_off(anon_client, hall, monkeypatch):
    monkeypatch.setenv("SEAT_FINDER", "false")
    assert anon_client.get("/find").status_code == 404
    resp = _find(anon_client, "D-6")
    assert resp.status_code == 404 and resp.get_json()["code"] == "off"


def test_lookups_are_rate_limited(anon_client, hall):
    codes = [_find(anon_client, "D-6").status_code for _ in range(screen.RATE_LIMIT + 1)]
    assert codes[-1] == 429 and set(codes[:-1]) == {200}


def test_lookups_count_each_client_behind_a_trusted_proxy(anon_client, hall, monkeypatch):
    monkeypatch.setenv("CHECKIN_TRUST_PROXY", "true")
    busy = {"X-Forwarded-For": "192.0.2.20"}
    codes = [_find(anon_client, "D-6", headers=busy).status_code for _ in range(screen.RATE_LIMIT + 1)]
    assert codes[-1] == 429
    assert _find(anon_client, "D-6", headers={"X-Forwarded-For": "192.0.2.21"}).status_code == 200


def test_screen_rotates_the_chosen_views_with_a_qr_code(client, hall):
    # The page is React (BigScreen.test.tsx rotates through what this answers).
    assert client.get("/screen").status_code in (200, 503)
    body = client.get("/api/screen?views=stats,heat,nonsense&every=5&theme=ops&hall=h-2").get_json()
    assert body["views"] == [{"id": "stats", "url": "/stats?screen=1&theme=ops"},
                             {"id": "heat", "url": "/plan?screen=1&layers=marks%2Cstatus&hall=h-2&theme=ops"}]
    assert body["every"] == 10   # at least 10 seconds
    assert body["qr"]["image"].startswith("data:image/svg+xml") and body["qr"]["url"].endswith("/find")


def test_screen_without_qr_and_theme_injection(client, hall):
    body = client.get("/api/screen", query_string={"qr": "0", "theme": '"><script>', "every": "x"}).get_json()
    assert body["qr"] is None and body["every"] == 30
    assert [v["url"] for v in body["views"]] == ["/dashboards/kiosk", "/plan?screen=1&layers=marks%2Cstatus",
                                                  "/stats?screen=1"]   # the default views, no theme


def test_screen_has_no_qr_code_while_the_finder_is_off(client, hall, monkeypatch):
    monkeypatch.setenv("SEAT_FINDER", "false")
    assert client.get("/api/screen").get_json()["qr"] is None


def test_screen_needs_floor_plan_access(anon_client, app_module, monkeypatch):
    monkeypatch.setattr(app_module.app.extensions["auth"], "public_read", False)
    assert anon_client.get("/screen").status_code in (302, 401)
    assert anon_client.get("/api/screen").status_code == 401


def test_seat_traffic_for_the_heat_view(client, app_module):
    stats = app_module.app.extensions["floorbit_stats"]
    stats.reset()
    dev = {"id": "s1", "name": "sw-d-01"}
    stats.record([(dev, {"name": "Gi1/0/6", "state": "up", "download_bps": 5e6, "upload_bps": 1e6}, "D-6"),
                  (dev, {"name": "Gi1/0/7", "state": "down"}, "D-7")], ["sw-d-01"], now=1000)
    assert client.get("/api/stats/seats").get_json() == {"seats": {"D-6": 6_000_000}, "last_poll": 1000}


def test_plan_shapes_name_their_block():
    """The React editor selects blocks by id."""
    from floorbit.blueprints.screen import plan
    data = {'seat_blocks': [{'id': 'b1', 'name': 'A', 'x': 30, 'y': 30, 'cols': 2, 'rows': 1}]}
    assert plan(data)[0]['shapes'][0]['id'] == 'b1'
    data['seat_blocks'][0]['group'] = 'g-1'
    assert plan(data)[0]['shapes'][0]['group'] == 'g-1'


def test_plan_box_takes_in_every_block():
    """The fit box covers all blocks of the hall, not only the last one, and not the origin."""
    from floorbit.blueprints.screen import CELL, PLAN_H, PLAN_W, plan
    data = {'seat_blocks': [
        {'id': 'b', 'name': 'B', 'x': 80, 'y': 80, 'cols': 4, 'rows': 1},
        {'id': 'a', 'name': 'A', 'x': 30, 'y': 30, 'cols': 4, 'rows': 1},
    ]}
    x, y, w, h = map(float, plan(data)[0]['box'].split())
    assert x > 0 and y > 0
    assert x <= 0.3 * PLAN_W - 2 * CELL and x + w >= 0.8 * PLAN_W + 2 * CELL
    assert y <= 0.3 * PLAN_H - 2 * CELL and y + h >= 0.8 * PLAN_H + CELL
