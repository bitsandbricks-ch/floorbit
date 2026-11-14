"""Post-event report (issue #22)."""
import time

import pytest

from floorbit import pdf, report
from integrations import history


@pytest.fixture
def stats(client, app_module, monkeypatch, tmp_path):
    monkeypatch.setenv("CHECKIN_HISTORY_FILE", str(tmp_path / "checkins-history.jsonl"))
    client.post("/api/seat-blocks", json={"name": "D", "x": 40, "y": 50, "cols": 4, "rows": 1})
    s = app_module.app.extensions["floorbit_stats"]
    s.reset()
    return s


def _read(stats, up, now, bps=1e6):
    dev = {"id": "s1", "name": "sw-d-01"}
    ports = [(dev, {"name": f"Gi1/0/{n}", "state": "up" if f"D-{n}" in up else "down",
                    "download_bps": bps, "upload_bps": 0}, f"D-{n}") for n in range(1, 5)]
    stats.record(ports, ["sw-d-01"], now=now)


def _viewer(app_module):
    app_module.app.extensions["auth"].users.add("vic", "vic-password-1", role="viewer")
    c = app_module.app.test_client()
    assert c.post("/login", data={"username": "vic", "password": "vic-password-1"}).status_code == 302
    return c


def test_hours_outages_and_problem_ports(stats):
    t0 = 1_000_000 * 3600
    _read(stats, {"D-1"}, t0, bps=1e6)
    _read(stats, {"D-1", "D-2"}, t0 + 1800, bps=3e6)
    _read(stats, {"D-2"}, t0 + 3600, bps=2e6)
    stats.record_switch({"id": "s1", "name": "sw-d-01", "status": "offline", "since": t0 + 600})
    stats.record_switch({"id": "s1", "name": "sw-d-01", "status": "online", "since": t0 + 900})
    stats.record_switch({"id": "s1", "name": "sw-d-01", "status": "offline", "since": t0 + 4000})
    flap = {"switch_id": "s1", "switch": "sw-d-01", "port": "Gi1/0/2", "seat": "D-2", "kind": "flapping"}
    stats.count_problems([flap], now=t0)
    stats.count_problems([flap, {**flap, "kind": "errors"}], now=t0 + 60)
    ev = stats.event()
    # Four ports each read: the traffic counts every access port, the seats only those that are up.
    assert ev["hours"] == [{"t": t0, "online_max": 2, "peak_bps": 12e6, "avg_bps": 8_000_000},
                           {"t": t0 + 3600, "online_max": 1, "peak_bps": 8e6, "avg_bps": 8_000_000}]
    built = report.build(ev, [[t0 - 60, "D-1", 1], [t0 + 100, "D-2", 1], [t0 + 200, "D-1", 0]], 4, now=t0 + 4600)
    assert [h["checked_in"] for h in built["hours"]] == [2, 1]
    assert built["online_max"] == 2 and built["checked_in_max"] == 2
    assert built["outages"] == [{"switch": "sw-d-01", "times": 2, "down_s": 900, "longest_s": 600, "still_down": True}]
    assert built["problem_ports"][0]["count"] == 3
    assert built["problem_ports"][0]["kinds"] == {"flapping": 2, "errors": 1}
    stats.new_event(now=t0 + 5000)
    assert stats.event()["hours"] == [] and stats.event()["switch_events"] == []


def test_status_monitor_changes_reach_the_report(app_module, monkeypatch):
    from floorbit import stats as stats_mod
    from integrations import events
    # Other tests clear the subscribers; start from a clean list and put everything back afterwards.
    monkeypatch.setattr(events, "_subscribers", [])
    monkeypatch.setattr(stats_mod, "_current", stats_mod._current)
    monkeypatch.setitem(app_module.app.extensions, "floorbit_stats", app_module.app.extensions["floorbit_stats"])
    stats_mod.init_stats(app_module.app)
    stats_mod.init_stats(app_module.app)   # a second app in the same process doesn't subscribe twice
    s = app_module.app.extensions["floorbit_stats"]
    s._loaded = True   # nothing saved from other tests
    events.publish("switch.status", {"id": "s9", "name": "sw-x", "status": "offline", "since": 123.0})
    assert s.event()["switch_events"] == [[123.0, "s9", "sw-x", "offline"]]


def test_report_api_has_no_people_by_default(client, stats, app_module):
    now = time.time()
    _read(stats, {"D-1", "D-2"}, now - 4000)
    _read(stats, {"D-2"}, now - 100)
    history.record("checkin", {"seat": "D-3", "username": "player-three", "ip": "198.51.100.3"}, ts=now - 3000)
    client.post("/api/incidents", json={"seat": "D-2", "title": "Port flapping"})
    stats.count_problems([{"switch_id": "s1", "switch": "sw-d-01", "port": "Gi1/0/2", "seat": "D-2",
                           "kind": "flapping"}])
    data = client.get("/api/report").get_json()
    assert data["seats"] == 4 and data["online_max"] == 2 and data["people"] is False
    assert data["incidents"]["total"] == 1 and data["incidents"]["items"][0]["seat"] == "D-2"
    assert data["may_add_people"] is True
    body = client.get("/api/report").get_data(as_text=True)
    assert "player-three" not in body and "198.51.100.3" not in body and "reported_by" not in body


def test_people_only_for_admins_and_audited(client, stats, app_module, monkeypatch):
    stats.count_problems([{"switch_id": "s1", "switch": "sw-d-01", "port": "Gi1/0/2", "seat": "D-2",
                           "kind": "flapping"}])
    monkeypatch.setattr("integrations.seat_sources.load",
                        lambda max_age=None: {"D-2": {"username": "player-two", "ip_address": "198.51.100.2"}})
    viewer = _viewer(app_module)
    assert viewer.get("/api/report").status_code == 200
    assert viewer.get("/api/report").get_json()["may_add_people"] is False
    assert viewer.get("/api/report?people=1").status_code == 403
    assert viewer.get("/api/report.pdf?people=1").status_code == 403
    assert viewer.post("/api/report/new-event").status_code == 403
    data = client.get("/api/report?people=1").get_json()
    assert data["people"] is True
    assert data["problem_ports"][0]["nick"] == "player-two" and data["problem_ports"][0]["ip"] == "198.51.100.2"
    actions = [e["action"] for e in client.get("/api/settings/audit").get_json()["entries"]]
    assert "Downloaded the report with nicks and IPs" in actions
    assert client.post("/api/report/new-event").status_code == 200
    actions = [e["action"] for e in client.get("/api/settings/audit").get_json()["entries"]]
    assert "Started a new event" in actions


def test_pdf_download(client, stats):
    now = time.time()
    _read(stats, {"D-1"}, now - 7200)
    _read(stats, {"D-1", "D-2"}, now - 3600)
    _read(stats, {"D-2"}, now - 60)
    client.post("/api/incidents", json={"seat": "D-2", "title": "Kein Internet (Störung)"})
    resp = client.get("/api/report.pdf?lang=de&tz=-60")
    assert resp.status_code == 200 and resp.mimetype == "application/pdf"
    assert resp.headers["Content-Disposition"] == 'attachment; filename="floorbit-report.pdf"'
    body = resp.data
    assert body.startswith(b"%PDF-1.4") and body.rstrip().endswith(b"%%EOF")
    # The cross-reference table points at every object.
    xref = int(body[body.rindex(b"startxref") + 9:].split()[0])
    assert body[xref:xref + 4] == b"xref"
    assert client.get("/api/report.pdf?tz=nonsense").status_code == 200


def test_pdf_text_is_escaped_and_fits():
    page = pdf.Page()
    page.text(10, 10, "Grüße (a\\b)")
    assert b"(Gr\xfc\xdfe \\(a\\\\b\\))" in page.stream()
    assert pdf.text_width(pdf.fit("x" * 200, 10, 50), 10) <= 50
