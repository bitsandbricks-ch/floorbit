"""A mute that runs out on something still down says so once (issue #262)."""
import time

from integrations import alerting
from integrations.discord import DiscordNotifier
from tests.test_health import fake_checks, registry, service, wall  # noqa: F401 (fixtures)
from tests.test_service_mutes import red_wall


def later(minutes=31):
    return time.time() + minutes * 60


def test_a_switch_still_offline_when_its_mute_ends(client, monkeypatch):
    monkeypatch.setenv("DISCORD_MENTION", "<@&1>")
    a = client.post("/api/switches", json={"name": "sw-a-01", "x": 10, "y": 10}).get_json()["id"]
    b = client.post("/api/switches", json={"name": "sw-a-02", "x": 20, "y": 10}).get_json()["id"]
    client.post("/api/alerts/mutes", json={"switch_id": a, "minutes": 30, "reason": "PSU swap"})
    client.post("/api/alerts/mutes", json={"switch_id": b, "minutes": 30})
    notifier = DiscordNotifier()
    notifier.monitor = type("M", (), {"statuses": {a: {"status": "offline"}, b: {"status": "online"}}})()

    assert notifier.check_mutes() is None  # still running
    msg = notifier.check_mutes(now=later())
    # The one that came back while muted is left out: nothing is wrong with it.
    assert [e["title"] for e in msg["embeds"]] == ["🔔 Mute on sw-a-01 ended: still offline"]
    assert msg["embeds"][0]["description"] == "Muted because: PSU swap" and msg["content"] == "<@&1>"
    assert a in notifier._last_alert
    # Said once: the ended mutes are gone.
    assert notifier.check_mutes(now=later()) is None
    assert alerting.mutes() == {} and alerting.take_expired(later()) == {}


def test_a_mute_lifted_by_hand_says_nothing(client):
    a = client.post("/api/switches", json={"name": "sw-a-01", "x": 10, "y": 10}).get_json()["id"]
    client.post("/api/alerts/mutes", json={"switch_id": a, "minutes": 30})
    client.delete(f"/api/alerts/mutes/{a}")
    notifier = DiscordNotifier()
    notifier.monitor = type("M", (), {"statuses": {a: {"status": "offline"}}})()
    assert notifier.check_mutes(now=later()) is None


def test_a_service_still_down_when_its_mute_ends(app_module, client, wall, fake_checks, monkeypatch):  # noqa: F811
    red_wall(wall, fake_checks, monkeypatch)
    monkeypatch.setenv("PUBLIC_URL", "https://floor.example.com")
    client.post("/api/alerts/mutes", json={"service_id": "demo:game-1", "minutes": 30})
    notifier = DiscordNotifier(app=app_module.app)
    msg = notifier.check_mutes(now=later())
    embed = msg["embeds"][0]
    assert embed["title"] == "🔔 Mute on Game server 1 ended: still down"
    assert embed["description"] == "The mute ran out and it has not come back."
    assert embed["url"] == "https://floor.example.com/health" and msg["allowed_mentions"] == {"parse": []}

    client.post("/api/alerts/mutes", json={"service_id": "demo:game-1", "minutes": 30})
    monkeypatch.setenv("DISCORD_HEALTH_ALERTS", "0")
    assert notifier.check_mutes(now=later()) is None


def test_the_poll_posts_it(app_module, client, monkeypatch):
    a = client.post("/api/switches", json={"name": "sw-a-01", "x": 10, "y": 10}).get_json()["id"]
    client.post("/api/alerts/mutes", json={"switch_id": a, "minutes": 1})
    notifier = app_module.app.extensions["lal_integrations"]["discord"]
    assert notifier.monitor is app_module.app.extensions["lal_integrations"]["monitor"]
    monkeypatch.setitem(notifier.monitor.statuses, a, {"id": a, "name": "sw-a-01", "status": "offline", "since": 0})
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.example.com/api/webhooks/1/x")
    posted = []
    monkeypatch.setattr(notifier, "post", posted.append)
    monkeypatch.setattr(time, "time", lambda real=time.time: real() + 120)
    notifier.on_poll({"data": {"changes": []}})
    assert [p["embeds"][0]["title"] for p in posted] == ["🔔 Mute on sw-a-01 ended: still offline"]
