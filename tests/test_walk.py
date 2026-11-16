"""Walking the row (issue #473): which port just came up, and putting a seat on its port."""
import time

import pytest

from floorbit import sources, walk
from integrations import events
from tests.test_attention import Monitoring, port


@pytest.fixture
def hall(client, app_module, monkeypatch):
    mon = Monitoring()
    monkeypatch.setattr(sources, "monitoring", lambda: mon)
    monkeypatch.setattr(events, "publish", lambda kind, data=None, origin=None: None)
    monkeypatch.setattr(walk, "walks", walk.Walks())
    return {"mon": mon, "app": app_module.app}


def test_a_link_up_in_syslog_names_the_port_at_once(hall, client, monkeypatch):
    monkeypatch.setenv("SYSLOG_ENABLED", "1")
    receiver = hall["app"].extensions["floorbit_syslog"]
    since = time.time() - 1
    lines = [
        "<187>%LINK-3-UPDOWN: Interface GigabitEthernet1/0/5, changed state to up",
        "<189>%LINEPROTO-5-UPDOWN: Line protocol on Interface GigabitEthernet1/0/5, changed state to up",
        "<187>%LINK-3-UPDOWN: Interface GigabitEthernet1/0/6, changed state to down",     # down: not it
        "<30>ether7 link up (speed 1G, full duplex)",                                       # MikroTik
    ]
    for raw in lines:
        receiver.receive(raw, "192.0.2.201", check=False, device="sw-wk-01")
    receiver.receive("<187>%LINK-3-UPDOWN: Interface Gi1/0/9, changed state to up", "192.0.2.202", check=False,
                     device="sw-other")                                                     # another switch
    body = client.get(f"/api/cables/walk?switch=sw-wk-01&since={since}").get_json()
    assert body["syslog"] is True
    assert sorted(u["port"] for u in body["ups"]) == ["ether7", "gi1/0/5"]
    assert {u["how"] for u in body["ups"]} == {"syslog"}


def test_without_syslog_the_poll_finds_ports_that_were_not_up_before(hall, client, monkeypatch):
    monkeypatch.setenv("SYSLOG_ENABLED", "0")
    monkeypatch.setattr(walk, "POLL_EVERY", 0)
    hall["mon"].set("sw-wk-02", port("Gi1/0/1"), port("Gi1/0/2", state="down"), port("Te1/1/1"))
    url = "/api/cables/walk?switch=sw-wk-02&since=1000"
    body = client.get(url).get_json()
    assert body["syslog"] is False and body["ups"] == []        # up when the walk began: not news
    hall["mon"].set("sw-wk-02", port("Gi1/0/2"))
    [up] = client.get(url).get_json()["ups"]
    assert (up["port"], up["how"]) == ("Gi1/0/2", "poll")


def test_a_walk_begins_on_the_servers_clock(hall, client):
    assert client.get("/api/cables/walk").status_code == 400
    before = time.time()
    body = client.get("/api/cables/walk?switch=sw-wk-05").get_json()
    assert before <= body["since"] <= time.time() and body["ups"] == []


def _seat(client, seat):
    return next(c for c in client.get(f"/api/cables?seat={seat}").get_json()["cables"])


def test_assign_makes_moves_and_swaps_cables(hall, client):
    r = client.post("/api/cables/assign", json={"seat": "w-1", "switch": "sw-wk-03", "port": "Gi1/0/1"})
    assert r.status_code == 200 and r.get_json()["cable"]["seat"] == "W-1"          # made
    client.post("/api/cables/assign", json={"seat": "W-2", "switch": "sw-wk-03", "port": "Gi1/0/2"})
    # Found on another port: the seat's cable moves, no second cable.
    r = client.post("/api/cables/assign", json={"seat": "W-1", "switch": "sw-wk-03", "port": "GigabitEthernet1/0/3"})
    assert r.get_json()["changed"] == [_seat(client, "W-1")["label"]]
    assert _seat(client, "W-1")["port"] == "GigabitEthernet1/0/3"
    # Again, same port written short: nothing to do.
    assert client.post("/api/cables/assign", json={"seat": "W-1", "switch": "sw-wk-03",
                                                   "port": "Gi1/0/3"}).get_json()["changed"] == []
    # Another seat's port: asked first, then the two trade.
    r = client.post("/api/cables/assign", json={"seat": "W-1", "switch": "sw-wk-03", "port": "Gi1/0/2"})
    assert r.status_code == 409 and r.get_json()["other_seat"] == "W-2"
    r = client.post("/api/cables/assign", json={"seat": "W-1", "switch": "sw-wk-03", "port": "Gi1/0/2", "swap": True})
    assert r.status_code == 200 and r.get_json()["other_seat"] == "W-2"
    assert _seat(client, "W-1")["port"] == "Gi1/0/2" and _seat(client, "W-2")["port"] == "GigabitEthernet1/0/3"


def test_assign_takes_over_an_infrastructure_cable(hall, client):
    client.post("/api/cables", json={"switch": "sw-wk-04", "port": "Gi1/0/9", "note": "Infrastructure"})
    client.post("/api/cables/assign", json={"seat": "W-9", "switch": "sw-wk-04", "port": "Gi1/0/1"})
    client.post("/api/cables/assign", json={"seat": "W-9", "switch": "sw-wk-04", "port": "Gi1/0/9"})
    mine = [c for c in client.get("/api/cables").get_json()["cables"] if c["switch"] == "sw-wk-04"]
    assert [(c["port"], c["seat"]) for c in mine] == [("Gi1/0/9", "W-9")]     # one cable, at the port it's on


def test_viewers_may_watch_but_not_assign(app_module):
    from tests.test_rbac import sign_in_as
    viewer = sign_in_as(app_module, "vi5", "viewer")
    assert viewer.post("/api/cables/assign", json={"seat": "W-1", "switch": "s", "port": "Gi1/0/1"}).status_code == 403
