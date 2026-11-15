"""Aruba AOS-CX as a monitoring source (issue #39). Fake switches, never real ones."""
import pytest
import requests

from floorbit import sources


class Answer:
    def __init__(self, body=None, status=200):
        self.status_code = status
        self._body = body if body is not None else {}

    def json(self):
        return self._body


PLAYER_MAC = "02:00:00:00:00:0a"
SEAT = "/rest/v10.08/system/interfaces/1%2F1%2F7"
UPLINK = "/rest/v10.08/system/interfaces/1%2F1%2F49"
SWITCHES = {
    "192.0.2.1": {   # the core: the ARP table, and the player's MAC seen on its uplink to sw-a-01
        "system": {"hostname": "core-01", "platform_name": "6300"},
        "system/vrfs/default/neighbors": {"198.51.100.10,vlan100": {"ip_address": "198.51.100.10",
                                                                    "mac": PLAYER_MAC.upper()}},
        "system/vlans": {"1": "/rest/v10.08/system/vlans/1", "100": "/rest/v10.08/system/vlans/100"},
        f"system/vlans/100/macs/dynamic%2C{PLAYER_MAC.replace(':', '%3A')}": {"port": {"1/1/49": UPLINK}},
        "system/interfaces/1%2F1%2F49": {"description": "Uplink sw-a-01"},
    },
    "192.0.2.21": {
        "system": {"hostname": "sw-a-01", "platform_name": "6100"},
        "system/interfaces": {
            "1%2F1%2F7": {"name": "1/1/7", "type": "system", "description": "Seat A1", "admin_state": "up",
                          "link_state": "up", "link_speed": 1000000000, "duplex": "full",
                          "rate_statistics": {"rx_bits_per_second": 10000000, "tx_bits_per_second": 20000000},
                          "statistics": {"rx_error": 0, "tx_error": 3}},
            "1%2F1%2F8": {"name": "1/1/8", "type": "system", "admin_state": "down", "link_state": "down"},
            "vlan100": {"name": "vlan100", "type": "vlan", "link_state": "up"},
        },
        "system/vrfs/default/neighbors": {},
        "system/vlans": {"100": "/rest/v10.08/system/vlans/100"},
        f"system/vlans/100/macs/dynamic%2C{PLAYER_MAC.replace(':', '%3A')}": {"port": {"1/1/7": SEAT}},
        "system/interfaces/1%2F1%2F7": {"description": "Seat A1"},
    },
}


@pytest.fixture
def aruba(client, monkeypatch):
    calls = []

    def fake(self, method, url, **kw):
        host, _, path = url.removeprefix("https://").partition("/rest/v10.08/")
        calls.append((host, method, path))
        if host not in SWITCHES:
            raise requests.exceptions.ConnectTimeout("no answer")
        if path == "login":
            ok = kw.get("data") == {"username": "floorbit-ro", "password": "example-password"}
            self.signed_in = ok
            return Answer(status=200 if ok else 401)
        if path == "logout":
            self.signed_in = False
            return Answer()
        if not getattr(self, "signed_in", False):
            return Answer(status=401)
        body = SWITCHES[host].get(path)
        return Answer(body) if body is not None else Answer(status=404)

    monkeypatch.setattr(requests.Session, "request", fake)
    client.put("/api/settings", json={
        "plugin.aruba.switches": ["core-01=https://192.0.2.1", "sw-a-01=https://192.0.2.21",
                                  "sw-b-01=https://192.0.2.22"],
        "plugin.aruba.username": "floorbit-ro", "plugin.aruba.password": "example-password"})
    assert client.put("/api/settings/plugins/aruba", json={"enabled": True}).status_code == 200
    return calls


def test_aruba_switches_ports_and_where_a_player_is(app_module, aruba):
    with app_module.app.app_context():
        source = sources.monitoring()
        assert source.name == "aruba"
        devices = source.devices()
        assert [(d["hostname"], d["status"]) for d in devices] == [("core-01", 1), ("sw-a-01", 1), ("sw-b-01", 0)]
        assert devices[1]["model"] == "6100"

        details = source.device_details("sw-a-01")
        assert details["status"] == "online"
        assert details["up_ports"] == 1 and details["total_ports"] == 2   # the VLAN interface is not a port
        assert source.device_details("sw-b-01")["status"] == "offline"

        ports = {p["name"]: p for p in source.device_ports("sw-a-01")}
        assert ports["1/1/7"]["description"] == "Seat A1" and ports["1/1/7"]["speed_bps"] == 1e9
        assert ports["1/1/7"]["upload_bps"] == 10_000_000 and ports["1/1/7"]["download_bps"] == 20_000_000
        assert ports["1/1/7"]["duplex"] == "full" and ports["1/1/7"]["errors_out"] == 3
        assert ports["1/1/8"]["state"] == "disabled"

        found = source.resolve_ip("198.51.100.10")
        # The core sees the MAC on its uplink; the access switch's port wins.
        assert (found["device_name"], found["port"], found["vlan"]) == ("sw-a-01", "1/1/7", "100")
        assert found["mac"] == PLAYER_MAC and found["stats"]["state"] == "up"
        assert source.resolve_ip("198.51.100.99") is None

    # Every sign-in is followed by a sign-out: AOS-CX allows only a few sessions per user.
    logins = [h for h, m, p in aruba if p == "login" and h != "192.0.2.22"]   # sw-b-01 never answers
    logouts = [h for h, m, p in aruba if p == "logout"]
    assert sorted(logins) == sorted(logouts) and len(logins) > 3
    # Read-only: the only POSTs are signing in and out.
    assert {p for _h, m, p in aruba if m != "GET"} == {"login", "logout"}


def test_wrong_password_is_reported(client, aruba):
    client.put("/api/settings", json={"plugin.aruba.password": "wrong"})
    body = client.post("/api/settings/plugins/aruba/test").get_json()
    assert body["message"].startswith("0 of 3 switches answering. Not answering: core-01, sw-a-01, sw-b-01")
    log = client.get("/api/settings/plugins/aruba/log").get_json()
    assert any("refused the username or password" in line["line"] for line in log["lines"])
