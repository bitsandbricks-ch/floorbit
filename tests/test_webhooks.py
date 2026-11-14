"""Outgoing webhooks (issue #40). Receivers are faked; nothing leaves the test."""
import hashlib
import hmac
import json
import time

import pytest
import requests

from floorbit import webhooks
from integrations import events


class Answer:
    def __init__(self, status=200):
        self.status_code = status


@pytest.fixture
def receiver(monkeypatch):
    sent = []
    answers = []

    def fake_post(url, data=None, headers=None, timeout=None, allow_redirects=True):
        assert allow_redirects is False and timeout
        sent.append({"url": url, "body": json.loads(data), "raw": data, "headers": headers})
        status = answers.pop(0) if answers else 200
        if status == "timeout":
            raise requests.exceptions.ConnectTimeout("no answer")
        return Answer(status)

    monkeypatch.setattr(requests, "post", fake_post)
    # Other tests empty the event bus; listen again, and leave with this test.
    monkeypatch.setattr(events, "_subscribers", list(events._subscribers))
    events.subscribe_once("*", webhooks.on_event)
    with webhooks._lock:
        webhooks._queue.clear()
    return sent, answers


def _settle(sent, count, timeout=3):
    """The sender thread may already be running: send what's waiting until `count` arrived."""
    end = time.time() + timeout
    while len(sent) < count and time.time() < end:
        webhooks.drain(ignore_due=True)
        time.sleep(0.02)
    return sent


def _add(client, **body):
    resp = client.post("/api/settings/webhooks", json={
        "name": "Ticket bot", "url": "https://hooks.example.com/floorbit", "events": ["switch.down", "incident.opened",
                                                                                     "seat.checked_in"], **body})
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()


def test_events_are_sent_signed_and_without_personal_data(client, receiver):
    sent, _ = receiver
    made = _add(client)
    secret = made["secret"]
    assert secret.startswith("whsec_") and "secret" not in made["webhook"]
    assert "whsec_" not in json.dumps(client.get("/api/settings/webhooks").get_json())

    events.publish("switch.status", {"id": "sw1", "name": "sw-a-01", "status": "offline", "previous": "online",
                                     "since": 1.0, "down_for": None, "reason": "ping", "source": "librenms"})
    events.publish("switch.status", {"id": "sw1", "name": "sw-a-01", "status": "online"})   # not picked
    events.publish("checkin", {"seat": "A1", "username": "player-nick", "ip": "198.51.100.10",
                               "mac": "02:00:00:00:00:0a", "moved_from": None})
    events.publish("stats.changed", {})   # not a webhook event at all
    _settle(sent, 2)
    sent.sort(key=lambda s: s["body"]["event"] != "switch.down")   # the sender thread may race the test
    assert [s["body"]["event"] for s in sent] == ["switch.down", "seat.checked_in"]
    down = sent[0]
    assert down["body"]["data"] == {"id": "sw1", "name": "sw-a-01", "since": 1.0, "down_for": None, "reason": "ping"}
    assert sent[1]["body"]["data"] == {"seat": "A1", "moved_from": None}
    bodies = b"".join(s["raw"] for s in sent)
    assert b"player-nick" not in bodies and b"198.51.100.10" not in bodies and b"02:00" not in bodies

    # The receiver checks the signature over "<t>.<body>" with the shared secret.
    h = down["headers"]
    parts = dict(p.split("=", 1) for p in h["Floorbit-Signature"].split(","))
    want = hmac.new(secret.encode(), f"{parts['t']}.".encode() + down["raw"], hashlib.sha256).hexdigest()
    assert hmac.compare_digest(parts["v1"], want)
    assert h["Floorbit-Event"] == "switch.down" and h["Floorbit-Delivery"] == down["body"]["delivery"]


def test_incident_opened_and_changed(client, receiver):
    sent, _ = receiver
    _add(client, events=["incident.opened", "incident.changed"])
    client.put("/api/settings", json={})
    sw = client.post("/api/switches", json={"name": "sw-a-01", "x": 1, "y": 1}).get_json()
    incident = client.post("/api/incidents", json={"title": "No link", "switch_id": sw["id"]}).get_json()
    incident_id = incident.get("id") or incident["incident"]["id"]
    client.patch(f"/api/incidents/{incident_id}", json={"status": "fixed"})
    _settle(sent, 2)
    sent.sort(key=lambda s: s["body"]["event"] != "incident.opened")   # the sender thread may race the test
    assert [(s["body"]["event"], s["body"]["data"]["status"]) for s in sent] == \
        [("incident.opened", "open"), ("incident.changed", "fixed")]
    assert sent[0]["body"]["data"]["switch_name"] == "sw-a-01" and sent[0]["body"]["data"]["title"] == "No link"


def test_failures_are_retried_logged_and_paused_hooks_get_nothing(client, receiver):
    sent, answers = receiver
    hook = _add(client)["webhook"]
    answers.extend(["timeout", 500])
    events.publish("checkin", {"seat": "A2"})
    _settle(sent, 3)
    assert len(sent) == 3 and len({s["body"]["delivery"] for s in sent}) == 1   # one delivery, three tries
    listed = client.get("/api/settings/webhooks").get_json()["webhooks"][0]
    assert [d["ok"] for d in listed["deliveries"]] == [True, False, False]   # newest first
    assert listed["deliveries"][1]["error"] == "Answered 500" and listed["last"]["ok"] is True

    assert client.patch(f"/api/settings/webhooks/{hook['id']}", json={"active": False}).get_json()["active"] is False
    events.publish("checkin", {"seat": "A3"})
    webhooks.drain(ignore_due=True)
    assert len(sent) == 3 and webhooks.pending() == 0


def test_ping_new_secret_bad_input_audit_and_admins_only(app_module, client, receiver):
    sent, answers = receiver
    hook = _add(client)["webhook"]
    assert client.post(f"/api/settings/webhooks/{hook['id']}/test").get_json() == \
        {"ok": True, "status": 200, "error": None}
    assert sent[-1]["body"]["event"] == "ping"
    answers.append(404)
    assert client.post(f"/api/settings/webhooks/{hook['id']}/test").get_json()["error"] == "Answered 404"
    rotated = client.post(f"/api/settings/webhooks/{hook['id']}/secret").get_json()
    assert rotated["secret"].startswith("whsec_")

    for body in ({"name": "x", "url": "ftp://example.com", "events": ["switch.down"]},
                 {"name": "x", "url": "https://hooks.example.com", "events": []},
                 {"name": "x", "url": "https://hooks.example.com", "events": ["everything"]},
                 {"name": "", "url": "https://hooks.example.com", "events": ["switch.down"]}):
        assert client.post("/api/settings/webhooks", json=body).status_code == 400, body
    assert client.patch("/api/settings/webhooks/nope", json={"active": False}).status_code == 404

    actions = [e["action"] for e in client.get("/api/settings/audit").get_json()["entries"]]
    assert {"Added webhook", "Made a new webhook secret"} <= set(actions)
    assert client.delete(f"/api/settings/webhooks/{hook['id']}").status_code == 200
    assert client.get("/api/settings/webhooks").get_json()["webhooks"] == []

    from tests.test_rbac import sign_in_as
    lead = sign_in_as(app_module, "le1", "lead")
    assert lead.get("/api/settings/webhooks").status_code == 403
    # Backups never carry webhooks: they hold secrets.
    backup = client.get("/api/settings/backup").get_data(as_text=True)
    assert "whsec_" not in backup and "webhooks" not in backup
