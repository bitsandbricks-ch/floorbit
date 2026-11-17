"""Firewalls and the seat ranges they serve (issue #470): the plan, failover, the seat panel."""
import pytest

from floorbit import firewalls, sources
from integrations import seat_sources


class Source:
    name, label = "nms", "Monitoring"

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


def test_a_network_splits_into_ranges_shared_over_the_firewalls(client, net):
    assert _add(client, "192.0.2.32/27", "fw-03").status_code == 201
    r = client.post("/api/firewalls/ranges/split",
                    json={"cidr": "192.0.2.0/24", "size": 27, "firewalls": ["fw-01", "fw-02", "fw-03"], "name": "Hall"})
    assert r.status_code == 201
    out = r.get_json()
    assert (out["added"], out["skipped"]) == (7, 1)
    got = {x["cidr"]: (x["name"], x["firewalls"]) for x in out["ranges"]}
    assert got["192.0.2.0/27"] == ("Hall 1", ["fw-01", "fw-02", "fw-03"])
    assert got["192.0.2.64/27"] == ("Hall 3", ["fw-03", "fw-01", "fw-02"])
    assert got["192.0.2.96/27"] == ("Hall 4", ["fw-01", "fw-02", "fw-03"])
    # The range planned before keeps its own line.
    kept = [x for x in client.get("/api/firewalls").get_json()["ranges"] if x["cidr"] == "192.0.2.32/27"]
    assert kept[0]["firewalls"] == ["fw-03"]
    again = client.post("/api/firewalls/ranges/split",
                        json={"cidr": "192.0.2.0/24", "size": 27, "firewalls": ["fw-01"]})
    assert again.status_code == 200 and again.get_json()["added"] == 0


@pytest.mark.parametrize("body", [
    {"cidr": "192.0.2.0/24", "size": 23, "firewalls": ["fw-01"]},
    {"cidr": "192.0.2.0/24", "size": "x", "firewalls": ["fw-01"]},
    {"cidr": "198.51.100.0/22", "size": 31, "firewalls": ["fw-01"]},
    {"cidr": "192.0.2.0/24", "size": 26, "firewalls": ["sw-a-01"]},
    {"cidr": "not a net", "size": 26, "firewalls": ["fw-01"]},
])
def test_a_split_that_makes_no_sense_is_refused(client, net, body):
    r = client.post("/api/firewalls/ranges/split", json=body)
    assert r.status_code == 400 and r.get_json()["error"]
    assert client.get("/api/firewalls").get_json()["ranges"] == []


def test_the_plan_layer_lists_seats_off_their_planned_firewall_by_name_only(client, net):
    assert client.get("/api/firewalls/seats").get_json() == {"enabled": False, "seats": {}}
    _add(client, "192.0.2.0/27", "fw-01", "fw-02")
    _add(client, "192.0.2.32/27", "fw-02")
    _add(client, "198.51.100.0/24", "fw-03")
    net.up["fw-01"] = False
    net.up["fw-03"] = False
    body = client.get("/api/firewalls/seats").get_json()
    assert body == {"enabled": True, "seats": {
        "A-1": {"now": "fw-02", "intended": "fw-01", "state": "failover"},
        "B-1": {"now": None, "intended": "fw-03", "state": "down"},
    }}
    assert "192.0.2" not in str(body) and "198.51" not in str(body)


NB_PREFIXES = [
    {"prefix": "192.0.2.0/27", "description": "Block A", "custom_fields": {"floorbit_firewalls": "fw-01, fw-02"}},
    {"prefix": "198.51.100.0/24", "description": "",
     "custom_fields": {"floorbit_firewalls": [{"id": 3, "name": "fw-02"}, {"id": 4, "display": "fw-03"}]}},
    {"prefix": "203.0.113.0/24", "custom_fields": {"floorbit_firewalls": None}},       # no firewalls: not a range
    {"prefix": "203.0.113.0/25", "custom_fields": {}},
]


def test_netbox_prefixes_become_ranges(app_module):
    from floorbit.builtin_plugins.netbox.plugin import firewall_range
    from tests.test_inventory import FakeHttp, FakeResponse, netbox_plugin
    assert firewall_range(NB_PREFIXES[0]) == {"cidr": "192.0.2.0/27", "name": "Block A",
                                              "firewalls": ["fw-01", "fw-02"]}
    assert firewall_range(NB_PREFIXES[1])["firewalls"] == ["fw-02", "fw-03"]
    assert firewall_range(NB_PREFIXES[2]) is None and firewall_range(NB_PREFIXES[3]) is None
    registry = app_module.app.extensions["floorbit_plugins"]
    http = FakeHttp({"/api/ipam/prefixes/": FakeResponse({"results": NB_PREFIXES, "next": None})})
    assert [r["cidr"] for r in netbox_plugin(registry, http).firewall_ranges()] == ["192.0.2.0/27", "198.51.100.0/24"]
    assert http.calls[0][1]["cf_floorbit_firewalls__empty"] == "false"     # NetBox filters, not us


def test_import_ranges_from_netbox(app_module, client, net, monkeypatch):
    nb_class = app_module.app.extensions["floorbit_plugins"].specs["netbox"].plugin_class()
    listed = [{"cidr": "192.0.2.0/27", "name": "Block A", "firewalls": ["fw-01", "fw-02"]},
              {"cidr": "198.51.100.0/24", "name": "", "firewalls": ["fw-02", "fw-03"]},
              {"cidr": "203.0.113.0/24", "name": "", "firewalls": ["fw-99"]},       # not in the inventory
              {"cidr": "192.0.2.64/27", "name": "", "firewalls": ["fw-03"]}]       # the crew planned it
    monkeypatch.setattr(nb_class, "firewall_ranges", lambda self: list(listed))
    assert _add(client, "192.0.2.64/27", "fw-01").status_code == 201
    assert client.get("/api/firewalls").get_json()["can_import"] is True

    r = client.post("/api/firewalls/ranges/import")
    assert r.status_code == 200, r.get_json()
    body = r.get_json()
    assert body["added"] == 2 and len(body["errors"]) == 2
    rows = {x["cidr"]: x for x in client.get("/api/firewalls").get_json()["ranges"]}
    assert rows["192.0.2.0/27"]["source"] == "import" and rows["192.0.2.0/27"]["plugin"] == "NetBox"
    assert rows["192.0.2.64/27"]["source"] == "floorbit" and rows["192.0.2.64/27"]["firewalls"] == ["fw-01"]
    imported = rows["198.51.100.0/24"]
    edit = client.put(f"/api/firewalls/ranges/{imported['id']}", json={"firewalls": ["fw-01"]})
    assert edit.status_code == 409 and "NetBox" in edit.get_json()["error"]

    # Importing again replaces the last import; a prefix gone from NetBox goes here too.
    listed.pop(0)
    assert client.post("/api/firewalls/ranges/import").get_json()["added"] == 1
    assert sorted(x["cidr"] for x in client.get("/api/firewalls").get_json()["ranges"]) == [
        "192.0.2.64/27", "198.51.100.0/24"]

    # NetBox down: the last import stays.
    def broken(self):
        from floorbit.plugins.base import PluginError
        raise PluginError("NetBox answered 503 for the prefix list")
    monkeypatch.setattr(nb_class, "firewall_ranges", broken)
    r = client.post("/api/firewalls/ranges/import")
    assert r.status_code == 502 and "503" in r.get_json()["error"]
    assert len(client.get("/api/firewalls").get_json()["ranges"]) == 2


def test_only_planners_import(app_module, client, net):
    from tests.test_rbac import sign_in_as
    viewer = sign_in_as(app_module, "vi1", "viewer")
    assert viewer.post("/api/firewalls/ranges/import").status_code == 403


def test_with_the_status_monitor_polling_the_page_never_asks_the_source_itself(client, net):
    from integrations.monitor import StatusMonitor
    _add(client, "192.0.2.0/27", "fw-01", "fw-02")
    monitor = StatusMonitor(lambda: [])
    monitor.poll_once()                                # answered: fw-01 and fw-02 up
    asked = []
    net.devices = lambda: asked.append(1) or []        # a hanging source would make the page wait
    assert client.get("/api/firewalls").get_json()["ranges"][0]["state"] == "primary"
    assert asked == []

    firewalls.health.reset()
    net.devices = lambda: (_ for _ in ()).throw(OSError("unreachable"))
    with pytest.raises(OSError):
        monitor.poll_once()                            # its last poll failed: unknown, like before
    assert client.get("/api/firewalls").get_json()["ranges"][0]["state"] == "unknown"
