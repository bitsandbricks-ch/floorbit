"""The patch plan checked against the network (issue #473), from the port watch's last read."""
import pytest

from floorbit import sources
from integrations import events
from tests.test_attention import Monitoring, poll, port


@pytest.fixture
def hall(client, app_module, monkeypatch):
    """Block A (4 seats in a row) and switch sw-a-01, with a fake LibreNMS, as in test_attention."""
    mon = Monitoring()
    monkeypatch.setattr(sources, "monitoring", lambda: mon)
    client.post("/api/seat-blocks", json={"name": "A", "x": 10, "y": 10, "cols": 4, "rows": 1})
    client.post("/api/switches", json={"name": "sw-a-01", "x": 10, "y": 5})
    watch = app_module.app.extensions["floorbit_attention"]
    watch.reset()
    monkeypatch.setattr(events, "publish", lambda kind, data=None, origin=None: None)
    return {"mon": mon, "watch": watch, "app": app_module.app}


def _plan(client, rows="1"):
    block = next(b for b in client.get("/api/seat-blocks").get_json() if b["name"] == "A")
    r = client.post("/api/cables/block", json={"rows": [f"{block['id']}:{rows}"], "switch": "sw-a-01",
                                               "first_port": "Gi1/0/1"})
    assert r.status_code == 200, r.get_json()
    return block


def test_nothing_to_say_before_the_first_read(app_module, client):
    app_module.app.extensions["floorbit_attention"].reset()      # earlier tests may have polled it
    body = client.get("/api/cables/check").get_json()
    assert body["last_poll"] is None and body["rows"] == []


def test_seats_ports_up_down_missing_and_unplanned(hall, client):
    block = _plan(client)                                  # A-1..A-4 on Gi1/0/1..4
    client.post("/api/cables", json={"switch": "sw-a-01", "port": "Gi1/0/48"})    # the uplink: a cable, no seat
    hall["mon"].set("sw-a-01",
                    port("GigabitEthernet1/0/1"), port("Gi1/0/2", state="down"), port("Gi1/0/3"),
                    # Gi1/0/4 isn't there at all: the plan has a typo, or it's the wrong switch
                    port("Gi1/0/7"), port("Gi1/0/48"), port("Gi1/0/9", state="down"))
    poll(hall, 1000)
    body = client.get("/api/cables/check").get_json()
    assert body["last_poll"] == 1000
    assert body["rows"] == [{"row": f"{block['id']}:1", "name": "1", "block_label": "A", "naming": "block",
                             "seats": 4, "up": 2}]
    assert [r["seat"] for r in body["down"]["rows"]] == ["A-2"] and body["down"]["rows"][0]["state"] == "down"
    assert [(r["seat"], r["port"]) for r in body["missing"]["rows"]] == [("A-4", "Gi1/0/4")]
    # Up, and no cable says what it is; the uplink has a cable, the down port isn't anyone yet.
    assert [r["port"] for r in body["unplanned"]["rows"]] == ["Gi1/0/7"]
    assert body["conflicts"]["count"] == 0 and body["unread"] == []


def test_a_description_naming_another_seat_is_a_conflict(hall, client):
    _plan(client)
    hall["mon"].set("sw-a-01", port("Gi1/0/1", description="Seat A-2"), port("Gi1/0/2"), port("Gi1/0/3"),
                    port("Gi1/0/4"))
    poll(hall, 1000)
    [row] = client.get("/api/cables/check").get_json()["conflicts"]["rows"]
    assert (row["seat"], row["port"], row["described_seat"]) == ("A-1", "Gi1/0/1", "A-2")


def test_switches_the_watch_did_not_read_are_named_not_counted_as_down(hall, client):
    client.post("/api/cables", json={"switch": "sw-z-09", "port": "Gi1/0/1", "seat": "Z-1"})
    hall["mon"].set("sw-a-01", port("Gi1/0/1"))
    poll(hall, 1000)
    body = client.get("/api/cables/check").get_json()
    assert body["unread"] == ["sw-z-09"] and body["down"]["count"] == 0 and body["missing"]["count"] == 0


def test_viewers_may_look(app_module, client):
    from tests.test_rbac import sign_in_as
    assert sign_in_as(app_module, "vi3", "viewer").get("/api/cables/check").status_code == 200


def test_uplinks_are_never_up_with_no_cable(hall, client, monkeypatch):
    """#1046: a port to another box is up with no seat cable by design: a link on the topology, an
    LLDP/CDP neighbour, or a port the uplink pattern names."""
    from floorbit import links
    _plan(client)
    client.post("/api/switches", json={"name": "sw-core-01", "x": 50, "y": 5})
    r = client.post("/api/links", json={"a": "sw-core-01", "a_port": "Te1/1/1", "b": "sw-a-01",
                                        "b_port": "TenGigabitEthernet1/0/1", "type": "fiber-sm", "speed": 10})
    assert r.status_code == 201, r.get_json()
    monkeypatch.setattr(links.reader, "cached_neighbours",
                        lambda sw: [{"port": "Te1/0/2", "remote": "sw-b-01"}] if sw == "sw-a-01" else [])
    hall["mon"].set("sw-a-01", port("Gi1/0/1"), port("Gi1/0/2"), port("Gi1/0/3"), port("Gi1/0/4"),
                    port("Te1/0/1"), port("Te1/0/2"), port("Gi1/0/47", description="Uplink to dist"),
                    port("Gi1/0/8"))
    poll(hall, 1000)
    assert [r["port"] for r in client.get("/api/cables/check").get_json()["unplanned"]["rows"]] == ["Gi1/0/8"]
