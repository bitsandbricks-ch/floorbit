"""Only the leader polls; the other pods read what it shares (issue #1417, floorbit/shared_state.py).

Two Cluster objects on an in-memory bus play two pods. Which one ``cluster.current`` is decides
which pod the code under test runs on.
"""
import threading

import pytest

from floorbit import cluster, shared_state, sources
from integrations import events
from integrations.monitor import StatusMonitor
from tests.test_cluster import MemoryBus, quiet
from tests.test_integrations import make_monitor


class Bus(MemoryBus):
    def __init__(self):
        super().__init__()
        self.values = {}

    def set(self, key, value, ttl):
        self._check()
        self.values[key] = value

    def get(self, key):
        self._check()
        return self.values.get(key)


@pytest.fixture
def pods(monkeypatch):
    bus = Bus()
    a, b = cluster.Cluster(bus, "pod-a", log=quiet), cluster.Cluster(bus, "pod-b", log=quiet)
    a.renew(), b.renew()          # pod-a took the lease first
    assert a.leading() and not b.leading()
    shared_state._read.clear()
    monkeypatch.setattr(shared_state, "REREAD", 0)
    yield bus, a, b
    shared_state._read.clear()


def on(monkeypatch, pod):
    monkeypatch.setattr(cluster, "current", pod)


@pytest.fixture(autouse=True)
def no_subscribers():
    events._subscribers.clear()
    yield
    events._subscribers.clear()


def two_monitors(devices, monkeypatch):
    switches = [{"id": "1", "name": "sw-a1"}, {"id": "2", "name": "sw-a2"}]
    return make_monitor(devices, switches, monkeypatch), make_monitor(devices, switches, monkeypatch)


def test_a_pod_that_does_not_lead_shows_what_the_leader_saw(pods, monkeypatch):
    _bus, a, b = pods
    devices = [{"display": "sw-a1", "status": 1}, {"display": "sw-a2", "status": 1}]
    leader, other = two_monitors(devices, monkeypatch)
    on(monkeypatch, a)
    leader.poll_once()
    devices[1]["status"] = 0
    leader.poll_once()
    on(monkeypatch, b)
    other.fetch_devices = lambda: pytest.fail("a pod that doesn't lead must not poll")
    assert other.snapshot() == {"1": "online", "2": "offline"}
    assert other.counts() == {"online": 1, "offline": 1, "unknown": 0}
    info = other.info()
    assert info["tracked"] == 2 and info["last_poll"] == leader.last_poll
    assert other.status_of("2") == "offline"
    assert StatusMonitor.latest_devices()["devices"] == devices


def test_the_loop_on_a_pod_that_does_not_lead_never_asks_the_source(pods, monkeypatch):
    _bus, _a, b = pods
    on(monkeypatch, b)
    m = make_monitor([], [{"id": "1", "name": "sw-a1"}], monkeypatch)
    asked = threading.Event()
    m.fetch_devices = lambda: asked.set() or []
    monkeypatch.setattr("integrations.monitor.FOLLOW_EVERY", 0.01)
    m.start()
    try:
        assert not asked.wait(0.3)
    finally:
        m._stop.set()


def test_a_new_leader_carries_on_where_the_old_one_stopped(pods, monkeypatch):
    bus, a, b = pods
    devices = [{"display": "sw-a1", "status": 1}, {"display": "sw-a2", "status": 0}]
    old, new = two_monitors(devices, monkeypatch)
    on(monkeypatch, a)
    old.poll_once()
    went_down = old.statuses["2"]["since"]
    # pod-a goes away; its lease runs out and pod-b takes it.
    bus.now += cluster.LEASE_MS / 1000 + 1
    b.renew()
    assert b.leading()
    on(monkeypatch, b)
    new.take_over()
    got = []
    events.subscribe("switch.status", got.append)
    assert new.poll_once() == [], "the same picture after the handover is no change"
    devices[1]["status"] = 1
    back = new.poll_once()
    assert back[0]["id"] == "2" and back[0]["previous"] == "offline"
    assert back[0]["down_for"] == pytest.approx(back[0]["since"] - went_down)


def test_poll_now_on_another_pod_runs_on_the_leader(pods, monkeypatch):
    bus, a, b = pods
    ran = []
    shared_state.answer("test.poll", lambda x: ran.append((cluster.current.pod, x)) or {"n": x})
    on(monkeypatch, b)
    stop = threading.Event()

    def leader_takes_calls():      # pod-a's call loop
        while not stop.is_set():
            raw = bus.pop(cluster.CALLS_KEY + "pod-a", 0.1)
            if raw:
                monkeypatch.setattr(cluster, "current", a)
                a._serve_call(raw)
    t = threading.Thread(target=leader_takes_calls, daemon=True)
    t.start()
    try:
        assert shared_state.ask("test.poll", 3, timeout=5) == {"n": 3}
    finally:
        stop.set()
    assert ran == [("pod-a", 3)]


def test_without_the_cluster_nothing_is_shared(monkeypatch):
    monkeypatch.setattr(cluster, "current", None)
    assert not shared_state.follower()
    shared_state.put("x", {"a": 1})
    assert shared_state.get("x", "none") == "none"
    shared_state.answer("test.here", lambda: "here")
    assert shared_state.ask("test.here") == "here"


def test_the_source_outage_shows_on_every_pod(pods, monkeypatch):
    _bus, a, b = pods
    m = make_monitor([], [{"id": "1", "name": "sw-a1"}], monkeypatch)

    def down():
        raise ConnectionError("LibreNMS is away")
    m.fetch_devices = down
    on(monkeypatch, a)
    with pytest.raises(ConnectionError):
        m.poll_once()
    m.share()
    try:
        on(monkeypatch, b)
        assert sources.offline() and "LibreNMS is away" in sources.health()["error"]
    finally:
        on(monkeypatch, None)
        sources.mark_off()
