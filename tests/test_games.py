"""Game and launcher insights (issue #88): launchers from DNS, traffic and the LAN cache's log."""
import os

import pytest

from floorbit import dns, games, lancache

HOUR = 1_794_650_400   # 2026-11-14 10:00 UTC, on the hour


def line(cache, size, result="HIT", status=200, when="14/Nov/2026:10:05:00 +0000", client="192.0.2.10"):
    return (f'[{cache}] {client} / - - - [{when}] "GET /depot/1/chunk/abc HTTP/1.1" {status} {size} "-" '
            f'"Valve/Steam HTTP Client 1.0" "{result}" "lancache.steamcontent.com" "-"')


@pytest.fixture
def cache(tmp_path):
    return lancache.LancacheStats(path=str(tmp_path / "lancache.json"))


def test_parse_reads_the_lancache_log_format():
    assert lancache.parse(line("steam", 1000)) == (HOUR, "steam", 1000, True)
    assert lancache.parse(line("blizzard", 500, "MISS", when="14/Nov/2026:11:05:00 +0100")) == \
        (HOUR, "blizzard", 500, False)
    assert lancache.parse(line("steam", 10, status=404)) is None
    assert lancache.parse(line("steam", "-")) is None
    assert lancache.parse("garbage") is None


def test_counts_per_hour_and_cache_without_clients(cache, tmp_path):
    cache.add_lines([line("steam", 800), line("steam", 200, "MISS"), line("riot", 50, "EXPIRED"),
                     line("steam", 100, "STALE", client="192.0.2.99")], now=HOUR + 600)
    snap = cache.snapshot(hours=1, now=HOUR + 600)
    assert snap["hit_bytes"] == 900 and snap["miss_bytes"] == 250 and snap["hit_ratio"] == round(900 / 1150, 4)
    assert snap["caches"][0] == {"cache": "steam", "hit_bytes": 900, "miss_bytes": 200, "requests": 3}
    cache._save()
    assert "192.0.2" not in (tmp_path / "lancache.json").read_text()


def test_reads_only_what_the_log_gained_and_follows_a_rotation(cache, tmp_path, monkeypatch):
    log = tmp_path / "access.log"
    monkeypatch.setenv("LANCACHE_LOG", str(log))
    log.write_text(line("steam", 100) + "\n" + line("steam", 200) + "\n" + line("steam", 7)[:40])
    cache.read_log(now=HOUR + 600)
    assert cache.snapshot(hours=1, now=HOUR + 600)["hit_bytes"] == 300
    with open(log, "a") as f:            # the half line is finished, and one more follows
        f.write(line("steam", 7)[40:] + "\n" + line("steam", 1000, "MISS") + "\n")
    cache.read_log(now=HOUR + 600)
    snap = cache.snapshot(hours=1, now=HOUR + 600)
    assert snap["hit_bytes"] == 307 and snap["miss_bytes"] == 1000
    # A new process carries on where this one stopped.
    again = lancache.LancacheStats(path=str(tmp_path / "lancache.json"))
    again.read_log(now=HOUR + 600)
    assert again.snapshot(hours=1, now=HOUR + 600)["hit_bytes"] == 307
    # Rotated: a new file is read from the top.
    os.rename(log, tmp_path / "access.log.1")
    log.write_text(line("riot", 5) + "\n")
    again.read_log(now=HOUR + 600)
    assert again.snapshot(hours=1, now=HOUR + 600)["hit_bytes"] == 312


def test_a_missing_log_is_explained(cache, monkeypatch, tmp_path):
    monkeypatch.setenv("LANCACHE_LOG", str(tmp_path / "nope.log"))
    cache.read_log()
    assert "Can't read" in cache.snapshot()["error"]


def test_the_demo_cache_serves_the_demo_hall(cache):
    cache.start_demo(now=HOUR)
    snap = cache.snapshot(hours=24, now=HOUR)
    assert snap["demo"] and 0.5 < snap["hit_ratio"] < 0.9
    assert {c["cache"] for c in snap["caches"]} >= {"steam", "blizzard", "riot"}


def test_insights_join_dns_traffic_and_the_cache(cache, tmp_path):
    stats = dns.DnsStats(path=str(tmp_path / "dns.json"))
    stats.add([{"ts": HOUR + 60 + i, "domain": "cdn.steamcontent.com", "client": f"198.51.100.{i}"} for i in range(6)]
              + [{"ts": HOUR + 60, "domain": "eu.battle.net", "client": "198.51.100.1"}], now=HOUR + 600)
    cache.add_lines([line("steam", 900), line("steam", 100, "MISS"), line("wsus", 400)], now=HOUR + 600)
    flows = {"min_seats": 5, "services": [
        {"name": "Steam", "category": "gaming", "bytes": 5000, "seats": 30},
        {"name": "Tournament servers", "category": "gaming", "bytes": 2000, "seats": 12},
        {"name": "Web", "category": "web", "bytes": 9000, "seats": 80}]}
    out = games.insights(stats, flows, cache, hours=1, now=HOUR + 600)
    steam = out["launchers"][0]
    assert steam == {"id": "steam", "name": "Steam", "lookups": 6, "dns_seats_max": 6, "traffic_bytes": 5000,
                     "traffic_seats": 30, "cache_hit_bytes": 900, "cache_miss_bytes": 100}
    assert [r["id"] for r in out["launchers"]] == ["steam"]       # one seat's Battle.net lookup isn't named
    assert out["games"] == [{"name": "Tournament servers", "bytes": 2000, "seats": 12}]
    assert [c["cache"] for c in out["other_caches"]] == ["wsus"]
    assert out["sources"] == {"dns": True, "traffic": True, "cache": True}


def test_api(client, app_module):
    app_module.app.extensions["floorbit_lancache"].stop()
    body = client.get("/api/games?hours=6").get_json()
    assert len(body["cache"]["hours"]) == 6 and "launchers" in body
    assert client.get("/api/games?hours=200").status_code == 400
    assert client.get("/games").status_code in (200, 503)   # 503 only when the React app isn't built
    client.put("/api/settings/features", json={"games": False})
    assert client.get("/api/games").status_code == 404
    client.put("/api/settings/features", json={"games": True})
