"""Several Floorbit pods sharing Redis (issue #465, floorbit/cluster.py). An in-memory bus stands in
for Redis; two Cluster objects are two pods."""
import json
import threading
import time

import pytest

from floorbit import agent_link, cluster
from integrations import events


class MemoryBus:
    def __init__(self):
        self.now = 0.0
        self.keys, self.hashes, self.lists, self.listeners = {}, {}, {}, []
        self.cond = threading.Condition()
        self.down = False

    def _check(self):
        if self.down:
            raise ConnectionError("Redis is down")

    def lease(self, key, value, ms):
        self._check()
        holder, until = self.keys.get(key, (None, 0))
        if holder is None or until <= self.now or holder == value:
            self.keys[key] = (value, self.now + ms / 1000)
        return self.keys[key][0]

    def publish(self, channel, message):
        self._check()
        for handler in list(self.listeners):
            handler(message)

    def listen(self, channel, handler, stop, on_resume=None):
        self.listeners.append(handler)
        self.on_resume = on_resume

    def push(self, key, message, ttl=None):
        with self.cond:
            self.lists.setdefault(key, []).append(message)
            self.cond.notify_all()

    def pop(self, key, timeout):
        deadline = time.monotonic() + timeout
        with self.cond:
            while not self.lists.get(key):
                left = deadline - time.monotonic()
                if left <= 0:
                    return None
                self.cond.wait(left)
            return self.lists[key].pop(0)

    def hset(self, key, field, value):
        self.hashes.setdefault(key, {})[field] = value

    def hgetall(self, key):
        return dict(self.hashes.get(key, {}))


def quiet(*_):
    pass


def test_one_pod_leads_and_another_takes_over_when_it_stops():
    bus = MemoryBus()
    a, b = cluster.Cluster(bus, "pod-a", log=quiet), cluster.Cluster(bus, "pod-b", log=quiet)
    assert a.renew() and not b.renew()
    bus.now += 10
    assert a.renew() and not b.renew()           # renewed in time
    bus.now += cluster.LEASE_MS / 1000 + 1       # pod-a died
    assert b.renew() and not a.renew()
    bus.down = True
    assert a.renew() and a.leading()             # no Redis: everyone acts


def test_events_reach_the_other_pods_browsers_only():
    bus = MemoryBus()
    got_a, got_b = [], []
    a = cluster.Cluster(bus, "pod-a", deliver=got_a.append, log=quiet)
    b = cluster.Cluster(bus, "pod-b", deliver=got_b.append, log=quiet)
    for pod in (a, b):
        bus.listen(cluster.CHANNEL, pod._heard, None)
    a.publish({"id": 1, "type": "switch.status", "data": {"name": "sw-a-01"}})
    assert got_a == [] and got_b[0]["data"] == {"name": "sw-a-01"}
    b._heard("not json")                          # ignored


def test_a_call_goes_to_the_pod_the_agent_is_connected_to():
    bus = MemoryBus()
    asked = []

    def run_call(method, args, targets, timeout):
        asked.append((method, args, targets))
        if method == "arp":
            raise agent_link.AgentError("LibreNMS said no")
        return {"devices": 3}

    a = cluster.Cluster(bus, "pod-a", run_call=run_call, log=quiet)
    b = cluster.Cluster(bus, "pod-b", log=quiet)
    a.agent_seen("agt1", now=time.time())
    assert b.agents_elsewhere() == {"agt1": "pod-a"} and a.agents_elsewhere() == {}

    def serve_one():
        a._serve_call(bus.pop(cluster.CALLS_KEY + "pod-a", 5))
    for _ in range(2):
        threading.Thread(target=serve_one, daemon=True).start()
    assert b.forward("pod-a", "devices", [], {"agt1"}, 5) == {"ok": True, "result": {"devices": 3}}
    failed = b.forward("pod-a", "arp", ["192.0.2.0/24"], None, 5)
    assert failed["ok"] is False and "LibreNMS said no" in failed["error"] and not failed["unavailable"]
    assert asked == [("devices", [], ["agt1"]), ("arp", ["192.0.2.0/24"], None)]
    assert b.forward("pod-a", "devices", [], None, 1) is None      # nobody serves: the caller gives up


def test_a_late_call_is_dropped():
    bus = MemoryBus()
    a = cluster.Cluster(bus, "pod-a", run_call=lambda *a: pytest.fail("ran a call nobody waits for"), log=quiet)
    a._serve_call(json.dumps({"id": "x", "method": "devices", "args": [], "timeout": 5, "deadline": time.time() - 1}))
    assert not bus.lists


@pytest.fixture
def two_pods(monkeypatch):
    bus = MemoryBus()
    here = cluster.Cluster(bus, "pod-b", log=quiet)
    monkeypatch.setattr(cluster, "current", here)
    agent_link.tunnel.reset()
    yield bus, here
    agent_link.tunnel.reset()


def test_the_tunnel_asks_through_the_other_pod(two_pods):
    bus, _here = two_pods
    other = cluster.Cluster(bus, "pod-a", run_call=lambda m, a, t, timeout: {"asked": m, "targets": t}, log=quiet)
    assert not agent_link.tunnel.connected()
    other.agent_seen("agt1", now=time.time())
    assert agent_link.tunnel.connected() and agent_link.tunnel.connected(agent="agt1")
    assert agent_link.tunnel.connected_agents() == {"agt1"}
    threading.Thread(target=lambda: other._serve_call(bus.pop(cluster.CALLS_KEY + "pod-a", 5)), daemon=True).start()
    assert agent_link.tunnel.call("devices", targets={"agt1"}, timeout=5) == {"asked": "devices", "targets": ["agt1"]}
    with pytest.raises(agent_link.AgentUnavailable):
        agent_link.tunnel.call("devices", targets={"agt2"}, timeout=1)


def test_followers_skip_side_effects_of_background_events(two_pods, monkeypatch, app_module):
    bus, here = two_pods
    monkeypatch.setattr(events, "_subscribers", [])
    sent, counted = [], []
    events.subscribe("switch.status", sent.append, leader_only=True)
    events.subscribe("switch.status", counted.append)
    bus.keys[cluster.LEADER_KEY] = ("pod-a", bus.now + 60)
    here.renew()
    assert not cluster.leading()
    events.publish("switch.status", {"name": "sw-a-01"})              # from a background loop
    assert (len(sent), len(counted)) == (0, 1)
    with app_module.app.test_request_context("/api/x"):
        events.publish("switch.status", {"name": "sw-a-01"})          # a crew member did something
    assert (len(sent), len(counted)) == (1, 2)
    monkeypatch.setattr(cluster, "current", None)
    events.publish("switch.status", {"name": "sw-a-01"})              # one pod: always the leader
    assert len(sent) == 2


def test_cluster_mode_is_off_unless_set(monkeypatch):
    monkeypatch.delenv("FLOORBIT_CLUSTER", raising=False)
    assert cluster.init() is None
    monkeypatch.setenv("FLOORBIT_CLUSTER", "zookeeper")
    with pytest.raises(ValueError):
        cluster.init()


# ── RedisBus against a fake redis-py client ─────────────────────────────────────

class FakeRedisClient:
    """The commands RedisBus sends, with expiry on a clock the test moves."""

    def __init__(self, shared):
        self.s = shared

    def _live(self, key):
        value, until = self.s["keys"].get(key, (None, None))
        if until is not None and until <= self.s["now"]:
            self.s["keys"].pop(key, None)
            return None
        return value

    def set(self, key, value, nx=False, xx=False, px=None):
        there = self._live(key) is not None
        if (nx and there) or (xx and not there):
            return None
        self.s["keys"][key] = (value, None if px is None else self.s["now"] + px / 1000)
        return True

    def get(self, key):
        value = self._live(key)
        if self.s.get("after_get"):
            self.s.pop("after_get")()
        return value

    def pexpire(self, key, ms):
        if self._live(key) is None:
            return False
        self.s["keys"][key] = (self.s["keys"][key][0], self.s["now"] + ms / 1000)
        return True

    def rpush(self, key, value):
        self.s["lists"].setdefault(key, []).append(value)

    def expire(self, key, seconds):
        self.s["ttl"][key] = seconds

    def blpop(self, keys, timeout=0):
        for key in keys:
            if self.s["lists"].get(key):
                return key, self.s["lists"][key].pop(0)
        return None

    def hset(self, key, field, value):
        self.s["hashes"].setdefault(key, {})[field] = value

    def hgetall(self, key):
        return dict(self.s["hashes"].get(key, {}))


@pytest.fixture
def redis_bus(monkeypatch):
    import redis
    shared = {"now": 0.0, "keys": {}, "lists": {}, "hashes": {}, "ttl": {}}
    monkeypatch.setattr(redis, "Redis", lambda **kw: FakeRedisClient(shared))
    return cluster.RedisBus(host="redis.example.com", port=6379), shared


def test_the_lease_is_taken_kept_and_expires(redis_bus):
    bus, shared = redis_bus
    assert bus.lease("lead", "pod-a", 20_000) == "pod-a"
    assert bus.lease("lead", "pod-b", 20_000) == "pod-a"
    shared["now"] = 15
    assert bus.lease("lead", "pod-a", 20_000) == "pod-a"     # renewed: still there at 30 s
    shared["now"] = 30
    assert bus.lease("lead", "pod-b", 20_000) == "pod-a"
    shared["now"] = 40
    assert bus.lease("lead", "pod-b", 20_000) == "pod-b"


def test_renewing_never_overwrites_a_lease_another_pod_just_took(redis_bus):
    bus, shared = redis_bus
    bus.lease("lead", "pod-a", 20_000)

    def pod_b_takes_it():      # pod-a's lease runs out right after its GET, and pod-b takes it
        shared["keys"]["lead"] = ("pod-b", shared["now"] + 20)
    shared["after_get"] = pod_b_takes_it
    bus.lease("lead", "pod-a", 20_000)
    assert shared["keys"]["lead"][0] == "pod-b"


def test_calls_and_agents_through_the_bus(redis_bus):
    bus, _ = redis_bus
    bus.push("calls", "one", ttl=40)
    assert bus.pop("calls", 1) == "one" and bus.pop("calls", 1) is None
    bus.hset("agents", "a1", "x")
    assert bus.hgetall("agents") == {"a1": "x"}


def test_rows_from_another_version_are_skipped():
    bus = MemoryBus()
    pod = cluster.Cluster(bus, pod="pod-a")
    for agent_id, raw in {"ok": json.dumps({"pod": "pod-b", "at": 100}), "list": "[1]", "nopod": '{"at": 100}',
                          "badat": '{"pod": "pod-b", "at": "soon"}', "text": "garbage"}.items():
        bus.hset(cluster.AGENTS_KEY, agent_id, raw)
    assert pod.agents_elsewhere(now=110) == {"ok": "pod-b"}
    for raw in ('{"id": "c1"}', '[]', '{"id": "c2", "method": "check", "timeout": "x", "deadline": 1e12}'):
        pod._serve_call(raw)       # dropped, not a crash in the worker
    assert not bus.lists


def test_a_hosted_tenant_s_bus_keeps_to_its_keys(monkeypatch):
    import redis
    shared = {"now": 0.0, "keys": {}, "lists": {}, "hashes": {}, "ttl": {}}
    monkeypatch.setattr(redis, "Redis", lambda **kw: FakeRedisClient(shared))
    a = cluster.RedisBus(prefix="club-a:", host="redis.example.com", port=6379)
    b = cluster.RedisBus(prefix="club-b:", host="redis.example.com", port=6379)
    assert a.lease("lead", "pod-a", 20_000) == "pod-a"
    assert b.lease("lead", "pod-b", 20_000) == "pod-b"      # each tenant has its own leader
    a.push("calls", "one")
    assert b.pop("calls", 1) is None and a.pop("calls", 1) == "one"
    a.hset("agents", "a1", "x")
    assert b.hgetall("agents") == {} and set(shared["hashes"]) == {"club-a:agents"}


def test_pods_say_who_leads_for_the_agents_page():
    bus = MemoryBus()
    a = cluster.Cluster(bus, pod="pod-a", log=lambda *_: None)
    b = cluster.Cluster(bus, pod="pod-b", log=lambda *_: None)
    a.renew()
    b.renew()
    pods = b.pods()
    assert [(p["pod"], p["leader"], p["me"]) for p in pods] == [("pod-b", False, True), ("pod-a", True, False)]
    bus.hashes[cluster.PODS_KEY]["pod-old"] = json.dumps({"at": time.time() - 3600, "leader": False})
    bus.hashes[cluster.PODS_KEY]["junk"] = "not json"
    assert {p["pod"] for p in a.pods()} == {"pod-a", "pod-b"}


def test_a_pod_tells_its_browsers_to_fetch_again_when_redis_is_back(monkeypatch):
    """Changes on other pods while Redis was away never reached this pod's browsers: they refetch."""
    class Error(Exception):
        pass

    class FakeRedis:
        RedisError = Error

    class PubSub:
        calls = 0

        def subscribe(self, channel):
            PubSub.calls += 1
            if PubSub.calls == 1:
                raise Error("connection refused")

        def get_message(self, timeout):
            stop.set()

    class Blocking:
        def pubsub(self, ignore_subscribe_messages):
            return PubSub()

    bus = cluster.RedisBus.__new__(cluster.RedisBus)
    bus._redis, bus.prefix, bus.blocking = FakeRedis, "", Blocking()
    stop = threading.Event()
    monkeypatch.setattr(stop, "wait", lambda seconds: None)
    resumed = []
    bus.listen("ch", lambda raw: None, stop, on_resume=lambda: resumed.append(1))
    assert PubSub.calls == 2 and resumed == [1]


def test_resumed_sends_a_resync_to_this_pods_browsers(monkeypatch):
    sent = []
    monkeypatch.setattr(events, "deliver_local", sent.append)
    pod = cluster.Cluster(MemoryBus(), pod="a", deliver=lambda e: None, log=lambda *_: None)
    pod._resumed()
    assert [e["type"] for e in sent] == ["resync"]
