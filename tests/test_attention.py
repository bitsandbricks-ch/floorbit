"""Needs attention (issue #15): flapping ports, errors rising, half duplex, online without a check-in."""
import pytest

from floorbit import attention, sources
from integrations import checkin, events


def port(name, state="up", errors=0, duplex="full", last_change=None, description=""):
    return {"name": name, "state": state, "errors_in": errors, "errors_out": 0, "duplex": duplex,
            "last_change": last_change, "description": description}


class Monitoring:
    """All ports of each switch, the way ``device_ports`` gives them."""

    def __init__(self):
        self.ports = {}

    def enabled(self):
        return True

    def device_ports(self, hostname):
        return list(self.ports.get(hostname, {}).values())

    def set(self, switch, *ports):
        self.ports.setdefault(switch, {}).update({p["name"]: p for p in ports})


@pytest.fixture
def hall(client, app_module, monkeypatch):
    mon = Monitoring()
    monkeypatch.setattr(sources, "monitoring", lambda: mon)
    client.post("/api/seat-blocks", json={"name": "A", "x": 10, "y": 10, "cols": 4, "rows": 1})
    sw = client.post("/api/switches", json={"name": "sw-a-01", "x": 10, "y": 5}).get_json()
    watch = app_module.app.extensions["floorbit_attention"]
    watch.reset()
    published = []
    monkeypatch.setattr(events, "publish", lambda kind, data=None, origin=None: published.append(kind))
    return {"mon": mon, "switch": sw, "watch": watch, "app": app_module.app, "published": published}


def poll(hall, now):
    with hall["app"].app_context():
        return hall["watch"].poll_once(now=now)


def kinds(hall):
    return sorted((i["kind"], i["port"]) for i in hall["watch"].snapshot()["items"])


def test_seat_of_reads_the_port_description():
    names = {"a-12": "A-12"}
    assert attention.seat_of("Seat A-12", names) == "A-12"
    assert attention.seat_of("a-12 desk", names) == "A-12"
    assert attention.seat_of("uplink to core-1", names) is None
    assert attention.seat_of(None, names) is None


def test_a_port_that_keeps_going_up_and_down_is_flapping(hall):
    mon = hall["mon"]
    for i, state in enumerate(["up", "down", "up", "down"]):
        mon.set("sw-a-01", port("Gi1/0/9", state=state, last_change=100 + i))
        poll(hall, 1000 + i * 60)
    assert kinds(hall) == [("flapping", "Gi1/0/9")]
    [item] = hall["watch"].snapshot()["items"]
    assert item["switch_id"] == hall["switch"]["id"] and "3 link changes" in item["title"]
    # Quiet for more than ten minutes: it clears on its own.
    poll(hall, 1000 + 3 * 60 + 601)
    assert kinds(hall) == []


def test_two_changes_are_not_flapping_yet(hall):
    for i, state in enumerate(["up", "down", "up"]):
        hall["mon"].set("sw-a-01", port("Gi1/0/9", state=state))
        poll(hall, 1000 + i * 60)
    assert kinds(hall) == []


def test_errors_rising_between_polls(hall):
    mon = hall["mon"]
    mon.set("sw-a-01", port("Gi1/0/3", errors=500))   # old errors from before the first poll don't count
    poll(hall, 1000)
    assert kinds(hall) == []
    mon.set("sw-a-01", port("Gi1/0/3", errors=505))
    poll(hall, 1120)
    assert kinds(hall) == []
    mon.set("sw-a-01", port("Gi1/0/3", errors=540))
    poll(hall, 1240)
    assert kinds(hall) == [("errors", "Gi1/0/3")]
    assert "+35" in hall["watch"].snapshot()["items"][0]["title"]
    poll(hall, 1360)   # stopped growing
    assert kinds(hall) == []


def test_half_duplex_only_on_an_up_port(hall):
    hall["mon"].set("sw-a-01", port("Gi1/0/4", duplex="half"), port("Gi1/0/5", state="down", duplex="half"))
    poll(hall, 1000)
    assert kinds(hall) == [("duplex", "Gi1/0/4")]


def test_online_without_a_check_in(hall, monkeypatch):
    monkeypatch.setattr(checkin, "load_all", lambda: {"A-2": {}})
    hall["mon"].set("sw-a-01", port("Gi1/0/1", description="Seat A-1"), port("Gi1/0/2", description="Seat A-2"),
                    port("Gi1/0/3", state="down", description="Seat A-3"), port("Gi1/0/48", description="uplink"))
    poll(hall, 1000)
    assert kinds(hall) == []   # check-in is off
    monkeypatch.setenv("CHECKIN_ENABLED", "true")
    poll(hall, 1120)
    assert kinds(hall) == [("checkin", "Gi1/0/1")]
    [item] = hall["watch"].snapshot()["items"]
    assert item["seat"] == "A-1" and item["where"] == "sw-a-01 Gi1/0/1 (seat A-1)"
    assert "username" not in item and "nick" not in str(item)


def test_unplaced_and_offline_switches_are_skipped(hall, client):
    client.post("/api/switches", json={"name": "sw-spare"})   # not on the floor plan
    hall["mon"].set("sw-spare", port("Gi1/0/1", duplex="half"))
    hall["mon"].set("sw-a-01", port("Gi1/0/4", duplex="half"))
    monitor = hall["app"].extensions["lal_integrations"]["monitor"]
    monitor.statuses = {hall["switch"]["id"]: {"status": "offline"}}
    try:
        poll(hall, 1000)
    finally:
        monitor.statuses = {}
    assert kinds(hall) == []


def test_entries_keep_their_first_time_and_announce_changes(hall):
    hall["mon"].set("sw-a-01", port("Gi1/0/4", duplex="half"))
    assert [e["kind"] for e in poll(hall, 1000)] == ["duplex"]
    assert poll(hall, 1120) == []   # still there, not new
    assert hall["watch"].snapshot()["items"][0]["since"] == 1000
    assert [k for k in hall["published"] if k == "attention.changed"] == ["attention.changed"]
    hall["mon"].set("sw-a-01", port("Gi1/0/4"))
    poll(hall, 1240)
    assert [k for k in hall["published"] if k == "attention.changed"] == ["attention.changed"] * 2


def test_without_monitoring_nothing_is_asked(hall, monkeypatch):
    monkeypatch.setattr(sources, "monitoring", lambda: sources.NoMonitoring())
    assert poll(hall, 1000) == []


def test_problems_list_them_newest_first_with_a_floor_plan_link(hall, client):
    mon = hall["mon"]
    mon.set("sw-a-01", port("Gi1/0/4", duplex="half"))
    poll(hall, 1000)
    mon.set("sw-a-01", port("Gi1/0/5", duplex="half", description="Seat A-2"))
    poll(hall, 1120)
    body = client.get("/api/problems").get_json()
    assert body["problems"] == []   # port trouble doesn't mix with what is down
    assert body["counts"]["attention"] == 2
    first, second = body["attention"]
    assert first["where"] == "sw-a-01 Gi1/0/5 (seat A-2)"
    assert first["link"] == "/?seat=A-2" and first["kind"] == "duplex" and first["level"] == "warn"
    assert second["link"] == f"/?switch={hall['switch']['id']}"


def test_the_background_thread_runs_in_the_app_context(hall, monkeypatch):
    seen = []
    watch = hall["watch"]
    monkeypatch.setattr(watch, "poll_once", lambda: (seen.append(bool(attention._app_ext())), watch.stop()))
    watch._stop.clear()
    watch._run()
    assert seen == [True]
