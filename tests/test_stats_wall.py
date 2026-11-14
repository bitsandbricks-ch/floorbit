"""Public stats wall (issue #105): fun facts, hall-wide and per seat block only."""
import time

import pytest

from floorbit import recording, stats_wall
from floorbit.store import load_data

HOUR = 3600


def _frame(t, down, blocks):
    return {'t': t, 'down': down, 'up': 0, 'online': sum(b[1] for b in blocks.values()), 'seats': ['A-1'],
            'incidents': [], 'blocks': blocks}


def test_downloaded_from_the_recording_and_without_made_up_gaps():
    frames = [_frame(0, 8_000, {}), _frame(300, 16_000, {}), _frame(300 + 5 * HOUR, 0, {})]
    # 300 s at 8 kbit/s, then the app was off for 5 hours: count one hour at most
    assert stats_wall.downloaded(frames, []) == 300 * 1000 + HOUR * 2000
    assert stats_wall.downloaded([], [{'t': 0, 'avg_bps': 8_000, 'online_max': 1, 'peak_bps': 1}]) == HOUR * 1000


def test_loyal_block_names_only_blocks_of_five_or_more():
    frames = [
        _frame(0, 0, {'A': [10, 5, 0, 0], 'B': [10, 9, 0, 0], 'TINY': [2, 2, 0, 0]}),
        _frame(HOUR, 0, {'A': [10, 10, 0, 0], 'B': [10, 8, 0, 0], 'TINY': [2, 2, 0, 0]}),
        _frame(2 * HOUR, 0, {}),
    ]
    best = stats_wall.loyal_block(frames)
    assert best == {'name': 'B', 'hours': 1.7, 'share': 0.85}
    assert stats_wall.loyal_block(frames[:1]) is None


def test_top_games_are_names_with_a_bar():
    insights = {'launchers': [
        {'name': 'Steam', 'cache_hit_bytes': 800, 'cache_miss_bytes': 200, 'traffic_bytes': 5, 'lookups': 9},
        {'name': 'Riot Games', 'cache_hit_bytes': None, 'cache_miss_bytes': None, 'traffic_bytes': 250, 'lookups': 3},
        {'name': 'EA app', 'cache_hit_bytes': None, 'cache_miss_bytes': None, 'traffic_bytes': None, 'lookups': 0},
    ], 'games': [{'name': 'Tournament servers', 'bytes': 500, 'seats': 40}]}
    assert stats_wall.top_games(insights) == [
        {'name': 'Steam', 'bar': 1.0}, {'name': 'Tournament servers', 'bar': 0.5}, {'name': 'Riot Games', 'bar': 0.25}]


def test_units_by_language():
    assert stats_wall.size(1_530_000_000_000) == '1.5 TB'
    assert stats_wall.size(1_530_000_000_000, 'de') == '1,5 TB'
    assert stats_wall.rate(3_200_000_000) == '3.2 Gbit/s'
    assert stats_wall.size(0) == '0 B'


@pytest.fixture
def hall(client, app_module):
    client.post("/api/seat-blocks", json={"name": "A", "x": 40, "y": 50, "cols": 5, "rows": 2})
    stats = app_module.app.extensions["floorbit_stats"]
    stats.reset()
    return stats


def test_off_by_default(anon_client, hall):
    assert anon_client.get("/wall").status_code == 404
    assert anon_client.get("/wall.json").status_code == 404


def test_the_wall_shows_numbers_and_no_people(client, anon_client, hall):
    assert client.put("/api/settings", json={"public.stats_wall": True}).status_code == 200
    now = time.time()
    dev = {"id": "s1", "name": "sw-a-01"}
    ports = [(dev, {"name": f"Gi1/0/{n}", "state": "up", "download_bps": 4e8, "upload_bps": 1e8,
                    "description": f"Seat A-{n}"}, f"A-{n}") for n in range(1, 7)]
    hall.record(ports, ["sw-a-01"], now=now - 600)
    hall.record(ports, ["sw-a-01"], now=now - 10)
    data = load_data()
    seat_bps = {f"A-{n}": 5e8 for n in range(1, 7)}
    recording.capture({'t': now - 600, 'down': 2.4e9, 'up': 6e8, 'online': 6}, seat_bps, set(), data)
    recording.capture({'t': now - 10, 'down': 2.4e9, 'up': 6e8, 'online': 6}, seat_bps, set(), data)
    body = anon_client.get("/wall.json").get_json()
    assert body["online"] == 6 and body["seats"] == 10
    assert body["downloaded"] == round(2.4e9 * 590 / 8)
    assert body["loyal_block"]["name"] == "A" and body["loyal_block"]["share"] == 0.6
    assert body["peak"]["bps"] >= 3e9
    page = anon_client.get("/wall")
    assert page.status_code == 200
    text = page.get_data(as_text=True)
    assert "Seats online now" in text and "Most loyal seat block" in text
    for private in ("sw-a-01", "Gi1/0", "A-1"):
        assert private not in text and private not in str(body)
    de = anon_client.get("/wall?screen=1", headers={"Accept-Language": "de-CH,de"}).get_data(as_text=True)
    assert "Plätze jetzt online" in de and 'class="screen"' in de


def test_an_empty_event_says_so(client, anon_client, hall):
    client.put("/api/settings", json={"public.stats_wall": True})
    assert "Nothing to show yet" in anon_client.get("/wall").get_data(as_text=True)
