"""Zabbix as a monitoring source (issue #39). A fake JSON-RPC API, never a real Zabbix."""
import pytest
import requests

from floorbit import sources


class Answer:
    def __init__(self, body, status=200):
        self.status_code = status
        self._body = body

    def json(self):
        return self._body


HOSTS = [
    {"hostid": "10", "host": "sw-a-01", "name": "sw-a-01", "status": "0",
     "interfaces": [{"ip": "192.0.2.21", "available": "1", "type": "2"}]},
    {"hostid": "11", "host": "sw-b-01", "name": "sw-b-01", "status": "0",
     "interfaces": [{"ip": "192.0.2.22", "available": "2", "type": "2"}]},
    {"hostid": "12", "host": "sw-old", "name": "sw-old", "status": "1", "interfaces": []},
]
ITEMS = [
    {"key_": "net.if.status[ifOperStatus.1]", "name": "Interface Gi1/0/1(Seat A1): Operational status",
     "lastvalue": "1"},
    {"key_": "net.if.in[ifHCInOctets.1]", "name": "Interface Gi1/0/1(Seat A1): Bits received", "lastvalue": "10000000"},
    {"key_": "net.if.out[ifHCOutOctets.1]", "name": "Interface Gi1/0/1(Seat A1): Bits sent", "lastvalue": "20000000"},
    {"key_": "net.if.speed[ifHighSpeed.1]", "name": "Interface Gi1/0/1(Seat A1): Speed", "lastvalue": "1000000000"},
    {"key_": "net.if.in.errors[ifInErrors.1]", "name": "Interface Gi1/0/1(Seat A1): Inbound packets with errors",
     "lastvalue": "0"},
    {"key_": "net.if.status[ifOperStatus.2]", "name": "Interface Gi1/0/2(): Operational status", "lastvalue": "2"},
    {"key_": "net.if.in[ifHCInOctets.2]", "name": "Interface Gi1/0/2(): Bits received", "lastvalue": "garbage"},
    {"key_": "system.cpu.util[0]", "name": "CPU utilization", "lastvalue": "12"},
]


@pytest.fixture
def zabbix(client, monkeypatch):
    calls = []

    def fake(self, method, url, **kw):
        assert url == "https://zabbix.example.com/api_jsonrpc.php" and method == "POST"
        rpc = kw["json"]
        calls.append((rpc["method"], rpc["params"], self.headers.get("Authorization")))
        if self.headers.get("Authorization") != "Bearer example-token":
            return Answer({"jsonrpc": "2.0", "error": {"code": -32602, "message": "Invalid params.",
                                                       "data": "Not authorized."}, "id": 1})
        params = rpc["params"]
        if rpc["method"] == "hostgroup.get":
            result = [{"groupid": "5"}] if params["filter"]["name"] == ["Switches"] else []
        elif rpc["method"] == "host.get":
            result = HOSTS
        else:
            result = ITEMS if params.get("hostids") == ["10"] else []
        return Answer({"jsonrpc": "2.0", "result": result, "id": 1})

    monkeypatch.setattr(requests.Session, "request", fake)
    client.put("/api/settings", json={"plugin.zabbix.url": "https://zabbix.example.com",
                                      "plugin.zabbix.token": "example-token"})
    assert client.put("/api/settings/plugins/zabbix", json={"enabled": True}).status_code == 200
    return calls


def test_zabbix_hosts_and_ports(app_module, zabbix):
    from integrations.monitor import StatusMonitor
    with app_module.app.app_context():
        source = sources.monitoring()
        assert source.name == "zabbix"
        devices = source.devices()
        assert [StatusMonitor.device_status(d) for d in devices] == ["online", "offline", "unknown"]

        details = source.device_details("sw-a-01")
        assert details["status"] == "online" and details["up_ports"] == 1 and details["total_ports"] == 2
        assert details["total_traffic_bps"] == 30_000_000
        ports = {p["name"]: p for p in source.device_ports("sw-a-01")}
        assert ports["Gi1/0/1"]["description"] == "Seat A1" and ports["Gi1/0/1"]["speed_bps"] == 1e9
        assert ports["Gi1/0/1"]["upload_bps"] == 10_000_000 and ports["Gi1/0/1"]["download_bps"] == 20_000_000
        assert ports["Gi1/0/2"]["state"] == "down" and ports["Gi1/0/2"]["description"] is None
        assert source.port_stats("sw-a-01", "gi1/0/1")["state"] == "up"
        assert source.device_details("sw-b-01")["status"] == "offline"
        assert source.device_details("sw-old")["status"] == "unknown"
        assert source.resolve_ip("198.51.100.10") is None
    assert all(method.endswith(".get") for method, _p, _a in zabbix)   # it only reads


def test_bad_token_and_missing_group_are_explained(client, zabbix):
    client.put("/api/settings", json={"plugin.zabbix.group": "Nope"})
    body = client.post("/api/settings/plugins/zabbix/test").get_json()
    assert body["ok"] is False and 'no host group "Nope"' in body["message"]
    client.put("/api/settings", json={"plugin.zabbix.group": "Switches", "plugin.zabbix.token": "wrong"})
    body = client.post("/api/settings/plugins/zabbix/test").get_json()
    assert body["ok"] is False and body["message"] == "Zabbix: Not authorized."


def test_connection_test_counts_hosts(client, zabbix):
    body = client.post("/api/settings/plugins/zabbix/test").get_json()
    assert body["message"] == 'Connected: 3 hosts in "Switches", 1 reachable.'
