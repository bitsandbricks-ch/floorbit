"""Which agent a service check runs from (issue #1444): "Checked from", the device's own agents,
else the group's primary, so the numbers come from one place."""
import pytest

from floorbit import agent_ha, agent_link, services


@pytest.fixture
def agents(client, monkeypatch):
    """Agents a1 (tag hall-b), a2 and a3 connected; a2 is the primary of their group."""
    services.poller.reset()
    calls = []
    monkeypatch.setattr(services, "_via_agent", lambda: True)
    monkeypatch.setattr(agent_link, "_routing", lambda: ({}, ["a1", "a2", "a3"], {}))
    monkeypatch.setattr(agent_link.tunnel, "connected_agents", lambda: {"a1", "a2", "a3"})
    monkeypatch.setattr(agent_link, "all_agents", lambda *a, **k: [
        {"id": "a1", "tags": ["hall-b"]}, {"id": "a2", "tags": []}, {"id": "a3", "tags": []}])
    monkeypatch.setattr(agent_ha, "action_targets", lambda ids, now=None: ["a2"])

    def call(method, args=(), timeout=None, targets=None):
        calls.append((method, targets))
        return {"sent": 3, "lost": 0, "ms": 1.0}
    monkeypatch.setattr(agent_link.tunnel, "call", call)
    yield calls
    services.poller.reset()


def _run(client, calls, **body):
    r = client.post("/api/services/checks", json={"name": "Check", "kind": "ping", **body})
    assert r.status_code == 201, r.get_json()
    item = r.get_json()
    services.check_own(item)
    return item, calls[-1]


def test_a_check_runs_on_the_primary_by_default(client, agents):
    item, call = _run(client, agents, host="192.0.2.40")
    assert item["from"] == "" and call == ("check_probe", {"a2"})


def test_checked_from_one_agent_or_a_tag(client, agents):
    assert _run(client, agents, host="192.0.2.40", **{"from": "a3"})[1] == ("check_probe", {"a3"})
    assert _run(client, agents, host="192.0.2.40", **{"from": "tag:hall-b"})[1] == ("check_probe", {"a1"})


def test_an_agent_that_is_away_hands_the_check_to_the_default(client, agents):
    item, call = _run(client, agents, host="192.0.2.40", **{"from": "gone"})
    assert item["from"] == "gone" and call == ("check_probe", {"a2"})


def test_a_check_of_an_inventory_device_runs_where_the_device_is_collected(client, agents, monkeypatch):
    from floorbit import inventory
    monkeypatch.setattr(inventory, "devices", lambda data, include_hidden=False: [
        {"name": "sw-b-01", "mgmt_ip": "192.0.2.21"}])
    monkeypatch.setattr(agent_link, "agent_for", lambda name: "a1" if name == "sw-b-01" else "a2")
    assert _run(client, agents, host="192.0.2.21")[1] == ("check_probe", {"a1"})
    assert _run(client, agents, host="sw-b-01.example.com")[1] == ("check_probe", {"a1"})


def test_a_bad_checked_from_is_refused(client, agents):
    r = client.post("/api/services/checks", json={"name": "X", "kind": "ping", "host": "192.0.2.1", "from": "tag:"})
    assert r.status_code == 400


def test_without_a_connected_agent_whoever_answers(client, agents, monkeypatch):
    monkeypatch.setattr(agent_link.tunnel, "connected_agents", set)
    assert _run(client, agents, host="192.0.2.40")[1] == ("check_probe", None)
