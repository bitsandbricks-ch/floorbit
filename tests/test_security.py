"""Security detection (issue #29): findings from plugins, seats, alerts and one-click shutdown."""
import pytest

from floorbit import ports, security
from integrations import events

MAC = "02:00:00:00:00:1b"


@pytest.fixture
def registry(app_module):
    return app_module.app.extensions["floorbit_plugins"]


@pytest.fixture
def watch(app_module):
    w = app_module.app.extensions["floorbit_security"]
    w.stop()      # the background thread must not poll in the middle of a test
    w.reset()
    for state in (ports._last, ports._failures, ports._busy):
        state.clear()
    yield w
    w.reset()


@pytest.fixture
def fake(client, registry, watch, monkeypatch):
    """The demo plugin on, reporting whatever the test puts in the list."""
    client.put("/api/settings/plugins/demo", json={"enabled": True})
    answer = []
    real = registry.call

    def call(spec, method, *args):
        if method == "security_findings" and spec.id == "demo":
            if answer and answer[0] == "fail":
                raise security.PluginError("Demo data failed")
            return list(answer)
        return real(spec, method, *args)

    monkeypatch.setattr(registry, "call", call)
    from integrations import seat_sources
    monkeypatch.setattr(seat_sources, "load", lambda *a, **k: {"B-4": {"mac": MAC.upper().replace(":", "-")},
                                                               "B-9": {"ip_address": "192.0.2.42"}})
    return answer


def spoof(**extra):
    return {"id": "arp-1", "kind": "arp-spoof", "severity": "high", "title": "192.0.2.42 is answered by two MACs",
            "switch": "sw-b-01", "port": "Gi1/0/4", "mac": MAC, "ip": "192.0.2.42", **extra}


def sign_in(app_module, username, role):
    app_module.app.extensions["auth"].users.add(username, "role-password-1", role=role)
    c = app_module.app.test_client()
    assert c.post("/login", data={"username": username, "password": "role-password-1"}).status_code == 302
    return c


def test_security_is_a_plugin_area(registry):
    from floorbit.plugins import AREA_METHODS, EVENTS
    assert AREA_METHODS["security"] == ("security_findings",) and "security.finding" in EVENTS
    assert "set_port" in AREA_METHODS["ports"]


def test_findings_need_seats_view(app_module, client, watch):
    # They name MACs and IPs: personal data.
    for role in ("viewer", "kiosk"):
        c = sign_in(app_module, f"someone-{role}", role)
        assert c.get("/api/security").status_code == 403
        assert c.get("/api/security/markers").status_code == 403
    tech = sign_in(app_module, "fixer", "tech")
    assert tech.get("/api/security").status_code == 200
    assert tech.post("/api/security/check").status_code == 403      # plugins.run


def test_demo_findings(client, watch):
    client.put("/api/settings/plugins/demo", json={"enabled": True})
    body = client.get("/api/security").get_json()
    kinds = {f["kind"] for f in body["findings"]}
    assert {"arp-spoof", "mac-flap", "storm"} <= kinds
    assert body["findings"][0]["severity"] == "high"     # worst first
    assert body["can_act"] is True and body["needs_login"] is False


def test_findings_are_cleaned_and_find_their_seat(client, fake):
    fake += [spoof(), spoof(id="arp-1", title="duplicate"),
             {"id": "x", "title": "Odd", "kind": "nonsense", "severity": "extreme", "mac": "not a mac",
              "ip": "192.0.2.42", "evidence": ["a" * 300]},
             {"title": "no id"}]
    found = {f["id"]: f for f in client.get("/api/security").get_json()["findings"]}
    assert set(found) == {"demo:arp-1", "demo:x"}
    assert found["demo:arp-1"]["seat"] == "B-4"          # by MAC, whatever its spelling, not by the victim's IP
    odd = found["demo:x"]
    assert (odd["kind"], odd["severity"], odd["mac"], odd["seat"]) == ("other", "medium", "", "B-9")   # by IP
    assert len(odd["evidence"][0]) == 160


def test_new_findings_alert_once_and_clear(client, fake, watch):
    seen = []
    events.subscribe("security.finding", lambda ev: seen.append(ev["data"]))
    fake.append(spoof())
    assert watch.poll_once() == []                       # baseline: a restart pages nobody
    fake.append(spoof(id="arp-2"))
    new = watch.poll_once()
    assert [f["id"] for f in new] == ["demo:arp-2"]
    # Open browsers get this event: where, not who.
    assert seen[-1] == {"id": "demo:arp-2", "kind": "arp-spoof", "severity": "high", "switch": "sw-b-01",
                        "port": "Gi1/0/4", "seat": "B-4"}
    assert watch.poll_once() == []                       # still there: no second alert
    fake.pop()
    watch.poll_once()
    snap = watch.snapshot()
    assert [f["id"] for f in snap["findings"]] == ["demo:arp-1"]
    assert [f["id"] for f in snap["cleared"]] == ["demo:arp-2"]


def test_a_failing_plugin_clears_nothing(client, fake, watch):
    fake.append(spoof())
    watch.poll_once()
    fake[0] = "fail"
    watch.poll_once()
    assert [f["id"] for f in watch.snapshot()["findings"]] == ["demo:arp-1"]
    assert watch.snapshot()["cleared"] == []


def test_discord_gets_where_not_who(app_module):
    discord = app_module.app.extensions["lal_integrations"]["discord"]
    discord._last_alert.clear()
    msg = discord.build_security_message({"id": "demo:arp-1", "kind": "arp-spoof", "severity": "high",
                                          "switch": "sw-b-01", "port": "Gi1/0/4", "seat": "B-4"}, now=1000)
    text = str(msg)
    assert "ARP spoofing" in text and "sw-b-01 Gi1/0/4" in text and "B-4" in text
    assert MAC not in text and "192.0.2" not in text
    assert discord.build_security_message({"id": "demo:arp-1", "kind": "arp-spoof", "severity": "high"},
                                          now=1010) is None          # cooldown
    assert discord.build_security_message({"id": "demo:low", "kind": "other", "severity": "low"}) is None


def test_acknowledge(client, fake):
    fake.append(spoof())
    client.get("/api/security")
    resp = client.post("/api/security/demo:arp-1/ack", json={"on": True})
    assert resp.status_code == 200 and resp.get_json()["ack"]["by"] == "tester"
    assert client.post("/api/security/demo:gone/ack", json={}).status_code == 404


def test_one_click_shutdown_uses_the_findings_port(client, fake):
    assert client.post("/api/inventory", json={"name": "sw-b-01", "mgmt_ip": "198.51.100.7"}).status_code in (200, 201)
    fake.append(spoof())
    client.get("/api/security")
    # Whatever switch and port the browser adds, the finding decides.
    resp = client.post("/api/ports/shutdown", json={"finding": "demo:arp-1", "switch": "core-01", "port": "Gi9/9/9",
                                                    "reason": "ARP spoofing"})
    body = resp.get_json()
    assert resp.status_code == 200, body
    assert (body["switch"], body["port"], body["seat"]) == ("sw-b-01", "Gi1/0/4", "B-4")
    from floorbit import sources
    assert sources.monitoring().port_stats("sw-b-01.example.com", "Gi1/0/4")["state"] == "down"
    shut = client.get("/api/ports/shut").get_json()["ports"]
    assert [(p["switch"], p["port"], p["reason"], p["by"]) for p in shut] == [("sw-b-01", "Gi1/0/4", "ARP spoofing",
                                                                               "tester")]
    assert client.post("/api/ports/enable", json={"switch": "sw-b-01", "port": "Gi1/0/4"}).status_code == 200
    assert client.get("/api/ports/shut").get_json()["ports"] == []
    assert client.post("/api/ports/shutdown", json={"finding": "demo:nope"}).status_code == 400
    assert client.post("/api/ports/reload", json={}).status_code == 404


def test_markers(client, fake):
    client.post("/api/inventory", json={"name": "sw-d-02", "mgmt_ip": "198.51.100.9"})
    fake += [spoof(), {"id": "storm", "kind": "storm", "title": "Storm", "switch": "sw-d-02", "port": "Gi1/0/48"}]
    client.get("/api/security")
    marks = client.get("/api/security/markers").get_json()
    assert marks["seats"] == {"B-4": 1} and list(marks["switches"].values()) == [1]
