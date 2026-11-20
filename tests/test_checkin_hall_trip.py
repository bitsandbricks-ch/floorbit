"""Check-in opened on Floorbit's own address goes on to an agent's front door (integrations/hall_trip):
only there is the seat PC's own address known. By itself only where Floorbit is sure the browser is
in the hall; otherwise the page offers it."""
import pytest

from tests.test_agent import clean_tunnel, enrol, head  # noqa: F401  # the fixture resets the tunnel
from tests.test_front_door import door

PC = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
PHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) Mobile"
HALL = "203.0.113.20"       # the hall's uplink, as hosted Floorbit sees it
HOME = "198.51.100.77"      # somebody at home


@pytest.fixture
def checkin_on(monkeypatch):
    monkeypatch.setenv("CHECKIN_ENABLED", "true")
    monkeypatch.setenv("CHECKIN_ADDRESS", "checkin.lan")


def info(anon_client, addr=HOME, ua=PC, headers=None):
    return anon_client.get("/api/checkin/info", headers={"User-Agent": ua, **(headers or {})},
                           environ_base={"REMOTE_ADDR": addr}).get_json()


def test_a_pc_on_floorbits_address_is_offered_the_hall(client, anon_client, checkin_on):
    got = info(anon_client)
    assert got["outside"] is True
    assert got["hall"]["url"].startswith("http://checkin.lan/checkin?via=")
    assert got["hall"]["sure"] is False        # nothing says this browser is in the hall


def test_phones_and_the_front_door_get_no_trip(client, anon_client, checkin_on):
    assert info(anon_client, ua=PHONE)["hall"] is None
    key = enrol(client)["key"]
    got = info(anon_client, headers=door(key))
    assert got["ip"] == "10.10.1.7" and got["hall"] is None


def test_without_an_agent_address_there_is_nowhere_to_go(client, anon_client, monkeypatch):
    monkeypatch.setenv("CHECKIN_ENABLED", "true")
    assert info(anon_client)["hall"] is None


def test_a_trip_that_arrives_marks_the_address_it_left_from(client, anon_client, checkin_on):
    key = enrol(client)["key"]
    url = info(anon_client, addr=HALL)["hall"]["url"]
    token = url.split("via=")[1]
    resp = anon_client.get(f"/checkin?via={token}&pin=K7M2X", headers=door(key))
    # The code leaves the address bar, the PIN from the seat card stays.
    assert resp.status_code == 302 and resp.headers["Location"].endswith("/checkin?pin=K7M2X")
    assert info(anon_client, addr=HALL)["hall"]["sure"] is True
    assert info(anon_client, addr=HOME)["hall"]["sure"] is False
    # A code works once.
    from integrations import hall_trip
    assert hall_trip.arrived(token) is False


def test_a_code_not_through_a_front_door_marks_nothing(client, anon_client, checkin_on):
    token = info(anon_client, addr=HALL)["hall"]["url"].split("via=")[1]
    resp = anon_client.get(f"/checkin?via={token}", environ_base={"REMOTE_ADDR": HALL})
    assert resp.status_code == 302 and resp.headers["Location"].endswith("/checkin")
    assert info(anon_client, addr=HALL)["hall"]["sure"] is False


def test_the_address_a_connected_agent_comes_from_is_the_halls(client, anon_client, checkin_on):
    made = enrol(client)
    anon_client.get("/api/agent/v1/hello", headers=head(made["key"]), environ_base={"REMOTE_ADDR": HALL})
    assert info(anon_client, addr=HALL)["hall"]["sure"] is True
    assert info(anon_client, addr=HOME)["hall"]["sure"] is False


def test_a_private_address_is_never_sure(client, anon_client, checkin_on):
    """Behind a proxy Floorbit doesn't trust, every browser has the proxy's address: one trip from
    the hall must not send everybody there."""
    key = enrol(client)["key"]
    anon_client.get("/api/agent/v1/hello", headers=head(key), environ_base={"REMOTE_ADDR": "10.42.0.5"})
    token = info(anon_client, addr="10.42.0.5")["hall"]["url"].split("via=")[1]
    anon_client.get(f"/checkin?via={token}", headers=door(key))
    assert info(anon_client, addr="10.42.0.5")["hall"]["sure"] is False


def test_public_addresses():
    from integrations.hall_trip import public
    assert public("203.0.113.20") == "203.0.113.20"
    assert public("2001:db8::1") == "2001:db8::1"
    for local in ("10.1.2.3", "172.20.0.1", "192.168.1.1", "100.64.0.9", "127.0.0.1", "::1", "fd00::1",
                  "::ffff:10.0.0.1", "nonsense", None):
        assert public(local) is None
