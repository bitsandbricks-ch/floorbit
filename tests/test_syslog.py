"""Syslog receiver (issue #91): allow-list, caps, parsing and search."""
import json
import os
import socket
import time

import pytest

from floorbit import syslog

NOW = 1_794_650_400.0   # 2026-11-14 10:00 UTC


@pytest.fixture
def receiver(tmp_path, monkeypatch):
    monkeypatch.setenv("SYSLOG_ALLOW", "192.0.2.0/24")
    r = syslog.SyslogReceiver(path=str(tmp_path / "syslog"))
    r._allow_cache = (time.time() + 3600, [syslog.ipaddress.ip_network("192.0.2.0/24")], {"198.51.100.5": "sw-a-01"})
    return r


def test_parse_rfc3164_cisco_and_rfc5424():
    line = syslog.parse(b"<187>Nov 14 10:00:01 sw-a-01 %LINK-3-UPDOWN: Interface Gi1/0/4, changed state to down",
                        now=NOW)
    assert line["severity"] == "err" and line["facility"] == 23
    assert line["host"] == "sw-a-01" and line["program"] == "%LINK-3-UPDOWN"
    assert line["message"] == "Interface Gi1/0/4, changed state to down"
    bare = syslog.parse("<189>%LINEPROTO-5-UPDOWN: Line protocol on Interface Gi1/0/4, changed state to up", now=NOW)
    assert bare["program"] == "%LINEPROTO-5-UPDOWN" and bare["severity"] == "notice"
    rfc5424 = syslog.parse("<30>1 2026-11-14T09:59:00Z dhcp-01 dhcpd 812 - - DHCPACK on 192.0.2.40", now=NOW)
    assert rfc5424["ts"] == NOW - 60 and rfc5424["host"] == "dhcp-01" and rfc5424["program"] == "dhcpd"
    assert rfc5424["message"] == "DHCPACK on 192.0.2.40"
    # No PRI at all, and a clock a year off: user.notice, stamped when it arrived.
    plain = syslog.parse("<13>1 2025-01-01T00:00:00Z h a - - - text", now=NOW)
    assert plain["ts"] == NOW
    assert syslog.parse("just text", now=NOW)["severity"] == "notice"
    assert len(syslog.parse("<13>" + "x" * 5000, now=NOW)["message"]) <= syslog.MAX_LINE


def test_ports_long_and_short_are_the_same():
    assert syslog.canonical_port("GigabitEthernet1/0/4") == syslog.canonical_port("Gi1/0/4") == "gi1/0/4"
    assert syslog.ports_in("flapping between port Gi1/0/6 and port Gi1/0/7") == ["gi1/0/6", "gi1/0/7"]
    assert syslog.ports_in("Interface TenGigabitEthernet1/1/1, changed state to up") == ["te1/1/1"]
    assert syslog.ports_in("nothing here") == []


def test_only_allowed_senders_are_kept(receiver):
    assert receiver.receive(b"<14>hello", "192.0.2.9", now=NOW)
    assert receiver.receive(b"<14>from the switch", "198.51.100.5", now=NOW)["device"] == "sw-a-01"
    assert receiver.receive(b"<14>who is this", "203.0.113.7", now=NOW) is None
    assert receiver.receive(b"<14>not an address", "nonsense", now=NOW) is None
    assert receiver.counts == {"received": 4, "kept": 2, "not_allowed": 2, "rate_limited": 0}


def test_switches_need_not_be_listed_unless_turned_off(receiver, monkeypatch):
    monkeypatch.setenv("SYSLOG_ALLOW_SWITCHES", "0")
    assert receiver.receive(b"<14>from the switch", "198.51.100.5", now=NOW) is None


def test_a_chatty_sender_is_capped(receiver, monkeypatch):
    monkeypatch.setenv("SYSLOG_RATE", "5")
    kept = [receiver.receive(b"<14>spam", "192.0.2.9", now=NOW) for _ in range(8)]
    assert sum(1 for k in kept if k) == 5 and receiver.counts["rate_limited"] == 3
    # A second later the bucket is full again; another sender has its own.
    assert receiver.receive(b"<14>later", "192.0.2.9", now=NOW + 1)
    assert receiver.receive(b"<14>other", "192.0.2.10", now=NOW)


def test_a_port_finds_its_seat(receiver):
    receiver.port_seats = lambda: {("sw-a-01", "Gi1/0/4"): "A-4"}
    line = receiver.receive(b"<187>%LINK-3-UPDOWN: Interface GigabitEthernet1/0/4, changed state to down",
                            "198.51.100.5", now=NOW)
    assert line["port"] == "gi1/0/4" and line["seat"] == "A-4"
    other = receiver.receive(b"<187>%LINK-3-UPDOWN: Interface Gi1/0/5, changed state to down", "198.51.100.5", now=NOW)
    assert other["port"] == "gi1/0/5" and other["seat"] is None
    # The port watch reads the ports later: the line finds its seat then.
    receiver.port_seats = lambda: {("sw-a-01", "Gi1/0/5"): "A-5"}
    assert [ln["id"] for ln in receiver.search(seat="A-5")] == [other["id"]]


def test_search_filters_newest_first(receiver):
    receiver.port_seats = lambda: {("sw-a-01", "Gi1/0/4"): "A-4"}
    receiver.receive(b"<187>%LINK-3-UPDOWN: Interface Gi1/0/4, changed state to down", "198.51.100.5", now=NOW)
    receiver.receive(b"<190>dhcpd: DHCPACK on 192.0.2.40", "192.0.2.9", now=NOW + 1)
    receiver.receive(b"<188>%SW_MATM-4-MACFLAP_NOTIF: Host 0200.0000.003d flapping", "198.51.100.5", now=NOW + 2)
    assert [ln["id"] for ln in receiver.search()] == [3, 2, 1]
    assert [ln["id"] for ln in receiver.search(severity="warning")] == [3, 1]
    assert [ln["id"] for ln in receiver.search(device="SW-A-01")] == [3, 1]
    assert [ln["id"] for ln in receiver.search(seat="a-4")] == [1]
    assert [ln["id"] for ln in receiver.search(port="GigabitEthernet1/0/4")] == [1]
    assert [ln["id"] for ln in receiver.search(q="dhcpack 192.0.2.40")] == [2]
    assert [ln["id"] for ln in receiver.search(after=1)] == [3, 2]
    assert [ln["id"] for ln in receiver.search(before=3, limit=1)] == [2]
    assert receiver.status()["devices"] == ["192.0.2.9", "sw-a-01"]


def test_lines_survive_a_restart_and_age_out(receiver, tmp_path, monkeypatch):
    now = time.time()
    receiver.receive(b"<14>old", "192.0.2.9", now=now - 30 * 3600)
    receiver.receive(b"<14>new", "192.0.2.9", now=now)
    folder = tmp_path / "syslog"
    assert len(os.listdir(folder)) == 2
    row = json.loads((folder / sorted(os.listdir(folder))[-1]).read_text().splitlines()[0])
    assert row["message"] == "new" and row["sender"] == "192.0.2.9"
    again = syslog.SyslogReceiver(path=str(folder))
    assert [ln["message"] for ln in again.lines] == ["new"] and again.next_id == 3
    again.prune_files(now=now)
    assert len(os.listdir(folder)) == 1


def test_memory_and_disk_are_capped(receiver, tmp_path, monkeypatch):
    monkeypatch.setenv("SYSLOG_MAX_LINES", "100")
    for i in range(150):
        receiver.receive(f"<14>line {i}".encode(), "192.0.2.9", now=NOW + i / 1000, check=False)
    assert len(receiver.lines) == 100 and receiver.lines[0]["message"] == "line 50"
    folder = tmp_path / "syslog"
    for hour in range(3):
        (folder / f"2026-11-14-0{hour}.jsonl").write_text("x" * 700_000)
    monkeypatch.setenv("SYSLOG_MAX_MB", "1")
    receiver.prune_files(now=NOW)
    left = sorted(os.listdir(folder))
    assert "2026-11-14-00.jsonl" not in left and "2026-11-14-10.jsonl" in left


def test_udp_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv("SYSLOG_ENABLED", "1")
    monkeypatch.setenv("SYSLOG_PORT", str(_free_port()))
    monkeypatch.setenv("SYSLOG_BIND", "127.0.0.1")
    monkeypatch.setenv("SYSLOG_ALLOW", "127.0.0.1")
    r = syslog.SyslogReceiver(path=str(tmp_path / "syslog"))
    r._allow_cache = (time.time() + 3600, [syslog.ipaddress.ip_network("127.0.0.1/32")], {})
    r.start()
    try:
        assert r.listening and r.listening["port"] == int(os.environ["SYSLOG_PORT"])
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.sendto(b"<14>hello over udp", ("127.0.0.1", r.listening["port"]))
        for _ in range(100):
            if r.lines:
                break
            time.sleep(0.02)
        assert r.lines and r.lines[-1]["message"] == "hello over udp" and r.lines[-1]["sender"] == "127.0.0.1"
    finally:
        r.stop()
    assert r.listening is None


def test_off_by_default(tmp_path):
    r = syslog.SyslogReceiver(path=str(tmp_path / "syslog"))
    r.start()
    assert r.listening is None and r.status()["enabled"] is False


def test_the_demo_hall_sends_lines():
    lines = syslog.demo_lines(NOW)
    assert any("%LINK-3-UPDOWN" in raw for _dev, raw in lines)
    for _dev, raw in lines:
        for word in raw.replace(",", " ").split():
            if word.count(".") == 3 and word.replace(".", "").isdigit():
                assert word.startswith(("192.0.2.", "198.51.100.", "203.0.113.")), word


def test_api(client, app_module, monkeypatch):
    receiver = app_module.app.extensions["floorbit_syslog"]
    monkeypatch.setattr(receiver, "lines", syslog.deque())
    receiver.receive(b"<187>%LINK-3-UPDOWN: Interface Gi1/0/4, changed state to down", "192.0.2.9", check=False)
    receiver.receive(b"<190>dhcpd: DHCPACK on 192.0.2.40", "192.0.2.9", check=False)
    body = client.get("/api/logs?severity=err").get_json()
    assert [ln["message"] for ln in body["lines"]] == ["Interface Gi1/0/4, changed state to down"]
    assert body["status"]["enabled"] is False and body["status"]["lines"] == 2
    last = body["status"]["last_id"]
    assert client.get(f"/api/logs?after={last}").get_json()["lines"] == []
    assert client.get("/api/logs?severity=loud").status_code == 400
    assert client.get("/api/logs?limit=0").status_code == 400
    assert client.get("/api/logs?after=x").status_code == 400
    assert client.get("/logs").status_code in (200, 503)   # 503 only when the React app isn't built


def test_logs_need_seats_view(client, app_module):
    app_module.app.extensions["auth"].users.add("hall-screen", "kiosk-password-1", role="kiosk")
    kiosk = app_module.app.test_client()
    kiosk.post("/login", data={"username": "hall-screen", "password": "kiosk-password-1"})
    assert kiosk.get("/api/logs").status_code == 403


def test_feature_off_hides_logs(client):
    assert client.put("/api/settings/features", json={"syslog": False}).status_code == 200
    assert client.get("/api/logs").status_code == 404


def _free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]
