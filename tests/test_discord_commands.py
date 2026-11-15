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
    down = {"id": sw["id"], "name": "sw-b-01", "status": "offline", "since": time.time() - 300}
    monkeypatch.setattr(monitor, "statuses", {sw["id"]: down})
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


def _opt(name, value, focused=False):
    return [{"type": 3, "name": name, "value": value, **({"focused": True} if focused else {})}]


def test_seat_shows_state_port_and_incidents_but_no_people(bridge, client, anon_client, key, floor, monkeypatch):
    from floorbit import seat_view
    monkeypatch.setattr(seat_view, "_port_of_seat", lambda: {"B-1": ("sw-b-01", "Gi1/0/1")})
    client.post("/api/incidents", json={"seat": "B-1", "title": "No link at all"})
    text = _ask(anon_client, key, _command("seat", options=_opt("seat", "b-1")))
    assert text.startswith("**Seat B-1**") and "Port: sw-b-01 Gi1/0/1" in text
    assert "No link at all" in text and "https://floor.example.com/plan?seat=B-1" in text
    assert "192.0.2" not in text and "nick" not in text.lower()
    assert "no seat Z-9" in _ask(anon_client, key, _command("seat", options=_opt("seat", "Z-9")))
    assert "works incidents" in _ask(anon_client, key, _command("seat", user_id="222", options=_opt("seat", "B-1")))
    assert "not linked" in _ask(anon_client, key, _command("seat", user_id="333", options=_opt("seat", "B-1")))


def test_switch_lists_its_seats_that_are_not_online(bridge, anon_client, key, floor, monkeypatch):
    from floorbit import seat_view
    monkeypatch.setattr(seat_view, "_port_of_seat", lambda: {"B-1": ("sw-b-01", "Gi1/0/1"),
                                                             "B-2": ("sw-b-01", "Gi1/0/2")})
    text = _ask(anon_client, key, _command("switch", options=_opt("name", "SW-B-01")))
    assert text.startswith("**sw-b-01** · 🔴 down since <t:")
    assert "Seats online: 0 of 2" in text and "B-1 (Gi1/0/1), B-2 (Gi1/0/2)" in text
    assert "no switch called sw-x" in _ask(anon_client, key, _command("switch", options=_opt("name", "sw-x")))


def test_autocomplete_suggests_seats_and_switches_to_crew_only(bridge, anon_client, key, floor):
    def choices(name, opt, typed, user_id="111"):
        body = {**_command(name, user_id=user_id, options=_opt(opt, typed, focused=True)), "type": 4}
        resp = anon_client.post("/api/discord/interactions", **_interaction(key, body)).get_json()
        assert resp["type"] == 8
        return [c["value"] for c in resp["data"]["choices"]]

    seats = choices("seat", "seat", "b-1")
    assert seats[0] == "B-1" and "B-10" in seats and all(s.startswith("B-1") for s in seats)
    assert len(choices("seat", "seat", "")) == 16   # blocks A (4) and B (12)
    assert choices("switch", "name", "sw-b") == ["sw-b-01"]
    assert choices("switch", "name", "sw-b", user_id="222") == []   # not crew
    assert choices("seat", "seat", "B", user_id="333") == []         # not linked


def _sub(sub, **values):
    focused = values.pop("_focused", None)
    return [{"type": 1, "name": sub, "options": [
        {"type": 3, "name": k, "value": v, **({"focused": True} if k == focused else {})} for k, v in values.items()]}]


def test_report_take_and_fix_an_incident_from_discord(bridge, client, anon_client, key, floor):
    text = _ask(anon_client, key, _command("incident", options=_sub("report", seat="b-2", problem="Cable cut")))
    assert text.startswith("Filed: seat B-2 · Cable cut")
    (inc,) = client.get("/api/incidents").get_json()["incidents"]
    assert inc["source"] == "discord" and inc["reported_by"] == "tech-ana"

    body = {**_command("incident", options=_sub("take", incident="cable", _focused="incident")), "type": 4}
    choices = anon_client.post("/api/discord/interactions", **_interaction(key, body)).get_json()["data"]["choices"]
    assert choices == [{"name": "seat B-2 · Cable cut (open)", "value": inc["id"]}]

    assert "You have it" in _ask(anon_client, key, _command("incident", options=_sub("take", incident=inc["id"])))
    assert "seat B-2 · Cable cut" in _ask(anon_client, key, _command("jobs"))
    done = _command("incident", options=_sub("fixed", incident=inc["id"], note="New cable"))
    assert "Marked fixed" in _ask(anon_client, key, done)
    (inc,) = client.get("/api/incidents").get_json()["incidents"]
    assert inc["status"] == "fixed" and inc["notes"][-1]["text"] == "New cable"
    assert "no incidents right now" in _ask(anon_client, key, _command("jobs"))
    actions = {e["action"] for e in client.get("/api/settings/audit").get_json()["entries"]}
    assert {"Filed an incident from Discord", "Took an incident from Discord",
            "Marked an incident fixed from Discord"} <= actions


def test_incident_commands_follow_the_accounts_permissions(bridge, client, anon_client, key, floor):
    assert "not linked" in _ask(anon_client, key, _command("jobs", user_id="333"))
    report = _command("incident", user_id="222", options=_sub("report", seat="B-2", problem="Broken"))
    assert "can't" in _ask(anon_client, key, report)          # a viewer can't file
    assert "no seat Z-1" in _ask(anon_client, key, _command("incident", options=_sub("report", seat="Z-1",
                                                                                     problem="x")))
    assert "Pick the incident" in _ask(anon_client, key, _command("incident", options=_sub("take", incident="nope")))
    assert client.get("/api/incidents").get_json()["incidents"] == []


def test_statusupdate_posts_for_attendees_as_a_lead(bridge, client, anon_client, key, floor, app_module):
    users = app_module.app.extensions["auth"].users
    users.add("lead-lu", "example-pass-1", role="lead", identities={"discord": "444"})
    post = [{"type": 3, "name": "text", "value": "Block B is back."}, {"type": 3, "name": "area", "value": "Hall B"}]
    assert "assigns incidents" in _ask(anon_client, key, _command("statusupdate", options=post))   # a tech can't
    assert "not linked" in _ask(anon_client, key, _command("statusupdate", user_id="333", options=post))
    text = _ask(anon_client, key, _command("statusupdate", user_id="444", options=post))
    assert text.startswith("Posted: Block B is back.") and "status page is off" in text
    (update,) = client.get("/api/status-page").get_json()["updates"]
    assert update["text"] == "Block B is back." and update["area"] == "Hall B"
    actions = {e["action"] for e in client.get("/api/settings/audit").get_json()["entries"]}
    assert "Posted status update from Discord" in actions
