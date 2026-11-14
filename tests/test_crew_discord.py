"""The crew's Discord channel (issue #32). Discord itself is faked: nothing leaves the test."""
import json
import time

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from integrations import crew
from tests.conftest import TEST_USER

CHANNEL = "900000000000000001"


class Resp:
    def __init__(self, status, body=None):
        self.status_code = status
        self._body = body or {}
        self.content = json.dumps(self._body).encode() if body is not None else b""
        self.text = self.content.decode()

    def json(self):
        return self._body


class FakeDiscord:
    """Answers the bot's REST calls and remembers them."""

    def __init__(self):
        self.calls = []
        self.next_id = 1000
        self.gone = set()

    def __call__(self, method, url, json=None, timeout=None, headers=None):
        assert headers["Authorization"] == "Bot test-bot-token"
        path = url.removeprefix(crew.API)
        self.calls.append((method, path, json))
        if method == "PATCH" and path.split("/")[-1] in self.gone:
            return Resp(404, {"message": "Unknown Message"})
        if method == "POST":
            self.next_id += 1
            return Resp(200, {"id": str(self.next_id)})
        return Resp(200, {})

    def sent(self, method=None, part=""):
        return [c for c in self.calls if (method is None or c[0] == method) and part in c[1]]


@pytest.fixture
def key():
    return Ed25519PrivateKey.generate()


@pytest.fixture
def bridge(client, app_module, monkeypatch, key):
    raw = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "test-bot-token")
    monkeypatch.setenv("DISCORD_CREW_CHANNEL", CHANNEL)
    monkeypatch.setenv("DISCORD_APP_PUBLIC_KEY", raw)
    monkeypatch.setenv("DISCORD_CREW_INCIDENTS", "false")   # the tests sync by hand, no worker thread
    monkeypatch.setenv("PUBLIC_URL", "https://floor.example.com")
    b = app_module.app.extensions["floorbit_crew"]
    fake = FakeDiscord()
    monkeypatch.setattr(b, "request", fake)
    client.post("/api/seat-blocks", json={"name": "A", "x": 10, "y": 10, "cols": 4, "rows": 1})
    b.fake = fake
    return b


def test_an_incident_gets_a_message_and_a_thread_that_follow_it(bridge, client, app_module):
    inc = client.post("/api/incidents", json={"seat": "A-2", "title": "No link", "note": "Cable looks fine"}).get_json()
    with app_module.app.app_context():
        record = bridge.sync(inc["id"])
    fake = bridge.fake
    (post, thread, first) = fake.calls
    assert post[0:2] == ("POST", f"/channels/{CHANNEL}/messages")
    embed = post[2]["embeds"][0]
    assert "No link" in embed["title"] and {"name": "Where", "value": "Seat A-2", "inline": True} in embed["fields"]
    labels = [b["label"] for b in post[2]["components"][0]["components"]]
    assert labels == ["Take it", "Fixed", "Open in Floorbit"]
    assert post[2]["allowed_mentions"] == {"parse": []}
    assert thread[1] == f"/channels/{CHANNEL}/messages/{record['message']}/threads"
    assert thread[2]["name"] == "Seat A-2: No link"
    assert first[1] == f"/channels/{record['thread']}/messages" and "Cable looks fine" in first[2]["content"]

    # Nothing changed: nothing is sent.
    with app_module.app.app_context():
        bridge.sync(inc["id"])
    assert len(fake.calls) == 3

    client.patch(f"/api/incidents/{inc['id']}", json={"assignee": TEST_USER, "note": "On it"})
    with app_module.app.app_context():
        bridge.sync(inc["id"])
    edit, line = fake.calls[3:]
    assert edit[0] == "PATCH" and edit[1].endswith(record["message"])
    assert [b["label"] for b in edit[2]["components"][0]["components"]] == ["Fixed", "Open in Floorbit"]
    assert "has it" in line[2]["content"] and "On it" in line[2]["content"]

    client.patch(f"/api/incidents/{inc['id']}", json={"status": "fixed"})
    with app_module.app.app_context():
        bridge.sync(inc["id"])
    edit, line, archive = fake.calls[5:]
    assert [b["label"] for b in edit[2]["components"][0]["components"]] == ["Open in Floorbit"]
    assert line[2]["content"].startswith("✅ Fixed")
    assert archive == ("PATCH", f"/channels/{record['thread']}", {"archived": True})

    client.patch(f"/api/incidents/{inc['id']}", json={"status": "open"})
    with app_module.app.app_context():
        bridge.sync(inc["id"])
    assert ("PATCH", f"/channels/{record['thread']}", {"archived": False}) in fake.calls
    assert "Reopened" in fake.calls[-1][2]["content"]


def test_a_deleted_message_is_posted_again(bridge, client, app_module):
    inc = client.post("/api/incidents", json={"seat": "A-1", "title": "Slow"}).get_json()
    with app_module.app.app_context():
        first = bridge.sync(inc["id"])
        bridge.fake.gone.add(first["message"])
        client.patch(f"/api/incidents/{inc['id']}", json={"title": "Very slow"})
        again = bridge.sync(inc["id"])
    assert again["message"] != first["message"]


def test_incident_events_are_queued_only_when_turned_on(bridge, client, monkeypatch):
    monkeypatch.setattr(bridge, "_ensure_worker", lambda: None)
    bridge.on_incident({"data": {"id": "abc"}})
    assert bridge._queue.empty()
    monkeypatch.setenv("DISCORD_CREW_INCIDENTS", "true")
    bridge.on_incident({"data": {"id": "abc"}})
    assert bridge._queue.get_nowait() == "abc"


def test_alerts_go_to_the_crew_channel_without_a_webhook(bridge, app_module, monkeypatch):
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    from integrations.discord import DiscordNotifier
    notifier = DiscordNotifier(crew=bridge)
    assert notifier.enabled() and notifier.info()["via"] == "crew channel"
    notifier.send(notifier.build_test_message())
    ((method, path, body),) = bridge.fake.calls
    assert method == "POST"
    assert path == f"/channels/{CHANNEL}/messages" and "username" not in body


def _interaction(key, payload, stamp=None):
    body = json.dumps(payload).encode()
    stamp = str(int(stamp if stamp is not None else time.time()))
    sig = key.sign(stamp.encode() + body).hex()
    return {"data": body, "content_type": "application/json",
            "headers": {"X-Signature-Ed25519": sig, "X-Signature-Timestamp": stamp}}


def _click(action, incident_id, user_id="111", channel=CHANNEL):
    return {"type": 3, "channel_id": channel, "data": {"custom_id": f"fb:{action}:{incident_id}"},
            "member": {"user": {"id": user_id, "username": "someone"}}}


def test_the_buttons_need_discords_signature(bridge, anon_client, key):
    assert anon_client.post("/api/discord/interactions", **_interaction(key, {"type": 1})).get_json() == {"type": 1}
    other = Ed25519PrivateKey.generate()
    assert anon_client.post("/api/discord/interactions", **_interaction(other, {"type": 1})).status_code == 401
    old = _interaction(key, {"type": 1}, stamp=time.time() - 3600)
    assert anon_client.post("/api/discord/interactions", **old).status_code == 401
    assert anon_client.post("/api/discord/interactions", json={"type": 1}).status_code == 401


def test_a_click_acts_as_the_linked_account(bridge, client, anon_client, app_module, key):
    users = app_module.app.extensions["auth"].users
    users.add("tech-ana", "example-pass-1", role="tech", identities={"discord": "111"})
    users.add("viewer-vi", "example-pass-1", role="viewer", identities={"discord": "222"})
    inc = client.post("/api/incidents", json={"seat": "A-3", "title": "No power"}).get_json()

    def press(*args, **kwargs):
        resp = anon_client.post("/api/discord/interactions", **_interaction(key, _click(*args, **kwargs)))
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["type"] == 4 and body["data"]["flags"] == 64   # only the clicker sees the answer
        return body["data"]["content"]

    assert "not linked" in press("take", inc["id"], user_id="333")
    assert "can't" in press("take", inc["id"], user_id="222")
    assert "crew channel" in press("take", inc["id"], channel="900000000000000002")
    assert client.get("/api/incidents").get_json()["incidents"][0]["assignee"] is None

    assert "You have it" in press("take", inc["id"])
    (board,) = client.get("/api/incidents").get_json()["incidents"]
    assert board["assignee"] == "tech-ana" and board["status"] == "assigned"
    assert "Marked fixed" in press("fixed", inc["id"])
    assert client.get("/api/incidents").get_json()["incidents"][0]["status"] == "fixed"
    entries = client.get("/api/settings/audit").get_json()["entries"]
    assert {"Took an incident from Discord", "Marked an incident fixed from Discord"} <= {e["action"] for e in entries}


def test_no_buttons_without_the_public_key(bridge, client, anon_client, app_module, monkeypatch, key):
    monkeypatch.delenv("DISCORD_APP_PUBLIC_KEY")
    inc = client.post("/api/incidents", json={"seat": "A-4", "title": "Slow"}).get_json()
    with app_module.app.app_context():
        bridge.sync(inc["id"])
    labels = [b["label"] for b in bridge.fake.calls[0][2]["components"][0]["components"]]
    assert labels == ["Open in Floorbit"]
    assert anon_client.post("/api/discord/interactions", **_interaction(key, {"type": 1})).status_code == 404
