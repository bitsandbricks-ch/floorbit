"""The service health wall (issue #28): health plugins, confirmed changes and red alerts."""
import pytest

from floorbit import health
from integrations import events


@pytest.fixture
def registry(app_module):
    return app_module.app.extensions["floorbit_plugins"]


@pytest.fixture
def wall(app_module):
    w = app_module.app.extensions["floorbit_health"]
    w.stop()      # the background thread must not poll in the middle of a test
    w.reset()
    yield w
    w.reset()


@pytest.fixture
def fake_checks(client, registry, monkeypatch):
    """The demo plugin on, answering whatever the test puts in the list."""
    client.put("/api/settings/plugins/demo", json={"enabled": True})
    answer = []
    real = registry.call

    def call(spec, method, *args):
        if method == "health_checks" and spec.id == "demo":
            if isinstance(answer, list) and answer and answer[0] == "fail":
                raise health.PluginError("Demo data failed (RuntimeError); details are in its log")
            return list(answer)
        return real(spec, method, *args)

    monkeypatch.setattr(registry, "call", call)
    return answer


def service(status, **extra):
    return {"id": "game-1", "name": "Game server 1", "kind": "game", "status": status, **extra}


def test_health_area_is_a_plugin_area(registry):
    from floorbit.plugins import AREA_METHODS, AREAS, EVENTS
    assert "health" in AREAS and AREA_METHODS["health"] == ("health_checks",)
    assert "health.status" in EVENTS
    assert "health" in registry.specs["demo"].uses and "health" in registry.specs["http-check"].uses


def test_wall_is_empty_without_health_plugins(client, wall):
    body = client.get("/api/health").get_json()
    assert body["checks"] == [] and body["plugins"] == 0


def test_demo_fills_every_kind(client, wall):
    client.put("/api/settings/plugins/demo", json={"enabled": True})
    body = client.get("/api/health").get_json()
    kinds = {c["kind"] for c in body["checks"]}
    assert {"dhcp", "dns", "cache", "game", "uplink"} <= kinds
    dhcp = next(c for c in body["checks"] if c["id"] == "demo:dhcp-players")
    assert dhcp["status"] == "warn" and "leases left" in dhcp["summary"]
    assert sum(body["counts"].values()) == len(body["checks"])


def test_checks_are_cleaned_like_widgets(client, wall, fake_checks):
    fake_checks += [
        {"id": "x", "name": "<b>Cache</b>", "kind": "nonsense", "status": "purple", "link": "https://evil.example.com",
         "summary": "a" * 500,
         "metrics": [{"label": "Hit", "value": True}, {"value": 3}, "junk", *({"label": f"m{i}", "value": i}
                                                                              for i in range(10))]},
        {"id": "x", "name": "Duplicate"},
        {"name": "No id"},
        "not a dict",
    ]
    checks = client.get("/api/health").get_json()["checks"]
    assert len(checks) == 1
    c = checks[0]
    assert c["id"] == "demo:x" and c["name"] == "<b>Cache</b>"      # text stays text; React shows it as text
    assert c["kind"] == "other" and c["status"] == "unknown" and c["link"] == ""
    assert len(c["summary"]) == 120 and len(c["metrics"]) == health.MAX_METRICS
    assert c["metrics"][0] == {"label": "Hit", "value": "True", "unit": "", "tone": ""}


def test_a_failing_plugin_is_one_grey_tile(client, wall, fake_checks):
    fake_checks.append("fail")
    checks = client.get("/api/health").get_json()["checks"]
    assert [(c["id"], c["status"]) for c in checks] == [("demo:*", "unknown")]
    assert "RuntimeError" not in checks[0]["summary"]


def test_a_change_counts_once_confirmed(client, wall, fake_checks, monkeypatch):
    seen = []
    events.subscribe("health.changed", lambda ev: seen.append(ev["data"]["changes"]))
    monkeypatch.setenv("HEALTH_CONFIRM", "2")
    fake_checks.append(service("up"))
    assert wall.poll_once() == []                       # the first poll is a baseline
    fake_checks[0] = service("down", summary="Not answering")
    assert wall.poll_once() == []                       # seen once: could be one slow answer
    changes = wall.poll_once()
    assert [(c["id"], c["previous"], c["status"]) for c in changes] == [("demo:game-1", "up", "down")]
    assert seen[-1] == changes
    fake_checks[0] = service("up")
    wall.poll_once()
    fake_checks[0] = service("down")
    assert wall.poll_once() == []                       # a flap back is not confirmed either
    assert wall.confirmed["demo:game-1"] == "down"


def test_red_services_reach_discord(app_module):
    discord = app_module.app.extensions["lal_integrations"]["discord"]
    discord._last_alert.clear()
    msg = discord.build_health_message([
        {"id": "demo:game-1", "name": "Game server 1", "status": "down", "previous": "up", "summary": "Not answering"},
        {"id": "demo:cache", "name": "LAN cache", "status": "warn", "previous": "up"},   # amber pages nobody
    ], now=1000)
    assert [e["title"] for e in msg["embeds"]] == ["🔴 Game server 1 is down"]
    assert msg["embeds"][0]["description"] == "Not answering"
    # The same service again within the cooldown stays quiet; coming back is posted.
    assert discord.build_health_message([{"id": "demo:game-1", "name": "Game server 1", "status": "down",
                                          "previous": "warn"}], now=1010) is None
    back = discord.build_health_message([{"id": "demo:game-1", "name": "Game server 1", "status": "up",
                                          "previous": "down"}], now=1020)
    assert back["embeds"][0]["title"] == "🟢 Game server 1 is back" and back["allowed_mentions"] == {"parse": []}


def test_check_now_needs_plugins_run(client, app_module, wall):
    users = app_module.app.extensions["auth"].users
    users.add("watcher", "viewer-password-1", role="viewer")
    viewer = app_module.app.test_client()
    viewer.post("/login", data={"username": "watcher", "password": "viewer-password-1"})
    assert viewer.get("/api/health").status_code == 200
    assert viewer.post("/api/health/check").status_code == 403
    assert client.post("/api/health/check").status_code == 200


def test_kiosk_sees_the_wall_page(app_module, wall):
    users = app_module.app.extensions["auth"].users
    users.add("hall-screen", "kiosk-password-1", role="kiosk")
    kiosk = app_module.app.test_client()
    kiosk.post("/login", data={"username": "hall-screen", "password": "kiosk-password-1"})
    assert kiosk.get("/api/health").status_code == 200
    page = kiosk.get("/health")
    assert page.status_code in (200, 503)   # 503 only when the React app isn't built
    assert b'data-preset="kiosk"' in page.data


def test_http_check_feeds_the_wall(client, wall, monkeypatch):
    import requests

    class Resp:
        status_code = 200

    def fake_request(self, method, url, **kw):
        if "down" in url:
            raise requests.exceptions.ConnectionError("refused")
        return Resp()

    monkeypatch.setattr(requests.Session, "request", fake_request)
    client.put("/api/settings", json={"plugin.http-check.targets": ["Tickets=https://tickets.example.com",
                                                                    "https://down.example.com"]})
    client.put("/api/settings/plugins/http-check", json={"enabled": True})
    checks = {c["name"]: c for c in client.get("/api/health").get_json()["checks"]}
    assert checks["Tickets"]["status"] == "up" and checks["Tickets"]["kind"] == "web"
    assert checks["down.example.com"]["status"] == "down"
