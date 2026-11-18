"""Checking in from a PC (docs/seat-mapping.md): the PIN from the seat card and a nick, never the
seat. The PIN names the seat, the PC's switch port is learned, and that seat to port pair is what
the floor plan keeps. Made-up nicks, RFC 5737 addresses."""
import contextlib
import threading

import pytest

from floorbit import cables, port_clients, sources
from floorbit.attention import AttentionWatch
from floorbit.builtin_plugins.librenms import client as librenms
from integrations import checkin, events

PORT_OF = checkin.port_of   # the real one, before the fixture fakes it


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



def test_a_typed_seat_that_isnt_one_is_answered_about_seats(hall):
    r = hall.post("/api/checkin", json={"seat": "my desk!", "username": "pixel"},
                  environ_base={"REMOTE_ADDR": "192.0.2.21"}, headers={"Accept-Language": "de-CH"})
    assert r.status_code == 400 and r.get_json()["error"].startswith("Gib die Platznummer von deinem Ticket ein")
    empty = hall.post("/api/checkin", json={"username": "pixel"}, environ_base={"REMOTE_ADDR": "192.0.2.21"})
    assert empty.status_code == 400 and "PIN" in empty.get_json()["error"]

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
    typed = check_in(hall, "192.0.2.22", seat="a1", username="nova")
    assert typed.status_code == 409                                   # nor by typing the seat
    # They typed a seat, so the answer talks about the seat, not about a PIN they never entered.
    assert typed.get_json()["error"] == ("Seat A-1 was already checked in with its seat card. "
                                         "Ask the crew if this is your seat.")
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


def test_crew_overview_counts_states_and_lists_the_portal_fetches(hall):
    from floorbit import captive
    check_in(hall, "192.0.2.22", pin=pins(hall)["A-2"], username="pixel", device="pc")
    check_in(hall, "192.0.2.24", verify=False, pin=pins(hall)["A-3"], username="nova", device="pc")
    check_in(hall, "192.0.2.30", pin=pins(hall)["A-4"], username="orbit", device="mobile")
    captive.answer(hall.application, agent="hall-a")
    body = hall.get("/api/checkins/overview").get_json()
    c = body["counts"]
    assert (c["checked_in"], c["verified"], c["pending"], c["not_wired"]) == (3, 1, 1, 1)
    assert c["pins"] == 4 and c["unused_pins"] == 1 and c["learned"] == 1
    rows = {r["seat"]: r for r in body["rows"]}
    assert rows["A-2"]["port"]["port"] == "Gi1/0/2" and rows["A-2"]["learned"]["switch"] == "sw-a-01"
    assert rows["A-4"]["device"] == "mobile" and rows["A-4"]["wired"] == "not_wired"
    fetch = body["portal"]["fetches"][0]
    assert fetch["agent"] == "hall-a" and fetch["done"] == 3
    assert body["verifier"] == {"last_error": None}


def test_crew_can_look_for_a_port_again(lan_here, hall, monkeypatch):
    check_in(hall, "192.0.2.24", pin=pins(hall)["A-3"], username="nova")
    monkeypatch.setattr(checkin, "VERIFY_GIVE_UP", -1)          # the lookup gave up
    checkin.verify_pending()
    assert checkin.load_all()["A-3"]["wired"] == "unverified"
    r = hall.post("/api/checkins/a-3/retry")
    assert r.status_code == 200 and r.get_json()["wired"] == "pending"
    assert hall.post("/api/checkins/A-1/retry").status_code == 404
    monkeypatch.setitem(PORTS, "192.0.2.24", edge("sw-a-01", "Gi1/0/3"))   # the PC moved to its own port
    monkeypatch.setattr(checkin, "VERIFY_GIVE_UP", 15 * 60)
    checkin.verify_pending()
    assert checkin.load_all()["A-3"]["wired"] == "verified"


def test_check_in_page_is_listed_only_while_check_in_is_on(hall, monkeypatch):
    from floorbit import page_index
    entry = next(p for p in page_index.PAGES if p[0] == "/checkins")
    assert entry[3]({}, lambda perm: True)
    monkeypatch.setenv("CHECKIN_ENABLED", "false")
    assert not entry[3]({}, lambda perm: True)
    assert hall.get("/api/checkins/overview").status_code in (403, 404, 409)


def test_crew_can_forget_a_wrong_learned_port(hall):
    check_in(hall, "192.0.2.22", pin=pins(hall)["A-2"], username="pixel")
    assert hall.delete("/api/checkins/a-2/port").get_json() == {"ok": True}
    assert checkin.learned_ports() == {}
    assert hall.delete("/api/checkins/A-2/port").status_code == 404


def test_signed_in_crew_needs_no_admin_token(hall, monkeypatch):
    # The token guards the API for scripts; the page is behind sign-in and roles already.
    monkeypatch.setenv("CHECKIN_ADMIN_TOKEN", "s3cret")
    assert hall.get("/api/checkins/overview").status_code == 200


def test_seat_inspector_says_where_the_port_lookup_stands(hall):
    check_in(hall, "192.0.2.22", pin=pins(hall)["A-2"], username="pixel")
    check_in(hall, "192.0.2.24", pin=pins(hall)["A-3"], username="nova")
    assert hall.get("/api/plan/seats/A-2").get_json()["checkin_wired"] == "verified"
    assert hall.get("/api/plan/seats/A-3").get_json()["checkin_wired"] == "pending"   # an AP port is no seat's port
    assert "checkin_wired" not in hall.get("/api/plan/seats/A-1").get_json()


def test_a_burst_at_doors_open_is_looked_up_at_the_set_rate_and_drains(lan_here, hall, monkeypatch):
    # 2 lookups a second, saved up for one round (20): 30 check-ins take two rounds, oldest first.
    monkeypatch.setenv("CHECKIN_VERIFY_RATE", "2")
    monkeypatch.setattr(checkin, "_bucket", {"tokens": None, "at": None})
    hall.post("/api/seat-blocks", json={"name": "B", "x": 10, "y": 60, "cols": 30, "rows": 1})
    asked = []
    monkeypatch.setattr(checkin, "port_of", lambda ip: asked.append(ip) or edge("sw-b-01", ip))
    seats = pins(hall)
    for i in range(30):
        check_in(hall, f"198.51.100.{i + 1}", verify=False, pin=seats[f"B-{i + 1}"], username=f"n{i}")
    assert checkin.queue_depth() == 30
    assert len(checkin.verify_pending(now=1000)) == 20
    assert asked[0] == "198.51.100.1" and checkin.queue_depth() == 10
    assert len(checkin.verify_pending(now=1001)) == 2 and len(asked) == 22   # 1 s later: 2 more
    checkin.verify_pending(now=1010)
    assert checkin.queue_depth() == 0 and len(set(asked)) == 30


def test_the_seat_hint_never_waits_for_librenms(hall, monkeypatch):
    # At doors-open every page load would be a LibreNMS lookup: the hint comes from the cache, and
    # a miss is looked up in the background, so the next load shows it. The app's own verify thread
    # may do that lookup while the test runs, so only lookups on the request's thread count as waiting.
    hall.post("/api/cables", json={"switch": "sw-a-01", "port": "Gi1/0/1", "seat": "A-1"})
    asked = []
    waited = []

    class Monitor:
        def enabled(self):
            return True

        def resolve_ip(self, ip):
            asked.append(ip)
            if threading.current_thread() is request_thread:
                waited.append(ip)
            return {"device_name": "sw-a-01", "port": "Gi1/0/1", "macs_on_port": 1}
    monkeypatch.setattr(checkin, "_monitoring", Monitor)
    monkeypatch.setattr(checkin, "port_of", PORT_OF)
    request_thread = threading.current_thread()   # the test client serves requests on this thread
    info = lambda: hall.get("/api/checkin/info", environ_base={"REMOTE_ADDR": "192.0.2.21"}).get_json()  # noqa: E731
    assert info()["suggested_seat"] is None and waited == []
    checkin.verify_pending()
    assert "192.0.2.21" in asked and info()["suggested_seat"] == "A-1"


def test_guessing_pins_locks_that_pc_out_for_a_while(hall, monkeypatch):
    monkeypatch.setenv("CHECKIN_PIN_TRIES", "3")
    good = pins(hall)["A-1"]
    for _ in range(3):
        assert check_in(hall, "192.0.2.21", verify=False, pin="ZZZZZ", username="pixel").status_code == 403
    # Even the right PIN waits now: otherwise the limit would only slow a script down.
    r = check_in(hall, "192.0.2.21", verify=False, pin=good, username="pixel")
    assert r.status_code == 429 and "10 min" in r.get_json()["error"]
    # Another PC is not held up by this one.
    assert check_in(hall, "192.0.2.22", verify=False, pin=pins(hall)["A-2"], username="nova").status_code == 200
    # Ten minutes later.
    guesses = checkin._wrong_pins["192.0.2.21"]
    checkin._wrong_pins["192.0.2.21"] = [t - checkin.WRONG_PIN_WINDOW for t in guesses]
    assert check_in(hall, "192.0.2.21", verify=False, pin=good, username="pixel").status_code == 200


def test_the_lockout_speaks_german_too(hall, monkeypatch):
    monkeypatch.setenv("CHECKIN_PIN_TRIES", "1")
    check_in(hall, "192.0.2.21", verify=False, pin="ZZZZZ", username="pixel")
    r = hall.post("/api/checkin", json={"pin": "ZZZZZ", "username": "pixel"},
                  environ_base={"REMOTE_ADDR": "192.0.2.21"}, headers={"Accept-Language": "de-CH"})
    assert r.status_code == 429 and "Zu viele falsche PINs" in r.get_json()["error"]


def test_outside_the_event_network_a_pin_is_not_even_looked_at(hall, monkeypatch):
    monkeypatch.setenv("CHECKIN_ALLOWED_NETWORKS", "192.0.2.0/24")
    good = pins(hall)["A-1"]
    wrong = check_in(hall, "198.51.100.7", verify=False, pin="ZZZZZ", username="pixel")
    right = check_in(hall, "198.51.100.7", verify=False, pin=good, username="pixel")
    # Same answer either way, so the PIN can't be tested from outside.
    assert wrong.status_code == right.status_code == 403
    assert wrong.get_json()["error"] == right.get_json()["error"]
    assert checkin._wrong_pins == {}


@pytest.mark.parametrize("body", [{"seat": "A-1", "username": 7}, {"pin": ["x"], "username": "pixel"},
                                  {"seat": {"a": 1}, "username": "pixel"},
                                  {"seat": "A-1", "username": "pixel", "device": 3}])
def test_values_of_the_wrong_type_are_a_clear_no_not_a_crash(hall, body):
    r = hall.post("/api/checkin", json=body, environ_base={"REMOTE_ADDR": "192.0.2.21"})
    assert r.status_code < 500 and r.is_json


def test_two_pcs_with_the_same_pin_at_once_only_one_gets_the_seat(hall, app_module, monkeypatch):
    # The PIN's one-use check read the check-ins before the write lock: PCs typing the same card at
    # the same moment all passed it, and the last one took the seat from the others.
    pin = pins(hall)["A-1"]
    real = checkin.load_all
    gate = threading.Barrier(8)

    def slow_load():
        rows = real()
        with contextlib.suppress(threading.BrokenBarrierError):
            gate.wait(timeout=1)          # every request has read "nobody holds A-1"
        return rows
    monkeypatch.setattr(checkin, "load_all", slow_load)
    codes = []

    def one(n):
        c = app_module.app.test_client()
        r = c.post("/api/checkin", json={"pin": pin, "username": f"pc{n}"},
                   environ_base={"REMOTE_ADDR": f"192.0.2.{40 + n}"})
        codes.append(r.status_code)
    threads = [threading.Thread(target=one, args=(n,)) for n in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(codes) == [200] + [409] * 7
    monkeypatch.setattr(checkin, "load_all", real)
    assert len([r for r in checkin.load_all().values() if r["seat"] == "A-1"]) == 1
