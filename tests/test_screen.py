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


def test_find_a_seat_by_number_without_an_account(anon_client, hall, app_module, monkeypatch):
    monkeypatch.setattr(app_module.app.extensions["auth"], "public_read", False)
    page = anon_client.get("/find").get_data(as_text=True)
    assert "Find your seat" in page and 'name="q"' in page
    resp = anon_client.get("/find?q=d-6")
    body = resp.get_data(as_text=True)
    assert resp.status_code == 200 and "Seat D-6" in body
    assert "Block D, row 2 of 2, seat 2 from the left" in body
    assert body.count('class="cell hit"') == 1 and "player-six" not in body


def test_unknown_seat(anon_client, hall):
    resp = anon_client.get("/find?q=Z-99")
    assert resp.status_code == 404 and "No seat" in resp.get_data(as_text=True)


def test_nicks_find_nothing_unless_switched_on(anon_client, hall, monkeypatch):
    assert anon_client.get("/find?q=player-six").status_code == 404
    monkeypatch.setenv("SEAT_FINDER_NICKS", "true")
    assert "Seat D-6" in anon_client.get("/find?q=PLAYER-SIX").get_data(as_text=True)
    assert anon_client.get("/find?q=player").status_code == 404   # only the exact nick


def test_finder_can_be_switched_off(anon_client, hall, monkeypatch):
    monkeypatch.setenv("SEAT_FINDER", "false")
    assert anon_client.get("/find?q=D-6").status_code == 404


def test_lookups_are_rate_limited(anon_client, hall):
    codes = [anon_client.get("/find?q=D-6").status_code for _ in range(screen.RATE_LIMIT + 1)]
    assert codes[-1] == 429 and set(codes[:-1]) == {200}


def test_german_for_german_browsers(anon_client, hall):
    page = anon_client.get("/find?q=D-6", headers={"Accept-Language": "de-CH,de;q=0.9"}).get_data(as_text=True)
    assert "Platz D-6" in page and 'lang="de"' in page


def test_screen_rotates_the_chosen_views_with_a_qr_code(client, hall):
    page = client.get("/screen?views=stats,heat,nonsense&every=5&theme=ops").get_data(as_text=True)
    assert 'data-src="/stats?screen=1&amp;theme=ops"' in page and 'data-src="/kiosk?view=heat&amp;theme=ops"' in page
    assert "nonsense" not in page and "SCREEN_EVERY = 10" in page   # at least 10 seconds
    assert 'class="qr"' in page and "data:image/svg+xml" in page and "/find" in page


def test_screen_without_qr_and_theme_injection(client, hall):
    page = client.get("/screen", query_string={"qr": "0", "theme": '"><script>'}).get_data(as_text=True)
    assert 'class="qr"' not in page and '"><script>' not in page and "?theme=" not in page
    assert 'data-src="/kiosk"' in page   # the default views


def test_screen_needs_floor_plan_access(anon_client, app_module, monkeypatch):
    monkeypatch.setattr(app_module.app.extensions["auth"], "public_read", False)
    assert anon_client.get("/screen").status_code in (302, 401)


def test_seat_traffic_for_the_heat_view(client, app_module):
    stats = app_module.app.extensions["floorbit_stats"]
    stats.reset()
    dev = {"id": "s1", "name": "sw-d-01"}
    stats.record([(dev, {"name": "Gi1/0/6", "state": "up", "download_bps": 5e6, "upload_bps": 1e6}, "D-6"),
                  (dev, {"name": "Gi1/0/7", "state": "down"}, "D-7")], ["sw-d-01"], now=1000)
    assert client.get("/api/stats/seats").get_json() == {"seats": {"D-6": 6_000_000}, "last_poll": 1000}
