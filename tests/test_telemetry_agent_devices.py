"""The Telemetry page and its widget ask the agents' telemetry part for its devices, even while
LibreNMS answers monitoring (issue #1223)."""
import pytest

from floorbit import agent_plugins, sources, telemetry
from floorbit.plugins.base import PluginError


class LibreNMS:
    """The monitoring source while LibreNMS polls: its devices, none of them telemetry's."""

    def devices(self):
        return [{"hostname": "sw-a-01", "status": 1, "source": "librenms"},
                {"hostname": "core-1", "status": 1, "source": "librenms"}]


def standby_and_primary(spec, way, op, args=None, agent=None):
    assert (spec.id, way, op) == ("telemetry", "call", "devices")
    standby = {"primary": False, "devices": [
        {"name": "sw-a-01", "drivers": ["snmp"], "collects": False, "online": False, "seen": None, "problems": []}]}
    primary = {"primary": True, "devices": [
        {"name": "sw-a-01", "drivers": ["snmp", "traps"], "collects": True, "online": True, "seen": 100.0,
         "ports": 52, "macs": 140, "arp": 0, "neighbours": 2, "problems": []},
        {"name": "sw-a-02", "drivers": ["snmp"], "collects": True, "online": False, "seen": None,
         "problems": [{"driver": "snmp", "kind": "timeout", "address": "192.0.2.22:161", "detail": "x"}]}]}
    return [{"agent": "b", "name": "Standby", "result": standby}, {"agent": "a", "name": "Hall", "result": primary}]


@pytest.fixture
def on_agents(client, monkeypatch):
    assert client.put("/api/settings/plugins/telemetry", json={"enabled": True}).status_code == 200
    monkeypatch.setattr(telemetry, "collector_here", lambda: False)
    monkeypatch.setattr(agent_plugins, "health_of", lambda pid: {})
    before = sources.use(LibreNMS())
    yield monkeypatch
    sources.use(before)


def test_the_page_shows_telemetrys_counts_while_librenms_answers(client, on_agents):
    on_agents.setattr(agent_plugins, "ask", standby_and_primary)
    seen = client.get("/api/telemetry/overview").get_json()["seen"]
    assert list(seen) == ["sw-a-01", "sw-a-02"]
    # The collecting agent's row wins over the standby's.
    assert seen["sw-a-01"]["online"] is True and seen["sw-a-01"]["ports"] == 52 and seen["sw-a-01"]["macs"] == 140
    assert seen["sw-a-02"]["problems"][0]["kind"] == "timeout" and "ports" not in seen["sw-a-02"]


def test_the_widget_lists_telemetrys_devices_not_librenms(client, on_agents):
    on_agents.setattr(agent_plugins, "ask", standby_and_primary)
    w = client.get("/api/plugins/telemetry/widgets/devices").get_json()
    assert [(i["label"], i["state"], i["detail"]) for i in w["items"]] == [
        ("sw-a-01", "up", "snmp, traps"), ("sw-a-02", "down", "snmp")]
    assert w["sub"] == "1 of 2 up: 1 down"


def test_no_agent_to_ask_falls_back_to_the_monitoring_source(client, on_agents):
    def nobody(*args, **kwargs):
        raise PluginError("No local agent is connected.")
    on_agents.setattr(agent_plugins, "ask", nobody)
    # LibreNMS's devices are not telemetry's: nothing to show rather than the wrong list.
    assert client.get("/api/telemetry/overview").get_json()["seen"] == {}
    assert client.get("/api/plugins/telemetry/widgets/devices").get_json()["items"] == []
