"""The LAN cache page on the hosted side (docs/lancache.md). The plugin itself, which reads the cache
in the hall and hands its counts to the core, lives in bitsandbricks-ch/floorbit-plugin-lancache and
is tested there; here the core is fed what an agent sends and the page reads it back."""
import time

import pytest

AGENT = {"id": "agent-1", "name": "Hall A agent"}
ODD = [None, 5, "x", [], {}, [1], {"a": 1}, True, -1, 10 ** 30, "9" * 400]


def _hour():
    return str(int(time.time() // 3600 * 3600))


def _payload():
    hour = _hour()
    return {"hours": {hour: {"steam": [6000, 1000, 8], "blizzard": [0, 600, 3]}}, "lines": 12,
            "min_clients": 5, "window_hours": 24,
            "downloads": [{"cache": "steam", "item": "depot 228988", "hit_bytes": 6000, "miss_bytes": 0,
                           "requests": 6, "clients": 6}],
            "other_downloads": {"hit_bytes": 0, "miss_bytes": 1000, "requests": 2, "items": 1},
            "suspects": [{"cache": "blizzard", "item": "tpr/wow", "files": 1, "misses": 3}],
            "dns": {"services": {"steam": 4}, "hours": {}}, "clients": {hour: 7}}


STATUS = {"at": 1, "disk": {"used": 800, "total": 1000, "free": 200},
          "heartbeat": {"ok": True, "ms": 3, "processed_by": "cache-01"},
          "dns_check": {"ok": True}, "clearing": {"running": False, "removed": 3, "finished": 5}}


@pytest.fixture
def stats(app_module):
    stats = app_module.app.extensions["floorbit_lancache"]
    kept = dict(stats.hours)
    yield stats
    # The app outlives this test: leave the cache numbers as they were.
    stats.remote.clear()
    stats.hours.clear()
    stats.hours.update(kept)


def test_the_page_shows_what_the_agents_counted(client, stats):
    stats.merge_agent(AGENT, _payload())
    stats.merge_status(AGENT, {**STATUS, "at": time.time()})
    page = client.get("/api/lancache").get_json()
    assert page["configured"] and page["plugin_on"] is False      # not installed in the tests
    assert page["downloads"][0]["item"] == "depot 228988" and page["downloads"][0]["hit_ratio"] == 1.0
    assert page["agents"][0]["name"] == "Hall A agent" and page["agents"][0]["heartbeat"]["ok"]
    assert page["agents"][0]["disk"]["used"] == 800 and page["suspects"][0]["item"] == "tpr/wow"
    assert any(row["cache"] == "steam" for row in page["caches"])
    assert page["dns_services"] == [{"cache": "steam", "lookups": 4}]


def test_odd_agent_payloads_never_break_the_page(client, stats):
    # Another plugin version, or a broken one: whatever it sends, the page still answers.
    good = _payload()
    for field in good:
        for odd in ODD + [[odd] for odd in ODD] + [{_hour(): odd} for odd in ODD]:
            stats.merge_agent(AGENT, {**good, field: odd})
            for name in STATUS:
                stats.merge_status(AGENT, {**STATUS, name: odd})
            res = client.get("/api/lancache")
            assert res.status_code == 200, (field, odd, res.data[:200])


def test_the_page_is_for_the_crew(anon_client, client):
    assert client.get("/api/lancache").status_code == 200
    assert anon_client.get("/api/lancache").status_code in (302, 401)
