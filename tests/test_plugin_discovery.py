"""Discovery areas from plugins (issue #968): the manifest's discovery: list, the agent part's
discover(), and a run that puts the facts where the built-in areas put theirs."""
import importlib.util

import pytest
from test_plugins import write_plugin

from floorbit import agent_plugins, inventory, inventory_discovery, inventory_properties, plugin_discovery
from floorbit.plugins import _load, validate
from floorbit.plugins.agent import AgentPlugin, MemoryContext
from floorbit.plugins.base import PluginError
from floorbit.store import load_data

YAML = """
id: fwthing
name: Firewall thing
version: "1.0"
floorbit: ">=0.1,<2"
uses: [agent]
agent:
  targets: {credentials: [api], roles: [firewall]}
discovery:
  - {area: identity, minutes: 60}
  - {area: routes, platforms: [opnsense]}
  - {area: gateways, name: Gateways, fields: [name, status, rtt_ms], minutes: 5}
"""

PY = """
from floorbit.plugins.base import Plugin as Base

class Plugin(Base):
    pass
"""

AGENT_PY = """
from floorbit.plugins.agent import AgentPlugin as Base

class AgentPlugin(Base):
    answers = {}

    def discover(self, area, devices):
        return {d['id']: AgentPlugin.answers.get(area, {}) for d in devices}
"""


def manifest(**change):
    import yaml
    m = yaml.safe_load(YAML)
    m.update(change)
    return m


@pytest.fixture
def fwthing(tmp_path, app_module, client, monkeypatch):
    registry = app_module.app.extensions["floorbit_plugins"]
    folder = write_plugin(tmp_path, "fwthing", YAML, PY)
    (folder / "agent.py").write_text(AGENT_PY)
    spec = _load(folder, "development", registry.version)
    assert spec.error == ""
    registry.specs[spec.id] = spec
    registry._register_settings()
    client.put("/api/settings/plugins/fwthing", json={"enabled": True})
    loader = importlib.util.spec_from_file_location("fwthing_agent", folder / "agent.py")
    module = importlib.util.module_from_spec(loader)
    loader.loader.exec_module(module)
    calls = []

    def ask(spec_, way, op, args=None, agent=None):
        # The agent part, as the agent runs it, with the targets the inventory hands out.
        calls.append((spec_.id, way, op, args))
        data = load_data()
        targets = [{"id": d["id"], "name": d["name"], "role": d.get("role"), "platform": d.get("platform") or "",
                    "credential": {"id": "c1", "rev": 1}}
                   for d in inventory.devices(data) if d.get("role") == "firewall"]
        part = module.AgentPlugin(MemoryContext("fwthing", {"targets": targets}))
        return [{"agent": "a1", "name": "Agent A", "result": getattr(part, f"{way}_{op}")(args)}]
    monkeypatch.setattr(agent_plugins, "ask", ask)
    module.AgentPlugin.answers = {}
    yield module.AgentPlugin, calls
    registry.specs.pop(spec.id, None)


def add(client, **body):
    r = client.post("/api/inventory", json=body)
    assert r.status_code in (200, 201), r.get_json()
    return (r.get_json().get("device") or r.get_json())["id"]


# ── the manifest ──────────────────────────────────────────────────────────────────────────

def test_a_good_discovery_list_gets_defaults():
    m = manifest()
    assert validate(m) == ""
    identity, routes, gateways = m["discovery"]
    assert identity["builtin"] and identity["roles"] == ["firewall"]
    assert identity["name"] == "Model, serial and software"
    assert routes["privacy"] == "device" and routes["platforms"] == ["opnsense"] and routes["minutes"] == 15
    assert not gateways["builtin"] and gateways["privacy"] == "aggregate" and gateways["roles"] == ["firewall"]
    assert "discover" in m["agent"]["calls"]


@pytest.mark.parametrize("change, error", [
    ({"uses": ["settings"], "agent": None}, "add \"agent\" under uses"),
    ({"agent": {}}, "set agent.targets"),
    ({"discovery": []}, "a list of areas"),
    ({"discovery": [{"area": "Bad Name"}]}, "lowercase"),
    ({"discovery": [{"area": "gateways"}]}, "needs a name"),
    ({"discovery": [{"area": "routes"}, {"area": "routes"}]}, "listed twice"),
    ({"discovery": [{"area": "interfaces"}]}, "interfaces come in through monitoring"),
    ({"discovery": [{"area": "routes", "roles": ["switch"]}]}, "the area is about firewall"),
    ({"discovery": [{"area": "routes", "fields": ["x"]}]}, "built-in area has the fields"),
    ({"discovery": [{"area": "routes", "minutes": 1}]}, "minutes: a whole number"),
    ({"discovery": [{"area": "routes", "privacy": "open"}]}, "privacy"),
    ({"discovery": [{"area": "routes", "every": 5}]}, "unknown key"),
])
def test_bad_discovery_lists_are_refused(change, error):
    assert error in validate(manifest(**change))


def test_the_agent_part_answers_only_for_the_devices_asked_and_keeps_addresses_home():
    class Part(AgentPlugin):
        def discover(self, area, devices):
            return {d["id"]: {"gw": "192.0.2.1"} for d in devices} | {"other": {"x": 1}}
    targets = [{"id": "d1", "name": "fw-01"}, {"id": "d2", "name": "fw-02"}]
    part = Part(MemoryContext("x", {"targets": targets}))
    assert part.call_discover({"area": "routes", "devices": ["d1"], "privacy": "device"}) == \
        {"facts": {"d1": {"gw": "192.0.2.1"}}}
    assert part.call_discover({"area": "gw", "devices": ["d1", "d2"], "privacy": "aggregate"}) == {"facts": {}}
    with pytest.raises(PluginError):
        AgentPlugin(MemoryContext("x", {"targets": targets})).call_discover({"area": "a", "devices": ["d1"]})


# ── a run ─────────────────────────────────────────────────────────────────────────────────

def test_areas_are_actions_with_their_own_clock(client, fwthing):
    ids = [a["id"] for a in client.get("/api/inventory/discovery").get_json()["actions"]]
    assert ids[:6] == list(inventory_discovery.ACTION_IDS)
    assert ids[6:] == ["fwthing.identity", "fwthing.routes", "fwthing.gateways"]
    r = client.put("/api/inventory/discovery/actions/fwthing.gateways", json={"minutes": 30})
    gateways = next(a for a in r.get_json()["actions"] if a["id"] == "fwthing.gateways")
    assert gateways["minutes"] == 30 and gateways["custom"] and gateways["plugin"] == "fwthing"
    assert "fwthing.gateways" in inventory_discovery.due_actions(load_data(), 0)


def test_a_run_puts_the_facts_where_the_built_in_areas_put_theirs(client, fwthing):
    part, calls = fwthing
    fw = add(client, name="fw-01", role="firewall", mgmt_ip="192.0.2.1", platform="OPNsense", model="Typed by hand")
    other = add(client, name="fw-02", role="firewall", mgmt_ip="192.0.2.2", platform="pfSense")
    add(client, name="sw-a-01", role="switch", mgmt_ip="192.0.2.10")
    part.answers = {
        "identity": {"model": "DEC850", "serial": "SN0001", "descr": "OPNsense 24.7"},
        "routes": {"routes": [{"network": "0.0.0.0/0", "next_hop": "198.51.100.1", "interface": "wan"}]},
        "gateways": {"name": "WAN_GW", "status": "online", "rtt_ms": 4.2, "secret": "left out"},
    }
    r = client.post("/api/inventory/discovery/run", json={"actions": ["fwthing.identity", "fwthing.routes",
                                                                      "fwthing.gateways"]})
    assert r.status_code == 200, r.get_json()
    report = r.get_json()["report"]
    # Routes only on the OPNsense box; switches never.
    # The store may list devices in any order (Postgres sorts by id), so compare each call as a set.
    assert [set(c[3]["devices"]) for c in calls] == [{fw, other}, {fw}, {fw, other}]
    assert report["areas"]["fwthing.routes"] == {"devices": 1, "changed": 1}
    data = load_data()
    dev = inventory.find(data, fw)
    # Hand values win; an empty field is filled and set by the plugin; a disagreement is drift.
    assert dev["model"] == "Typed by hand" and dev["serial"] == "SN0001"
    view = inventory_properties.view(data, dev)
    assert view["system"]["system.serial"]["set_by"] == "fwthing"
    assert view["system"]["system.model"]["sources"]["fwthing"] == "DEC850"
    assert {"kind": "field", "field": "model", "actual": "DEC850", "source": "fwthing"}.items() <= \
        next(r for r in data["inventory_drift"][fw]).items()
    assert inventory_discovery.discovered_of(data, fw)["routes"][0]["next_hop"] == "198.51.100.1"
    assert inventory_discovery.discovered_of(data, other)["routes"] == []
    assert view["auto"]["auto.gateways.status"] == {"value": "online", "source": "fwthing",
                                                    "seen": view["auto"]["auto.gateways.status"]["seen"]}
    assert view["auto"]["auto.gateways.rtt_ms"]["value"] == 4.2 and "auto.gateways.secret" not in view["auto"]
    runs = data[inventory_discovery.RUNS]
    assert runs["fwthing.gateways"]["devices"] == 2 and "fwthing.identity" in runs


def test_the_monitoring_source_keeps_its_routes_and_drift(client, fwthing):
    part, _calls = fwthing
    fw = add(client, name="fw-01", role="firewall", platform="OPNsense")
    from floorbit.blueprints.inventory import data_lock
    from floorbit.store import save_data
    with data_lock:
        data = load_data()
        data["inventory_discovered"] = {fw: {"routes": [{"network": "10.0.0.0/8", "next_hop": "", "interface": "",
                                                         "proto": "static"}], "at": "x"}}
        save_data(data)
    part.answers = {"routes": {"routes": [{"network": "0.0.0.0/0", "next_hop": "198.51.100.1"}]}}
    client.post("/api/inventory/discovery/run", json={"actions": ["fwthing.routes"]})
    assert [r["network"] for r in inventory_discovery.discovered_of(load_data(), fw)["routes"]] == ["10.0.0.0/8"]


def test_an_aggregate_area_refuses_addresses_and_a_device_run_leaves_the_clock(client, fwthing):
    part, _calls = fwthing
    fw = add(client, name="fw-01", role="firewall")
    part.answers = {"gateways": {"name": "WAN_GW", "address": "198.51.100.1"}}
    # The agent part already leaves it out; the hosted side checks again.
    a = plugin_discovery.area("fwthing.gateways")
    assert plugin_discovery.clean(a, {"name": "fw-01"}, {"address": "198.51.100.1"})[0] is None
    r = client.post("/api/inventory/discovery/run", json={"actions": ["fwthing.gateways"], "device": fw})
    assert r.get_json()["report"]["areas"]["fwthing.gateways"]["devices"] == 0
    assert "fwthing.gateways" not in (load_data().get(inventory_discovery.RUNS) or {})


def test_an_agent_that_cannot_be_asked_is_the_areas_error(client, fwthing, monkeypatch):
    add(client, name="fw-01", role="firewall")

    def down(*_a, **_k):
        raise PluginError("No local agent is connected.")
    monkeypatch.setattr(agent_plugins, "ask", down)
    report = plugin_discovery.run({"fwthing.gateways"})
    assert report["areas"]["fwthing.gateways"]["error"] == "No local agent is connected."
    assert load_data()[inventory_discovery.RUNS]["fwthing.gateways"]["error"]


def test_unknown_actions_are_refused(client, fwthing):
    assert client.post("/api/inventory/discovery/run", json={"actions": ["fwthing.nope"]}).status_code == 400
    assert client.put("/api/inventory/discovery/actions/other.routes", json={"minutes": 5}).status_code == 404
