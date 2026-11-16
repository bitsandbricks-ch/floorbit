"""Discord messages in German (issue #467): DISCORD_LANGUAGE for alerts, the crew bot and attendee channels."""
from floorbit import i18n
from integrations.discord import DiscordNotifier
from tests.test_crew_discord import bridge, key  # noqa: F401 (fixtures)


def _queued(monkeypatch):
    sent = []
    notifier = DiscordNotifier()
    monkeypatch.setattr(notifier, "_ensure_worker", lambda: None)
    monkeypatch.setattr(notifier._queue, "put_nowait", sent.append)
    return notifier, sent


def test_alerts_go_out_in_the_language_set(monkeypatch):
    notifier, sent = _queued(monkeypatch)
    changes = [{"id": "1", "name": "sw-a-01", "status": "online", "previous": "offline", "down_for": 125}]
    msg = notifier.build_status_message(changes)
    monkeypatch.delenv("DISCORD_LANGUAGE", raising=False)
    notifier.post(msg)
    assert sent[-1]["embeds"][0]["title"] == "🟢 sw-a-01 is back online"        # English stays the default
    monkeypatch.setenv("DISCORD_LANGUAGE", "de-CH")
    notifier.post(msg)
    embed = sent[-1]["embeds"][0]
    assert embed["title"] == "🟢 sw-a-01 ist wieder online"
    assert {"name": "Ausgefallen während", "value": "2m 5s", "inline": True} in embed["fields"]
    assert msg["embeds"][0]["title"] == "🟢 sw-a-01 is back online"            # the built message isn't changed

    notifier.post(notifier.build_source_message("monitoring.offline", {"source": "LibreNMS"}))
    assert sent[-1]["embeds"][0]["title"] == "⚠️ LibreNMS ist nicht erreichbar"
    assert sent[-1]["embeds"][0]["description"].startswith("Der Switch-Status bleibt")


def test_names_and_notes_are_left_as_they_are():
    payload = {"content": "💬 **tester**: Cable looks fine\n🙋 tester has it.",
               "embeds": [{"title": "🔧 Seat A-1 Slow", "fields": [{"name": "Where", "value": "Seat A-1"}]}],
               "username": "Seat bot"}
    out = i18n.translate_payload(payload, "de")
    assert out["content"] == "💬 **tester**: Cable looks fine\n🙋 tester hat sie."
    assert out["embeds"][0]["fields"][0] == {"name": "Wo", "value": "Platz A-1"}
    assert out["username"] == "Seat bot"                           # not a text Discord shows as a message
    # The short Discord patterns don't leak into the API's own messages.
    assert i18n.translate("Seat A-1", "de-CH") == "Seat A-1"


def test_the_crew_bot_speaks_german_too(bridge, client, app_module, monkeypatch):  # noqa: F811
    monkeypatch.setenv("DISCORD_LANGUAGE", "de")
    inc = client.post("/api/incidents", json={"seat": "A-2", "title": "No link"}).get_json()
    with app_module.app.app_context():
        bridge.sync(inc["id"])
    post = bridge.fake.calls[0][2]
    embed = post["embeds"][0]
    assert embed["title"] == "🔧 Kein Link"
    assert {"name": "Wo", "value": "Platz A-2", "inline": True} in embed["fields"]
    labels = [b["label"] for row in post["components"] for b in row["components"]]
    assert "Übernehmen" in labels and "In Floorbit öffnen" in labels


def test_slash_answers_follow_the_askers_discord_language(bridge, client, anon_client, key, app_module,  # noqa: F811
                                                          monkeypatch):
    from tests.test_discord_commands import _ask, _command
    users = app_module.app.extensions["auth"].users
    users.add("tech-ana", "example-pass-1", role="tech", identities={"discord": "111"})
    client.post("/api/switches", json={"name": "sw-b-01", "x": 60, "y": 60})
    asked = _command("switch", options=[{"type": 3, "name": "name", "value": "sw-b-01"}])
    assert "Seats online" in _ask(anon_client, key, asked) or "No seats known" in _ask(anon_client, key, asked)
    german = _ask(anon_client, key, {**asked, "locale": "de"})
    assert "An diesem Switch sind noch keine Plätze bekannt." in german
    assert "Floorbit kennt diesen Befehl nicht." in _ask(anon_client, key, {**_command("frobnicate"), "locale": "de"})
    assert "does not know" in _ask(anon_client, key, {**_command("frobnicate"), "locale": "en-US"})
