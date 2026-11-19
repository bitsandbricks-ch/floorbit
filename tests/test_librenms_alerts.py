"""LibreNMS alerts through the agent (issue #951): the agent part checks the token and passes the
alert on; the hosted part keeps it as a problem until its recovery. No LibreNMS, no network."""
import importlib.util
import json
import pathlib

import pytest
from test_agent import enrol, head

from floorbit.plugins.agent import MemoryContext

BLOCK = {"sends": {"alert": {"privacy": "device"}}}
PLUGIN = pathlib.Path(__file__).parent.parent / "floorbit" / "builtin_plugins" / "librenms-alerts"


def _agent_part(settings):
    spec = importlib.util.spec_from_file_location("librenms_alerts_agent", PLUGIN / "agent.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    ctx = MemoryContext("librenms-alerts", settings, BLOCK)
    ctx.listen_http = lambda port, handler, tls=False: port
    return ctx, module.AgentPlugin(ctx)


def _alert(state=1, alert_id=7, faults=None, at="2026-01-10 18:00:00", **extra):
    return {"alert_id": alert_id, "rule_id": 3, "device_id": 12, "hostname": "sw-a-01.example.com",
            "sysName": "sw-a-01", "state": state, "severity": "critical", "title": "Port down on sw-a-01",
            "name": "Port down", "timestamp": at, "faults": faults or {}, **extra}


def _ports(*names):
    return {str(i + 1): {"ifName": n, "port_id": 100 + i} for i, n in enumerate(names)}


# ── the agent part ─────────────────────────────────────────────────────────────────────────

def test_the_agent_part_is_off_without_a_port_or_token():
    ctx, plugin = _agent_part({"port": 0, "token": "fbl_x"})
    plugin.start()
    assert ctx.health_.report()["status"] == "off"
    ctx, plugin = _agent_part({"port": 9530})
    plugin.start()
    assert ctx.health_.report()["status"] == "off" and "token" in ctx.health_.report()["message"]


def test_the_agent_part_checks_the_token_and_passes_the_alert_on():
    ctx, plugin = _agent_part({"port": 9530, "token": "fbl_right"})
    plugin.start()
    assert ctx.health_.report()["status"] == "ok" and "9530" in plugin.check()
    body = json.dumps(_alert()).encode()
    assert plugin.handle("POST", "/librenms", {"Authorization": "Bearer fbl_wrong"}, body)[0] == 401
    assert plugin.handle("POST", "/librenms", {}, body)[0] == 401
    assert plugin.handle("GET", "/librenms", {"Authorization": "Bearer fbl_right"}, b"")[0] == 404
    assert plugin.handle("POST", "/librenms", {"Authorization": "Bearer fbl_right"}, b"{nope")[0] == 400
    assert plugin.handle("POST", "/librenms", {"Authorization": "Bearer fbl_right"}, b"[1]")[0] == 400
    assert plugin.handle("POST", "/librenms", {"Authorization": "Bearer fbl_right"}, b"x" * 300_000)[0] == 413
    assert ctx.sent == []
    assert plugin.handle("POST", "/librenms/", {"authorization": "bearer fbl_right"}, body)[0] == 202
    assert ctx.sent == [("alert", _alert())]


# ── reading and keeping ────────────────────────────────────────────────────────────────────

def test_faults_come_as_an_object_a_list_or_a_string(app_module):
    from floorbit import librenms_alerts as la
    as_object = la.read(_alert(faults=_ports("Gi1/0/1", "Gi1/0/2")))
    as_list = la.read(_alert(faults=[{"ifName": "Gi1/0/1"}, {"ifDescr": "Gi1/0/2"}]))
    as_text = la.read(_alert(faults=json.dumps(_ports("Gi1/0/1", "Gi1/0/2"))))
    assert as_object["ports"] == as_list["ports"] == as_text["ports"] == ["Gi1/0/1", "Gi1/0/2"]
    assert la.read(_alert(faults="not json"))["ports"] == []
    assert la.read(_alert(severity="weird"))["severity"] == "warning"


@pytest.mark.parametrize("bad, says", [
    ([], "JSON object"), ({**_alert(), "sysName": "", "hostname": ""}, "hostname"),
    ({**_alert(), "state": "x"}, "state"), ({**_alert(), "alert_id": None, "rule_id": None}, "alert_id"),
])
def test_a_wrong_template_is_said(app_module, bad, says):
    from floorbit import librenms_alerts as la
    with pytest.raises(la.AlertError, match=says):
        la.read(bad)


def test_an_alert_lives_until_its_recovery(app_module):
    from floorbit import librenms_alerts as la
    from floorbit import sources
    sources.status_wake.clear()
    assert la.take(_alert(faults=_ports("Gi1/0/1", "Gi1/0/2")), agent="hall") == "opened"
    assert sources.status_wake.is_set()                  # the status monitor looks at once
    [a] = la.active()
    assert a["ports"].keys() == {"Gi1/0/1", "Gi1/0/2"} and a["host"] == "sw-a-01"
    # Better: one port came back, the other is still down and keeps its since.
    first = a["ports"]["Gi1/0/2"]
    assert la.take(_alert(4, faults=_ports("Gi1/0/2"), at="2026-01-10 18:05:00"), agent="hall") == "updated"
    [a] = la.active()
    assert list(a["ports"]) == ["Gi1/0/2"] and a["ports"]["Gi1/0/2"] == first
    # An older one arriving late changes nothing; the recovery clears it.
    assert la.take(_alert(3, faults=_ports("Gi1/0/9"), at="2026-01-10 17:00:00"), agent="hall") == "stale"
    assert la.take(_alert(0, at="2026-01-10 18:10:00"), agent="hall") == "cleared"
    assert la.active() == []
    assert la.take(_alert(0, at="2026-01-10 18:11:00"), agent="hall") == "unknown"


def test_alerts_are_kept_per_agent_host_and_alert_id(app_module):
    from floorbit import librenms_alerts as la
    la.take(_alert(alert_id=1), agent="hall")
    la.take(_alert(alert_id=2), agent="hall")
    la.take(_alert(alert_id=1, sysName="sw-b-01"), agent="hall")
    la.take(_alert(alert_id=1), agent="other")
    assert len(la.active()) == 4


def test_acknowledged_stays_but_is_no_longer_down(app_module):
    from floorbit import librenms_alerts as la
    la.take(_alert(), agent="hall")
    assert la.problems()[0]["level"] == "down"
    la.take(_alert(2, at="2026-01-10 18:01:00"), agent="hall")
    [p] = la.problems()
    assert p["level"] == "warn" and p["title"] == "Port down on sw-a-01 (acknowledged in LibreNMS)"


# ── the hosted side ────────────────────────────────────────────────────────────────────────

def _enable(client):
    res = client.put("/api/settings/plugins/librenms-alerts", json={"enabled": True})
    assert res.status_code == 200, res.data


def test_the_agent_gets_a_token_and_its_alerts_reach_problems(client, anon_client):
    key = enrol(client)["key"]
    _enable(client)
    cfg = anon_client.get("/api/agent/v1/plugins", headers=head(key)).get_json()
    settings = cfg["plugins"]["librenms-alerts"]["settings"]
    assert settings["port"] == 9530 and settings["token"].startswith("fbl_")
    # The same token every time: LibreNMS keeps what was pasted.
    again = anon_client.get("/api/agent/v1/plugins", headers=head(key)).get_json()
    assert again["plugins"]["librenms-alerts"]["settings"]["token"] == settings["token"]

    res = anon_client.post("/api/agent/v1/plugins/librenms-alerts/alert", headers=head(key),
                           json={"payload": _alert(faults=_ports("Gi1/0/5"))})
    assert res.status_code == 200, res.data
    problems = client.get("/api/problems").get_json()["problems"]
    [p] = [p for p in problems if p["kind"] == "librenms"]
    assert p["title"] == "Port down on sw-a-01" and p["where"].endswith("Gi1/0/5") and p["level"] == "down"

    # A broken template is declined, so the agent doesn't send it again and again.
    res = anon_client.post("/api/agent/v1/plugins/librenms-alerts/alert", headers=head(key),
                           json={"payload": {"state": 1}})
    assert 400 <= res.status_code < 500

    # The crew clears one whose recovery got lost.
    res = client.delete(f"/api/alerts/librenms/{p['clear_id']}")
    assert res.status_code == 200
    assert not [p for p in client.get("/api/problems").get_json()["problems"] if p["kind"] == "librenms"]
    assert client.delete(f"/api/alerts/librenms/{p['clear_id']}").status_code == 404


def test_setup_shows_what_to_paste(client):
    enrol(client)
    _enable(client)
    body = client.get("/api/alerts/librenms/setup").get_json()
    assert body["enabled"] and body["token"].startswith("fbl_") and body["port"] == 9530
    assert body["agents"][0]["url"] == "https://<agent address>:9530/librenms"
    assert "$alert->faults" in body["body"] and "$alert->state" in body["body"]
    new = client.post("/api/alerts/librenms/token").get_json()["token"]
    assert new != body["token"] and client.get("/api/alerts/librenms/setup").get_json()["token"] == new


def test_setup_and_clearing_need_their_permissions(app_module):
    from auth import roles
    assert roles.needed_for("/api/alerts/librenms/setup", "GET") == "settings.manage"
    assert roles.needed_for("/api/alerts/librenms/token", "POST") == "settings.manage"
    assert roles.needed_for("/api/alerts/librenms/abc", "DELETE") == "incidents.work"
