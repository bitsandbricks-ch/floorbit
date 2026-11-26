"""The switch terminal behind several workers or pods (issue #1417, floorbit/terminal_cluster.py).

Two Cluster objects on an in-memory bus are two pods in this one test process. The terminal's
session list answers the pod-a thread that serves passed-on requests, and looks empty to the
request, which plays pod-b: as if the browser's next request landed on the other worker.
"""
import json
import threading

import pytest

from floorbit import cluster, terminal, terminal_cluster
from tests.test_cluster import MemoryBus, quiet
from tests.test_terminal import SWITCH, audit_lines, read_until

pytestmark = pytest.mark.usefixtures("lan_here")

HOLDER = "pod-a-serve"


class Bus(MemoryBus):
    def __init__(self):
        super().__init__()
        self.pushed = []

    def push(self, key, message, ttl=None):
        self.pushed.append(message)
        super().push(key, message, ttl)

    def hget(self, key, field):
        return self.hashes.get(key, {}).get(field)

    def hdel(self, key, field):
        self.hashes.get(key, {}).pop(field, None)


class HeldByPodA(dict):
    """terminal._sessions as each pod sees it: only pod-a's thread finds the sessions in it."""

    def _mine(self):
        return threading.current_thread().name == HOLDER or self.opening

    def get(self, key, default=None):
        return super().get(key, default) if self._mine() else default

    def values(self):
        return super().values() if self._mine() else []

    opening = True


@pytest.fixture
def pods(client, monkeypatch):
    assert client.post("/api/inventory", json=SWITCH).status_code in (200, 201)
    client.put("/api/settings/plugins/demo", json={"enabled": True})
    bus = Bus()
    a, b = cluster.Cluster(bus, "pod-a", log=quiet), cluster.Cluster(bus, "pod-b", log=quiet)
    a.renew(), b.renew()
    held = HeldByPodA()
    monkeypatch.setattr(terminal, "_sessions", held)
    monkeypatch.setattr(cluster, "current", a)
    stop = threading.Event()

    def serve():          # pod-a's call loop (Cluster._take_calls), one call at a time
        while not stop.is_set():
            raw = bus.pop(cluster.CALLS_KEY + "pod-a", 0.2)
            if raw:
                a._serve_call(raw)
    threading.Thread(target=serve, name=HOLDER, daemon=True).start()
    yield bus, a, b, held
    stop.set()
    held.opening = True
    for s in list(dict.values(held)):
        s.end("test over")


def open_on_pod_a(client, pods):
    _bus, _a, b, held = pods
    resp = client.post("/api/terminal", json={"switch": "sw-a-01"})
    assert resp.status_code == 201, resp.data
    held.opening = False
    cluster.current = b      # from here on, the requests land on pod-b
    return resp.get_json()["id"]


def test_a_terminal_answers_through_the_pod_that_holds_it(client, pods):
    bus, _a, _b, _held = pods
    sid = open_on_pod_a(client, pods)
    row = json.loads(bus.hashes[terminal_cluster.TERMINALS_KEY][sid])
    assert row["pod"] == "pod-a" and row["switch"] == "sw-a-01"
    out, after, _ = read_until(client, sid, "sw-a-01#")
    assert "sw-a-01#" in out
    for piece in ("show version", "\r"):
        assert client.post(f"/api/terminal/{sid}/input", json={"data": piece}).status_code == 200
    out, after, _ = read_until(client, sid, "Version", after)
    assert "Cisco IOS Software" in out
    assert client.post(f"/api/terminal/{sid}/resize", json={"cols": 100, "rows": 30}).status_code == 200
    assert [s["id"] for s in client.get("/api/terminal").get_json()["sessions"]] == [sid]
    assert client.delete(f"/api/terminal/{sid}").status_code == 200
    assert sid not in bus.hashes[terminal_cluster.TERMINALS_KEY]
    assert client.get(f"/api/terminal/{sid}/output?wait=0").status_code == 404
    entries = [(e["action"], e["target"]) for e in audit_lines()]
    assert ("Typed", "sw-a-01: show version") in entries
    # What the tech typed crossed the bus sealed, never in the clear.
    assert bus.pushed and not any("show version" in m for m in bus.pushed)


def test_someone_else_cannot_reach_it_through_another_pod(app_module, client, pods):
    from tests.test_terminal import sign_in
    sid = open_on_pod_a(client, pods)
    other = sign_in(app_module, "boss", "lead")
    assert other.get(f"/api/terminal/{sid}/output?wait=0").status_code == 404
    assert other.post(f"/api/terminal/{sid}/input", json={"data": "x"}).status_code == 404
    assert other.get("/api/terminal").get_json()["sessions"] == []


def test_limits_count_the_terminals_other_pods_hold(client, pods, monkeypatch):
    open_on_pod_a(client, pods)
    monkeypatch.setattr(terminal, "MAX_PER_ACCOUNT", 1)
    assert client.post("/api/terminal", json={"switch": "sw-a-01"}).status_code == 429


def test_a_stopped_pods_terminals_are_gone(client, pods):
    bus, _a, b, _held = pods
    bus.hset(terminal_cluster.TERMINALS_KEY, "gone1",
             json.dumps({"pod": "pod-x", "account": "tester", "switch": "sw-a-01", "opened": 1}))
    cluster.current = b
    assert client.get("/api/terminal/gone1/output?wait=0").status_code == 404
    assert "gone1" not in bus.hashes[terminal_cluster.TERMINALS_KEY]


def test_one_process_needs_no_bus(monkeypatch):
    monkeypatch.setattr(cluster, "current", None)
    assert terminal_cluster.elsewhere() == {} and terminal_cluster.find("x", "tester") is None


def test_the_redis_bus_reads_and_drops_one_field(monkeypatch):
    # agent_left() used these too, and they were missing: an agent's row stayed until it went stale.
    import redis

    from tests.test_cluster import FakeRedisClient

    class Client(FakeRedisClient):
        def hget(self, key, field):
            return self.s["hashes"].get(key, {}).get(field)

        def hdel(self, key, field):
            self.s["hashes"].get(key, {}).pop(field, None)

    shared = {"now": 0.0, "keys": {}, "lists": {}, "hashes": {}, "ttl": {}}
    monkeypatch.setattr(redis, "Redis", lambda **kw: Client(shared))
    bus = cluster.RedisBus(prefix="t:", host="redis.example.com", port=6379)
    bus.hset("terminals", "s1", "x")
    assert bus.hget("terminals", "s1") == "x"
    bus.hdel("terminals", "s1")
    assert bus.hget("terminals", "s1") is None and shared["hashes"]["t:terminals"] == {}
