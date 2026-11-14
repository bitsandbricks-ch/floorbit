"""Log alerts (issue #92): known syslog patterns become needs-attention items; seats light up."""
import time

import pytest

from floorbit import log_alerts, syslog
from integrations import events

NOW = 1_794_650_400.0


@pytest.fixture
def receiver(tmp_path):
    r = syslog.SyslogReceiver(path=str(tmp_path / "syslog"))
    r.port_seats = lambda: {("sw-b-01", "Gi1/0/3"): "B-3"}
    return r


def test_known_patterns():
    cases = {
        "%PM-4-ERR_DISABLE: bpduguard error detected on Gi1/0/3, putting Gi1/0/3 in err-disable state": "err_disable",
        "%PORT_SECURITY-2-PSECURE_VIOLATION: Security violation occurred on port Gi1/0/9": "port_security",
        "%DHCP_SNOOPING-5-DHCP_SNOOPING_UNTRUSTED_PORT: drop message on untrusted port": "dhcp_snooping",
        "%SW_MATM-4-MACFLAP_NOTIF: Host 0200.0000.003d is flapping between port Gi1/0/6 and port Gi1/0/7":
            "mac_flap",
        "%ETHCNTR-3-LOOP_BACK_DETECTED: Loop-back detected on Gi1/0/2": "loop",
        "%STORM_CONTROL-3-FILTERED: A Broadcast storm detected on Gi1/0/5": "storm",
        "%SPANTREE-5-TOPOTRAP: Topology Change Trap for vlan 100": "stp",
        "%LINK-3-UPDOWN: Interface Gi1/0/4, changed state to down": None,
    }
    for message, want in cases.items():
        assert log_alerts.match(message) == want, message


def test_a_flood_is_one_item(receiver, monkeypatch):
    published = []
    monkeypatch.setattr(events, "publish", lambda kind, data: published.append(kind))
    raw = b"<188>%PM-4-ERR_DISABLE: bpduguard error detected on Gi1/0/3, putting Gi1/0/3 in err-disable state"
    for i in range(50):
        receiver.receive(raw, "198.51.100.11", now=NOW + i, check=False, device="sw-b-01")
    items = receiver.alert_items(now=NOW + 50)
    assert len(items) == 1
    item = items[0]
    assert item["pattern"] == "err_disable" and item["count"] == 50 and item["seat"] == "B-3"
    assert item["port"] == "gi1/0/3" and "bpduguard" not in item["title"]
    assert published.count("logs.alert") == 1
    # Another port is its own item.
    receiver.receive(raw.replace(b"1/0/3", b"1/0/4"), "198.51.100.11", now=NOW + 60, check=False, device="sw-b-01")
    assert len(receiver.alert_items(now=NOW + 60)) == 2


def test_items_clear_once_quiet(receiver, monkeypatch):
    monkeypatch.setenv("LOG_ALERT_MINUTES", "5")
    receiver.receive(b"<189>%SPANTREE-5-TOPOTRAP: Topology Change Trap for vlan 100", "198.51.100.2", now=NOW,
                     check=False, device="dist-01")
    assert len(receiver.alert_items(now=NOW + 299)) == 1
    assert receiver.alert_items(now=NOW + 301) == []


def test_markers_count_recent_warnings_per_seat_and_switch(receiver):
    now = time.time()
    receiver.receive(b"<187>%LINK-3-UPDOWN: Interface Gi1/0/3, changed state to down", "198.51.100.11", now=now,
                     check=False, device="sw-b-01")
    receiver.receive(b"<189>%SPANTREE-5-TOPOTRAP: Topology Change Trap", "198.51.100.2", now=now, check=False,
                     device="dist-01")
    receiver.receive(b"<187>%LINK-3-UPDOWN: Interface Gi1/0/1, changed state to down", "198.51.100.11",
                     now=now - 3600, check=False, device="sw-b-01")
    receiver.receive(b"<190>dhcpd: DHCPACK", "192.0.2.9", now=now, check=False, device="dist-01")
    marks = receiver.markers({"sw-b-01": "sw-b-01-id", "dist-01": "dist-01-id"})
    # The notice and the info line are below warning; the hour-old line is too old.
    assert marks["seats"] == {"B-3": 1} and marks["switches"] == {}
    receiver.receive(b"<188>%STORM_CONTROL-3-FILTERED: storm", "198.51.100.2", now=now, check=False, device="dist-01")
    assert receiver.markers({"dist-01": "dist-01-id"})["switches"] == {"dist-01-id": 1}


def test_problems_and_api(client, app_module, monkeypatch):
    receiver = app_module.app.extensions["floorbit_syslog"]
    monkeypatch.setattr(receiver, "alerts", log_alerts.LogAlerts())
    receiver.receive(b"<188>%PM-4-ERR_DISABLE: bpduguard error detected on Gi1/0/3, putting Gi1/0/3 in "
                     b"err-disable state", "198.51.100.11", check=False, device="sw-b-01")
    attention = client.get("/api/problems").get_json()["attention"]
    log = [a for a in attention if a["kind"] == "log"]
    assert len(log) == 1 and log[0]["title"] == "Port shut down by the switch (err-disable)"
    assert log[0]["link"] == "/logs?device=sw-b-01" and log[0]["where"] == "sw-b-01 gi1/0/3"
    assert client.get("/api/logs/alerts").get_json()["alerts"][0]["pattern"] == "err_disable"
    assert client.get("/api/logs/markers").get_json()["minutes"] == 10
    # The feature off: no log items.
    assert client.put("/api/settings/features", json={"syslog": False}).status_code == 200
    assert not [a for a in client.get("/api/problems").get_json()["attention"] if a["kind"] == "log"]


def test_webhook_payload_leaves_the_line_out():
    from floorbit import webhooks
    out = webhooks.translate({"type": "logs.alert", "data": {
        "id": "log:err_disable:sw-b-01:gi1/0/3", "pattern": "err_disable", "title": "t", "device": "sw-b-01",
        "port": "gi1/0/3", "seat": "B-3", "message": "MAC 0200.0000.0007"}})
    assert out == [("logs.alert", {"id": "log:err_disable:sw-b-01:gi1/0/3", "pattern": "err_disable", "title": "t",
                                   "device": "sw-b-01", "port": "gi1/0/3", "seat": "B-3"})]
