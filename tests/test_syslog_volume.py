"""The logs page's time range, volume chart and download (issue #1048)."""
import time

import pytest

from floorbit import syslog

NOW = 1_794_650_400.0   # 2026-11-14 10:00 UTC


@pytest.fixture
def receiver(tmp_path, monkeypatch):
    monkeypatch.setenv("SYSLOG_ALLOW", "192.0.2.0/24")
    r = syslog.SyslogReceiver(path=str(tmp_path / "syslog"))
    r._allow_cache = (time.monotonic() + 3600, [syslog.ipaddress.ip_network("192.0.2.0/24")], {})
    return r


def _fill(receiver):
    receiver.receive(b"<187>%LINK-3-UPDOWN: Interface Gi1/0/4, changed state to down", "192.0.2.9", now=NOW)
    receiver.receive(b"<190>dhcpd: DHCPACK on 192.0.2.40", "192.0.2.9", now=NOW + 30)
    receiver.receive(b"<187>%LINK-3-UPDOWN: Interface Gi1/0/5, changed state to down", "192.0.2.9", now=NOW + 90)


def test_search_keeps_a_time_window(receiver):
    _fill(receiver)
    assert [ln["id"] for ln in receiver.search(since=NOW + 30)] == [3, 2]
    assert [ln["id"] for ln in receiver.search(until=NOW + 30)] == [1]
    assert [ln["id"] for ln in receiver.search(since=NOW + 1, until=NOW + 60)] == [2]


def test_volume_counts_lines_and_errors_per_slice(receiver):
    _fill(receiver)
    v = receiver.volume(NOW, NOW + 120, buckets=2)
    assert v["step"] == 60
    assert v["buckets"] == [[NOW, 2, 1], [NOW + 60, 1, 1]]
    assert receiver.volume(NOW, NOW + 120, buckets=2, q="dhcpack")["buckets"] == [[NOW, 1, 0], [NOW + 60, 0, 0]]


def test_volume_and_download_api(client, app_module, monkeypatch):
    receiver = app_module.app.extensions["floorbit_syslog"]
    monkeypatch.setattr(receiver, "lines", syslog.deque())
    now = time.time()
    receiver.receive(b"<187>%LINK-3-UPDOWN: Interface Gi1/0/4, changed state to down", "192.0.2.9", check=False)
    receiver.receive(b"<190>dhcpd: DHCPACK on 192.0.2.40", "192.0.2.9", check=False)
    body = client.get("/api/logs/volume?buckets=10").get_json()
    assert len(body["buckets"]) == 10
    assert sum(b[1] for b in body["buckets"]) == 2 and sum(b[2] for b in body["buckets"]) == 1
    assert client.get("/api/logs/volume?since=5&until=4").status_code == 400
    assert client.get("/api/logs/volume?buckets=0").status_code == 400
    assert client.get(f"/api/logs?since={now + 3600}").get_json()["lines"] == []

    res = client.get("/api/logs/download?severity=err")
    assert res.status_code == 200
    assert res.headers["Content-Disposition"].startswith('attachment; filename="floorbit-syslog-')
    text = res.get_data(as_text=True)
    assert text.count("\n") == 1 and "err" in text and "Interface Gi1/0/4, changed state to down" in text
    lines = client.get("/api/logs/download").get_data(as_text=True).splitlines()
    assert "LINK" in lines[0] and "DHCPACK" in lines[1]   # oldest first, like a log file
    assert client.get("/api/logs/download?since=x").status_code == 400
    from floorbit import audit
    assert any(e["action"] == "Downloaded syslog lines" for e in audit.read(area="security")[0])
