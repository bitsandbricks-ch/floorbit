"""Discord announcements of what is about to start (issue #430). Nothing reaches Discord: post is patched."""
import pytest

from floorbit import schedule_announce
from integrations import events
from integrations.discord import DiscordNotifier

HOOK = "https://discord.example.com/api/webhooks/1/programme"
NOW = 1_800_000_000


@pytest.fixture
def announce(app_module, client, monkeypatch):
    # The app's own announcer stays quiet, so only this test's ticks post.
    monkeypatch.setattr(app_module.app.extensions["floorbit_schedule_announce"], "tick", lambda now=None: [])
    sent = []
    monkeypatch.setattr(DiscordNotifier, "post", lambda self, payload: sent.append(payload))
    # Other tests clear the subscribers: wire a notifier of our own, gone again after the test.
    monkeypatch.setattr(events, "_subscribers", [])
    DiscordNotifier().attach()
    for item in ({"title": "Opening", "kind": "talk", "start": NOW + 300, "where": "Main stage",
                  "note": "Doors close at the start."},
                 {"title": "Quiet hours", "kind": "quiet", "start": NOW + 300, "end": NOW + 3600},
                 {"title": "Rocket Cup final", "kind": "tournament", "start": NOW + 3600},
                 {"title": "Breakfast", "kind": "meal", "start": NOW - 60}):
        assert client.post("/api/schedule/items", json=item).status_code == 201
    return schedule_announce.Announcer(app_module.app), sent


def test_starting_soon():
    items = [{"id": "a", "start": NOW + 600}, {"id": "b", "start": NOW + 601}, {"id": "c", "start": NOW},
             {"id": "d", "start": NOW + 1}]
    assert [i["id"] for i in schedule_announce.starting_soon(items, NOW, 600)] == ["d", "a"]


def test_nothing_without_a_webhook_or_the_public_page(client, announce, monkeypatch):
    announcer, sent = announce
    assert announcer.tick(NOW) == []          # no webhook
    monkeypatch.setenv("DISCORD_SCHEDULE_WEBHOOK_URL", HOOK)
    assert announcer.tick(NOW) == []          # the public schedule page is off
    client.put("/api/settings", json={"public.schedule": True})
    monkeypatch.setenv("SCHEDULE_ANNOUNCE_MINUTES", "0")
    assert announcer.tick(NOW) == [] and sent == []


def test_announces_once_what_starts_soon(client, announce, monkeypatch):
    announcer, sent = announce
    monkeypatch.setenv("DISCORD_SCHEDULE_WEBHOOK_URL", HOOK)
    client.put("/api/settings", json={"public.schedule": True})
    assert [i["title"] for i in announcer.tick(NOW)] == ["Opening", "Quiet hours"]
    assert len(sent) == 1 and sent[0]["_webhook"] == HOOK and sent[0]["allowed_mentions"] == {"parse": []}
    talk, quiet = sent[0]["embeds"]
    assert talk["title"] == "Opening"
    assert talk["description"] == (f"Starts <t:{NOW + 300}:R>, at <t:{NOW + 300}:t> · Main stage\n"
                                   "Doors close at the start.")
    assert quiet["title"] == "Quiet hours" and "Please keep it down." in quiet["description"]
    assert announcer.tick(NOW + 30) == [] and len(sent) == 1          # once
    assert [i["title"] for i in announcer.tick(NOW + 3000)] == ["Rocket Cup final"]
    # Moved: announced again at the new time.
    opening = next(i for i in client.get("/api/schedule").get_json()["items"] if i["title"] == "Opening")
    client.patch(f"/api/schedule/items/{opening['id']}", json={"start": NOW + 3300})
    assert [i["title"] for i in announcer.tick(NOW + 3000)] == ["Opening"]
    from tests.conftest import TEST_USER
    assert TEST_USER not in str(sent)


def test_links_the_agenda_with_a_public_url(client, announce, monkeypatch, app_module):
    announcer, sent = announce
    monkeypatch.setenv("DISCORD_SCHEDULE_WEBHOOK_URL", HOOK)
    monkeypatch.setattr(app_module.app.extensions["auth"], "public_url", lambda: "https://floor.example.com/")
    client.put("/api/settings", json={"public.schedule": True})
    announcer.tick(NOW)
    assert sent[0]["embeds"][0]["url"] == "https://floor.example.com/agenda"
