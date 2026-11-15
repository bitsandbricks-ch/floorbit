"""MikroTik (RouterOS REST) as a monitoring source (issue #39). Fake devices, never real ones."""
import pytest
import requests

from floorbit import sources


class Answer:
    def __init__(self, body=None, status=200):
        self.status_code = status
        self._body = body if body is not None else []

    def json(self):
        return self._body


PLAYER_MAC = "02:00:00:00:00:0A"
DEVICES = {
    "192.0.2.1": {   # the core: the ARP table, and the player's MAC seen on its uplink to sw-a-01
        "system/resource": {"cpu-load": "5", "total-memory": "1000", "free-memory": "500", "board-name": "CRS326"},
        "interface": [{"name": "sfp1", "type": "ether", "running": "true", "comment": "Uplink sw-a-01"}],
        "ip/arp": [{"address": "198.51.100.10", "mac-address": PLAYER_MAC, "interface": "vlan100"}],
        "interface/bridge/host": [{"mac-address": PLAYER_MAC, "on-interface": "sfp1", "vid": "100"}],
    },
    "192.0.2.21": {
        "system/resource": {"cpu-load": "12", "total-memory": "1000", "free-memory": "250", "board-name": "CRS354"},
        "interface": [
            {"name": "ether1", "type": "ether", "running": "true", "disabled": "false", "comment": "Seat A1",
             "rx-error": "0", "tx-error": "3"},
            {"name": "ether2", "type": "ether", "running": "false", "disabled": "true"},
            {"name": "bridge", "type": "bridge", "running": "true"},
        ],
        "interface/monitor-traffic": [{"name": "ether1", "rx-bits-per-second": "10000000",
                                       "tx-bits-per-second": "20000000"},
                                      {"name": "ether2", "rx-bits-per-second": "0", "tx-bits-per-second": "0"}],
        "interface/ethernet/monitor": [{"name": "ether1", "rate": "1Gbps", "full-duplex": "true"},
                                       {"name": "ether2", "status": "no-link"}],
        "ip/arp": [],
        "interface/bridge/host": [{"mac-address": PLAYER_MAC, "on-interface": "ether1", "vid": "100"}],
    },
}


@pytest.fixture
def mikrotik(client, monkeypatch):
    calls = []

    def fake(self, method, url, **kw):
        host, _, path = url.removeprefix("https://").partition("/rest/")
        calls.append((host, method, path, kw.get("params"), self.auth))
        if host not in DEVICES:
            raise requests.exceptions.ConnectTimeout("no answer")
        if self.auth != ("floorbit-ro", "example-password"):
            return Answer(status=401)
        body = DEVICES[host].get(path)
        if path in ("ip/arp", "interface/bridge/host") and kw.get("params"):
            key, want = next(iter(kw["params"].items()))
            body = [r for r in body if r.get(key) == want]
        return Answer(body) if body is not None else Answer(status=404)

    monkeypatch.setattr(requests.Session, "request", fake)
    client.put("/api/settings", json={
        "plugin.mikrotik.switches": ["core-01=https://192.0.2.1", "sw-a-01=https://192.0.2.21/ignored",
                                     "sw-b-01=https://192.0.2.22"],
        "plugin.mikrotik.username": "floorbit-ro", "plugin.mikrotik.password": "example-password"})
    assert client.put("/api/settings/plugins/mikrotik", json={"enabled": True}).status_code == 200
    return calls


def test_mikrotik_switches_ports_and_where_a_player_is(app_module, mikrotik):
    with app_module.app.app_context():
        source = sources.monitoring()
        assert source.name == "mikrotik"
        assert [(d["hostname"], d["status"]) for d in source.devices()] == \
            [("core-01", 1), ("sw-a-01", 1), ("sw-b-01", 0)]

        details = source.device_details("sw-a-01")
        assert (details["status"], details["cpu_load"], details["mem_percent"]) == ("online", 12, 75)
        assert details["up_ports"] == 1 and details["total_ports"] == 2   # the bridge is not a port
        assert source.device_details("sw-b-01")["status"] == "offline"

        ports = {p["name"]: p for p in source.device_ports("sw-a-01")}
        assert ports["ether1"]["description"] == "Seat A1" and ports["ether1"]["speed_bps"] == 1e9
        assert ports["ether1"]["upload_bps"] == 10_000_000 and ports["ether1"]["download_bps"] == 20_000_000
        assert ports["ether1"]["duplex"] == "full" and ports["ether1"]["errors_out"] == 3
        assert ports["ether2"]["state"] == "disabled"

        found = source.resolve_ip("198.51.100.10")
        # The core sees the MAC on its uplink; the access switch's port wins.
        assert (found["device_name"], found["port"], found["vlan"]) == ("sw-a-01", "ether1", "100")
        assert found["mac"] == "02:00:00:00:00:0a" and found["stats"]["state"] == "up"
        assert source.resolve_ip("198.51.100.99") is None
        assert source.ip_for_mac("02-00-00-00-00-0a") == "198.51.100.10"

    # Read-only: only GETs and the two monitor calls, always with the account.
    assert {(m, p) for _h, m, p, _q, _a in mikrotik if m == "POST"} <= {
        ("POST", "interface/monitor-traffic"), ("POST", "interface/ethernet/monitor")}


def test_bad_settings_and_wrong_password(client, mikrotik):
    client.put("/api/settings", json={"plugin.mikrotik.password": "wrong"})
    body = client.post("/api/settings/plugins/mikrotik/test").get_json()
    assert body["message"].startswith("0 of 3 switches answering. Not answering: core-01, sw-a-01, sw-b-01")
    log = client.get("/api/settings/plugins/mikrotik/log").get_json()
    assert any("refused the username or password" in line["line"] for line in log["lines"])
    client.put("/api/settings", json={"plugin.mikrotik.switches": ["sw-a-01 192.0.2.21"]})
    body = client.post("/api/settings/plugins/mikrotik/test").get_json()
    assert body["ok"] is False and "is not Name=https://address" in body["message"]
