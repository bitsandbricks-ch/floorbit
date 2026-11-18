"""Big-screen rotation (issue #18). The "find your seat" page was removed."""
import pytest

from integrations import seat_sources


@pytest.fixture
def hall(client, monkeypatch):
    monkeypatch.setenv("SEAT_SOURCES", "manual")
    seat_sources.invalidate()
    client.post("/api/seat-blocks", json={"name": "D", "x": 40, "y": 50, "cols": 4, "rows": 2})
    seat_sources.invalidate()


def test_the_seat_finder_is_gone(client, hall):
    assert client.get("/api/seat-finder?q=D-6").status_code == 404


def test_screen_rotates_the_chosen_views(client, hall):
    # The page is React (BigScreen.test.tsx rotates through what this answers).
    assert client.get("/screen").status_code in (200, 503)
    body = client.get("/api/screen?views=stats,heat,nonsense&every=5&theme=ops&hall=h-2").get_json()
    assert body["views"] == [{"id": "stats", "url": "/stats?screen=1&theme=ops"},
                             {"id": "heat", "url": "/plan?screen=1&layers=marks%2Cstatus&hall=h-2&theme=ops"}]
    assert body["every"] == 10   # at least 10 seconds
    assert "qr" not in body


def test_screen_without_theme_injection(client, hall):
    body = client.get("/api/screen", query_string={"theme": '"><script>', "every": "x"}).get_json()
    assert body["every"] == 30
    assert [v["url"] for v in body["views"]] == ["/dashboards/kiosk", "/plan?screen=1&layers=marks%2Cstatus",
                                                  "/stats?screen=1"]   # the default views, no theme


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
    assert 'group' not in plan(data)[0]['shapes'][0]      # groups are plan groups (floorbit/plan_groups.py)


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
