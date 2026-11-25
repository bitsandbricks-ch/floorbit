"""Only the leader polls; the other pods read what it shares (issue #1417, floorbit/shared_state.py).

Two Cluster objects on an in-memory bus play two pods. Which one ``cluster.current`` is decides
which pod the code under test runs on.
"""
import threading
import types

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
def state_in_tmp(tmp_path, monkeypatch):
    # Saved stats and DNS hours go to the state folder: keep them out of the checkout, where a
    # later test would find them (tests/test_stats.py backfills only an empty day).
    from floorbit import store
    monkeypatch.setattr(store, "DATA_FILE", str(tmp_path / "data.json"))


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


# ── the other loops ──────────────────────────────────────────────────────────
def test_security_findings_show_on_every_pod_and_only_the_leader_asks(pods, monkeypatch):
    from floorbit import security
    _bus, a, b = pods
    asked = []

    class Registry:
        def feeders(self, area):
            return [type("Spec", (), {"id": "demo", "name": "Demo"})()]

        def call(self, spec, method, *args):
            asked.append(cluster.current.pod)
            return [{"id": "loop-1", "kind": "loop", "severity": "high", "title": "Loop on sw-a-01",
                     "switch": "sw-a-01", "port": "Gi1/0/1"}]
    monkeypatch.setattr(security, "_seat_index", lambda: {})
    leader, other = security.SecurityWatch(Registry()), security.SecurityWatch(Registry())
    on(monkeypatch, a)
    assert shared_state.my_turn(leader)
    leader.poll_once()
    on(monkeypatch, b)
    assert not shared_state.my_turn(other)
    snap = other.fresh()           # a pod that doesn't lead never polls, even when its own copy is old
    assert [f["id"] for f in snap["findings"]] == ["demo:loop-1"]
    assert other.get("demo:loop-1")["switch"] == "sw-a-01"
    assert asked == ["pod-a"]


def test_the_port_watch_keeps_its_switch_and_port_keys_across_pods(pods, monkeypatch):
    from floorbit import attention
    _bus, a, b = pods
    leader, other = attention.AttentionWatch(), attention.AttentionWatch()
    leader.port_seats = {("sw-a-01", "Gi1/0/4"): "A-4"}
    leader.port_reads = {("sw-a-01", "gi1/0/4"): {"switch": "sw-a-01", "port": "Gi1/0/4", "state": "up"}}
    leader.read_switches = {"sw-a-01"}
    leader.items = {"errors:1:Gi1/0/4": {"id": "errors:1:Gi1/0/4", "since": 5}}
    leader.last_poll = 10
    on(monkeypatch, a)
    leader.share()
    on(monkeypatch, b)
    seen = other.view()
    assert seen.port_seats == {("sw-a-01", "Gi1/0/4"): "A-4"}
    assert seen.port_reads[("sw-a-01", "gi1/0/4")]["state"] == "up"
    assert seen.read_switches == {"sw-a-01"}
    assert [i["id"] for i in other.snapshot()["items"]] == ["errors:1:Gi1/0/4"]
    # And a pod that takes the lead starts from it.
    fresh = attention.AttentionWatch()
    fresh.take_over()
    assert fresh.port_seats == leader.port_seats and fresh.read_switches == {"sw-a-01"}


def test_the_dns_open_hour_crosses_as_counts_only(pods, monkeypatch, tmp_path):
    from floorbit import dns
    from tests.test_dns import HOUR, lookups
    _bus, a, b = pods
    bus = pods[0]
    leader = dns.DnsStats(path=str(tmp_path / "dns.json"))
    other = dns.DnsStats(path=str(tmp_path / "dns.json"))
    on(monkeypatch, a)
    leader.add(lookups("cdn.steamcontent.com", 5) + lookups("www.hobby.example", 4), now=HOUR + 600)
    leader.last_poll = HOUR + 600
    leader.share()
    raw = bus.values[shared_state.KEY + "dns"]
    assert "hobby" not in raw and "198.51.100" not in raw, "only sites enough clients looked up, no clients"
    on(monkeypatch, b)
    snap = other.snapshot(hours=1, now=HOUR + 600)
    assert [s["site"] for s in snap["sites"]] == ["steamcontent.com"]
    assert snap["lookups"] == 9 and snap["last_poll"] == HOUR + 600


def test_traffic_on_a_pod_that_does_not_lead_comes_from_the_leader(pods, monkeypatch):
    from floorbit import stats
    _bus, a, b = pods
    leader, other = stats.Stats(), stats.Stats()
    on(monkeypatch, a)
    dev = {"id": "1", "name": "sw-a-01"}
    port = {"name": "Gi1/0/4", "state": "up", "in_bps": 4_000_000, "out_bps": 1_000_000}
    leader.record([(dev, port, "A-4")], ["sw-a-01"], now=1000)
    on(monkeypatch, b)
    saved = []
    monkeypatch.setattr(stats.store, "write_json", lambda *a, **k: saved.append(a))
    assert other.seats()["seats"] == leader.seat_bps and other.seats()["last_poll"] == 1000
    assert other.snapshot(now=1000)["now"]["t"] == 1000
    other.reset_peak()
    assert saved == [], "only the leader writes the stats"


def test_what_an_agent_sends_goes_to_the_leader(pods, monkeypatch):
    from floorbit import agent_plugins
    _bus, _a, b = pods
    on(monkeypatch, b)
    sent = []
    monkeypatch.setattr(shared_state, "ask", lambda name, *args, **kw: sent.append((name, args)) or {"ok": True})

    spec = types.SimpleNamespace(id="shelly", name="Shelly", error=None, agent={"sends": {"readings": {}}},
                                 plugin_class=lambda: type("P", (), {"agent_readings": lambda *a: None}))

    class Registry:
        def __init__(self):
            self.specs = {"shelly": spec}

        def enabled(self, spec):
            return True

        def call(self, *a):
            pytest.fail("a pod that doesn't lead hands it on")
    monkeypatch.setattr(agent_plugins, "check_payload", lambda *a: None)
    answer = agent_plugins.take({"id": "ag1", "name": "hall-a"}, "shelly", "readings", {"meters": []}, Registry())
    assert answer == {"ok": True}
    assert sent == [(agent_plugins.TAKE, ({"id": "ag1", "name": "hall-a"}, "shelly", "readings", {"meters": []}))]


def test_every_loop_can_take_the_lead(monkeypatch, tmp_path):
    """my_turn() on each loop that waits for it: the first turn as leader takes over."""
    from floorbit import attention, dns, game_servers, health, links, port_clients, power, security, services
    monkeypatch.setattr(cluster, "current", None)
    loops = [attention.AttentionWatch(), dns.DnsStats(path=str(tmp_path / "dns.json")), game_servers.Poller(),
             health.HealthWall(None), links.Refresher(), port_clients.Finder(), power.PowerWatch(None),
             security.SecurityWatch(None), services.Poller()]
    for loop in loops:
        assert shared_state.my_turn(loop), type(loop).__name__
