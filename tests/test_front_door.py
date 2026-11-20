"""Attendees through the local agent's front door (floorbit-agent's front_door.py): with the agent's
key on the request, the address it saw is the client's, so check-in works behind the hall's NAT.
Without the key, the headers mean nothing."""
import pytest

from tests.test_agent import clean_tunnel, enrol  # noqa: F401  # the fixture resets the tunnel


@pytest.fixture
def checkin_on(monkeypatch):
    monkeypatch.setenv("CHECKIN_ENABLED", "true")


def door(key, ip="10.10.1.7", host=None):
    h = {"Floorbit-Front-Door": key, "Floorbit-Client-IP": ip}
    if host:
        h["Floorbit-Front-Door-Host"] = host
    return h


def test_the_front_door_names_the_attendees_address(client, anon_client, checkin_on):
    key = enrol(client)["key"]
    got = anon_client.get("/api/checkin/info", headers=door(key)).get_json()
    assert got["ip"] == "10.10.1.7"


def test_without_the_agents_key_the_header_is_ignored(client, anon_client, checkin_on):
    key = enrol(client)["key"]
    for headers in (door(key[:-3] + "xyz"), door("fba_00000000_" + "a" * 30), {"Floorbit-Client-IP": "10.10.1.7"}):
        assert anon_client.get("/api/checkin/info", headers=headers).get_json()["ip"] != "10.10.1.7"


def test_a_revoked_agents_front_door_stops_counting(client, anon_client, checkin_on):
    from floorbit import agent_link
    made = enrol(client)
    assert anon_client.get("/api/checkin/info", headers=door(made["key"])).get_json()["ip"] == "10.10.1.7"
    assert client.delete(f"/api/agents/{made['id']}").status_code == 200
    agent_link._doors.clear()       # what DOOR_RECHECK seconds do
    assert anon_client.get("/api/checkin/info", headers=door(made["key"])).get_json()["ip"] != "10.10.1.7"


def test_a_bad_address_is_not_taken(client, anon_client, checkin_on):
    key = enrol(client)["key"]
    assert anon_client.get("/api/checkin/info", headers=door(key, ip="not-an-ip")).get_json()["ip"] != "not-an-ip"


def test_the_short_address_typed_at_the_front_door_opens_check_in(client, anon_client, checkin_on, monkeypatch):
    monkeypatch.setenv("CHECKIN_ADDRESS", "http://checkin.lan/")
    key = enrol(client)["key"]
    resp = anon_client.get("/", headers=door(key, host="checkin.lan"))
    assert resp.status_code == 302 and resp.headers["Location"].endswith("/checkin")
    # Someone else can't send people there by naming the host without the key.
    resp = anon_client.get("/", headers={"Floorbit-Front-Door-Host": "checkin.lan"})
    assert not (resp.status_code == 302 and resp.headers.get("Location", "").endswith("/checkin"))


def test_a_form_sent_from_the_front_doors_page_is_same_origin(client, anon_client, checkin_on):
    """The browser's page is on the name it typed at the door (checkin.lan:8080), not the hosted
    name, so its Origin is that name: with the agent's key it counts as this site."""
    key = enrol(client)["key"]
    body = {"name": "sw", "x": 1, "y": 1}
    origin = {"Origin": "http://checkin.lan:8080"}
    through = door(key, host="checkin.lan:8080")
    assert client.post("/api/switches", json=body, headers={**through, **origin}).status_code == 201
    # Naming the host without the key is a cross-site post like any other.
    assert client.post("/api/switches", json=body,
                       headers={"Floorbit-Front-Door-Host": "checkin.lan:8080", **origin}).status_code == 403
    assert client.post("/api/switches", json=body,
                       headers={**through, "Origin": "https://evil.example.com"}).status_code == 403
