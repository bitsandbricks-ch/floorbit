"""LibreNMS alerts with two agents in one group (issue #1405): an alert raised through one and
cleared through the other is one alert, and the same alert through both is kept once."""
from test_agent import enrol, head
from test_librenms_alerts import _alert, _enable, _ports


def _post(anon_client, key, payload):
    res = anon_client.post("/api/agent/v1/plugins/librenms-alerts/alert", headers=head(key),
                           json={"payload": payload})
    assert res.status_code == 200, res.data


def _librenms(client):
    return [p for p in client.get("/api/problems").get_json()["problems"] if p["kind"] == "librenms"]


def test_an_alert_through_one_agent_clears_through_the_other(client, anon_client):
    a, b = enrol(client, "Agent A")["key"], enrol(client, "Agent B")["key"]
    _enable(client)
    _post(anon_client, a, _alert(faults=_ports("Gi1/0/5")))
    _post(anon_client, b, _alert(faults=_ports("Gi1/0/5")))      # LibreNMS posts to both
    assert len(_librenms(client)) == 1
    _post(anon_client, b, _alert(state=0, at="2026-01-10 18:05:00"))   # the VIP moved: B sends the recovery
    assert _librenms(client) == []
