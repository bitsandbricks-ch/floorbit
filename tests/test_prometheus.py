"""Prometheus as a monitoring source (issue #39). A fake query API, never a real server."""
import re

import pytest
import requests

from floorbit import sources


class Answer:
    def __init__(self, body, status=200):
        self.status_code = status
        self._body = body

    def json(self):
        return self._body


def vector(*rows):
    return {"status": "success", "data": {"resultType": "vector",
                                          "result": [{"metric": m, "value": [0, str(v)]} for m, v in rows]}}


PORT = {"job": "snmp", "instance": "sw-a-01", "ifIndex": "1", "ifName": "Gi1/0/1", "ifAlias": "Seat A1"}
UPLINK = {**PORT, "ifIndex": "49", "ifName": "Te1/1/1", "ifAlias": "Uplink core"}
SERIES = {
    "up": [({"job": "snmp", "instance": "sw-a-01"}, 1), ({"job": "snmp", "instance": "sw-b-01"}, 0)],
    "ifOperStatus": [(PORT, 1), (UPLINK, 2)],
    "ifAdminStatus": [(PORT, 1), (UPLINK, 1)],
    "ifHighSpeed": [(PORT, 1000), (UPLINK, 10000)],
    "ifHCInOctets": [(PORT, 1_250_000), (UPLINK, 0)],
    "ifHCOutOctets": [(PORT, 2_500_000), (UPLINK, 0)],
    "ifInErrors": [(PORT, 0), (UPLINK, 0)],
    "ifOutErrors": [(PORT, 0), (UPLINK, 0)],
}


@pytest.fixture
def prometheus(client, app_module, monkeypatch):
    asked = []

    def fake(self, method, url, **kw):
        assert url.startswith("https://prometheus.example.com/api/v1/query")
        query = kw["params"]["query"]
        asked.append(query)
        metric = re.search(r"(\w+)\{", query).group(1)
        device = re.search(r'instance="([^"]*)"', query)
        rows = [(m, v) for m, v in SERIES.get(metric, []) if not device or m["instance"] == device.group(1)]
        return Answer(vector(*rows))

    monkeypatch.setattr(requests.Session, "request", fake)
    client.put("/api/settings", json={"plugin.prometheus.url": "https://prometheus.example.com"})
    assert client.put("/api/settings/plugins/prometheus", json={"enabled": True}).status_code == 200
    return asked


def test_prometheus_takes_over_from_an_unset_librenms(app_module, prometheus):
    with app_module.app.app_context():
        source = sources.monitoring()
        assert source.name == "prometheus"
        devices = source.devices()
        assert [(d["hostname"], d["status"]) for d in devices] == [("sw-a-01", 1), ("sw-b-01", 0)]

        details = source.device_details("sw-a-01")
        assert details["status"] == "online" and details["up_ports"] == 1 and details["total_ports"] == 2
        assert details["total_traffic_bps"] == 30_000_000   # (1.25 + 2.5) MB/s * 8

        ports = {p["name"]: p for p in source.device_ports("sw-a-01")}
        assert ports["Gi1/0/1"]["state"] == "up" and ports["Gi1/0/1"]["download_bps"] == 20_000_000
        assert ports["Gi1/0/1"]["description"] == "Seat A1" and ports["Gi1/0/1"]["speed_bps"] == 1e9
        assert ports["Te1/1/1"]["state"] == "down"
        assert source.port_stats("sw-a-01", "gi1/0/1")["upload_bps"] == 10_000_000
        assert source.device_details("sw-b-01")["status"] == "offline"
        assert source.device_details("sw-zz")["status"] == "unknown"
        assert source.resolve_ip("192.0.2.10") is None and source.arp("192.0.2.10") == []
    assert any(q.startswith("rate(ifHCInOctets{") and q.endswith("[2m])") for q in prometheus)


def test_names_and_settings_cannot_break_the_query(app_module, prometheus, client):
    from floorbit.builtin_plugins.prometheus.plugin import quote
    # A name stays inside one quoted label value: its quote and backslash are escaped.
    assert quote('sw"} or vector(1) #') == '"sw\\"} or vector(1) #"'
    assert quote("a\\") == '"a\\\\"'
    with app_module.app.app_context():
        assert sources.monitoring().device_ports('sw"} or vector(1) #') == []   # not a switch: never asked
    client.put("/api/settings", json={"plugin.prometheus.device_label": "instance} or up{"})
    test = client.post("/api/settings/plugins/prometheus/test")
    assert test.get_json()["ok"] is False and "is not a label name" in test.get_json()["message"]


def test_connection_test_counts_switches(client, prometheus):
    body = client.post("/api/settings/plugins/prometheus/test").get_json()
    assert body["message"] == 'Connected: 2 switches in job "snmp", 1 answering.'
