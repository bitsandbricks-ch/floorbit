"""UniFi as a monitoring source (issue #39). A fake controller, never a real one."""
import pytest
import requests

from floorbit import sources


class Answer:
    def __init__(self, body=None, status=200, headers=None):
        self.status_code = status
        self._body = body or {}
        self.headers = headers or {}

    def json(self):
        return self._body


SWITCH = {"type": "usw", "name": "sw-a-01", "mac": "AA:BB:CC:00:00:01", "ip": "192.0.2.11", "state": 1,
          "model": "USW-48", "system-stats": {"cpu": "12.5", "mem": "40"}, "general_temperature": 41,
          "port_table": [
              {"port_idx": 1, "name": "Seat A1", "up": True, "enable": True, "speed": 1000, "full_duplex": True,
               "rx_bytes-r": 1_250_000, "tx_bytes-r": 2_500_000, "rx_errors": 0, "tx_errors": 0},
              {"port_idx": 2, "name": "Port 2", "up": False, "enable": True, "speed": 0},
              {"port_idx": 3, "name": "Port 3", "up": False, "enable": False},
          ]}
OFFLINE = {"type": "usw", "name": "sw-b-01", "mac": "aa:bb:cc:00:00:02", "state": 0, "port_table": []}
AP = {"type": "uap", "name": "ap-hall", "mac": "aa:bb:cc:00:00:03", "state": 1}
CLIENTS = [{"mac": "02:00:00:00:00:0a", "ip": "198.51.100.10", "is_wired": True, "sw_mac": "aa:bb:cc:00:00:01",
            "sw_port": 1, "vlan": 100},
           {"mac": "02:00:00:00:00:0b", "ip": "198.51.100.11", "is_wired": False}]


@pytest.fixture
def controller(client, monkeypatch):
    calls = []

    def fake(self, method, url, **kw):
        path = url.split("unifi.example.com", 1)[1]
        calls.append((method, path, dict(self.headers)))
        if path == "/api/auth/login":
            if kw["json"] != {"username": "floorbit-ro", "password": "example-password"}:
                return Answer(status=401)
            return Answer(headers={"x-csrf-token": "csrf-1"})
        if path == "/proxy/network/api/s/default/stat/device":
            return Answer({"data": [SWITCH, OFFLINE, AP]})
        if path == "/proxy/network/api/s/default/stat/sta":
            return Answer({"data": CLIENTS})
        if path == "/api/auth/logout":
            return Answer()
        return Answer(status=404)

    monkeypatch.setattr(requests.Session, "request", fake)
    client.put("/api/settings", json={"plugin.unifi.url": "https://unifi.example.com",
                                      "plugin.unifi.username": "floorbit-ro",
                                      "plugin.unifi.password": "example-password"})
    assert client.put("/api/settings/plugins/unifi", json={"enabled": True}).status_code == 200
    return calls


def test_unifi_switches_ports_and_clients(app_module, controller):
    with app_module.app.app_context():
        source = sources.monitoring()
        assert source.name == "unifi"
        assert [(d["hostname"], d["status"]) for d in source.devices()] == [("sw-a-01", 1), ("sw-b-01", 0)]

        details = source.device_details("sw-a-01")
        assert details["status"] == "online" and details["cpu_load"] == 12 and details["temperature"] == 41
        assert details["up_ports"] == 1 and details["total_ports"] == 3

        ports = {p["name"]: p for p in source.device_ports("sw-a-01")}
        assert ports["Port 1"]["description"] == "Seat A1" and ports["Port 1"]["download_bps"] == 20_000_000
        assert ports["Port 2"]["state"] == "down" and ports["Port 2"]["description"] is None
        assert ports["Port 3"]["state"] == "disabled"
        assert source.port_stats("sw-a-01", "seat a1")["upload_bps"] == 10_000_000

        found = source.resolve_ip("198.51.100.10")
        assert (found["device_name"], found["port"], found["vlan"]) == ("sw-a-01", "Port 1", "100")
        assert found["stats"]["state"] == "up"
        assert source.resolve_ip("198.51.100.11") is None    # on Wi-Fi: no switch port
        assert source.mac_for_ip("198.51.100.10") == "02:00:00:00:00:0a"
        assert source.ip_for_mac("02-00-00-00-00-0A") == "198.51.100.10"
        assert source.device_details("sw-b-01")["status"] == "offline"

    # Every read signs in with the CSRF token it was given, and signs out again.
    reads = [c for c in controller if c[1].startswith("/proxy/")]
    assert reads and all(c[2].get("X-CSRF-Token") == "csrf-1" for c in reads)
    assert sum(c[1] == "/api/auth/login" for c in controller) == sum(c[1] == "/api/auth/logout" for c in controller)


def test_wrong_password_and_bad_site_are_explained(client, controller):
    client.put("/api/settings", json={"plugin.unifi.password": "wrong"})
    body = client.post("/api/settings/plugins/unifi/test").get_json()
    assert body["ok"] is False and "refused the username or password" in body["message"]
    client.put("/api/settings", json={"plugin.unifi.password": "example-password", "plugin.unifi.site": "../x"})
    body = client.post("/api/settings/plugins/unifi/test").get_json()
    assert body["ok"] is False and "is not a site name" in body["message"]


def test_connection_test_counts_switches(client, controller):
    body = client.post("/api/settings/plugins/unifi/test").get_json()
    assert body["message"] == 'Connected: 2 UniFi switches on site "default", 1 online.'
