"""The local agent is the only way Floorbit reaches the event network, also self-hosted (Mike,
2026-11-17): floorbit/agent_link.py lan_here, and the guard in floorbit/plugins Registry.call."""
import pytest

from floorbit import agent_link, sources, syslog
from floorbit.plugins import LAN_METHODS, PluginError
from tests.test_agent import clean_tunnel, enrol  # noqa: F401  # the fixture resets the tunnel


@pytest.fixture
def registry(app_module):
    return app_module.app.extensions["floorbit_plugins"]


def test_by_default_every_lan_question_goes_to_the_agent(client):
    assert not agent_link.lan_here() and agent_link.active()
    assert sources.monitoring().name == "agent"


def test_the_server_refuses_to_ask_a_lan_plugin_itself(client, registry):
    librenms = registry.specs["librenms"]
    for method in ("devices", "resolve_ip", "port_clients"):
        with pytest.raises(PluginError, match="local agent"):
            registry.call(librenms, method, "192.0.2.10")
    # Reading its own settings is no LAN access.
    registry.call(librenms, "configured")
    assert {"inventory", "bounce_port", "health_checks", "dns_queries", "wifi_aps"} <= LAN_METHODS


def test_the_agent_process_may(client, registry, monkeypatch):
    monkeypatch.setenv("FLOORBIT_AGENT_KEY", "fba_0123abcd_example-key-for-tests-only")
    assert agent_link.lan_here() and not agent_link.active()
    registry.call(registry.specs["librenms"], "configured")


def test_demo_data_stays_here(client):
    client.put("/api/settings/plugins/demo", json={"enabled": True})
    assert not agent_link.active()
    assert sources.monitoring().name == "demo"


def test_an_enrolled_agent_still_wins_over_demo_data(client):
    client.put("/api/settings/plugins/demo", json={"enabled": True})
    enrol(client)
    assert agent_link.active() and sources.monitoring().name == "agent"


def test_the_server_does_not_listen_for_syslog(tmp_path, monkeypatch):
    monkeypatch.setenv("SYSLOG_ENABLED", "1")
    monkeypatch.setenv("SYSLOG_PORT", "0")
    r = syslog.SyslogReceiver(path=str(tmp_path / "syslog"))
    r.start()
    assert r.listening is None and "local agent" in r.error


def test_without_an_agent_pages_say_so_instead_of_failing(client):
    wall = client.get("/api/health").get_json()
    assert any(c["id"] == "agent:*" for c in wall["checks"])
    details = sources.monitoring().device_details("sw-a-01")
    assert details["status"] == "unknown"


def test_there_is_no_switch_for_direct_access(client, monkeypatch):
    monkeypatch.setenv("LAN_ACCESS", "direct")     # the old development switch is gone
    assert not agent_link.lan_here() and agent_link.active()
    assert sources.monitoring().name == "agent"


def test_the_server_has_no_flows_collector_of_its_own():
    import importlib.util

    from floorbit.flows import collector
    assert not hasattr(collector, "main") and importlib.util.find_spec("floorbit.flows.__main__") is None


def test_the_test_button_of_a_lan_plugin_runs_on_the_agent(client, registry, monkeypatch):
    import threading

    from tests.test_agent import head
    assert client.put("/api/settings/plugins/librenms", json={"enabled": True}).status_code == 200
    cls = registry.specs["librenms"].plugin_class()
    monkeypatch.setattr(cls, "test", lambda self: pytest.fail("tested from the server"))
    body = client.post("/api/settings/plugins/librenms/test").get_json()
    assert body["ok"] is False and "agent" in body["message"]

    key = enrol(client)["key"]
    agent = client.application.test_client()

    def answer():
        calls = agent.get("/api/agent/v1/calls?wait=5", headers=head(key)).get_json()["calls"]
        call = calls[0]
        assert (call["method"], call["args"]) == ("plugin_test", ["librenms"])
        agent.post("/api/agent/v1/answers", headers=head(key),
                   json={"answers": [{"id": call["id"], "ok": True, "result": "LibreNMS answers: 3 devices"}]})
    agent.get("/api/agent/v1/calls?wait=0", headers=head(key))      # connected
    t = threading.Thread(target=answer)
    t.start()
    body = client.post("/api/settings/plugins/librenms/test").get_json()
    t.join(5)
    assert body == {"ok": True, "message": "LibreNMS answers: 3 devices"}
