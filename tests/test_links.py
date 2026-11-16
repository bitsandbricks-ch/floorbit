"""Links between switches (issue #468): type and speed, live state, LLDP suggestions, the topology."""
import pytest

from floorbit import links, sources
from tests.test_attention import Monitoring, port


class Lldp(Monitoring):
    def __init__(self):
        super().__init__()
        self.seen = {}

    def neighbours(self, hostname):
        return self.seen.get(hostname, [])


@pytest.fixture
def net(client, monkeypatch):
    mon = Lldp()
    monkeypatch.setattr(sources, "monitoring", lambda: mon)
    links.reader.reset()
    for name, role in (("core-01", "router"), ("dist-01", "switch"), ("sw-a-01", "switch"), ("ap-01", "access-point")):
        assert client.post("/api/inventory", json={"name": name, "role": role}).status_code in (200, 201)
    yield mon
    links.reader.reset()


def _add(client, **body):
    return client.post("/api/links", json={"a": "sw-a-01", "a_port": "Te1/1/1", "b": "dist-01", "b_port": "Te1/0/1",
                                           "type": "fiber-mm", "speed": 10, **body})


def test_a_link_has_a_type_and_speed_and_its_ports_are_its_own(client, net):
    r = _add(client)
    assert r.status_code == 201 and r.get_json()["speed"] == 10
    assert _add(client, a_port="TenGigabitEthernet1/1/1", b_port="Te1/0/9").status_code == 409   # same port, long name
    assert _add(client, b="sw-a-01").status_code == 400
    assert _add(client, b="nope-99").status_code == 400
    assert _add(client, a_port="Te1/1/2", b_port="Te1/0/2", type="cat7").status_code == 400
    assert _add(client, a_port="Te1/1/2", b_port="Te1/0/2", speed=2).status_code == 400
    link = r.get_json()
    assert client.put(f"/api/links/{link['id']}", json={"speed": 25}).get_json()["speed"] == 25
    assert client.delete(f"/api/links/{link['id']}").status_code == 200
    assert client.get("/api/links").get_json()["links"] == []


def test_the_topology_says_which_links_are_down_or_slow(client, net):
    _add(client)
    _add(client, a="dist-01", a_port="Fo1/1/1", b="core-01", b_port="Fo1/0/1", speed=40)
    net.set("sw-a-01", {**port("TenGigabitEthernet1/1/1"), "speed_bps": 1_000_000_000})
    net.set("dist-01", port("Fo1/1/1", state="down"))
    body = client.get("/api/links").get_json()
    by_port = {link["a_port"]: link for link in body["links"]}
    assert (by_port["Te1/1/1"]["issue"], by_port["Te1/1/1"]["speed_bps"]) == ("slow", 1_000_000_000)
    assert by_port["Fo1/1/1"]["issue"] == "down" and by_port["Fo1/1/1"]["media"] == "fiber"
    assert body["counts"] == {"links": 2, "down": 1, "slow": 1}
    assert [n["name"] for n in body["nodes"]] == ["core-01", "dist-01", "sw-a-01"]          # no access points


def test_lldp_neighbours_no_link_explains_are_suggested_once(client, net):
    _add(client)
    net.seen = {
        # The first is planned already.
        "dist-01": [{"port": "Te1/0/1", "remote": "sw-a-01", "remote_port": "Te1/1/1", "protocol": "lldp"},
                    {"port": "Fo1/1/1", "remote": "core-01.example.com", "remote_port": "Fo1/0/1", "protocol": "lldp"}],
        "core-01": [{"port": "Fo1/0/1", "remote": "dist-01", "remote_port": "Fo1/1/1", "protocol": "cdp"},
                    {"port": "Gi0/1", "remote": "isp-router", "remote_port": "ge-0/0/0"}],  # unknown
    }
    net.set("dist-01", {**port("Fo1/1/1"), "speed_bps": 40_000_000_000})
    [s] = client.get("/api/links").get_json()["suggestions"]
    assert {(s["a"], s["a_port"]), (s["b"], s["b_port"])} == {("dist-01", "Fo1/1/1"), ("core-01", "Fo1/0/1")}
    links.reader.reset()
    assert client.post("/api/links", json={k: s[k] for k in ("a", "a_port", "b", "b_port")}).status_code == 201
    assert client.get("/api/links").get_json()["suggestions"] == []


def test_viewers_see_the_topology_but_do_not_change_it(app_module):
    from tests.test_rbac import sign_in_as
    viewer = sign_in_as(app_module, "vi8", "viewer")
    assert viewer.get("/api/links").status_code == 200
    assert viewer.post("/api/links", json={}).status_code == 403


def test_librenms_neighbours_name_the_local_port(monkeypatch):
    from floorbit.builtin_plugins.librenms import client

    class Answer:
        ok, status_code = True, 200

        def __init__(self, body):
            self.body = body

        def json(self):
            return self.body

        def raise_for_status(self):
            pass

    def fake_get(url, params=None, **kwargs):
        if url.endswith('/ports'):
            return Answer({'ports': [{'port_id': 5, 'ifName': 'Te1/1/1'}]})
        assert url.endswith('/devices/14/links')
        return Answer({'links': [
            {'local_port_id': 5, 'remote_hostname': 'dist-01', 'remote_port': 'Te1/0/1', 'protocol': 'lldp'},
            {'local_port_id': 6, 'remote_hostname': 'dist-02', 'remote_port': 'Te1/0/1'},      # a port it didn't list
            {'local_port_id': 5, 'remote_hostname': '', 'remote_port': 'x'}]})

    monkeypatch.setattr(client.requests, 'get', fake_get)
    monkeypatch.setattr(client, 'fetch_librenms_device_by_hostname', lambda h, headers: {'device_id': 14})
    assert client.neighbours('sw-a-01') == [{'port': 'Te1/1/1', 'remote': 'dist-01', 'remote_port': 'Te1/0/1',
                                             'protocol': 'lldp'}]


def test_links_between_placed_switches_are_drawn_on_the_plan(client, net):
    client.post("/api/seat-blocks", json={"name": "A", "x": 40, "y": 50, "cols": 2, "rows": 1})
    for name, x in (("sw-a-01", 30), ("dist-01", 60)):
        client.post("/api/switches", json={"name": name, "x": x, "y": 20})
    _add(client)
    _add(client, a="dist-01", a_port="Fo1/1/1", b="core-01", b_port="Fo1/0/1", speed=40)    # core-01 isn't placed
    net.set("sw-a-01", port("Te1/1/1", state="down"))
    assert client.get("/api/plan").get_json()["links"][0]["issue"] == ""        # the plan doesn't read switches
    client.get("/api/links")                                                    # the topology page did
    [drawn] = client.get("/api/plan").get_json()["links"]
    assert (drawn["a"], drawn["b"], drawn["media"], drawn["speed"], drawn["issue"]) == (
        "sw-a-01", "dist-01", "fiber", 10, "down")


def test_seat_cables_have_a_type_and_speed_too(client):
    r = client.post("/api/cables", json={"switch": "sw-a-01", "port": "Gi1/0/1", "seat": "A-1", "type": "cat6a",
                                         "speed": 1})
    assert r.status_code == 201 and (r.get_json()["type"], r.get_json()["speed"]) == ("cat6a", 1)
    cable = r.get_json()
    assert client.patch(f"/api/cables/{cable['id']}", json={"speed": 3}).status_code == 400
    assert client.patch(f"/api/cables/{cable['id']}", json={"type": "cat9"}).status_code == 400
    assert "type,speed,note,source" in client.get("/api/cables.csv").get_data(as_text=True).splitlines()[0]
