"""Muting a service on the health wall, like a switch (issue #256)."""
from integrations import alerting
from tests.test_health import fake_checks, registry, service, wall  # noqa: F401 (fixtures)
from tests.test_rbac import sign_in_as


def red_wall(wall, fake_checks, monkeypatch):  # noqa: F811
    monkeypatch.setenv("HEALTH_CONFIRM", "1")
    fake_checks.append(service("up"))
    wall.poll_once()
    fake_checks[0] = service("down", summary="Not answering")
    wall.poll_once()


def test_a_muted_service_is_marked_and_pages_nobody(app_module, client, wall, fake_checks, monkeypatch):  # noqa: F811
    red_wall(wall, fake_checks, monkeypatch)
    item = next(p for p in client.get("/api/problems").get_json()["problems"] if p["kind"] == "health")
    assert item["mute_id"] == "health:demo:game-1" and item["muted"] is None and item["name"] == "Game server 1"

    mute = {"service_id": "demo:game-1", "minutes": 30, "reason": "Restarting it"}
    answer = client.post("/api/alerts/mutes", json=mute)
    assert answer.status_code == 201 and answer.get_json()["switch_id"] == "health:demo:game-1"
    body = client.get("/api/problems").get_json()
    item = next(p for p in body["problems"] if p["kind"] == "health")
    assert item["muted"]["reason"] == "Restarting it"
    assert body["counts"]["down"] == 0 and body["counts"]["muted"] == 1
    assert body["mutes"][0]["kind"] == "health" and body["mutes"][0]["name"] == "Game server 1"

    discord = app_module.app.extensions["lal_integrations"]["discord"]
    discord._last_alert.clear()
    changes = [{"id": "demo:game-1", "name": "Game server 1", "status": "down", "previous": "up"}]
    assert discord.build_health_message(changes) is None
    entries = client.get("/api/settings/audit").get_json()["entries"]
    assert entries[0]["action"] == "Muted service alerts" and entries[0]["target"] == "Game server 1"

    assert client.delete("/api/alerts/mutes/health:demo:game-1").status_code == 200
    assert discord.build_health_message(changes)["embeds"][0]["title"] == "🔴 Game server 1 is down"
    assert alerting.mutes() == {}


def test_only_services_on_the_wall_and_only_crew(app_module, client, wall, fake_checks, monkeypatch):  # noqa: F811
    red_wall(wall, fake_checks, monkeypatch)
    nope = client.post("/api/alerts/mutes", json={"service_id": "demo:nope", "minutes": 30})
    assert nope.status_code == 400 and nope.get_json()["error"] == "There is no such service."
    assert client.post("/api/alerts/mutes", json={"service_id": "demo:game-1", "minutes": 0}).status_code == 400
    viewer = sign_in_as(app_module, "vi1", "viewer")
    assert viewer.post("/api/alerts/mutes", json={"service_id": "demo:game-1", "minutes": 30}).status_code == 403


def test_the_wall_says_until_when_a_service_is_muted(client, wall, fake_checks, monkeypatch):  # noqa: F811
    red_wall(wall, fake_checks, monkeypatch)
    assert client.get("/api/health").get_json()["checks"][0]["muted_until"] is None
    client.post("/api/alerts/mutes", json={"service_id": "demo:game-1", "minutes": 30, "reason": "Restarting it"})
    check = client.get("/api/health").get_json()["checks"][0]
    # Until when only: who and why are on the Problems page, not on a wall screen.
    assert check["muted_until"] > 0 and "Restarting it" not in str(check)
    assert client.post("/api/health/check").get_json()["checks"][0]["muted_until"] == check["muted_until"]
