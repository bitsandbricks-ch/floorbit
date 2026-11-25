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


def _title(name, seats=0, hit=None, miss=None, part_of=None, **seen):
    return {'id': name.lower(), 'name': name, 'part_of': part_of, 'seats': seats, 'cache_hit_bytes': hit,
            'cache_miss_bytes': miss, 'dns_seats_max': None, 'traffic_seats': None, 'players': None, **seen}


def test_top_games_are_titles_by_seats():
    insights = {'titles': [_title('Valorant', 61, dns_seats_max=61, traffic_seats=40),
                           _title('Counter-Strike 2', 142, traffic_seats=142, players=30),
                           _title('Baldur\'s Gate 3', 0, hit=500)]}
    assert stats_wall.top_games(insights) == [
        {'name': 'Counter-Strike 2', 'bar': 1.0, 'seats': 142, 'via': ['traffic', 'servers']},
        {'name': 'Valorant', 'bar': 0.43, 'seats': 61, 'via': ['dns', 'traffic']}]


def test_downloads_by_title_then_what_is_left_of_the_launcher():
    insights = {'titles': [_title('Counter-Strike 2', 0, hit=900, miss=300, part_of='steam')],
                'launchers': [{'id': 'steam', 'name': 'Steam', 'cache_hit_bytes': 1800, 'cache_miss_bytes': 600},
                              {'id': 'epic', 'name': 'Epic Games', 'cache_hit_bytes': None, 'cache_miss_bytes': None}],
                'sitegroups': [{'id': 'wsus', 'name': 'Windows updates', 'cache_hit_bytes': 400,
                                'cache_miss_bytes': 0}]}
    assert stats_wall.top_downloads(insights) == [
        {'name': 'Counter-Strike 2', 'bar': 1.0, 'bytes': 1200}, {'name': 'Steam', 'bar': 1.0, 'bytes': 1200},
        {'name': 'Windows updates', 'bar': 0.333, 'bytes': 400}]


def test_top_sites_only_name_sites_of_a_known_application():
    insights = {'sites': [{'site': 'discord.com', 'lookups': 900, 'seats': 412, 'application': 'Voice and chat',
                           'category': 'social'},
                          {'site': 'example.com', 'lookups': 800, 'seats': 300, 'application': None, 'category': None},
                          {'site': 'twitch.tv', 'lookups': 400, 'seats': 201, 'application': 'Streaming',
                           'category': 'streaming'}]}
    assert stats_wall.top_sites(insights) == [
        {'name': 'discord.com', 'bar': 1.0, 'seats': 412, 'category': 'social'},
        {'name': 'twitch.tv', 'bar': 0.488, 'seats': 201, 'category': 'streaming'}]


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
    # The app-wide DNS counts outlive a test: an earlier test's demo lookups made the "empty" wall
    # show Steam and Battle.net on Postgres (issue #508).
    dns = app_module.app.extensions.get("floorbit_dns")
    if dns is not None:
        with dns._lock:
            dns.hours.clear()
            dns.current = None
    return stats


def test_off_by_default(anon_client, hall):
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
    # The widget is React (EventNumbersView draws it from this JSON).
    for private in ("sw-a-01", "Gi1/0", "A-1"):
        assert private not in str(body)


def test_an_empty_event_says_so(client, anon_client, hall):
    client.put("/api/settings", json={"public.stats_wall": True})
    body = anon_client.get("/wall.json").get_json()
    # What EventNumbersView.tsx reads as "nothing to show yet". On failure, show which fact was not
    # empty: it failed once on Postgres (issue #508).
    assert not (body["online"] or body["downloaded"] or body["peak"] or body["games"]), body
