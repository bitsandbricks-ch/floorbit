"""No Shut port on uplinks (#886): the Security page and the port actions refuse a port that leads to more seats."""
import pytest

from floorbit import links, sources, uplink_guard

pytestmark = pytest.mark.usefixtures("lan_here")


class Neighbours:
    def __init__(self, seen):
        self.seen = seen

    def neighbours(self, hostname):
        return self.seen.get(hostname, [])


@pytest.fixture
def no_neighbours(monkeypatch):
    seen = {}
    monkeypatch.setattr(sources, "monitoring", lambda: Neighbours(seen))
    return seen


def test_an_edge_port_is_no_uplink(no_neighbours):
    assert uplink_guard.reason("sw-b-01", "Gi1/0/4", {}) is None


def test_a_topology_link_makes_an_uplink_whatever_the_port_is_called(no_neighbours):
    data = {links.KEY: [{"id": "l1", "a": "core-01.example.com", "a_port": "Te1/1/1",
                         "b": "sw-d-02", "b_port": "TenGigabitEthernet1/0/1"}]}
    assert uplink_guard.reason("sw-d-02", "Te1/0/1", data) == "topology"
    assert uplink_guard.reason("core-01", "TenGigabitEthernet1/1/1", data) == "topology"
    assert uplink_guard.reason("sw-d-02", "Te1/0/2", data) is None


def test_an_lldp_neighbour_or_the_name_makes_an_uplink(no_neighbours):
    no_neighbours["sw-a-01"] = [{"port": "Gi1/0/48", "remote": "core-01"}]
    assert uplink_guard.reason("sw-a-01", "GigabitEthernet1/0/48", {}) == "neighbour"
    assert uplink_guard.reason("sw-a-01", "Port-channel-uplink", {}) == "pattern"


def test_a_source_that_fails_does_not_block_the_check(monkeypatch):
    class Broken:
        def neighbours(self, hostname):
            raise RuntimeError("down")
    monkeypatch.setattr(sources, "monitoring", lambda: Broken())
    assert uplink_guard.reason("sw-a-01", "Gi1/0/3", {}) is None


def test_the_port_actions_refuse_an_uplink_but_turn_it_on(client, no_neighbours):
    assert client.post("/api/inventory", json={"name": "sw-a-01", "mgmt_ip": "198.51.100.4"}).status_code in (200, 201)
    client.put("/api/settings/plugins/demo", json={"enabled": True})
    no_neighbours["sw-a-01"] = [{"port": "Gi1/0/48", "remote": "core-01"}]
    for action in ("shutdown", "bounce"):
        resp = client.post(f"/api/ports/{action}", json={"switch": "sw-a-01", "port": "Gi1/0/48"})
        assert resp.status_code == 409 and "switch terminal" in resp.get_json()["error"]
    # Turning a port back on is never what cuts a hall.
    assert client.post("/api/ports/enable", json={"switch": "sw-a-01", "port": "Gi1/0/48"}).status_code == 200


def test_the_demo_storm_on_an_uplink_offers_no_shut_port(client):
    client.put("/api/settings/plugins/demo", json={"enabled": True})
    found = {f["kind"]: f for f in client.post("/api/security/check").get_json()["findings"]}
    assert found["storm"]["uplink"] == "neighbour"
    assert found["arp-spoof"]["uplink"] is None
