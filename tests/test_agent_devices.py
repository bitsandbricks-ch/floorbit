"""The Devices tab on an agent's page (issue #1013): the agent's telemetry part says which devices it
collects and why one sends nothing; the hosted side lists them for that agent only."""
import importlib
import time

import pytest
from test_telemetry_problems import REFUSED, TARGET, AgentCtx

from floorbit import agent_devices, agent_link, agent_plugins
from floorbit.telemetry import problems, state, supervisor, targets

pytestmark = pytest.mark.usefixtures("lan_here")


@pytest.fixture(autouse=True)
def fresh():
    state.state.reset()
    yield
    state.state.reset()
    state.state.problems = None


def test_the_agent_says_what_it_collects_and_why_one_is_silent(tmp_path, monkeypatch):
    agent = importlib.import_module("floorbit.builtin_plugins.telemetry.agent")
    monkeypatch.setattr(supervisor, "binary", lambda: None)
    quiet = {**TARGET, "id": "a2", "name": "sw-a-02", "address": "192.0.2.22", "mine": True}
    traps = {**TARGET, "id": "a3", "name": "pdu-01", "drivers": ["traps"]}
    ctx = AgentCtx("telemetry", {"targets": [TARGET, quiet, traps]}, {}, state_dir=str(tmp_path))
    plugin = agent.AgentPlugin(ctx)
    plugin.start()
    try:
        token = (tmp_path / "ingest-token").read_text()
        ctx.handler("POST", "/write", {"Authorization": f"Token {token}"},
                    b"fb_if,device=sw-a-01,agent_host=192.0.2.21,ifIndex=1,ifName=Gi1/0/1 ifOperStatus=1i\n"
                    b"fb_sys,device=fw-01,driver=telegraf uptime=12i")
        p = problems.parse_line(REFUSED.replace("sw-a-01", "sw-a-02").replace("192.0.2.21", "192.0.2.22"))
        plugin.problems.note(p, time.time())
        answer = plugin.call_devices({})
    finally:
        ctx.stopping.set()
        plugin.stop()
    rows = {r["name"]: r for r in answer["devices"]}
    assert answer["primary"] is True
    assert rows["sw-a-01"]["online"] and rows["sw-a-01"]["ports"] == 1 and rows["sw-a-01"]["problems"] == []
    assert not rows["sw-a-02"]["online"] and rows["sw-a-02"]["mine"] is True
    assert rows["sw-a-02"]["problems"][0]["kind"] == "refused" and rows["sw-a-02"]["problems"][0]["hint"]
    assert rows["pdu-01"]["drivers"] == ["traps"] and rows["pdu-01"]["seen"] is None
    assert rows["fw-01"]["collects"] is True               # sent by itself, not given here
    assert "community" not in str(answer)                  # no logins


def _given(monkeypatch, rows):
    monkeypatch.setattr(targets, "listing", lambda data=None: rows)


@pytest.fixture
def client(client):
    assert client.put("/api/settings/plugins/telemetry", json={"enabled": True}).status_code == 200
    return client


def test_the_tab_lists_this_agents_devices_with_their_state(client, monkeypatch):
    enrolled = client.post("/api/agents", json={"name": "Hall A"}).get_json()
    other = client.post("/api/agents", json={"name": "Hall B"}).get_json()
    me, them = enrolled["id"], other["id"]
    _given(monkeypatch, [
        {"name": "sw-a-01", "inventory_id": "d1", "kind": "switch", "drivers": ["snmp"], "agent": ""},
        {"name": "sw-a-02", "inventory_id": "d2", "kind": "switch", "drivers": ["snmp"], "agent": me},
        {"name": "sw-b-01", "inventory_id": "d3", "kind": "switch", "drivers": ["snmp"], "agent": them},
        {"name": "pdu-01", "inventory_id": "d4", "kind": "pdu", "drivers": ["traps"], "agent": ""},
        {"name": "sw-a-03", "inventory_id": "d5", "kind": "switch", "drivers": ["snmp"], "agent": ""},
    ])
    monkeypatch.setattr(agent_link.tunnel, "connected_agents", lambda now=None: {me, them})
    asked = []

    def ask(spec, way, op, args=None, agent=None):
        asked.append((way, op, agent))
        return [{"agent": agent, "name": "Hall A", "result": {"primary": True, "devices": [
            {"name": "sw-a-01", "collects": True, "online": True, "seen": 1.0, "ports": 48, "problems": []},
            {"name": "sw-a-02", "collects": True, "online": False, "seen": None,
             "problems": [{"driver": "snmp", "kind": "refused", "hint": "nothing listens"}]},
            {"name": "SW-A-03", "collects": True, "online": False, "seen": 5.0, "problems": []},
            {"name": "fw-01", "collects": True, "online": True, "seen": 2.0, "drivers": ["telegraf"]},
        ]}}]
    monkeypatch.setattr(agent_plugins, "ask", ask)
    body = client.get(f"/api/agents/{me}/devices").get_json()
    assert asked == [("call", "devices", me)]
    rows = {r["name"]: r for r in body["devices"]}
    assert "sw-b-01" not in rows                                     # another agent's own device
    assert rows["sw-a-02"]["state"] == "silent" and rows["sw-a-02"]["pinned"] is True
    assert rows["sw-a-01"]["state"] == "up" and rows["sw-a-01"]["ports"] == 48
    assert rows["sw-a-03"]["state"] == "silent"                       # heard once, quiet now
    assert rows["pdu-01"]["state"] == "waiting"                       # traps come when something happens
    assert rows["fw-01"]["pushed"] is True and rows["fw-01"]["state"] == "up"
    assert body["devices"][0]["state"] == "silent"                    # what needs a look first
    assert body["error"] is None and body["primary"] is True


def test_an_agent_away_or_too_old_still_lists_what_it_is_given(client, monkeypatch):
    me = client.post("/api/agents", json={"name": "Hall A"}).get_json()["id"]
    _given(monkeypatch, [{"name": "sw-a-01", "inventory_id": "d1", "kind": "switch", "drivers": ["snmp"]}])
    body = client.get(f"/api/agents/{me}/devices").get_json()
    assert body["error"] == "offline" and body["devices"][0]["state"] == "unknown"
    monkeypatch.setattr(agent_link.tunnel, "connected_agents", lambda now=None: {me})
    monkeypatch.setattr(agent_plugins, "ask", lambda *a, **k: [{"agent": me, "error": "no such call devices"}])
    body = client.get(f"/api/agents/{me}/devices").get_json()
    assert body["error"] == "no_answer" and "devices" in body["detail"]
    assert body["devices"][0]["state"] == "unknown"
    assert client.get("/api/agents/nope/devices").status_code == 404


def test_a_standby_agent_says_so(client, monkeypatch):
    me = client.post("/api/agents", json={"name": "Hall A"}).get_json()["id"]
    _given(monkeypatch, [{"name": "sw-a-01", "inventory_id": "d1", "kind": "switch", "drivers": ["snmp"]}])
    monkeypatch.setattr(agent_link.tunnel, "connected_agents", lambda now=None: {me})
    monkeypatch.setattr(agent_plugins, "ask", lambda *a, **k: [{"agent": me, "result": {"primary": False, "devices": [
        {"name": "sw-a-01", "collects": False, "online": False, "problems": []}]}}])
    body = client.get(f"/api/agents/{me}/devices").get_json()
    assert body["primary"] is False and body["devices"][0]["state"] == "standby"


def test_telemetry_off_says_so(client, monkeypatch):
    me = client.post("/api/agents", json={"name": "Hall A"}).get_json()["id"]
    monkeypatch.setattr(agent_link.tunnel, "connected_agents", lambda now=None: {me})
    client.put("/api/settings/plugins/telemetry", json={"enabled": False})
    assert client.get(f"/api/agents/{me}/devices").get_json()["error"] == "no_telemetry"


def test_only_admins_see_it(anon_client, kiosk_client):
    for c in (anon_client, kiosk_client):
        assert c.get("/api/agents/x/devices").status_code in (401, 403)


def test_states_sort_what_needs_a_look_first():
    assert agent_devices._state({"online": False, "seen": None, "drivers": ["snmp"]}, True) == "never"
    assert agent_devices._state({"online": True, "problems": [{}]}, True) == "partial"
