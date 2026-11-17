"""Agent plugins: the manifest's agent: block, the privacy check, config and intake for the agent,
calls and actions over the tunnel, and per-plugin health in the agent's report."""
import threading

import pytest
from test_agent import clean_tunnel, enrol, head  # noqa: F401  # clean_tunnel is autouse there
from test_plugins import write_plugin

from floorbit import agent_link
from floorbit.plugins import _load, validate
from floorbit.plugins.agent import AgentPlugin, MemoryContext, check_payload, personal_data
from floorbit.plugins.base import PluginError

YAML = """
id: hallthing
name: Hall thing
version: "1.0"
floorbit: ">=0.1,<2"
uses: [agent, settings, actions]
settings:
  - {key: path, type: string, default: /logs/access.log}
  - {key: token, type: secret}
actions:
  - {id: clear, role: admin, danger: true}
agent:
  sends:
    stats: {privacy: aggregate}
    devices: {privacy: device}
  calls: [status]
  actions: [clear]
"""

PY = """
from floorbit.plugins.base import Plugin as Base

class Plugin(Base):
    got = []

    def agent_stats(self, agent, payload):
        Plugin.got.append((agent['name'], payload))
        return {'ok': True, 'kept': True}

    def run_clear(self, params):
        return {'message': 'asked', 'answers': self.ctx.agent_action('clear', {'what': 'steam'})}
"""

AGENT_PY = """
from floorbit.plugins.agent import AgentPlugin as Base

class AgentPlugin(Base):
    def call_status(self, args):
        return {'up': True}
"""


@pytest.fixture
def hallthing(tmp_path, app_module):
    registry = app_module.app.extensions["floorbit_plugins"]
    folder = write_plugin(tmp_path, "hallthing", YAML, PY)
    (folder / "agent.py").write_text(AGENT_PY)
    spec = _load(folder, "development", registry.version)
    assert spec.error == ""
    registry.specs[spec.id] = spec
    registry._register_settings()
    spec.module.Plugin.got.clear()
    yield spec
    registry.specs.pop(spec.id, None)


def manifest(**change):
    import yaml
    m = yaml.safe_load(YAML)
    m.update(change)
    return m


@pytest.mark.parametrize("change, error", [
    ({"uses": ["settings", "actions"]}, '"agent" is not under uses'),
    ({"agent": None}, "has no agent: block"),
    ({"agent": {"module": "../evil.py"}}, "agent.module"),
    ({"agent": {"sends": {"Bad Kind": {}}}}, "bad kind"),
    ({"agent": {"sends": {"stats": {"privacy": "everything"}}}}, "privacy must be"),
    ({"agent": {"actions": ["reboot"]}}, "add an action reboot"),
    ({"agent": {"calls": "status"}}, "agent.calls"),
])
def test_bad_agent_blocks_are_refused(change, error):
    assert error in validate(manifest(**change))


def test_a_good_agent_block_gets_defaults():
    m = manifest(agent={"sends": {"stats": None}})
    assert validate(m) == ""
    assert m["agent"] == {"module": "agent.py", "sends": {"stats": {"privacy": "aggregate"}},
                          "calls": [], "actions": []}


def test_the_agent_module_must_exist(tmp_path, app_module):
    folder = write_plugin(tmp_path, "hallthing", YAML, PY)
    spec = _load(folder, "development", "1.0")
    assert "agent.py is missing" in spec.error


def test_hosted_receivers_must_be_listed(tmp_path):
    folder = write_plugin(tmp_path, "hallthing", YAML, PY + "\n    def agent_secrets(self, agent, payload): pass\n")
    (folder / "agent.py").write_text(AGENT_PY)
    assert "agent.sends has no secrets" in _load(folder, "development", "1.0").error


# ── privacy ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("value", [
    {"seat": "192.0.2.10"}, ["fine", {"deep": ["2001:db8::1"]}], {"198.51.100.0/24": 1},
    "client 00:11:22:33:44:55 joined", "aabb.ccdd.eeff", {"x": "fe80::1"}, "10.0.0.1:443",
])
def test_addresses_are_found(value):
    assert personal_data(value)


@pytest.mark.parametrize("value", [
    {"sw-a-01|Gi1/0/1|in_bps": 12.5}, "Ethernet1/49", "18:00:01", "Sat 14.11.2026, 18:00", "v1.2.3",
    {"steam": {"hit_bytes": 1, "miss_bytes": 2}}, "lancache.steamcontent.com", "15.2(7)E3", "2026-11-17T11:30:00Z",
    "Te1/1/4", {"depot": 228988},
])
def test_names_times_and_versions_pass(value):
    assert personal_data(value) is None


def test_check_payload():
    block = {"sends": {"stats": {"privacy": "aggregate"}, "devices": {"privacy": "device"}}}
    assert check_payload(block, "stats", {"steam": 1}) == ""
    assert "aggregate-only" in check_payload(block, "stats", {"ip": "192.0.2.1"})
    assert "192" in check_payload(block, "stats", {"ip": "192.0.2.1"}) and "192.0.2.1" not in check_payload(
        block, "stats", {"ip": "192.0.2.1"})   # the error message names no address either
    assert check_payload(block, "devices", {"mgmt": "192.0.2.1"}) == ""
    assert "does not list" in check_payload(block, "other", {})


def test_memory_context_is_what_plugin_tests_use():
    ctx = MemoryContext("hallthing", {"path": "/x"}, {"sends": {"stats": {"privacy": "aggregate"}}})
    plugin = AgentPlugin(ctx)
    assert plugin.settings == {"path": "/x"} and plugin.check() == "loaded"
    ctx.send("stats", {"steam": 1})
    with pytest.raises(PluginError):
        ctx.send("stats", {"client": "192.0.2.4"})
    ctx.counter("lines", 5)
    ctx.gauge("disk_used_bytes", 100)
    ctx.health("warning", "log not found")
    ctx.error("could not read")
    with pytest.raises(PluginError):
        ctx.counter("Bad Name")
    report = ctx.health_.report()
    assert report["status"] == "warning" and report["metrics"] == {"disk_used_bytes": 100, "lines": 5}
    assert report["errors"][0]["error"] == "could not read" and ctx.sent == [("stats", {"steam": 1})]


# ── config and intake ───────────────────────────────────────────────────────────────────

def test_config_lists_only_plugins_that_are_on(client, anon_client, hallthing):
    key = enrol(client)["key"]
    got = anon_client.get("/api/agent/v1/plugins", headers=head(key))
    assert got.status_code == 200 and "hallthing" not in got.get_json()["plugins"]
    client.put("/api/settings/plugins/hallthing", json={"enabled": True})
    client.put("/api/settings", json={"plugin.hallthing.token": "s3cret"})
    got = anon_client.get("/api/agent/v1/plugins", headers=head(key))
    cfg = got.get_json()["plugins"]["hallthing"]
    assert cfg["settings"]["path"] == "/logs/access.log" and cfg["calls"] == ["status"]
    assert cfg["sends"] == {"devices": {"privacy": "device"}, "stats": {"privacy": "aggregate"}}
    assert got.headers["Cache-Control"] == "no-store"
    etag = got.headers["ETag"]
    assert anon_client.get("/api/agent/v1/plugins", headers={**head(key), "If-None-Match": etag}).status_code == 304
    assert anon_client.get("/api/agent/v1/plugins").status_code == 401


def test_intake_checks_and_hands_over(client, anon_client, hallthing):
    key = enrol(client)["key"]
    url = "/api/agent/v1/plugins/hallthing/stats"
    assert anon_client.post(url, json={"payload": {"steam": 1}}, headers=head(key)).status_code == 409
    client.put("/api/settings/plugins/hallthing", json={"enabled": True})
    res = anon_client.post(url, json={"payload": {"steam": 1}}, headers=head(key))
    assert res.status_code == 200 and res.get_json() == {"ok": True, "kept": True}
    assert hallthing.module.Plugin.got == [("Demo LAN 2026", {"steam": 1})]
    res = anon_client.post(url, json={"payload": {"top": ["192.0.2.7"]}}, headers=head(key))
    assert res.status_code == 422 and "192.0.2.7" not in res.get_data(as_text=True)
    assert len(hallthing.module.Plugin.got) == 1
    assert anon_client.post("/api/agent/v1/plugins/hallthing/secrets", json={"payload": {}},
                            headers=head(key)).status_code == 422
    assert anon_client.post("/api/agent/v1/plugins/hallthing/devices", json={"payload": {"a": "192.0.2.7"}},
                            headers=head(key)).get_json() == {"ok": True, "kept": False}
    assert anon_client.post("/api/agent/v1/plugins/nope/stats", json={"payload": {}},
                            headers=head(key)).status_code == 404
    assert anon_client.post(url, json={"payload": {}}).status_code == 401


# ── calls, actions and health ──────────────────────────────────────────────────────────

def fake_agent(test_client, key, stop, seen):
    while not stop.is_set():
        calls = test_client.get("/api/agent/v1/calls?wait=0.3", headers=head(key)).get_json()["calls"]
        out = []
        for c in calls:
            seen.append((c["method"], c["args"]))
            out.append({"id": c["id"], "ok": True, "result": {"done": c["args"][2]}})
        if out:
            test_client.post("/api/agent/v1/answers", json={"answers": out}, headers=head(key))


def test_actions_go_to_the_agent_after_the_role_check(client, app_module, hallthing):
    from tests.test_rbac import sign_in_as
    key = enrol(client)["key"]
    client.put("/api/settings/plugins/hallthing", json={"enabled": True})
    lead = sign_in_as(app_module, "le1", "lead")
    assert lead.post("/api/plugins/hallthing/actions/clear", json={}).status_code == 403
    stop, seen = threading.Event(), []
    t = threading.Thread(target=fake_agent, args=(app_module.app.test_client(), key, stop, seen), daemon=True)
    t.start()
    try:
        res = client.post("/api/plugins/hallthing/actions/clear", json={})
        assert res.status_code == 200, res.data
        answers = res.get_json()["data"]["answers"]
        assert answers[0]["name"] == "Demo LAN 2026" and answers[0]["result"] == {"done": "clear"}
        assert ("plugin", ["hallthing", "action", "clear", {"what": "steam"}]) in seen
    finally:
        stop.set()
        t.join(timeout=5)


def test_calls_must_be_listed(hallthing):
    from floorbit import agent_plugins
    with pytest.raises(PluginError, match="no agent call reboot"):
        agent_plugins.ask(hallthing, "call", "reboot")
    with pytest.raises(PluginError, match="No local agent"):
        agent_plugins.ask(hallthing, "call", "status")


def test_health_in_the_report_is_cleaned(client, anon_client):
    made = enrol(client)
    anon_client.get("/api/agent/v1/hello", headers=head(made["key"]))
    report = {"up_seconds": 5, "plugins": {
        "lancache": {"status": "warning", "message": "x" * 900, "running": True,
                     "metrics": {"lines": 10, "Bad Key": 1, "text": "no", "flag": True},
                     "errors": [{"at": 1.0, "error": "boom"}, "junk"]},
        "BAD ID": {"status": "ok"},
        "telemetry": {"status": "on fire"},
    }}
    res = anon_client.post("/api/agent/v1/report", json={"report": report}, headers=head(made["key"]))
    assert res.status_code == 200
    got = client.get("/api/agents").get_json()["agents"][0]["report"]["plugins"]
    assert set(got) == {"lancache", "telemetry"}
    assert got["lancache"]["metrics"] == {"lines": 10} and len(got["lancache"]["message"]) == 300
    assert got["lancache"]["errors"] == [{"at": 1.0, "error": "boom"}]
    assert got["telemetry"]["status"] == "error"
    from floorbit import agent_plugins
    assert agent_plugins.health_of("lancache")[made["id"]]["health"]["status"] == "warning"


def test_plugin_method_names_are_known_to_the_tunnel():
    assert {"plugin", "plugins_reload"} <= set(agent_link.METHODS)
