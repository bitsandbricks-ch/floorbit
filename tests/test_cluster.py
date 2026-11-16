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

    def listen(self, channel, handler, stop):
        self.listeners.append(handler)

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
