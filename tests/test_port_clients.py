"""Clients on seat ports that the patch plan doesn't explain (issue #473), from MAC tables and ARP."""
import pytest

from floorbit import port_clients, sources
from integrations import events, seat_sources
from tests.test_rbac import sign_in_as


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


def test_a_dhcp_lease_fills_in_what_arp_has_not_seen_yet(hall, client):
    from floorbit.dhcp_leases import leases
    hall["fdb"].tables["sw-a-01"] = [{"port": "Gi1/0/2", "mac": mac(3)}]
    leases.observe(f"DHCPACK on 192.0.2.13 to {mac(3)} via eth1")       # A-3's machine, before any ARP poll
    [moved] = read(hall, client)["moved"]["rows"]
    assert (moved["seat"], moved["ip"], moved["ip_seat"]) == ("A-2", "192.0.2.13", "A-3")


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


def test_ips_without_a_port_and_seats_without_a_machine(hall, client, monkeypatch):
    """Issue #949: PCs that never check in show up from the tables LibreNMS polls anyway."""
    fdb = hall["fdb"]
    fdb.tables["sw-a-01"] = [{"port": "Gi1/0/1", "mac": mac(1)}, {"port": "Gi1/0/7", "mac": mac(7)}]
    fdb.arp_rows = [{"ipv4_address": "192.0.2.11", "mac_address": mac(1)},
                    {"ipv4_address": "192.0.2.1", "mac_address": mac(0xfe)},     # the gateway
                    {"ipv4_address": "192.0.2.50", "mac_address": mac(0x50)},    # nowhere on an edge port
                    {"ipv4_address": "192.0.2.12", "mac_address": mac(2)}]       # A-2's IP, no port seen
    from integrations import checkin
    monkeypatch.setattr(checkin, "load_all", lambda: {})
    body = read(hall, client)
    assert [r["ip"] for r in body["no_port"]["rows"]] == ["192.0.2.12", "192.0.2.50"]
    assert body["no_port"]["rows"][0]["ip_seat"] == "A-2"
    assert body["empty"]["count"] == 0                          # before check-ins: no noise
    monkeypatch.setattr(checkin, "load_all", lambda: {"A-1": {"nick": "x"}})
    body = read(hall, client)
    assert [r["seat"] for r in body["empty"]["rows"]] == ["A-2", "A-3", "A-4"]


def test_a_switch_that_did_not_answer_lists_no_portless_ips(hall, client):
    fdb = hall["fdb"]
    fdb.broken.add("sw-a-01")
    fdb.arp_rows = [{"ipv4_address": "192.0.2.50", "mac_address": mac(0x50)}]
    assert read(hall, client)["no_port"]["count"] == 0


def test_an_ignored_machine_leaves_the_lists(hall, client, app_module):
    fdb = hall["fdb"]
    fdb.tables["sw-a-01"] = [{"port": "Gi1/0/7", "mac": mac(7)}]
    fdb.arp_rows = [{"ipv4_address": "192.0.2.50", "mac_address": mac(0x50)}]
    body = read(hall, client)
    assert body["unplanned"]["count"] == 1 and body["no_port"]["count"] == 1
    r = client.post("/api/cables/clients/ignored", json={"mac": mac(7).upper(), "note": "printer"})
    assert r.status_code == 200
    assert client.post("/api/cables/clients/ignored", json={"mac": "nope"}).status_code == 400
    body = client.get("/api/cables/clients").get_json()            # gone now, before the next read
    assert body["unplanned"]["count"] == 0 and body["ignored"] == 1
    client.post("/api/cables/clients/ignored", json={"mac": mac(0x50)})
    assert read(hall, client)["no_port"]["count"] == 0
    [row, _] = client.get("/api/cables/clients/ignored").get_json()["ignored"]
    assert row["mac"] == mac(7) and row["note"] == "printer"
    assert client.delete(f"/api/cables/clients/ignored/{mac(7)}").status_code == 200
    assert read(hall, client)["unplanned"]["count"] == 1
    viewer = sign_in_as(app_module, "vi9", "viewer")
    assert viewer.post("/api/cables/clients/ignored", json={"mac": mac(9)}).status_code == 403
