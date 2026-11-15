"""Shift handover (issue #33)."""
import time

from tests.test_rbac import sign_in_as


def _floor(client):
    client.post("/api/seat-blocks", json={"name": "A", "x": 10, "y": 10, "cols": 4, "rows": 1})


def test_summary_counts_the_shift_and_handover_starts_the_next(client, app_module):
    _floor(client)
    a = client.post("/api/incidents", json={"seat": "A-1", "title": "No link"}).get_json()
    b = client.post("/api/incidents", json={"seat": "A-2", "title": "Slow"}).get_json()
    client.patch(f"/api/incidents/{b['id']}", json={"status": "fixed"})
    client.post("/api/seat-blocks", json={"name": "B", "x": 60, "y": 10, "cols": 2, "rows": 1})
    stats = app_module.app.extensions["floorbit_stats"]
    now = time.time()
    stats.record_switch({"id": "s1", "name": "sw-a-01", "status": "offline", "since": now - 600})
    stats.record_switch({"id": "s1", "name": "sw-a-01", "status": "online", "since": now - 300})
    stats.record_switch({"id": "s2", "name": "sw-b-01", "status": "offline", "since": now - 60})

    body = client.get("/api/handover").get_json()
    assert body["previous"] is None
    assert [i["id"] for i in body["incidents"]["open"]] == [a["id"]]
    assert [i["id"] for i in body["incidents"]["fixed"]] == [b["id"]]
    assert body["counts"]["opened"] == 2 and body["counts"]["outages"] == 2 and body["counts"]["still_down"] == 1
    assert any(c["area"] == "floor plan" and c["action"] == "Added seat block" for c in body["changes"])
    assert all(c["area"] != "incidents" for c in body["changes"])

    done = client.post("/api/handover", json={"note": "Row B switch is flaky, spare on the desk."})
    assert done.status_code == 201 and done.get_json()["counts"]["open"] == 1
    after = client.get("/api/handover").get_json()
    assert after["previous"]["note"].startswith("Row B") and after["since"] == done.get_json()["at"]
    assert after["counts"]["opened"] == 0 and after["counts"]["open"] == 1   # still open carries over
    assert after["history"][0]["id"] == done.get_json()["id"]


def test_handover_is_for_the_crew(app_module, client):
    viewer = sign_in_as(app_module, "vi1", "viewer")
    assert viewer.get("/api/handover").status_code == 403
    assert viewer.post("/api/handover", json={"note": "x"}).status_code == 403
    tech = sign_in_as(app_module, "te1", "tech")
    assert tech.get("/api/handover").status_code == 200
    assert tech.post("/api/handover", json={"note": "Quiet night"}).status_code == 201
    entries = client.get("/api/settings/audit").get_json()["entries"]
    assert any(e["action"] == "Handed over the shift" and e["user"] == "te1" for e in entries)


def test_handover_can_go_to_discord(client, app_module, monkeypatch):
    notifier = app_module.app.extensions["floorbit_discord"]
    sent = []
    monkeypatch.setattr(notifier, "enabled", lambda: True)
    monkeypatch.setattr(notifier, "post", sent.append)
    client.post("/api/handover", json={"note": "All good", "discord": True})
    (msg,) = sent
    embed = msg["embeds"][0]
    assert embed["title"].startswith("🔁 Shift handover") and embed["fields"][0]["value"] == "All good"
    assert msg["allowed_mentions"] == {"parse": []}
    client.post("/api/handover", json={"note": "No post"})
    assert len(sent) == 1


def test_the_shift_s_seat_notes_are_in_the_summary(client):
    _floor(client)
    client.put("/api/plan/seats/A-2/note", json={"text": "Cable swapped"})
    client.put("/api/plan/seats/A-3/note", json={"text": "Own switch, leave it"})
    notes = client.get("/api/handover").get_json()["seat_notes"]
    assert [(n["seat"], n["text"]) for n in notes] == [("A-3", "Own switch, leave it"), ("A-2", "Cable swapped")]
    assert notes[0]["at"] and "by" in notes[0]

    client.post("/api/handover", json={"note": "Quiet night."})
    assert client.get("/api/handover").get_json()["seat_notes"] == []   # the next shift starts empty
    client.put("/api/plan/seats/A-2/note", json={"text": "Cable swapped again"})
    assert [n["seat"] for n in client.get("/api/handover").get_json()["seat_notes"]] == ["A-2"]


def test_the_summary_says_what_is_muted_and_the_crew_notice(client, app_module, monkeypatch):
    # A mute set by the last shift must not be forgotten by the next one (issue #258).
    from integrations import alerting
    alerting.mute("s1", "sw-a-01", 60, "kim", "Swapping the PSU")
    alerting.mute(alerting.service_key("demo:dns"), "DNS", 30, "kim")
    client.put("/api/notice", json={"text": "Row C has no power until 14:00", "hours": 2})
    body = client.get("/api/handover").get_json()
    assert [(m["kind"], m["name"], m["reason"]) for m in body["mutes"]] == [
        ("health", "DNS", ""), ("switch", "sw-a-01", "Swapping the PSU")]
    assert body["counts"]["muted"] == 2
    assert body["notice"]["text"] == "Row C has no power until 14:00"

    notifier = app_module.app.extensions["floorbit_discord"]
    sent = []
    monkeypatch.setattr(notifier, "enabled", lambda: True)
    monkeypatch.setattr(notifier, "post", sent.append)
    client.post("/api/handover", json={"note": "", "discord": True})
    assert "🔕 **2** muted: DNS (until " in sent[0]["embeds"][0]["description"]

    alerting.unmute("s1")
    alerting.unmute(alerting.service_key("demo:dns"))
    client.delete("/api/notice")
    body = client.get("/api/handover").get_json()
    assert body["mutes"] == [] and body["notice"] is None and body["counts"]["muted"] == 0
