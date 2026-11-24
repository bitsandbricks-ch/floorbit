"""An alert whose recovery got lost clears once LibreNMS no longer lists it as open (issue #951)."""
import pytest
import requests
from test_librenms_alerts import _alert
from test_librenms_client import Answer, librenms  # noqa: F401  # fixture

from floorbit.builtin_plugins.librenms import breaker, client


def test_a_lost_recovery_clears_when_librenms_no_longer_lists_the_alert(app_module):
    from floorbit import librenms_alerts as la
    la.take(_alert(alert_id=7), agent="hall", now=1000)
    la.take(_alert(alert_id=8, sysName="sw-b-01"), agent="hall", now=1000)
    la.take(_alert(alert_id=None, sysName="sw-c-01"), agent="hall", now=1000)    # no alert id: left alone
    assert la.reconcile(None, now=5000) == 0                                    # couldn't read: keep all
    assert len(la.active()) == 3
    assert la.reconcile([{"id": 8, "state": 1}], now=1000 + la.GRACE - 1) == 0  # too new to judge
    assert la.reconcile([{"id": 8, "state": 1}], now=5000) == 1
    assert sorted(a["host"] for a in la.active()) == ["sw-b-01", "sw-c-01"]


def test_the_status_poll_asks_at_most_every_few_minutes_and_only_with_open_alerts(app_module):
    from floorbit import librenms_alerts as la
    asked = []

    class Source:
        def active_alerts(self):
            asked.append(1)
            return []

    la._last_reconcile[0] = 0
    assert la.maybe_reconcile(Source(), now=10_000) == 0 and asked == []         # nothing open: no call
    la.take(_alert(), agent="hall", now=10_000)
    assert la.maybe_reconcile(Source(), now=10_000 + la.GRACE) == 1 and asked == [1]
    la.take(_alert(alert_id=9), agent="hall", now=10_000)
    assert la.maybe_reconcile(Source(), now=10_000 + la.GRACE + 10) == 0 and asked == [1]   # asked a moment ago
    la._last_reconcile[0] = 0


def test_the_client_lists_only_open_alerts_and_raises_when_it_cant_read(librenms, monkeypatch):  # noqa: F811
    rows = [{"id": 7, "device_id": 12, "rule_id": 3, "state": 1, "hostname": "sw-a-01.example.com", "notes": "x"},
            {"id": 8, "device_id": 13, "rule_id": 3, "state": 0, "hostname": "sw-b-01.example.com"},
            {"id": 9, "device_id": 14, "rule_id": 4, "state": 2, "hostname": "sw-c-01.example.com"}]
    answers = {"alerts": Answer({"alerts": rows})}

    def fake(url, headers=None, params=None, **kwargs):
        return answers["alerts"]

    monkeypatch.setattr(client.requests, "get", fake)
    breaker.reset()
    assert [a["id"] for a in client.active_alerts()] == [7, 9]          # acknowledged is still open
    assert "notes" not in client.active_alerts()[0]
    answers["alerts"] = Answer({}, 500)
    with pytest.raises(requests.HTTPError):
        client.active_alerts()
    answers["alerts"] = Answer({"status": "ok"})
    with pytest.raises(ValueError):
        client.active_alerts()


def test_through_the_agent_an_older_agent_clears_nothing(app_module, monkeypatch):
    from floorbit import agent_link
    from floorbit.plugins import LAN_METHODS
    assert "active_alerts" in agent_link.METHODS and "active_alerts" in LAN_METHODS   # only the agent reads LibreNMS
    source = agent_link.monitoring_source()
    monkeypatch.setattr(agent_link, "ask", lambda method, args: [{"id": 7, "state": 1}])
    assert source.active_alerts() == [{"id": 7, "state": 1}]

    def old_agent(method, args):
        raise agent_link.AgentError("active_alerts is not something the agent answers")

    monkeypatch.setattr(agent_link, "ask", old_agent)
    assert source.active_alerts() is None
