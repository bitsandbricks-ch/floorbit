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
