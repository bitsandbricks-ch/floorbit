"""The crew's walk-through check-in (floorbit/seat_walk.py, docs/seat-walk.md): a laptop plugged in
at each seat, its port found from its IP, kept per event and cleared a day after the event ended.
Demo hall and made-up addresses only."""
import pytest

from floorbit import schedule, seat_walk, tenancy
from floorbit.builtin_plugins.demo import plugin as demo_plugin
from integrations import checkin, events
from tests.test_rbac import sign_in_as


@pytest.fixture
def hall(client, app_module, monkeypatch):
    monkeypatch.setattr(events, "publish", lambda kind, data=None, origin=None: None)
    client.put("/api/settings/plugins/demo", json={"enabled": True})
    assert client.post("/api/demo/layout").get_json()["blocks"] == 5
    return client


def demo_seat(label):
    """(ip, mac, switch, port) of a demo seat that has a PC on it."""
    _l, block, number, i = next(s for s in demo_plugin._seats() if s[0] == label)
    assert demo_plugin._taken(i), label
    return (demo_plugin._ip(i), demo_plugin._mac(i), *demo_plugin._switch_for(block, number))


def identify(client, ip):
    """The laptop opened the local agent's hello page: the agent saw it at ``ip``."""
    with client.application.app_context():
        token = seat_walk.new_hello("crew")
        assert seat_walk.agent_said_hello(token, ip, "Hall agent")
    return token


def locate(client, seat, ip, **body):
    return client.post("/api/seat-walk/locate", json={"seat": seat, "hello": identify(client, ip), **body})


def test_walk_a_row_with_the_laptop(hall, monkeypatch):
    # The tables don't know the laptop at its new seat yet and no segment allows SNMP lookups:
    # SSH on the access switch is the last resort.
    monkeypatch.setattr(seat_walk, "_from_monitoring", lambda ip: None)
    a1, a2 = demo_seat("A-1"), demo_seat("A-2")
    block = hall.get("/api/seat-blocks").get_json()[0]["id"]
    first = hall.get(f"/api/seat-walk?rows={block}:1").get_json()
    assert first["switch_lookup"] and [s["seat"] for s in first["seats"][:3]] == ["A-1", "A-2", "A-3"]
    assert first["seats"][0]["port"] is None and first["keep_hours"] == 24 and "ip" not in first

    r = locate(hall, "A-1", a1[0]).get_json()
    # The MAC from what the monitoring source knows, the port read from the access switch itself.
    assert r["ok"] and r["how"] == "switch" and r["found"] == {"switch": a1[2], "port": a1[3]}
    assert r["mac"] == a1[1] and r["steps"][0] == {"step": "mac", "ok": True, "how": "monitoring"}
    assert checkin.learned_ports()["A-1"]["source"] == "walk"

    # The next seat: the MAC is passed on, so no ARP lookup: the tables, then the MAC tables.
    r2 = locate(hall, "A-2", a2[0], previous=r["found"], mac=a2[1], mac_ip=a2[0]).get_json()
    assert r2["ok"] and r2["found"]["port"] == a2[3] and [s["step"] for s in r2["steps"]] == ["monitoring", "switch"]

    rows = {s["seat"]: s["port"] for s in hall.get(f"/api/seat-walk?rows={block}:1").get_json()["seats"]}
    assert rows["A-1"]["port"] == a1[3] and rows["A-2"]["source"] == "walk"
    entries = hall.get("/api/settings/audit?area=check-in").get_json()["entries"]
    assert any(e["action"] == "Walk-through: seat A-1 found on its port" for e in entries)

    assert hall.delete("/api/seat-walk/a-2").status_code == 200
    assert hall.delete("/api/seat-walk/a-2").status_code == 404


def test_the_tables_answer_before_any_switch_is_asked(hall, monkeypatch):
    a1 = demo_seat("A-1")
    asked = []
    monkeypatch.setattr(seat_walk, "port_from_switches", lambda *a, **k: asked.append(a) or None)
    r = locate(hall, "A-1", a1[0]).get_json()
    assert r["ok"] and r["how"] == "monitoring" and r["found"] == {"switch": a1[2], "port": a1[3]}
    assert asked == []                                            # no SSH while the tables know it


def test_what_the_page_refuses(hall, monkeypatch):
    ip = demo_seat("A-1")[0]
    assert locate(hall, "Z-99", ip).status_code == 400
    monkeypatch.setenv("CHECKIN_ALLOWED_NETWORKS", "10.0.0.0/8")
    r = locate(hall, "A-1", ip)
    assert r.status_code == 409 and "Wi-Fi" in r.get_json()["error"]


def test_the_laptop_is_always_identified_through_the_agent(hall, client, monkeypatch):
    from tests.test_agent import enrol, head
    ip, _mac, switch, port = demo_seat("A-1")
    # Even on the hall's own network: the request's address is never taken for the laptop's.
    r = hall.post("/api/seat-walk/locate", json={"seat": "A-1"}, environ_base={"REMOTE_ADDR": ip})
    assert r.status_code == 409 and "Identify it again" in r.get_json()["error"]

    assert hall.post("/api/seat-walk/hello").status_code == 409     # no agent address yet
    monkeypatch.setenv("SEAT_WALK_AGENT_URL", "http://192.0.2.10:8908/")
    made = hall.post("/api/seat-walk/hello").get_json()
    token = made["hello"]
    assert made["url"] == f"http://192.0.2.10:8908/floorbit/hello/{token}"
    assert hall.get(f"/api/seat-walk/hello/{token}").get_json() == {}             # waiting for the laptop
    assert hall.post("/api/seat-walk/locate", json={"seat": "A-1", "hello": token}).status_code == 409

    agent = enrol(client, "Hall agent")
    key = agent["key"]
    said = client.post("/api/agent/v1/seat-walk", json={"token": token, "ip": ip}, headers=head(key))
    assert said.status_code == 200
    # A code is used once, and only a signed-in page makes them.
    assert client.post("/api/agent/v1/seat-walk", json={"token": token, "ip": "192.0.2.66"},
                       headers=head(key)).status_code == 404
    assert client.post("/api/agent/v1/seat-walk", json={"token": "x" * 20, "ip": ip},
                       headers=head(key)).status_code == 404
    assert client.post("/api/agent/v1/seat-walk", json={"token": token, "ip": ip}).status_code == 401
    assert hall.get(f"/api/seat-walk/hello/{token}").get_json()["ip"] == ip
    assert hall.get("/api/seat-walk/hello/" + "y" * 20).status_code == 404
    # The ports come from the demo hall here, not through this agent, which never answers calls.
    assert client.delete(f"/api/agents/{agent['id']}").status_code == 200
    from floorbit import agent_link, sources
    agent_link.tunnel.reset()
    sources._agent = None

    r = hall.post("/api/seat-walk/locate", json={"seat": "A-1", "hello": token}).get_json()
    assert r["ok"] and r["ip"] == ip and r["found"] == {"switch": switch, "port": port}


def test_a_typed_mac_needs_no_agent(hall):
    _ip, mac, switch, port = demo_seat("A-2")
    r = hall.post("/api/seat-walk/locate", json={"seat": "A-2", "mac": mac.upper().replace(":", "-"),
                                                 "mac_typed": True}).get_json()
    assert r["ok"] and r["mac"] == mac and r["found"] == {"switch": switch, "port": port}
    assert r["area_drift"] is None
    # Pinned to another row: the walker hears it right away (issue #1094).
    other = next(row for row in hall.get("/api/switch-areas").get_json()["switches"] if row["name"] == switch)
    from floorbit import seat_names
    from floorbit.store import load_data
    elsewhere = next(x for x in seat_names.hall_rows(load_data()) if "A-2" not in x["seats"])
    assert hall.put(f"/api/switch-areas/{other['name']}", json={"rows": [elsewhere["id"]]}).status_code == 200
    r = hall.post("/api/seat-walk/locate", json={"seat": "A-2", "mac": mac, "mac_typed": True}).get_json()
    assert r["area_drift"]["kind"] == "pin" and r["area_drift"]["switch"] == switch
    bad = hall.post("/api/seat-walk/locate", json={"seat": "A-2", "mac": "not a mac", "mac_typed": True})
    assert bad.status_code == 400


def test_only_seat_editors_save(app_module, hall):
    viewer = sign_in_as(app_module, "vi1", "viewer")
    assert viewer.post("/api/seat-walk/locate", json={"seat": "A-1"}).status_code == 403


END = 1_794_000_000      # November 2026


class Monitor:
    """A monitoring source whose MAC table answers what the test says, as LibreNMS or telemetry would."""

    def __init__(self, answers):
        self.answers = list(answers)

    def enabled(self):
        return True

    def mac_for_ip(self, ip):
        return "02:00:00:00:00:99"

    def neighbours(self, name):
        return []

    def resolve_ip(self, ip, search_device=None):
        port = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        return port and {"device_name": port[0], "port": port[1], "mac": "02:00:00:00:00:99"}


def test_an_old_mac_table_naming_the_last_seat_is_waited_out(app_module, monkeypatch):
    from floorbit import sources
    monitor = Monitor([("sw-a-01", "Gi1/0/1"), ("sw-a-01", "Gi1/0/1"), ("sw-a-01", "Gi1/0/2")])
    monkeypatch.setattr(sources, "monitoring", lambda: monitor)
    ticks = iter(range(0, 1000, 3))
    with app_module.app.app_context():
        r = seat_walk.locate("192.0.2.50", None, previous={"switch": "sw-a-01.example.com", "port": "Gi1/0/1"},
                             sleep=lambda s: None, clock=lambda: next(ticks))
    assert r["found"] == {"switch": "sw-a-01", "port": "Gi1/0/2"} and r["tries"] == 3 and r["how"] == "monitoring"

    monitor = Monitor([("sw-a-01", "Gi1/0/1")])
    monkeypatch.setattr(sources, "monitoring", lambda: monitor)
    ticks = iter(range(0, 1000, 3))
    with app_module.app.app_context():
        r = seat_walk.locate("192.0.2.50", None, previous={"switch": "sw-a-01", "port": "gi1/0/1"},
                             sleep=lambda s: None, clock=lambda: next(ticks))
    # Never the last seat's port: after the try budget the page is told to try again.
    assert r["found"] is None and r["stale"] and r["tries"] > 1


def test_mac_tables_skip_uplinks_and_other_macs():
    out = ("Vlan  Mac Address       Type     Ports\n 100  0200.0000.0099    DYNAMIC  Gi1/0/7\n"
           " 100  0200.0000.0098    DYNAMIC  Gi1/0/8\n"
           "* 100     0200.0000.0099   dynamic  0  F  F  Eth1/49\n")
    assert seat_walk._parse_mac_table(out, "02:00:00:00:00:99") == ["Gi1/0/7", "Eth1/49"]
    assert seat_walk._mac_command("02:00:00:00:00:99") == "show mac address-table address 0200.0000.0099"


def test_the_crew_wins_over_an_older_mapping_and_the_plan_is_named(hall):
    checkin.learn_port("A-3", {"switch": "sw-a-01", "port": "Gi1/0/1"}, "pixel")
    with hall.application.app_context():
        saved = seat_walk.save("A-1", {"switch": "sw-a-01", "port": "Gi1/0/1"}, "crew")
    assert saved["replaced"] == ["A-3"] and "A-3" not in checkin.learned_ports()
    # The demo's patch plan has A-1 on that port too: nothing to correct.
    assert saved["plan_seat"] is None
    with hall.application.app_context():
        saved = seat_walk.save("A-2", {"switch": "sw-a-01", "port": "gi1/0/5"}, "crew")
    # The plan gives that port to A-5 and wins on the floor plan, so the page offers to fix the plan.
    assert saved["plan_seat"] == "A-5"


def test_cleared_one_day_after_the_event_ended(hall):
    checkin.learn_port("A-1", {"switch": "sw-a-01", "port": "Gi1/0/1"}, "crew", source="walk")
    schedule.set_event({"start": END - 2 * 86400, "end": END})
    with hall.application.app_context():
        assert seat_walk.purge_ended(now=END + 23 * 3600) == []
        assert "A-1" in checkin.learned_ports()
        assert seat_walk.purge_ended(now=END + 25 * 3600) == ["main"]
    assert checkin.learned_ports() == {}


def test_a_closed_event_without_a_schedule_counts_from_closing(hall):
    later = tenancy.create("Next LAN")
    tenancy.update(later["id"], status="live")
    with tenancy.using_event(later):
        checkin.learn_port("A-1", {"switch": "sw-a-01", "port": "Gi1/0/1"}, "crew", source="walk")
    main = tenancy.find("main")
    with tenancy.using_event(main), hall.application.app_context():
        checkin.learn_port("A-2", {"switch": "sw-a-01", "port": "Gi1/0/2"}, "crew", source="walk")
        # The demo layout plans an event around today; this one has no schedule. Without clearing
        # it, the planned end won over closed_at and the test failed at some times of day.
        schedule.set_event({})
    tenancy.update("main", status="closed")
    closed_at = tenancy.find("main")["closed_at"]
    with hall.application.app_context():
        assert seat_walk.purge_ended(now=closed_at + 3600) == []
        assert seat_walk.purge_ended(now=closed_at + 25 * 3600) == ["main"]
    with tenancy.using_event(tenancy.find("main")):
        assert checkin.learned_ports() == {}
    with tenancy.using_event(tenancy.find(later["id"])):
        # The live event has no end yet: its mappings stay.
        assert "A-1" in checkin.learned_ports()
