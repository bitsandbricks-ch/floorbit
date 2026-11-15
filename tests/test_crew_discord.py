"""The crew's Discord channel (issue #32). Discord itself is faked: nothing leaves the test."""
import json
import time

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from integrations import crew
from tests.conftest import TEST_USER
from tests.test_health import fake_checks, registry, wall  # noqa: F401 (fixtures)
from tests.test_service_mutes import red_wall

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


def test_a_crew_notice_is_posted_once_put_up(bridge, client, monkeypatch):
    # Issue #248: what a lead puts up also reaches people who aren't looking at Floorbit.
    # "@everyone" stays in the text, but allowed_mentions keeps it from pinging anyone.
    monkeypatch.setattr(bridge, "_ensure_worker", lambda: None)
    client.put("/api/notice", json={"text": "Hall B: power work at 14:00 @everyone leave row C alone",
                                    "level": "warn", "hours": 2})
    kind, notice = bridge._queue.get_nowait()
    assert kind == "notice" and notice["level"] == "warn"
    bridge._handle((kind, notice))
    ((method, path, body),) = bridge.fake.calls
    assert method == "POST" and path.endswith("/messages")
    assert body["allowed_mentions"] == {"parse": []}   # "@everyone" in the text pings no one
    assert body["content"].startswith("⚠️ **Crew notice** (from ")
    assert body["content"].endswith(", for 2 hours)\n> Hall B: power work at 14:00 @everyone leave row C alone")

    client.delete("/api/notice")   # taking it down posts nothing
    assert bridge._queue.empty()
    monkeypatch.setenv("DISCORD_CREW_NOTICES", "false")
    client.put("/api/notice", json={"text": "Doors open at 18:00"})
    assert bridge._queue.empty()


def test_notice_message_without_an_end():
    from integrations.crew import CrewBridge
    notice = {"text": "Doors open at 18:00", "level": "info", "until": None, "by": None, "at": 0}
    text = CrewBridge.notice_message(notice)
    assert text == "📣 **Crew notice** (until taken down)\n> Doors open at 18:00"


def test_a_switch_alert_can_be_muted_from_discord(bridge, client, anon_client, app_module, monkeypatch, key):
    """Issue #272: "Mute … for 1 h" under a switch-offline alert, for crew who work incidents."""
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    from integrations import alerting
    from integrations.discord import DiscordNotifier
    sw = client.post("/api/switches", json={"name": "sw-a-01", "x": 10, "y": 10}).get_json()["id"]
    change = {"id": sw, "name": "sw-a-01", "status": "offline", "previous": "online"}
    notifier = DiscordNotifier(crew=bridge)
    notifier.send(notifier.build_status_message([change]))
    ((_, _, body),) = bridge.fake.calls
    (button,) = body["components"][0]["components"]
    assert button["label"] == "Mute sw-a-01 for 1 h" and button["custom_id"] == f"fb:mute:{sw}"
    assert "_mute" not in body

    users = app_module.app.extensions["auth"].users
    users.add("tech-ana", "example-pass-1", role="tech", identities={"discord": "111"})
    users.add("viewer-vi", "example-pass-1", role="viewer", identities={"discord": "222"})

    def press(user_id, switch_id=sw):
        resp = anon_client.post("/api/discord/interactions", **_interaction(key, _click("mute", switch_id, user_id)))
        return resp.get_json()["data"]["content"]

    assert "works incidents" in press("222") and alerting.mutes() == {}
    assert "not on the floor plan" in press("111", "gone-switch")
    assert press("111").startswith("Muted sw-a-01 until ")
    entry = alerting.mutes()[sw]
    assert entry["by"] == "tech-ana" and entry["reason"] == "Muted from Discord"
    assert 3500 < entry["until"] - time.time() <= 3600
    entries = client.get("/api/settings/audit").get_json()["entries"]
    assert entries[0]["action"] == "Muted switch alerts from Discord" and entries[0]["target"] == "sw-a-01"


def test_no_mute_button_without_the_public_key_or_through_a_webhook(bridge, client, monkeypatch):
    monkeypatch.delenv("DISCORD_APP_PUBLIC_KEY")
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    from integrations.discord import DiscordNotifier
    notifier = DiscordNotifier(crew=bridge)
    change = {"id": "s1", "name": "sw-a-01", "status": "offline", "previous": "online"}
    notifier.send(notifier.build_status_message([change]))
    ((_, _, body),) = bridge.fake.calls
    assert "components" not in body and "_mute" not in body

    # A webhook gets the alert without the private hint.
    sent = []
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.example.com/api/webhooks/1/x")
    import integrations.discord as discord_module

    class Ok:
        status_code = 204
    monkeypatch.setattr(discord_module.requests, "post", lambda url, json, timeout: sent.append(json) or Ok())
    notifier._last_alert.clear()
    notifier.send(notifier.build_status_message([change]))
    assert sent and "_mute" not in sent[0] and "components" not in sent[0]


def test_the_mute_button_id_takes_switch_ids_but_nothing_odd():
    assert crew.parse_custom_id("fb:mute:3f2b9c1e-7a4d-4e8f-9b1a-2c3d4e5f6a7b") == (
        "mute", "3f2b9c1e-7a4d-4e8f-9b1a-2c3d4e5f6a7b")
    assert crew.parse_custom_id("fb:mute:a/b") is None
    assert crew.parse_custom_id("fb:take:a-b") is None


def test_a_service_alert_can_be_muted_from_discord(bridge, client, anon_client, app_module, monkeypatch, key,
                                                   wall, fake_checks):  # noqa: F811
    """Issue #274: the same button under a red service on the health wall."""
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    from integrations import alerting
    from integrations.discord import DiscordNotifier
    # The app's own notifier would post the red wall too, from its thread: keep it out of the count.
    monkeypatch.setattr(app_module.app.extensions["floorbit_discord"], "post", lambda payload: None)
    red_wall(wall, fake_checks, monkeypatch)

    notifier = DiscordNotifier(crew=bridge)
    change = {"id": "demo:game-1", "name": "Game server 1", "status": "down", "previous": "up"}
    notifier.send(notifier.build_health_message([change]))
    ((_, _, body),) = bridge.fake.calls
    (button,) = body["components"][0]["components"]
    assert button["label"] == "Mute Game server 1 for 1 h" and button["custom_id"] == "fb:mute:health:demo:game-1"
    assert crew.parse_custom_id(button["custom_id"]) == ("mute", "health:demo:game-1")

    users = app_module.app.extensions["auth"].users
    users.add("tech-ana", "example-pass-1", role="tech", identities={"discord": "111"})

    def press(target):
        resp = anon_client.post("/api/discord/interactions", **_interaction(key, _click("mute", target)))
        return resp.get_json()["data"]["content"]

    assert press("health:demo:game-1").startswith("Muted Game server 1 until ")
    assert alerting.mutes()["health:demo:game-1"]["by"] == "tech-ana"
    assert "health wall" in press("health:demo:nope")
    entries = client.get("/api/settings/audit").get_json()["entries"]
    assert entries[0]["action"] == "Muted service alerts from Discord"


def test_an_incident_nobody_takes_gets_one_nudge(bridge, client, app_module, monkeypatch):
    monkeypatch.setenv("DISCORD_CREW_WAITING_ROLE", "<@&900000000000000077>")
    waiting = client.post("/api/incidents", json={"seat": "A-1", "title": "No link"}).get_json()
    taken = client.post("/api/incidents", json={"seat": "A-2", "title": "Slow"}).get_json()
    client.patch(f"/api/incidents/{taken['id']}", json={"assignee": TEST_USER})
    with app_module.app.app_context():
        record = bridge.sync(waiting["id"])
        bridge.sync(taken["id"])
        before = len(bridge.fake.calls)
        assert bridge.nudge_waiting(now=waiting["created_at"] + 9 * 60) == []
        assert bridge.nudge_waiting(now=waiting["created_at"] + 75 * 60) == [waiting["id"]]
        # Once only.
        assert bridge.nudge_waiting(now=waiting["created_at"] + 90 * 60) == []
    (call,) = bridge.fake.calls[before:]
    assert call[1] == f"/channels/{record['thread']}/messages"
    assert call[2]["content"] == "<@&900000000000000077> ⏳ Waiting 1 h 15 min. Nobody has taken it yet."
    assert call[2]["allowed_mentions"] == {"parse": [], "roles": ["900000000000000077"]}


def test_the_nudge_can_be_turned_off_and_pings_nobody_by_default(bridge, client, app_module, monkeypatch):
    inc = client.post("/api/incidents", json={"seat": "A-1", "title": "No link"}).get_json()
    with app_module.app.app_context():
        bridge.sync(inc["id"])
        monkeypatch.setenv("DISCORD_CREW_WAITING_MINUTES", "0")
        assert bridge.nudge_waiting(now=inc["created_at"] + 3600) == []
        monkeypatch.delenv("DISCORD_CREW_WAITING_MINUTES")
        assert bridge.nudge_waiting(now=inc["created_at"] + 11 * 60) == [inc["id"]]
    call = bridge.fake.calls[-1]
    assert call[2]["content"] == "⏳ Waiting 11 min. Nobody has taken it yet."
    assert call[2]["allowed_mentions"] == {"parse": [], "roles": []}
