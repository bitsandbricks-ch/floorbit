"""Seats behind a down switch or uplink (issue #950): floorbit/impact.py, the Problems list and the plan."""
import pytest

from floorbit import impact, links, sources
from floorbit.store import load_data
from tests.test_attention import Monitoring, port

#   core-01 (router)
#      |
#   dist-01 ── sw-a-01 ── sw-a-02      sw-b-01 hangs off dist-01 too
#      |
#   sw-b-01
BOXES = (("core-01", "router"), ("dist-01", "switch"), ("sw-a-01", "switch"), ("sw-a-02", "switch"),
         ("sw-b-01", "switch"))
LINKS = (("dist-01", "Fo1/1/1", "core-01", "Fo1/0/1"), ("sw-a-01", "Te1/1/1", "dist-01", "Te1/0/1"),
         ("sw-a-02", "Te1/1/1", "sw-a-01", "Te1/1/2"), ("sw-b-01", "Te1/1/1", "dist-01", "Te1/0/2"))
SEATS = {"sw-a-01": ("A-1", "A-2"), "sw-a-02": ("A-3",), "sw-b-01": ("B-1",)}


@pytest.fixture
def net(app_module, client, monkeypatch):
    mon = Monitoring()
    monkeypatch.setattr(sources, "monitoring", lambda: mon)
    links.reader.reset()
    ids = {}
    for name, role in BOXES:
        r = client.post("/api/inventory", json={"name": name, "role": role})
        assert r.status_code in (200, 201)
        ids[name] = r.get_json()["id"]
    for a, ap, b, bp in LINKS:
        assert client.post("/api/links", json={"a": a, "a_port": ap, "b": b, "b_port": bp}).status_code == 201
    for switch, seats in SEATS.items():
        for i, seat in enumerate(seats, 1):
            r = client.post("/api/cables", json={"switch": switch, "port": f"Gi1/0/{i}", "seat": seat})
            assert r.status_code == 201, r.get_json()
    monitor = app_module.app.extensions["floorbit_integrations"]["monitor"]
    yield {"mon": mon, "ids": ids, "monitor": monitor}
    monitor.statuses = {}
    links.reader.reset()


def _failures(app_module, offline, down_links=()):
    with app_module.app.test_request_context():
        return impact.failures(load_data(), offline, down_links)


def test_a_down_switch_takes_the_switches_behind_it_and_all_their_seats(app_module, net):
    found = _failures(app_module, ["sw-a-01"])
    assert found["switches"]["sw-a-01"] == {"behind": ["sw-a-02"], "seats": ["A-1", "A-2", "A-3"]}
    assert found["seats"] == {"A-1": "sw-a-01", "A-2": "sw-a-01", "A-3": "sw-a-01"}   # B-1 is fine


def test_a_switch_at_the_edge_takes_only_its_own_seats(app_module, net):
    found = _failures(app_module, ["sw-a-02"])
    assert found["switches"]["sw-a-02"] == {"behind": [], "seats": ["A-3"]}


def test_a_down_uplink_cuts_off_what_hangs_below_it(app_module, net):
    link = next(x for x in links.all_links(_data(app_module)) if x["a"] == "sw-a-01")
    found = _failures(app_module, [], [link["id"]])
    assert found["links"][link["id"]] == {"behind": ["sw-a-01", "sw-a-02"], "seats": ["A-1", "A-2", "A-3"]}
    assert found["seats"]["A-3"] == "sw-a-01 to dist-01"


def test_the_cause_furthest_up_gets_the_blame(app_module, net):
    # Both down, as monitoring sees it when sw-a-01 dies: sw-a-02 can't be reached either.
    found = _failures(app_module, ["sw-a-01", "sw-a-02"])
    assert found["seats"]["A-3"] == "sw-a-01"


def test_without_a_router_the_busiest_switch_is_the_core(app_module, client, net):
    core = net["ids"]["core-01"]
    assert client.delete(f"/api/inventory/{core}").status_code in (200, 204)
    found = _failures(app_module, ["sw-a-01"])
    assert found["switches"]["sw-a-01"]["behind"] == ["sw-a-02"]   # dist-01 has the most links


def _data(app_module):
    with app_module.app.app_context():
        return load_data()


def test_the_problems_list_counts_the_seats_and_points_at_the_cause(client, net):
    ids = net["ids"]
    net["monitor"].statuses = {ids[n]: {"id": ids[n], "name": n, "status": "offline", "since": 1}
                               for n in ("sw-a-01", "sw-a-02")}
    rows = {p["name"]: p for p in client.get("/api/problems").get_json()["problems"] if p["kind"] == "switch"}
    assert rows["sw-a-01"]["seats"] == ["A-1", "A-2", "A-3"] and rows["sw-a-01"]["behind"] == ["sw-a-02"]
    assert "cause" not in rows["sw-a-01"]
    assert rows["sw-a-02"]["cause"] == "sw-a-01"


def test_seats_behind_a_down_switch_are_down_on_the_plan(client, net, monkeypatch):
    ids = net["ids"]
    net["monitor"].statuses = {ids["sw-a-01"]: {"id": ids["sw-a-01"], "name": "sw-a-01", "status": "offline"}}
    monkeypatch.setattr(net["monitor"], "last_poll", 1)
    with client.application.test_request_context():
        from floorbit import seat_view
        cut = seat_view._cut_off(load_data())
    assert cut == {"A-1": "sw-a-01", "A-2": "sw-a-01", "A-3": "sw-a-01"}


def test_a_down_link_on_the_problems_list_carries_its_seats(client, net):
    net["mon"].set("dist-01", port("Te1/0/1", state="down"))
    links.refresher.read_once()
    [row] = [p for p in client.get("/api/problems").get_json()["problems"] if p["kind"] == "link"]
    assert row["seats"] == ["A-1", "A-2", "A-3"] and row["behind"] == ["sw-a-01", "sw-a-02"]
