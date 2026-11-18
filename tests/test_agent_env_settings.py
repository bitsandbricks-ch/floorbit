"""Plugin settings an agent's environment held, taken over once by Floorbit (agent_plugins.import_env),
the agent's environment no longer read for them (SettingsStore.ignore_env), and the plugins the
agent next to a self-hosted Floorbit gets turned on (local_defaults). docs/agent.md, "Settings come
from Floorbit"."""
from test_agent import enrol, head

from floorbit import agent_plugins, audit, sources
from floorbit.settings import SettingsStore

URL = "/api/agent/v1/env-settings"


def test_an_agents_environment_sets_up_what_nobody_set_up_here(client, anon_client):
    key = enrol(client)["key"]
    body = {"settings": {"plugin.pihole.url": "https://pihole.example.com", "plugin.pihole.password": "t0ken",
                         "plugin.syslog-relay.port": 5514, "no.such.key": "x"},
            "plugins": ["http-check"]}
    got = anon_client.post(URL, json=body, headers=head(key)).get_json()
    assert got == {"imported": ["http-check", "pihole", "syslog-relay"], "skipped": {}}
    registry = sources.registry
    store = registry.settings_store
    assert store.get("plugin.pihole.url") == "https://pihole.example.com"
    assert store.get("plugin.pihole.password") == "t0ken"
    assert store.get("plugin.syslog-relay.port") == 5514
    assert all(registry.enabled(registry.specs[p]) for p in ("pihole", "syslog-relay", "http-check"))
    rows = [r for r in audit.read(area="plugins")[0] if r["action"] == "Took over plugin settings from an agent"]
    assert {r["target"] for r in rows} == {"pihole", "syslog-relay", "http-check"}
    assert all(r["user"] == "agent Demo LAN 2026" for r in rows)
    assert "t0ken" not in str(rows)                     # names only, never values

    # Sent again (a restart): what is set up here now stays as it is.
    body["settings"]["plugin.syslog-relay.port"] = 9999
    again = anon_client.post(URL, json=body, headers=head(key)).get_json()
    assert again["imported"] == [] and set(again["skipped"]) == {"http-check", "pihole", "syslog-relay"}
    assert store.get("plugin.syslog-relay.port") == 5514


def test_only_plugins_that_work_on_an_agent_and_only_with_a_key(client, anon_client):
    key = enrol(client)["key"]
    assert anon_client.post(URL, json={"plugins": ["http-check"]}).status_code == 401
    got = anon_client.post(URL, json={"plugins": ["demo", "nope", "../x"]}, headers=head(key)).get_json()
    assert got["imported"] == []
    assert got["skipped"] == {"demo": "not a plugin for the agent", "nope": "unknown here", "../x": "unknown here"}
    assert not sources.registry.enabled(sources.registry.specs["demo"])


def test_a_plugin_turned_on_here_keeps_its_own_settings(client, anon_client):
    key = enrol(client)["key"]
    client.put("/api/settings/plugins/netflow-relay", json={"enabled": True})
    got = anon_client.post(URL, json={"settings": {"plugin.netflow-relay.port": 2055}}, headers=head(key)).get_json()
    assert got == {"imported": [], "skipped": {"netflow-relay": "already set up here"}}
    assert sources.registry.settings_store.get("plugin.netflow-relay.port") == 0


def test_on_the_agent_its_environment_no_longer_sets_plugins(tmp_path):
    env = {"LIBRENMS_URL": "https://old.example.com", "TZ": "UTC"}
    store = SettingsStore(str(tmp_path / "data.json"), environ=env)
    assert store.get("librenms.url") == "https://old.example.com"
    store.ignore_env({"librenms.url"})
    store.set_remote({"librenms.url": "https://librenms.example.com"})
    assert store.get("librenms.url") == "https://librenms.example.com" and store.source("librenms.url") == "hosted"
    store.set_remote({})
    assert store.get("librenms.url") == "" and store.source("librenms.url") == "default"


def test_the_local_agent_gets_syslog_flows_and_the_front_door_once(client):
    registry = sources.registry
    assert agent_plugins.local_defaults(registry) == ["syslog-relay", "netflow-relay", "front-door"]
    store = registry.settings_store
    assert store.get("plugin.syslog-relay.port") == 5514 and store.get("plugin.netflow-relay.port") == 2055
    assert store.get("plugin.front-door.address") == "0.0.0.0:8443"
    client.put("/api/settings/plugins/front-door", json={"enabled": False})
    assert agent_plugins.local_defaults(registry) == []       # once: turned off stays off
    assert not registry.enabled(registry.specs["front-door"])
