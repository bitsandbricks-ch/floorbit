"""Firewalls and the seat ranges they serve (issue #470): the plan, failover, the seat panel."""
import pytest

from floorbit import firewalls, sources
from integrations import seat_sources

# These run the plugins the way the local agent does (tests/conftest.py, lan_here).
pytestmark = pytest.mark.usefixtures("lan_here")


class Source:
    name, label = "nms", "Monitoring"

    def __init__(self):
        self.up = {}
        self.broken = False
        self.on = True

    def enabled(self):
        return self.on

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


def _add(client, cidr, *line, name="", fallback=None):
    body = {"cidr": cidr, "firewalls": list(line), "name": name}
    if fallback is not None:
        body["fallback"] = fallback
    return client.post("/api/firewalls/ranges", json=body)


def _parts(body, cidr):
    row = next(r for r in body["ranges"] if r["cidr"] == cidr)
    return [(p["cidr"], p["firewall"], p["now"], p["state"]) for p in row["parts"]]


def test_a_range_names_its_firewalls_in_order(client, net):
    r = _add(client, "192.0.2.7/27", "fw-01", "FW-02", "fw-01", name="  Block   A ")
    assert r.status_code == 201
    assert (r.get_json()["cidr"], r.get_json()["firewalls"], r.get_json()["name"], r.get_json()["fallback"]) == (
        "192.0.2.0/27", ["fw-01", "fw-02"], "Block A", [])
    assert _add(client, "192.0.2.0/27", "fw-03").status_code == 409
    assert _add(client, "192.0.2.0/33", "fw-01").status_code == 400
    assert _add(client, "192.0.2.64/27", "sw-a-01").status_code == 400        # not a firewall
    assert _add(client, "192.0.2.64/27").status_code == 400
    assert _add(client, "192.0.2.64/32", "fw-01", "fw-02").status_code == 400  # one address, two firewalls
    row = r.get_json()
    changed = client.put(f"/api/firewalls/ranges/{row['id']}", json={"firewalls": ["fw-03"]}).get_json()
    assert (changed["cidr"], changed["firewalls"]) == ("192.0.2.0/27", ["fw-03"])
    assert client.delete(f"/api/firewalls/ranges/{row['id']}").status_code == 200
    assert client.delete(f"/api/firewalls/ranges/{row['id']}").status_code == 404
    assert client.get("/api/firewalls").get_json()["ranges"] == []


def test_a_range_over_several_firewalls_is_cut_into_equal_parts(client, net):
    # Mike, 2026-11-24: four firewalls, and each quarter of the range goes to its own.
    assert _add(client, "192.0.2.0/24", "fw-01", "fw-02", "fw-03", "fw-01").status_code == 201
    body = client.get("/api/firewalls").get_json()
    assert body["ranges"][0]["firewalls"] == ["fw-01", "fw-02", "fw-03"]     # a firewall once only
    assert [p[:2] for p in _parts(body, "192.0.2.0/24")] == [
        ("192.0.2.0-192.0.2.85", "fw-01"), ("192.0.2.86-192.0.2.170", "fw-02"), ("192.0.2.171-192.0.2.255", "fw-03")]
    client.delete(f"/api/firewalls/ranges/{body['ranges'][0]['id']}")
    client.post("/api/inventory", json={"name": "fw-04", "role": "firewall"})
    net.up["fw-04"] = True
    assert _add(client, "192.0.2.0/24", "fw-01", "fw-02", "fw-03", "fw-04").status_code == 201
    body = client.get("/api/firewalls").get_json()
    assert [p[:2] for p in _parts(body, "192.0.2.0/24")] == [
        ("192.0.2.0/26", "fw-01"), ("192.0.2.64/26", "fw-02"), ("192.0.2.128/26", "fw-03"), ("192.0.2.192/26", "fw-04")]
    # A-1 (.10) is in the first quarter, A-2 and A-3 (.40, .41) too.
    assert [p["seats"] for p in body["ranges"][0]["parts"]] == [3, 0, 0, 0] and body["ranges"][0]["seats"] == 3
    fw1 = next(f for f in body["firewalls"] if f["name"] == "fw-01")
    assert (fw1["planned"], fw1["serving"], fw1["seats"]) == (["192.0.2.0/26"], ["192.0.2.0/26"], 3)
    assert firewalls.for_seat("A-1")["intended"] == "fw-01"


def test_a_part_goes_to_the_fallback_while_its_firewall_is_down(client, net):
    _add(client, "192.0.2.0/26", "fw-01", "fw-02", fallback=["fw-03", "fw-01"])
    _add(client, "198.51.100.0/24", "fw-02")
    net.up["fw-01"] = False
    body = client.get("/api/firewalls").get_json()
    assert body["ranges"][0]["fallback"] == ["fw-03"]                  # not one of its own firewalls
    assert _parts(body, "192.0.2.0/26") == [("192.0.2.0/27", "fw-01", "fw-03", "failover"),
                                             ("192.0.2.32/27", "fw-02", "fw-02", "primary")]
    assert body["ranges"][0]["state"] == "failover"
    fw3 = next(f for f in body["firewalls"] if f["name"] == "fw-03")
    assert (fw3["taken_over"], fw3["planned"]) == (["192.0.2.0/27"], [])
    firewalls.health.reset()
    net.up["fw-02"] = False
    body = client.get("/api/firewalls").get_json()
    # No fallback: its part has no firewall left.
    assert _parts(body, "198.51.100.0/24") == [("198.51.100.0/24", "fw-02", None, "down")]
    # Both halves of the first range on fw-03 now.
    assert body["counts"] == {"firewalls": 3, "down": 2, "failover": 2, "without": 1}


def test_an_unreadable_source_is_unknown_not_down(client, net):
    _add(client, "192.0.2.0/27", "fw-01", "fw-02")
    net.broken = True
    body = client.get("/api/firewalls").get_json()
    assert body["unread"] is True
    assert body["ranges"][0]["state"] == "unknown"
    assert {p["state"] for p in body["ranges"][0]["parts"]} == {"unknown"}


def test_without_a_monitoring_source_it_is_setup_not_trouble(client, net):
    # A fresh install showed "can't be read right now", as if something had broken.
    _add(client, "192.0.2.0/27", "fw-01")
    net.on = False
    body = client.get("/api/firewalls").get_json()
    assert body["monitoring"] is False and body["unread"] is False
    assert _parts(body, "192.0.2.0/27") == [("192.0.2.0/27", "fw-01", "fw-01", "unknown")]
    net.on = True
    firewalls.health.reset()
    assert client.get("/api/firewalls").get_json()["monitoring"] is True


def test_the_seat_panel_says_which_firewall_and_never_the_ip(client, net):
    _add(client, "192.0.2.0/27", "fw-01", fallback=["fw-02"], name="Block A")
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
    _add(client, "192.0.2.0/27", "fw-01", fallback=["fw-02"])
    _add(client, "192.0.2.32/27", "fw-01")
    net.up["fw-01"] = False
    tiles = {t["name"]: t for t in firewalls.health_checks()}
    assert (tiles["fw-01"]["kind"], tiles["fw-01"]["status"]) == ("firewall", "down")
    assert tiles["fw-01"]["summary"] == "192.0.2.32/27 without a firewall"
    assert (tiles["fw-02"]["status"], tiles["fw-02"]["summary"]) == ("up", "Serves 1 range, 1 seat")


def test_a_range_can_be_any_span_of_addresses(client, net):
    # The core routes .0 to .128 to one firewall and the rest to another: not CIDR blocks (#866).
    assert _add(client, "192.0.2.0 - 192.0.2.128", "fw-01").status_code == 201
    assert _add(client, "192.0.2.129-192.0.2.255", "fw-03").status_code == 201
    # A span that is one network is written as that network.
    assert _add(client, "198.51.100.0-198.51.100.255", "fw-03").get_json()["cidr"] == "198.51.100.0/24"
    body = client.get("/api/firewalls").get_json()
    assert [r["cidr"] for r in body["ranges"]] == [
        "192.0.2.0-192.0.2.128", "192.0.2.129-192.0.2.255", "198.51.100.0/24"]
    seats = {r["cidr"]: r["seats"] for r in body["ranges"]}
    assert seats["192.0.2.0-192.0.2.128"] == 3 and seats["198.51.100.0/24"] == 1
    # A narrower range inside one wins, like a longer prefix.
    assert _add(client, "192.0.2.32/27", "fw-03").status_code == 201
    assert firewalls.for_seat("A-2")["intended"] == "fw-03"
    assert firewalls.for_seat("A-1")["intended"] == "fw-01"


@pytest.mark.parametrize("text", ["192.0.2.9-192.0.2.1", "192.0.2.1-2001:db8::1", "192.0.2.1-5", "192.0.2.1-"])
def test_a_span_must_run_forwards_in_one_family(client, net, text):
    r = _add(client, text, "fw-01")
    assert r.status_code == 400 and "from-to" in r.get_json()["error"]


def test_ranges_that_only_cross_are_refused(client, net):
    assert _add(client, "192.0.2.0-192.0.2.100", "fw-01").status_code == 201
    r = _add(client, "192.0.2.50-192.0.2.150", "fw-03")
    assert r.status_code == 409 and "in part" in r.get_json()["error"]
    assert _add(client, "192.0.2.10-192.0.2.20", "fw-03").status_code == 201   # inside: fine


def test_the_plan_layer_lists_seats_off_their_planned_firewall_by_name_only(client, net):
    assert client.get("/api/firewalls/seats").get_json() == {"enabled": False, "seats": {}}
    _add(client, "192.0.2.0/26", "fw-01", "fw-02", fallback=["fw-03"])
    _add(client, "198.51.100.0/24", "fw-03")
    net.up["fw-02"] = False
    net.up["fw-03"] = False
    body = client.get("/api/firewalls/seats").get_json()
    # A-1 is in fw-01's half; A-2 and A-3 in fw-02's, whose fallback is down too.
    assert body == {"enabled": True, "seats": {
        "A-2": {"now": None, "intended": "fw-02", "state": "down"},
        "A-3": {"now": None, "intended": "fw-02", "state": "down"},
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
