"""Slash commands for the Discord bot. Discord itself is faked: nothing leaves the test."""
import time

import pytest

from floorbit import discord_commands, sources, status_page
from tests import test_crew_discord as crew_tests
from tests.test_crew_discord import Resp, _interaction

bridge, key = crew_tests.bridge, crew_tests.key   # the crew channel's fixtures: a faked bot and app key


def _command(name, user_id="111", guild=None, options=None):
    body = {"type": 2, "channel_id": "900000000000000009", "data": {"name": name, "options": options or []},
            "member": {"user": {"id": user_id, "username": "someone"}}}
    if guild:
        body["guild_id"] = guild
    return body


def _ask(anon_client, key, payload):
    resp = anon_client.post("/api/discord/interactions", **_interaction(key, payload))
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["type"] == 4 and body["data"]["flags"] == 64   # only the one who asked sees it
    assert body["data"]["allowed_mentions"] == {"parse": []}
    return body["data"]["content"]


@pytest.fixture
def floor(client, app_module, monkeypatch):
    client.post("/api/seat-blocks", json={"name": "B", "x": 40, "y": 50, "cols": 4, "rows": 3})
    sw = client.post("/api/switches", json={"name": "sw-b-01", "x": 60, "y": 60}).get_json()
    for n in range(3):   # still up, so it's "part of the network", not an outage
        client.post("/api/switches", json={"name": f"sw-z-0{n}", "x": 900 + n * 40, "y": 600})
    monitor = app_module.app.extensions["lal_integrations"]["monitor"]
    monkeypatch.setattr(monitor, "last_poll", time.time())
    monkeypatch.setattr(monitor, "statuses",
                        {sw["id"]: {"id": sw["id"], "status": "offline", "since": time.time() - 300}})
    monkeypatch.setattr(status_page, "_seats_of", {})
    status_page.learn_seats({("sw-b-01", "Gi1/0/1"): "B-1"})
    sources.mark_ok("test")
    users = app_module.app.extensions["auth"].users
    users.add("tech-ana", "example-pass-1", role="tech", identities={"discord": "111"})
    users.add("viewer-vi", "example-pass-1", role="viewer", identities={"discord": "222"})


def test_status_for_the_crew_names_the_switches(bridge, client, anon_client, key, floor):
    client.post("/api/status-page/updates", json={"text": "Replacing a switch in block B.", "area": "Block B"})
    text = _ask(anon_client, key, _command("status"))
    assert "Part of the network is down" in text and "since <t:" in text
    assert "Seat block B" in text and "switches: sw-b-01" in text
    assert "Replacing a switch in block B." in text


def test_status_for_others_is_only_what_the_public_page_shows(bridge, client, anon_client, key, floor):
    assert "not linked" in _ask(anon_client, key, _command("status", user_id="333"))
    assert "works incidents" in _ask(anon_client, key, _command("status", user_id="222"))
    client.put("/api/settings", json={"public.status_page": True})
    for who in ("333", "222"):
        text = _ask(anon_client, key, _command("status", user_id=who))
        assert "Seat block B" in text and "sw-b-01" not in text


def test_commands_only_on_the_crew_server(bridge, client, anon_client, key, floor, app_module):
    settings = app_module.app.extensions["floorbit_settings"]
    settings.update({"signin.discord_client_id": "555555555555555555",
                     "signin.discord_client_secret": "example-client-secret", "signin.discord_guild_id": "700"})
    assert "own server" in _ask(anon_client, key, _command("status", guild="701"))
    assert "Part of the network" in _ask(anon_client, key, _command("status", guild="700"))


def test_an_unknown_command(bridge, anon_client, key, floor):
    assert "does not know" in _ask(anon_client, key, _command("frobnicate"))


def test_commands_are_registered_once_per_change(bridge, monkeypatch):
    def fake(method, url, json=None, timeout=None, headers=None):
        bridge.fake.calls.append((method, url.removeprefix("https://discord.com/api/v10"), json))
        return Resp(200, {"id": "4242"} if method == "GET" else [])
    monkeypatch.setattr(bridge, "request", fake)
    monkeypatch.setattr(bridge, "commands_for", None)
    with bridge.app.app_context():
        assert bridge.register_commands() is True
        assert bridge.register_commands() is False   # nothing changed: no second call
    method, path, body = bridge.fake.calls[-1]
    assert method == "PUT" and path in ("/applications/4242/commands", "/applications/4242/guilds/" + bridge._guild_id()
                                        + "/commands")
    assert [c["name"] for c in body] == [c["name"] for c in discord_commands.COMMANDS]
    monkeypatch.delenv("DISCORD_APP_PUBLIC_KEY")
    monkeypatch.setattr(bridge, "commands_for", None)
    with bridge.app.app_context():
        assert bridge.register_commands() is False   # nothing could answer them
