"""Checking in from a PC (docs/seat-mapping.md): the PIN from the seat card and a nick, never the
seat. The PIN names the seat, the PC's switch port is learned, and that seat to port pair is what
the floor plan keeps. Made-up nicks, RFC 5737 addresses."""
import pytest

from floorbit import cables, port_clients, sources
from floorbit.attention import AttentionWatch
from floorbit.builtin_plugins.librenms import client as librenms
from integrations import checkin, events


def edge(switch, port, edge=True):
    return {"switch": switch, "port": port, "mac": None, "edge": edge}


PORTS = {"192.0.2.21": edge("sw-a-01", "Gi1/0/1"),
         "192.0.2.22": edge("sw-a-01", "Gi1/0/2"),
         "192.0.2.23": edge("sw-a-01", "Gi1/0/2"),
         "192.0.2.24": edge("sw-a-01", "Gi1/0/24", edge=False)}   # an AP port: many MACs


@pytest.fixture
def hall(client, tmp_path, monkeypatch):
    monkeypatch.setenv("CHECKIN_ENABLED", "true")
    monkeypatch.setenv("CHECKIN_FILE", str(tmp_path / "checkins.json"))
    monkeypatch.setattr(checkin, "lookup_mac", lambda ip: None)
    monkeypatch.setattr(checkin, "port_of", lambda ip: PORTS.get(ip))
    monkeypatch.setattr(events, "publish", lambda kind, data=None, origin=None: None)
    client.post("/api/seat-blocks", json={"name": "A", "x": 10, "y": 10, "cols": 4, "rows": 1})
    return client


def pins(client):
    return {s["seat"]: s["pin"] for s in client.get("/api/helpdesk/qr").get_json()["seats"]}


def check_in(client, ip, verify=True, **body):
    """Check in, then let the background look up the port (it runs in a thread in the app)."""
    r = client.post("/api/checkin", json=body, environ_base={"REMOTE_ADDR": ip})
    if verify:
        checkin.verify_pending()
    return r


def test_each_seat_card_gets_its_own_pin_and_keeps_it(hall):
    first = pins(hall)
    assert set(first) == {"A-1", "A-2", "A-3", "A-4"}
    assert len(set(first.values())) == 4
    assert all(len(p) == checkin.PIN_LENGTH and set(p) <= set(checkin.PIN_ALPHABET) for p in first.values())
    assert pins(hall) == first                       # a reprint gives the same cards
    sheet = hall.get("/api/helpdesk/qr").get_json()
    assert sheet["checkin"]["url"].endswith("/checkin")


def test_pin_and_nick_check_in_and_teach_the_seats_port(hall):
    pin = pins(hall)["A-2"]
    r = check_in(hall, "192.0.2.22", pin=pin.lower()[:2] + "-" + pin.lower()[2:], username="pixel")
    assert r.status_code == 200 and r.get_json()["seat"] == "A-2"
    assert checkin.learned_ports()["A-2"]["port"] == "Gi1/0/2"
    # Only the port lasts: the plan now knows which port A-2 is on, without a cable drawn.
    assert cables.port_seats()[("sw-a-01", "gi1/0/2")] == "A-2"
    # A typed seat is ignored when a PIN is given: the PIN names the seat.
    check_in(hall, "192.0.2.21", pin=pins(hall)["A-1"], seat="A-4", username="nova")
    assert set(checkin.load_all()) == {"A-1", "A-2"}


def test_a_wrong_pin_is_refused_in_the_readers_language(hall):
    r = hall.post("/api/checkin", json={"pin": "ZZZZZ", "username": "pixel"},
                  environ_base={"REMOTE_ADDR": "192.0.2.21"}, headers={"Accept-Language": "de-CH"})
    assert r.status_code == 403 and "PIN" in r.get_json()["error"] and "Karte" in r.get_json()["error"]
    assert checkin.learned_ports() == {}


def test_without_the_pin_option_the_phone_can_still_type_the_seat(hall, monkeypatch):
    assert check_in(hall, "192.0.2.21", seat="A-3", username="pixel").status_code == 200
    assert checkin.learned_ports() == {}             # a typed seat proves nothing about the port
    monkeypatch.setenv("CHECKIN_REQUIRE_PIN", "true")
    assert check_in(hall, "192.0.2.22", seat="A-4", username="nova").status_code == 403


def test_a_patched_cable_wins_over_a_learned_port(hall):
    hall.post("/api/cables", json={"switch": "sw-a-01", "port": "Gi1/0/2", "seat": "A-3"})
    check_in(hall, "192.0.2.22", pin=pins(hall)["A-2"], username="pixel")
    assert cables.port_seats()[("sw-a-01", "gi1/0/2")] == "A-3"
    conflicts = checkin.port_conflicts(None)
    assert {"kind": "plan", "seat": "A-2", "other": ["A-3"], "switch": "sw-a-01", "port": "Gi1/0/2"} in conflicts


def test_two_seats_on_one_port_go_to_the_problems_page(hall, app_module, monkeypatch):
    check_in(hall, "192.0.2.22", pin=pins(hall)["A-2"], username="pixel")
    check_in(hall, "192.0.2.23", pin=pins(hall)["A-4"], username="nova")
    shared = [c for c in checkin.port_conflicts(None) if c["kind"] == "shared"]
    assert shared == [{"kind": "shared", "seat": "A-2", "other": ["A-4"], "switch": "sw-a-01", "port": "Gi1/0/2"}]

    class Quiet:
        def enabled(self):
            return True

        def device_ports(self, name):
            return []
    monkeypatch.setattr(sources, "monitoring", lambda: Quiet())
    watch = AttentionWatch()
    with app_module.app.app_context():
        watch.poll_once(now=1000)
    items = [i for i in watch.snapshot()["items"] if i["kind"] == "mapping"]
    assert [i["title"] for i in items] == ["Seats A-2 and A-4 checked in on the same port"]
    assert "pixel" not in str(items) and "nova" not in str(items)     # where, never who


def test_another_nick_taking_a_seat_is_flagged(hall):
    check_in(hall, "192.0.2.21", seat="A-1", username="pixel")          # typed on a phone
    check_in(hall, "192.0.2.22", pin=pins(hall)["A-1"], username="nova")
    assert any(c["kind"] == "taken" and c["seat"] == "A-1" for c in checkin.port_conflicts(None))


def test_a_pin_is_used_once_and_the_crew_opens_it_again(hall):
    pin = pins(hall)["A-1"]
    check_in(hall, "192.0.2.21", pin=pin, username="pixel")
    again = check_in(hall, "192.0.2.22", pin=pin, username="nova")
    assert again.status_code == 409 and "already used" in again.get_json()["error"]
    typed = check_in(hall, "192.0.2.22", seat="A-1", username="nova")
    assert typed.status_code == 409                                   # nor by typing the seat
    # The PC that checked in may change its nick, with the PIN or without anything.
    assert check_in(hall, "192.0.2.21", pin=pin, username="pixel2").status_code == 200
    r = check_in(hall, "192.0.2.21", username="pixel3")
    assert r.status_code == 200 and r.get_json()["seat"] == "A-1"
    # The crew removes the check-in: the card works again.
    assert hall.delete("/api/checkins/A-1").status_code == 200
    assert check_in(hall, "192.0.2.22", pin=pin, username="nova").status_code == 200


def test_the_portal_answers_at_once_and_looks_up_the_port_later(hall, monkeypatch):
    asked = []
    monkeypatch.setattr(checkin, "port_of", lambda ip: asked.append(ip) or PORTS.get(ip))
    monkeypatch.setattr(checkin, "lookup_mac", lambda ip: asked.append(ip))
    r = check_in(hall, "192.0.2.21", verify=False, pin=pins(hall)["A-1"], username="pixel")
    assert r.get_json()["wired"] == "pending" and asked == []          # nothing slow in the request
    assert checkin.verify_pending() == ["A-1"]
    row = checkin.load_all()["A-1"]
    assert row["wired"] == "verified" and row["port_seen"] == {"switch": "sw-a-01", "port": "Gi1/0/1"}
    assert checkin.learned_ports()["A-1"]["port"] == "Gi1/0/1"


def test_only_a_wired_pc_on_one_access_port_teaches_the_seat(hall, monkeypatch):
    # The page says it is a phone (touch, small screen): the nick still counts, no port is learned.
    said = check_in(hall, "198.51.100.7", pin=pins(hall)["A-1"], username="pixel", device="mobile")
    assert said.status_code == 200 and said.get_json()["wired"] == "not_wired"
    phone = hall.post("/api/checkin", json={"pin": pins(hall)["A-2"], "username": "nova"},
                      environ_base={"REMOTE_ADDR": "192.0.2.22"},
                      headers={"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0) Mobile"})
    assert phone.get_json()["wired"] == "not_wired"
    check_in(hall, "192.0.2.24", pin=pins(hall)["A-3"], username="quark")       # on an AP port
    assert checkin.load_all()["A-3"]["wired"] == "pending"
    checkin.verify_pending(now=checkin.load_all()["A-3"]["checked_in_at"] + checkin.VERIFY_GIVE_UP + 1)
    assert checkin.load_all()["A-3"]["wired"] == "unverified"
    assert checkin.learned_ports() == {}
    info = hall.get("/api/checkin/info", environ_base={"REMOTE_ADDR": "198.51.100.7"},
                    headers={"User-Agent": "Mozilla/5.0 (Linux; Android 15) Mobile"}).get_json()
    assert info["on_pc"] is False
    assert checkin.load_all()["A-3"]["device"] == "unknown" and checkin.load_all()["A-2"]["device"] == "mobile"


def test_the_learned_port_shows_what_is_plugged_in_now(hall, app_module, monkeypatch):
    # Once the port is known, the seat shows the MAC and IP on it from the MAC and ARP tables.
    check_in(hall, "192.0.2.21", pin=pins(hall)["A-1"], username="pixel")

    class Fdb:
        def enabled(self):
            return True

        def port_clients(self, hostname):
            return [{"port": "Gi1/0/1", "mac": "02:00:00:00:00:31"}]

        def arp(self, query):
            return [{"mac_address": "02:00:00:00:00:31", "ipv4_address": "192.0.2.31"}]
    monkeypatch.setattr(sources, "monitoring", lambda: Fdb())
    monkeypatch.setattr("integrations.seat_sources.load", lambda max_age=None: {"A-1": {"ip_address": "192.0.2.21"}})
    finder = app_module.app.extensions["floorbit_port_clients"]
    finder.reset()
    with app_module.app.app_context():
        finder.run(now=1000)
    assert finder.seat_ips == {"192.0.2.31": "A-1"}


def test_the_short_address_lands_on_the_check_in_page(hall, monkeypatch):
    monkeypatch.setenv("CHECKIN_ADDRESS", "http://Checkin.LAN/")
    r = hall.get("/", headers={"Host": "checkin.lan"})
    assert r.status_code == 302 and r.headers["Location"].endswith("/checkin")
    other = hall.get("/", headers={"Host": "floor.example.com"})
    assert not other.headers.get("Location", "").endswith("/checkin")
    info = hall.get("/api/checkin/info", environ_base={"REMOTE_ADDR": "192.0.2.21"}).get_json()
    assert info["address"] == "checkin.lan"


def test_the_access_port_wins_over_uplinks():
    # ARP lives on the core; the access switches only know MACs, and every switch on the way
    # learns the MAC too, on its uplink. The port with the fewest MACs is where the PC sits.
    rows = [{"hostname": "core-01", "ifName": "Te1/1/1", "port_id": 1},
            {"hostname": "dist-01", "ifName": "Te1/0/1", "ifAlias": "Uplink core", "port_id": 2},
            {"hostname": "sw-a-01", "ifName": "Gi1/0/48", "port_id": 3},
            {"hostname": "sw-a-01", "ifName": "Gi1/0/7", "port_id": 4}]
    counts = {1: 900, 2: 400, 3: 48, 4: 1}
    import re
    edge = librenms.pick_edge_port(rows, lambda r: counts[r["port_id"]], (), re.compile("uplink", re.I))
    assert edge["ifName"] == "Gi1/0/7"
    assert librenms.pick_edge_port(rows, lambda r: counts[r["port_id"]], ("gi1/0/7",), None)["ifName"] == "Gi1/0/48"
    assert librenms.pick_edge_port([], lambda r: None) is None


def test_port_clients_reads_learned_seat_ports_like_cables(hall):
    check_in(hall, "192.0.2.21", pin=pins(hall)["A-1"], username="pixel")
    assert port_clients._learned_cables() == [{"switch": "sw-a-01", "port": "Gi1/0/1", "seat": "A-1",
                                               "label": "check-in"}]
