"""Redis is optional: a missing one costs a request nothing, and clearing the cache really forgets."""
import json

import pytest
import redis
from conftest import FakeRedis

from floorbit import cache


class Away(FakeRedis):
    made = 0

    def __init__(self, *args, **kwargs):
        super().__init__()
        Away.made += 1

    def ping(self):
        raise redis.ConnectionError("refused")


def test_a_redis_that_is_away_is_tried_once_in_a_while_not_on_every_request(monkeypatch):
    Away.made = 0
    monkeypatch.setattr(cache.redis, "Redis", Away)
    monkeypatch.setattr(cache, "redis_client", None)
    monkeypatch.setattr(cache, "_next_try", 0.0)
    for now in (100.0, 100.1, 110.0):
        cache.connect(now)
    assert Away.made == 1 and cache.redis_client is None
    cache.connect(100.0 + cache.RETRY_EVERY)
    assert Away.made == 2


def test_redis_coming_back_is_used_and_a_working_one_is_not_pinged_on_every_request(monkeypatch):
    pings = []

    class Counted(FakeRedis):
        def ping(self):
            pings.append(1)
            return True
    monkeypatch.setattr(cache.redis, "Redis", Counted)
    monkeypatch.setattr(cache, "redis_client", None)
    monkeypatch.setattr(cache, "_next_try", 0.0)
    cache.connect(200.0)
    assert isinstance(cache.redis_client.client, Counted) and len(pings) == 1   # under the tenant's prefix
    cache.connect(201.0)
    assert len(pings) == 1
    cache.connect(200.0 + cache.PING_EVERY)
    assert len(pings) == 2


def test_redis_going_away_turns_the_cache_off(monkeypatch):
    class Gone(FakeRedis):
        def ping(self):
            raise redis.ConnectionError("gone")
    monkeypatch.setattr(cache, "redis_client", Gone())
    monkeypatch.setattr(cache, "_checked_at", 0.0)
    cache.connect(1000.0)
    assert cache.redis_client is None


@pytest.fixture
def cached(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(cache, "redis_client", fake)
    monkeypatch.setattr(cache, "connect", lambda now=None: None)
    fake.set("arp:core", "[]")
    fake.set("mac:sw-a1", "[]")
    fake.set("mac:sw-b1", "[]")
    fake.set("resolve:192.0.2.10", json.dumps({"hostname": "198.51.100.11", "device_name": "sw-a1", "port": "Gi1/0/7"}))
    fake.set("resolve:192.0.2.20", json.dumps({"hostname": "198.51.100.12", "device_name": "sw-b1", "port": "Gi1/0/2"}))
    fake.set("stats:keep", "1")
    return fake


def test_clearing_everything_also_forgets_where_ips_were_seen(client, cached):
    assert client.post("/api/cache/invalid", json={}).status_code == 200
    assert sorted(cached.keys("*")) == ["stats:keep"]


def test_clearing_one_switch_forgets_only_what_was_seen_on_it(client, cached):
    got = client.post("/api/cache/invalid", json={"hostnames": ["sw-a1"]}).get_json()
    assert got["invalidated"] == ["sw-a1"]
    assert sorted(cached.keys("*")) == ["arp:core", "mac:sw-b1", "resolve:192.0.2.20", "stats:keep"]


@pytest.mark.parametrize("body", [{"hostnames": "sw-a1"}, {"hostnames": [1]}, {"hostnames": [""]},
                                  {"hostnames": ["sw"] * 501}])
def test_a_bad_list_of_switches_is_refused(client, cached, body):
    assert client.post("/api/cache/invalid", json=body).status_code == 400
    assert "arp:core" in cached.keys("*")


def test_a_body_that_is_not_an_object_is_refused_and_clears_nothing(client, cached):
    # A garbled body must not be read as "clear everything" (floorbit/json_body.py).
    assert client.post("/api/cache/invalid", json=["x"]).status_code == 400
    assert "arp:core" in cached.keys("*")


def test_without_redis_the_cache_api_says_so(client, monkeypatch):
    monkeypatch.setattr(cache, "connect", lambda now=None: None)
    monkeypatch.setattr(cache, "redis_client", None)
    assert client.post("/api/cache/invalid", json={}).status_code == 503
    assert client.get("/api/cache/stats").status_code == 503


def test_cache_stats_count_the_tables(client, cached):
    got = client.get("/api/cache/stats").get_json()
    assert got["arp_cache_entries"] == 1 and got["mac_cache_entries"] == 2 and got["total_keys"] == 6


def test_the_flow_collector_survives_redis_going_away_and_finds_it_again(monkeypatch):
    from floorbit.flows import store

    class Broken(FakeRedis):
        def setex(self, *args):
            raise redis.ConnectionError("gone")
    monkeypatch.setattr(cache, "redis_client", Broken())
    monkeypatch.setattr(cache, "_checked_at", 10**12)   # still counts as checked: setex is what fails
    assert store.publish({"mix_hour": {}}) is False

    monkeypatch.setattr(cache, "redis_client", None)
    monkeypatch.setattr(cache, "_next_try", 0.0)
    monkeypatch.setattr(cache.redis, "Redis", FakeRedis)
    assert store.publish({"mix_hour": {}}) is True and store.latest() == {"mix_hour": {}}
