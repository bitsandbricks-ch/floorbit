"""Alerting (issue #10): mutes, quiet hours, grouped outages and the Problems list."""
import time

import pytest

from integrations import alerting
from integrations.discord import SILENT, DiscordNotifier


@pytest.fixture
def floor(client):
    a = client.post("/api/switches", json={"name": "sw-a-01", "x": 10, "y": 10}).get_json()
    b = client.post("/api/switches", json={"name": "sw-a-02", "x": 20, "y": 10}).get_json()
    return {"a": a["id"], "b": b["id"]}


def change(sid, name, status="offline"):
    return {"id": sid, "name": name, "status": status, "previous": "online" if status == "offline" else "offline",
            "down_for": 120 if status == "online" else None}


def test_a_muted_switch_pages_nobody(client, floor):
    resp = client.post("/api/alerts/mutes", json={"switch_id": floor["a"], "minutes": 30, "reason": "PSU swap"})
    assert resp.status_code == 201 and resp.get_json()["by"] == "tester"
    msg = DiscordNotifier().build_status_message([change(floor["a"], "sw-a-01"), change(floor["b"], "sw-a-02")])
    assert [e["title"] for e in msg["embeds"]] == ["🔴 sw-a-02 is offline"]
    assert DiscordNotifier().build_status_message([change(floor["a"], "sw-a-01", "online")]) is None
    assert client.delete(f"/api/alerts/mutes/{floor['a']}").status_code == 200
    assert DiscordNotifier().build_status_message([change(floor["a"], "sw-a-01")]) is not None
    assert client.delete(f"/api/alerts/mutes/{floor['a']}").status_code == 404


def test_mutes_are_checked_and_end_on_their_own(client, floor, monkeypatch):
    assert client.post("/api/alerts/mutes", json={"switch_id": "nope", "minutes": 30}).status_code == 400
    assert client.post("/api/alerts/mutes", json={"switch_id": floor["a"], "minutes": 0}).status_code == 400
    assert client.post("/api/alerts/mutes", json={"switch_id": floor["a"], "minutes": "x"}).status_code == 400
    client.post("/api/alerts/mutes", json={"switch_id": floor["a"], "minutes": 1})
    assert alerting.is_muted(floor["a"])
    assert not alerting.is_muted(floor["a"], now=time.time() + 61)


def test_muting_needs_incidents_work(app_module, client, floor):
    app_module.app.extensions["auth"].users.add("watcher", "role-password-1", role="viewer")
    viewer = app_module.app.test_client()
    viewer.post("/login", data={"username": "watcher", "password": "role-password-1"})
    assert viewer.post("/api/alerts/mutes", json={"switch_id": floor["a"], "minutes": 30}).status_code == 403
    body = viewer.get("/api/problems").get_json()
    assert body["can_mute"] is False


def test_a_row_losing_power_is_one_message(client, floor, monkeypatch):
    # Five switches go dark at once; three of them hang on one power circuit.
    ids = [floor["a"], floor["b"]] + [client.post("/api/switches", json={"name": f"sw-b-0{n}", "x": n, "y": 30})
                                      .get_json()["id"] for n in (1, 2, 3)]
    block = client.post("/api/seat-blocks", json={"name": "A", "x": 10, "y": 10, "cols": 2, "rows": 1}).get_json()
    board = client.post("/api/power/boards", json={"name": "DB-1"}).get_json()
    client.post("/api/power/circuits", json={"board": board["id"], "name": "B row 1", "switches": ids[2:],
                                             "blocks": [{"block": block["id"]}]})
    names = ["sw-a-01", "sw-a-02", "sw-b-01", "sw-b-02", "sw-b-03"]
    msg = DiscordNotifier().build_status_message([change(i, n) for i, n in zip(ids, names, strict=True)])
    assert len(msg["embeds"]) == 1
    embed = msg["embeds"][0]
    assert embed["title"] == "🔴 5 switches offline"
    assert embed["description"] == "**Circuit B row 1**: sw-b-01, sw-b-02, sw-b-03\nOther: sw-a-01, sw-a-02"
    # Up to ALERT_GROUP_AFTER changes still get one card each.
    monkeypatch.setenv("ALERT_GROUP_AFTER", "5")
    assert len(DiscordNotifier().build_status_message([change(i, n) for i, n in zip(ids, names, strict=True)])
               ["embeds"]) == 5


def test_quiet_hours_post_silently(monkeypatch):
    sent = []
    notifier = DiscordNotifier()
    monkeypatch.setattr(notifier, "_ensure_worker", lambda: None)
    monkeypatch.setattr(notifier._queue, "put_nowait", sent.append)
    monkeypatch.setenv("DISCORD_MENTION", "@here")
    payload = {"content": "@here 3 switches went offline", "embeds": [],
               "allowed_mentions": {"parse": ["everyone"]}}
    monkeypatch.setenv("ALERT_QUIET_HOURS", "00:00-23:59")
    monkeypatch.setattr(alerting, "quiet_now", lambda now=None: True)
    notifier.post(payload)
    assert sent[-1]["content"] == "3 switches went offline"
    assert sent[-1]["flags"] == SILENT and sent[-1]["allowed_mentions"] == {"parse": []}
    monkeypatch.setattr(alerting, "quiet_now", lambda now=None: False)
    notifier.post(payload)
    assert sent[-1] is payload


@pytest.mark.parametrize("hours, minute, quiet", [
    ("02:00-08:00", 3 * 60, True), ("02:00-08:00", 9 * 60, False),
    ("23:00-07:00", 23 * 60 + 30, True), ("23:00-07:00", 6 * 60, True), ("23:00-07:00", 12 * 60, False),
    ("", 3 * 60, False), ("nonsense", 3 * 60, False), ("25:00-08:00", 3 * 60, False),
])
def test_quiet_hours_window(monkeypatch, hours, minute, quiet):
    monkeypatch.setenv("ALERT_QUIET_HOURS", hours)
    monkeypatch.setattr(time, "localtime", lambda _=None: time.struct_time(
        (2026, 11, 14, minute // 60, minute % 60, 0, 5, 318, 0)))
    assert alerting.quiet_now(1) is quiet


def test_problems_gather_everything(app_module, client, floor, monkeypatch):
    monitor = app_module.app.extensions["lal_integrations"]["monitor"]
    monkeypatch.setattr(monitor, "statuses", {
        floor["a"]: {"id": floor["a"], "name": "sw-a-01", "status": "offline", "since": time.time() - 600},
        floor["b"]: {"id": floor["b"], "name": "sw-a-02", "status": "online", "since": time.time()}})
    client.post("/api/alerts/mutes", json={"switch_id": floor["a"], "minutes": 30})
    client.put("/api/settings/plugins/demo", json={"enabled": True})
    sec = app_module.app.extensions["floorbit_security"]
    sec.stop()
    sec.reset()
    sec.poll_once()
    body = client.get("/api/problems").get_json()
    kinds = {p["kind"] for p in body["problems"]}
    assert {"switch", "security"} <= kinds
    switch = next(p for p in body["problems"] if p["kind"] == "switch")
    assert switch["muted"]["by"] == "tester" and body["counts"]["muted"] == 1
    assert body["mutes"][0]["name"] == "sw-a-01"
    # Without seats.view, security problems say where, not who.
    app_module.app.extensions["auth"].users.add("watcher", "role-password-1", role="viewer")
    viewer = app_module.app.test_client()
    viewer.post("/login", data={"username": "watcher", "password": "role-password-1"})
    titles = [p["title"] for p in viewer.get("/api/problems").get_json()["problems"] if p["kind"] == "security"]
    assert titles and all("192.0.2" not in t and ":" not in t for t in titles)
    sec.reset()
