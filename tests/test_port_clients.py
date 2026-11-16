"""Clients on seat ports that the patch plan doesn't explain (issue #473), from MAC tables and ARP."""
import pytest

from floorbit import port_clients, sources
from integrations import events, seat_sources


class Fdb:
    """MAC tables per switch and one ARP table, like LibreNMS through the monitoring plugin."""

    def __init__(self):
        self.tables, self.arp_rows, self.arp_asked, self.broken = {}, [], [], set()

    def enabled(self):
        return True

    def port_clients(self, hostname):
        if hostname in self.broken:
            raise RuntimeError("LibreNMS timed out")
        return self.tables.get(hostname, [])

    def arp(self, query):
        self.arp_asked.append(query)
        return self.arp_rows


def mac(n):
    return f"02:00:00:00:00:{n:02x}"


@pytest.fixture
def hall(client, app_module, monkeypatch):
    fdb = Fdb()
    monkeypatch.setattr(sources, "monitoring", lambda: fdb)
    monkeypatch.setattr(events, "publish", lambda kind, data=None, origin=None: None)
    seats = {"A-1": {"ip_address": "192.0.2.11"}, "A-2": {"ip_address": "192.0.2.12"},
             "A-3": {"ip_address": "192.0.2.13"}, "A-4": {"ip_address": "not an ip"}}
    monkeypatch.setattr(seat_sources, "load", lambda max_age=None: seats)
    client.post("/api/seat-blocks", json={"name": "A", "x": 10, "y": 10, "cols": 4, "rows": 1})
    block = next(b for b in client.get("/api/seat-blocks").get_json() if b["name"] == "A")
    r = client.post("/api/cables/block", json={"block": block["id"], "switch": "sw-a-01", "first_port": "Gi1/0/1"})
    assert r.status_code == 200, r.get_json()
    client.post("/api/cables", json={"switch": "sw-a-01", "port": "Gi1/0/48"})      # the uplink: no seat
    finder = app_module.app.extensions["floorbit_port_clients"]
    finder.reset()
    return {"fdb": fdb, "finder": finder, "app": app_module.app}


def read(hall, client):
    with hall["app"].app_context():
        hall["finder"].run(now=1000)
    return client.get("/api/cables/clients").get_json()


def test_unplanned_and_moved_clients(hall, client):
    fdb = hall["fdb"]
    fdb.tables["sw-a-01"] = [
        {"port": "Gi1/0/1", "mac": mac(1)},                    # A-1's own machine
        {"port": "Gi1/0/2", "mac": mac(3)},                    # A-3's machine on A-2's port: swapped
        {"port": "Gi1/0/7", "mac": "02-00-00-00-00-07"},       # no cable says what Gi1/0/7 is
        *({"port": "Gi1/0/48", "mac": mac(40 + i)} for i in range(10)),   # the uplink
        *({"port": "Gi1/0/9", "mac": mac(60 + i)} for i in range(6)),     # a switch under a desk
    ]
    fdb.arp_rows = [{"mac_address": mac(1), "ipv4_address": "192.0.2.11"},
                    {"mac_address": mac(3).upper(), "ipv4_address": "192.0.2.13"},
                    {"mac_address": mac(7), "ipv4_address": "192.0.2.99"}]
    body = read(hall, client)
    assert body["as_of"] == 1000 and body["switches"] == 1 and body["failed"] == []
    # One ARP query for the seats' network, not one per seat.
    assert fdb.arp_asked == ["192.0.2.0/24"]
    [moved] = body["moved"]["rows"]
    assert (moved["seat"], moved["port"], moved["ip_seat"], moved["ip"]) == ("A-2", "Gi1/0/2", "A-3", "192.0.2.13")
    [unplanned] = body["unplanned"]["rows"]
    assert (unplanned["port"], unplanned["mac"], unplanned["ip"], unplanned["ip_seat"]) == (
        "Gi1/0/7", mac(7), "192.0.2.99", "")
    assert body["clients"] == 3
    # Marked as infrastructure (a cable without a seat): it leaves the list before the next read.
    client.post("/api/cables", json={"switch": "sw-a-01", "port": "Gi1/0/7", "note": "Crew laptop"})
    assert client.get("/api/cables/clients").get_json()["unplanned"] == {"count": 0, "rows": []}


def test_a_switch_that_does_not_answer_is_named(hall, client):
    hall["fdb"].broken.add("sw-a-01")
    body = read(hall, client)
    assert body["failed"] == [{"switch": "sw-a-01", "error": "LibreNMS timed out"}]
    assert body["unplanned"]["count"] == 0 and hall["fdb"].arp_asked == []


def test_reads_are_started_in_the_background_at_most_every_two_minutes(hall, client, monkeypatch):
    started = []
    monkeypatch.setattr(port_clients, "_start", started.append)
    assert client.get("/api/cables/clients?read=1").get_json()["started"] is True
    body = client.get("/api/cables/clients?read=1").get_json()
    assert body["started"] is False and body["reading"] is True      # one is running already
    started[0]()                                                      # it finishes
    body = client.get("/api/cables/clients?read=1").get_json()
    assert body["started"] is False and body["reading"] is False and body["as_of"]   # and is fresh
    assert client.get("/api/cables/clients").get_json()["started"] is False         # a plain look reads nothing


def test_networks_merge_the_seat_ips():
    assert port_clients.networks(["192.0.2.1", "192.0.2.200", "198.51.100.5", "2001:db8::1"]) == [
        "192.0.2.0/24", "198.51.100.0/24"]


def test_viewers_without_the_seat_mapping_may_not_look(app_module):
    from tests.test_rbac import sign_in_as
    assert sign_in_as(app_module, "vi4", "viewer").get("/api/cables/clients").status_code == 403
    assert sign_in_as(app_module, "te4", "tech").get("/api/cables/clients").status_code == 200
