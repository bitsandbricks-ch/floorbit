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
    assert body["counts"] == {"links": 2, "down": 1, "slow": 1, "miswired": 0}
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


def test_a_down_or_slow_link_is_a_problem_without_the_topology_open(client, net):
    _add(client)
    _add(client, a="dist-01", a_port="Fo1/1/1", b="core-01", b_port="Fo1/0/1", speed=40)
    net.set("sw-a-01", port("Te1/1/1", state="down"))
    net.set("dist-01", {**port("Fo1/1/1"), "speed_bps": 10_000_000_000})
    assert [p for p in client.get("/api/problems").get_json()["problems"] if p["kind"] == "link"] == []   # not read yet
    links.refresher.read_once()
    found = {p["id"].split(":")[0] + p["title"]: p for p in client.get("/api/problems").get_json()["problems"]
             if p["kind"] == "link"}
    assert [(p["level"], p["title"]) for p in found.values()] == [
        ("down", "Link sw-a-01 Te1/1/1 to dist-01 Te1/0/1 is down"),
        ("warn", "Link dist-01 Fo1/1/1 to core-01 Fo1/0/1 runs at 10G")]
    assert [p["where"] for p in found.values()] == ["Fiber multi-mode, 10G planned", "Fiber multi-mode, 40G planned"]
    de = [p for p in client.get("/api/problems", headers={"Accept-Language": "de-CH"}).get_json()["problems"]
          if p["kind"] == "link"]
    assert [(p["title"], p["where"]) for p in de] == [
        ("Verbindung sw-a-01 Te1/1/1 zu dist-01 Te1/0/1 ist down", "Glasfaser Multimode, 10G geplant"),
        ("Verbindung dist-01 Fo1/1/1 zu core-01 Fo1/0/1 läuft mit 10G", "Glasfaser Multimode, 40G geplant")]


def test_the_topology_says_which_boxes_are_up(client, net):
    from floorbit import firewalls
    firewalls.health.reset()
    net.devices = lambda: [{"display": "core-01", "hostname": "core-01.example.com", "status": 1},
                           {"display": "dist-01", "hostname": "dist-01.example.com", "status": 0}]
    body = client.get("/api/links").get_json()
    assert {n["name"]: n["status"] for n in body["nodes"]} == {
        "core-01": "online", "dist-01": "offline", "sw-a-01": "unknown"}
    firewalls.health.reset()


def test_lldp_checks_the_planned_links_and_a_wrong_patch_is_a_problem(client, net):
    # Issue #540: the plan says sw-a-01 Te1/1/1 goes to dist-01 Te1/0/1.
    _add(client)
    _add(client, a="dist-01", a_port="Fo1/1/1", b="core-01", b_port="Fo1/0/1", speed=40)
    _add(client, a="dist-01", a_port="Fo1/1/2", b="core-01", b_port="Fo1/0/2", speed=40)
    net.seen = {
        "sw-a-01": [{"port": "TenGigabitEthernet1/1/1", "remote": "dist-01.example.com", "remote_port": "Te1/0/1"}],
        # Patched into the wrong core port: core-01 Fo1/0/9, not Fo1/0/1.
        "dist-01": [{"port": "Fo1/1/1", "remote": "core-01", "remote_port": "Fo1/0/9", "protocol": "cdp"},
                    {"port": "Te1/0/1", "remote": "sw-a-01", "remote_port": "Te1/1/1"}],
    }
    body = client.get("/api/links").get_json()
    by_port = {(link["a"], link["a_port"]): link["lldp"] for link in body["links"]}
    assert by_port[("sw-a-01", "Te1/1/1")] == {"state": "seen"}
    assert by_port[("dist-01", "Fo1/1/1")] == {"state": "other", "at": "a", "remote": "core-01",
                                             "remote_port": "Fo1/0/9"}
    assert by_port[("dist-01", "Fo1/1/2")] == {"state": "unseen"}       # dist-01 tells, but nothing on Fo1/1/2
    assert body["counts"]["miswired"] == 1
    links.reader.reset()
    links.refresher.read_once()
    found = [p for p in client.get("/api/problems").get_json()["problems"] if p["id"].startswith("link-lldp:")]
    assert [(p["level"], p["title"]) for p in found] == [
        ("warn", "Link dist-01 Fo1/1/1 to core-01 Fo1/0/1: dist-01 Fo1/1/1 sees core-01 Fo1/0/9")]
    [de] = [p for p in client.get("/api/problems", headers={"Accept-Language": "de-CH"}).get_json()["problems"]
            if p["id"].startswith("link-lldp:")]
    assert (de["title"], de["where"]) == ("Verbindung dist-01 Fo1/1/1 zu core-01 Fo1/0/1: dist-01 Fo1/1/1 sieht "
                                          "core-01 Fo1/0/9", "Patch prüfen (LLDP/CDP)")


def test_without_lldp_from_the_source_a_link_is_not_judged(client, net):
    _add(client)
    [link] = client.get("/api/links").get_json()["links"]
    assert link["lldp"] is None


def test_the_switch_panel_lists_its_links_and_what_lldp_sees(client, net):
    _add(client)
    net.seen = {"sw-a-01": [{"port": "Te1/1/1", "remote": "dist-01", "remote_port": "Te1/0/1", "protocol": "lldp"},
                            {"port": "Gi1/0/48", "remote": "desk-switch", "remote_port": "Gi0/1", "protocol": "cdp"}]}
    body = client.get("/api/plan/switches/sw-a-01").get_json()
    [link] = body["links"]
    assert (link["port"], link["to"], link["to_port"], link["lldp"]) == ("Te1/1/1", "dist-01", "Te1/0/1",
                                                                        {"state": "seen"})
    assert body["neighbours"] == [{"port": "Gi1/0/48", "remote": "desk-switch", "remote_port": "Gi0/1",
                                   "protocol": "cdp"}]
    # From the other end the same link points back.
    [back] = client.get("/api/plan/switches/dist-01").get_json()["links"]
    assert (back["port"], back["to"], back["to_port"]) == ("Te1/0/1", "sw-a-01", "Te1/1/1")
