"""Firewalls and the seat ranges they serve (issue #470): the plan, failover, the seat panel."""
import pytest

from floorbit import firewalls, sources
from integrations import seat_sources


class Source:
    def __init__(self):
        self.up = {}
        self.broken = False

    def enabled(self):
        return True

    def devices(self):
        if self.broken:
            raise OSError("unreachable")
        return [{"display": name, "hostname": f"{name}.example.com", "status": int(up)} for name, up in self.up.items()]


@pytest.fixture
def net(client, monkeypatch):
    src = Source()
    monkeypatch.setattr(sources, "monitoring", lambda: src)
    monkeypatch.setattr(seat_sources, "load", lambda *a, **k: {
        "A-1": {"ip_address": "192.0.2.10"}, "A-2": {"ip_address": "192.0.2.40"}, "A-3": {"ip_address": "192.0.2.41"},
        "B-1": {"ip_address": "198.51.100.7"}, "B-2": {"ip_address": "not an ip"}})
    firewalls.health.reset()
    for name, role in (("fw-01", "firewall"), ("fw-02", "firewall"), ("fw-03", "firewall"), ("sw-a-01", "switch")):
        assert client.post("/api/inventory", json={"name": name, "role": role}).status_code in (200, 201)
    src.up = {"fw-01": True, "fw-02": True, "fw-03": True}
    yield src
    firewalls.health.reset()


def _add(client, cidr, *line, name=""):
    return client.post("/api/firewalls/ranges", json={"cidr": cidr, "firewalls": list(line), "name": name})


def test_a_range_names_its_firewalls_in_order(client, net):
    r = _add(client, "192.0.2.7/27", "fw-01", "FW-02", "fw-01", name="  Block   A ")
    assert r.status_code == 201
    assert (r.get_json()["cidr"], r.get_json()["firewalls"], r.get_json()["name"]) == (
        "192.0.2.0/27", ["fw-01", "fw-02"], "Block A")
    assert _add(client, "192.0.2.0/27", "fw-03").status_code == 409
    assert _add(client, "192.0.2.0/33", "fw-01").status_code == 400
    assert _add(client, "192.0.2.64/27", "sw-a-01").status_code == 400        # not a firewall
    assert _add(client, "192.0.2.64/27").status_code == 400
    row = r.get_json()
    changed = client.put(f"/api/firewalls/ranges/{row['id']}", json={"firewalls": ["fw-03"]}).get_json()
    assert (changed["cidr"], changed["firewalls"]) == ("192.0.2.0/27", ["fw-03"])
    assert client.delete(f"/api/firewalls/ranges/{row['id']}").status_code == 200
    assert client.delete(f"/api/firewalls/ranges/{row['id']}").status_code == 404
    assert client.get("/api/firewalls").get_json()["ranges"] == []


def test_a_range_fails_over_to_the_next_firewall_that_is_up(client, net):
    _add(client, "192.0.2.0/27", "fw-01", "fw-02")
    _add(client, "192.0.2.32/27", "fw-02", "fw-03")
    _add(client, "192.0.2.40/29", "fw-03")                       # more specific: A-2 and A-3 are here
    net.up["fw-02"] = False
    net.up["fw-03"] = False
    body = client.get("/api/firewalls").get_json()
    by_cidr = {r["cidr"]: r for r in body["ranges"]}
    assert (by_cidr["192.0.2.0/27"]["now"], by_cidr["192.0.2.0/27"]["state"]) == ("fw-01", "primary")
    assert (by_cidr["192.0.2.32/27"]["now"], by_cidr["192.0.2.32/27"]["state"]) == (None, "down")
    assert [r["seats"] for r in body["ranges"]] == [1, 0, 2]
    assert body["counts"] == {"firewalls": 3, "down": 2, "failover": 0, "without": 2}
    firewalls.health.reset()
    net.up["fw-03"] = True
    body = client.get("/api/firewalls").get_json()
    by_cidr = {r["cidr"]: r for r in body["ranges"]}
    assert (by_cidr["192.0.2.32/27"]["now"], by_cidr["192.0.2.32/27"]["state"]) == ("fw-03", "failover")
    fw2 = next(f for f in body["firewalls"] if f["name"] == "fw-02")
    assert (fw2["status"], fw2["serving"], fw2["planned"], fw2["backup_for"]) == (
        "offline", [], ["192.0.2.32/27"], ["192.0.2.0/27"])


def test_an_unreadable_source_is_unknown_not_down(client, net):
    _add(client, "192.0.2.0/27", "fw-01", "fw-02")
    net.broken = True
    body = client.get("/api/firewalls").get_json()
    assert body["unread"] is True
    assert (body["ranges"][0]["now"], body["ranges"][0]["state"]) == ("fw-01", "unknown")


def test_the_seat_panel_says_which_firewall_and_never_the_ip(client, net):
    _add(client, "192.0.2.0/27", "fw-01", "fw-02", name="Block A")
    client.post("/api/seat-blocks", json={"name": "A", "x": 40, "y": 50, "cols": 3, "rows": 1})
    net.up["fw-01"] = False
    seat = client.get("/api/plan/seats/A-1").get_json()
    assert seat["firewall"] == {"intended": "fw-01", "now": "fw-02", "state": "failover", "range": "Block A"}
    assert client.get("/api/plan/seats/A-2").get_json()["firewall"] is None       # no range covers it
    assert "192.0.2" not in str(firewalls.for_seat("A-1"))


def test_viewers_see_the_firewalls_but_do_not_change_them(app_module):
    from tests.test_rbac import sign_in_as
    viewer = sign_in_as(app_module, "vi9", "viewer")
    assert viewer.get("/api/firewalls").status_code == 200
    assert viewer.post("/api/firewalls/ranges", json={}).status_code == 403


def test_a_down_firewall_is_red_on_the_health_wall(client, net):
    _add(client, "192.0.2.0/27", "fw-01", "fw-02")
    _add(client, "192.0.2.32/27", "fw-01")
    net.up["fw-01"] = False
    tiles = {t["name"]: t for t in firewalls.health_checks()}
    assert (tiles["fw-01"]["kind"], tiles["fw-01"]["status"]) == ("firewall", "down")
    assert tiles["fw-01"]["summary"] == "192.0.2.32/27 without a firewall"
    assert (tiles["fw-02"]["status"], tiles["fw-02"]["summary"]) == ("up", "Serves 1 range, 1 seat")
