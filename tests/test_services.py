"""Servers and services (issue #471): ISP uplinks, DNS resolvers, the LAN cache; the probes."""
import socket
import struct
import threading

import pytest

from floorbit import links, probes, services, sources
from tests.test_attention import Monitoring, port


@pytest.fixture
def net(client, monkeypatch):
    mon = Monitoring()
    monkeypatch.setattr(sources, "monitoring", lambda: mon)
    links.reader.reset()
    services.poller.reset()
    answers = {}
    monkeypatch.setattr(services, "_ask", lambda method, *args: answers[method](*args))
    for name, role in (("core-01", "router"), ("sw-a-01", "switch")):
        assert client.post("/api/inventory", json={"name": name, "role": role}).status_code in (200, 201)
    yield mon, answers
    services.poller.reset()
    links.reader.reset()


UPLINK = {"name": "ISP A", "device": "core-01", "port": "Te1/0/48", "capacity_mbps": 1000,
          "probe_host": "www.example.com", "probe_port": 443}


def test_uplinks_and_resolvers_are_checked(client, net):
    mon, answers = net
    assert client.post("/api/services/uplinks", json=UPLINK).status_code == 201
    assert client.post("/api/services/resolvers", json={"name": "Resolver 1", "address": "192.0.2.53",
                                                        "lookup": "Example.com."}).status_code == 201
    mon.set("core-01", {**port("TenGigabitEthernet1/0/48"), "upload_bps": 850_000_000, "download_bps": 90_000_000})
    answers["tcp_probe"] = lambda host, p, count: {"sent": 5, "lost": 1, "avg_ms": 12.5}
    answers["dns_probe"] = lambda server, name: {"ms": 3.2, "rcode": "NOERROR", "answers": 2}
    body = client.get("/api/services").get_json()
    [up], [res] = body["uplinks"], body["resolvers"]
    assert body["devices"][:2] == ["core-01", "sw-a-01"]          # routers first, for the form
    assert (up["status"], up["port_state"], up["in_bps"], up["utilization"], up["loss"], up["latency_ms"]) == (
        "warn", "up", 850_000_000, 0.85, 0.2, 12.5)
    assert (res["status"], res["lookup"], res["latency_ms"]) == ("up", "example.com", 3.2)
    answers["dns_probe"] = lambda server, name: {"ms": 250.0, "rcode": "NOERROR", "answers": 2}
    [res] = client.post("/api/services/check").get_json()["resolvers"]       # "Check now"
    assert (res["status"], res["latency_ms"]) == ("warn", 250.0)
    tiles = {t["id"].split(":")[0]: t for t in services.health_checks()}
    assert tiles["uplink"]["summary"] == "850 / 1000 Mbit/s in" and tiles["dns"]["status"] == "warn"


def test_a_down_line_or_a_failing_resolver_is_red(client, net):
    mon, answers = net
    client.post("/api/services/uplinks", json={**UPLINK, "probe_host": ""})
    client.post("/api/services/resolvers",
                json={"name": "Resolver 1", "address": "192.0.2.53", "lookup": "example.com"})
    mon.set("core-01", port("Te1/0/48", state="down"))
    answers["dns_probe"] = lambda server, name: {"ms": 3.2, "rcode": "SERVFAIL", "answers": 0}
    body = client.get("/api/services").get_json()
    assert body["uplinks"][0]["status"] == "down" and body["uplinks"][0]["loss"] is None
    assert (body["resolvers"][0]["status"], body["resolvers"][0]["error"]) == ("down", "example.com: SERVFAIL")


def test_what_is_kept_is_checked(client, net):
    assert client.post("/api/services/uplinks", json={**UPLINK, "device": "nope"}).status_code == 400
    assert client.post("/api/services/uplinks", json={**UPLINK, "capacity_mbps": "fast"}).status_code == 400
    assert client.post("/api/services/uplinks", json={**UPLINK, "probe_port": 22}).status_code == 400
    assert client.post("/api/services/resolvers", json={"name": "R", "address": "dns.example.com",
                                                        "lookup": "example.com"}).status_code == 400
    assert client.post("/api/services/resolvers", json={"name": "R", "address": "192.0.2.53",
                                                        "lookup": "localhost"}).status_code == 400
    assert client.post("/api/services/printers", json={}).status_code == 404
    item = client.post("/api/services/uplinks", json=UPLINK).get_json()
    changed = client.put(f"/api/services/uplinks/{item['id']}", json={"capacity_mbps": 10000}).get_json()
    assert (changed["capacity_mbps"], changed["port"]) == (10000, "Te1/0/48")
    assert client.delete(f"/api/services/uplinks/{item['id']}").status_code == 200
    assert client.delete(f"/api/services/uplinks/{item['id']}").status_code == 404


def test_viewers_see_services_but_do_not_change_them(app_module):
    from tests.test_rbac import sign_in_as
    viewer = sign_in_as(app_module, "vi10", "viewer")
    assert viewer.get("/api/services").status_code == 200
    assert viewer.post("/api/services/uplinks", json={}).status_code == 403
    assert viewer.post("/api/services/check").status_code == 403


def test_the_dns_probe_reads_the_answer(monkeypatch):
    srv = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    srv.bind(("127.0.0.1", 0))
    monkeypatch.setattr(probes, "DNS_PORT", srv.getsockname()[1])

    def answer():
        data, addr = srv.recvfrom(512)
        assert b"\x07example\x03com\x00" in data
        srv.sendto(b"\x00\x00" + data[:2] + b"\x81\x80" + struct.pack(">HHHH", 1, 1, 0, 0), addr)   # a stray id first
        srv.sendto(data[:2] + b"\x81\x80" + struct.pack(">HHHH", 1, 1, 0, 0) + data[12:], addr)

    t = threading.Thread(target=answer, daemon=True)
    t.start()
    got = probes.dns("127.0.0.1", "example.com", timeout=2)
    assert (got["rcode"], got["answers"]) == ("NOERROR", 1)
    srv.close()


def test_the_tcp_probe_counts_lost_connects(monkeypatch):
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(8)
    open_port = listener.getsockname()[1]
    monkeypatch.setattr(probes, "PROBE_PORTS", (open_port,))
    got = probes.tcp("127.0.0.1", open_port, count=3, timeout=1)
    assert (got["sent"], got["lost"]) == (3, 0) and got["avg_ms"] is not None
    listener.close()
    with pytest.raises(probes.ProbeError):
        probes.tcp("127.0.0.1", 22, count=1)


def test_the_server_never_probes_link_local_and_only_probe_nets_when_set(monkeypatch):
    monkeypatch.delenv("PROBE_NETS", raising=False)
    assert probes.target("127.0.0.1") == "127.0.0.1"
    assert probes.target("192.0.2.10") == "192.0.2.10"
    for host in ("169.254.169.254", "0.0.0.0", "224.0.0.1", "fe80::1", "::ffff:169.254.169.254"):
        with pytest.raises(probes.ProbeError):
            probes.target(host)
    monkeypatch.setenv("PROBE_NETS", "192.0.2.0/24, not-a-net")
    assert probes.target("192.0.2.10") == "192.0.2.10"
    with pytest.raises(probes.ProbeError):
        probes.target("127.0.0.1")
    with pytest.raises(probes.ProbeError):
        probes.target("198.51.100.1")
    assert probes.target("::ffff:192.0.2.10") == "192.0.2.10"           # mapped is checked as the IPv4 it is


def test_ipv6_that_reaches_the_metadata_service_is_refused(monkeypatch):
    monkeypatch.delenv("PROBE_NETS", raising=False)
    # NAT64 (64:ff9b::/96 and the local-use /48) and 6to4 carry an IPv4 address inside.
    for host in ("64:ff9b::a9fe:a9fe", "64:ff9b:1::a9fe:a9fe", "2002:a9fe:a9fe::1"):
        with pytest.raises(probes.ProbeError):
            probes.target(host)
        assert probes.unreachable(host)
    assert probes.target("64:ff9b::c000:20a") == "64:ff9b::c000:20a"   # 192.0.2.10 through NAT64 is fine
    assert probes.target("2001:db8::1") == "2001:db8::1"


def test_a_game_server_outside_probe_nets_is_not_queried(monkeypatch):
    from floorbit import game_query, game_servers
    monkeypatch.setattr(game_servers, "_via_agent", lambda: False)
    monkeypatch.setenv("PROBE_NETS", "192.0.2.0/24")
    monkeypatch.setattr(game_query, "query", lambda *a: pytest.fail("queried"))
    with pytest.raises(game_query.QueryError):
        game_servers._ask("game_query", "a2s", "169.254.169.254", 27015)
    with pytest.raises(game_query.QueryError):
        game_servers._ask("rcon", "198.51.100.5", 27015, "pw", "status")


def test_the_lan_cache_disk_is_a_tile_on_the_health_wall(client, monkeypatch, tmp_path):
    from collections import namedtuple
    usage = namedtuple("usage", "total used free")
    monkeypatch.setenv("LANCACHE_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(services.shutil, "disk_usage", lambda path: usage(1000, 950, 50))
    with client.application.app_context():
        tile = next(t for t in services.health_checks() if t["id"] == "lancache")
    assert (tile["kind"], tile["status"]) == ("cache", "warn")
    assert tile["summary"] == "The cache disk is 95 % full."
    assert {"label": "Disk", "value": 95, "unit": "%", "tone": "warn"} in tile["metrics"]
    # The health wall's own thread has no app context.
    monkeypatch.setattr(services.shutil, "disk_usage", lambda path: usage(1000, 400, 600))
    tile = next(t for t in services.health_checks() if t["id"] == "lancache")
    assert tile["status"] == "up"
    monkeypatch.delenv("LANCACHE_CACHE_DIR")
    with client.application.app_context():
        assert not [t for t in services.health_checks() if t["id"] == "lancache"]


def test_the_topology_shows_each_internet_line_on_its_router(client, net):
    mon, answers = net
    assert client.post("/api/services/uplinks", json=UPLINK).status_code == 201
    mon.set("core-01", {**port("TenGigabitEthernet1/0/48"), "upload_bps": 300_000_000, "download_bps": 90_000_000})
    answers["tcp_probe"] = lambda host, p, count: {"sent": 5, "lost": 0, "avg_ms": 9.0}
    client.get("/api/services")                       # checks what was just added
    [line] = client.get("/api/links").get_json()["uplinks"]
    assert (line["name"], line["device"], line["port"], line["status"], line["utilization"]) == (
        "ISP A", "core-01", "Te1/0/48", "up", 0.3)
