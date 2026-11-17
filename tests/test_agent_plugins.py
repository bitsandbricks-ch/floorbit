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
                          "calls": [], "actions": [], "targets": False}


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


def test_the_hosted_part_can_say_what_the_agent_gets(client, anon_client, hallthing):
    key = enrol(client)["key"]
    client.put("/api/settings/plugins/hallthing", json={"enabled": True})
    hallthing.module.Plugin.agent_settings = lambda self, settings: {**settings, "targets": ["sw-a-01"]}
    try:
        cfg = anon_client.get("/api/agent/v1/plugins", headers=head(key)).get_json()["plugins"]["hallthing"]
        assert cfg["settings"]["targets"] == ["sw-a-01"] and cfg["settings"]["path"] == "/logs/access.log"
    finally:
        del hallthing.module.Plugin.agent_settings


def blocked_report(rev="3"):
    return {"up_seconds": 5, "plugins": {"hallthing": {
        "status": "warning", "running": True, "metrics": {}, "errors": [],
        "auth_blocked": [{"device": "sw-a-01", "credential": "ssh-ops", "rev": rev, "since": 1.0,
                          "message": "Authentication failed"}, "junk"]}}}


def test_failed_logins_are_audited_once_and_listed(client, anon_client, monkeypatch):
    from floorbit import agent_plugins, audit
    made = enrol(client)
    kept = []
    fake_scope = type("Scope", (), {"auth_failed": staticmethod(lambda *a, **k: kept.append((a, k)))})
    monkeypatch.setattr(agent_plugins, "_scope", lambda: fake_scope)
    anon_client.get("/api/agent/v1/hello", headers=head(made["key"]))
    for _ in range(2):
        anon_client.post("/api/agent/v1/report", json={"report": blocked_report()}, headers=head(made["key"]))
    entries = [e for e in audit.read(50)[0] if "stopped logging in to sw-a-01" in e.get("action", "")]
    assert len(entries) == 1 and entries[0]["ok"] is False
    assert kept == [(("sw-a-01", "ssh-ops", "3", "hallthing", "Authentication failed"), {"agent": made["id"]})]
    blocks = agent_plugins.auth_blocks("sw-a-01")
    assert blocks[0]["plugin"] == "hallthing" and blocks[0]["agent_name"] == "Demo LAN 2026"
    assert agent_plugins.auth_blocks("sw-b-01") == []


def test_clearing_a_block_needs_plugins_run_and_reaches_the_agent(client, app_module, monkeypatch):
    from floorbit import agent_plugins
    from tests.test_rbac import sign_in_as
    made = enrol(client)
    cleared = []
    fake_scope = type("Scope", (), {"clear_block": staticmethod(lambda d, c, user=None: cleared.append((d, c, user)))})
    monkeypatch.setattr(agent_plugins, "_scope", lambda: fake_scope)
    viewer = sign_in_as(app_module, "vi1", "viewer")
    url = f"/api/agent-plugins/{made['id']}/hallthing/unblock"
    assert viewer.post(url, json={"device": "sw-a-01", "credential": "ssh-ops"}).status_code == 403
    assert client.post(url, json={"credential": "ssh-ops"}).status_code == 400
    stop, seen = threading.Event(), []
    t = threading.Thread(target=fake_agent, args=(app_module.app.test_client(), made["key"], stop, seen), daemon=True)
    t.start()
    try:
        res = client.post(url, json={"device": "sw-a-01", "credential": "ssh-ops"})
        assert res.status_code == 200, res.data
        assert ("plugin", ["hallthing", "unblock", "", {"device": "sw-a-01", "credential": "ssh-ops"}]) in seen
        assert cleared and cleared[0][:2] == ("sw-a-01", "ssh-ops")
    finally:
        stop.set()
        t.join(timeout=5)


def test_targets_come_from_the_inventory(client, anon_client, hallthing, monkeypatch):
    from floorbit import agent_plugins
    key = enrol(client)["key"]
    client.put("/api/settings/plugins/hallthing", json={"enabled": True})
    asked = []

    def targets(plugin_id, kinds=None):
        asked.append((plugin_id, kinds))
        return [{"id": "d1", "name": "sw-a-01", "credential": {"id": "c1", "rev": 2, "kind": "ssh"}}]
    monkeypatch.setattr(agent_plugins, "_scope", lambda: type("S", (), {"plugin_targets": staticmethod(targets)}))
    hallthing.manifest["agent"]["targets"] = {"credentials": ["ssh"]}
    try:
        cfg = anon_client.get("/api/agent/v1/plugins", headers=head(key)).get_json()["plugins"]["hallthing"]
        # A hosted agent_settings hook sees them first and can add devices of its own.
        hallthing.module.Plugin.agent_settings = lambda self, s: {**s, "targets": [*s["targets"], {"name": "fw-01"}]}
        client.put("/api/settings/plugins/hallthing", json={"enabled": True, "settings": {"path": "/x"}})
        merged = anon_client.get("/api/agent/v1/plugins", headers=head(key)).get_json()["plugins"]["hallthing"]
    finally:
        hallthing.manifest["agent"]["targets"] = False
        del hallthing.module.Plugin.agent_settings
    assert cfg["settings"]["targets"][0]["name"] == "sw-a-01" and asked[0] == ("hallthing", ["ssh"])
    assert [t["name"] for t in merged["settings"]["targets"]] == ["sw-a-01", "fw-01"]
    assert validate(manifest(agent={"targets": {"credentials": ["telnet"]}})).startswith("agent.targets")
    m = manifest(agent={"targets": True})
    assert validate(m) == "" and m["agent"]["targets"] == {"credentials": None}


def test_plugins_that_answer_for_the_hall_go_to_the_agent_with_their_settings(client, anon_client, monkeypatch):
    from floorbit import agent_plugins, sources
    key = enrol(client)["key"]
    registry = sources.registry
    store = registry.settings_store
    values = {"librenms.url": "https://librenms.example.com", "librenms.token": "example-token"}
    monkeypatch.setattr(store, "get", lambda k, _get=store.get: values.get(k, _get(k)))
    monkeypatch.setattr(registry, "enabled", lambda spec: spec.id in ("librenms", "demo", "lancache", "loki"))
    local = anon_client.get("/api/agent/v1/plugins", headers=head(key)).get_json()["local"]
    # LibreNMS answers monitoring calls: it goes, with what is set here. Demo never, nor a plugin
    # with its own agent part (lancache), nor one that answers nothing for the hall (loki).
    assert list(local) == ["librenms"]
    assert local["librenms"]["settings"]["librenms.url"] == "https://librenms.example.com"
    assert local["librenms"]["settings"]["librenms.token"] == "example-token"
    before = agent_plugins.config()["etag"]
    values["librenms.url"] = "https://other.example.com"
    assert agent_plugins.config()["etag"] != before
