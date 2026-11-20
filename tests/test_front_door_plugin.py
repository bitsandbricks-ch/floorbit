"""The attendees' front door as an agent plugin (docs/agent.md, "Attendees through the agent"): the
agent part answers on the event network with the agent's own address and key for Floorbit, on one
port for everything attendees and the crew open there: check-in, the check-in note on phones and the
seat walk-through's hello."""
import importlib.util
import json
import pathlib
import socket
import urllib.error
import urllib.request
from types import SimpleNamespace

from test_agent import enrol, head

from floorbit.plugins.agent import HostedSaidNo, MemoryContext
from floorbit.plugins.base import PluginError


def _plugin(ctx):
    path = pathlib.Path(__file__).parent.parent / "floorbit" / "builtin_plugins" / "front-door" / "agent.py"
    spec = importlib.util.spec_from_file_location("front_door_agent", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.AgentPlugin(ctx)


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _ctx(settings, said=None):
    ctx = MemoryContext("front-door", settings, {"sends": {}, "fetches": ["state"]})
    # Nothing listens on port 9 here: every request it hands on fails, which is all this test needs.
    ctx.host = SimpleNamespace(env={}, agent=SimpleNamespace(
        url="http://127.0.0.1:9", key="fba_test_key",
        seat_walk_hello=lambda code, ip: (said if said is not None else []).append((code, ip))))
    return ctx


def test_on_by_default_on_two_ports(client):
    registry = client.application.extensions["floorbit_plugins"]
    spec = registry.specs["front-door"]
    assert registry.enabled(spec) and "captive-note" not in registry.specs
    store = registry.settings_store
    assert store.get("plugin.front-door.address") == "0.0.0.0:8443"
    assert store.get("plugin.front-door.http_address") == "0.0.0.0:8080"


def test_off_without_an_address():
    ctx = _ctx({"address": "", "http_address": ""})
    plugin = _plugin(ctx)
    plugin.start()
    assert ctx.health_.report()["status"] == "off" and plugin.check().startswith("off")


def test_it_answers_with_the_agents_link(monkeypatch):
    monkeypatch.delenv("FLOORBIT_AGENT_TLS_CERT", raising=False)
    port = _free_port()
    ctx = _ctx({"address": f"127.0.0.1:{port}", "http_address": "", "proxies": ""})
    plugin = _plugin(ctx)
    plugin.start()
    try:
        assert ctx.health_.report()["status"] == "ok" and f"http://127.0.0.1:{port}" in ctx.health_.report()["message"]
        assert plugin.door.url == "http://127.0.0.1:9" and plugin.door.key == "fba_test_key"
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/checkin", timeout=10)
        except urllib.error.HTTPError as exc:
            assert exc.code >= 500                        # Floorbit away: said so, not hung
        assert sum(plugin.door.counts.values()) == 1 and "1 requests so far" in plugin.check()
    finally:
        ctx.close()


def test_a_taken_port_is_an_error():
    with socket.socket() as taken:
        taken.bind(("127.0.0.1", 0))
        taken.listen()
        ctx = _ctx({"address": f"127.0.0.1:{taken.getsockname()[1]}", "http_address": ""})
        plugin = _plugin(ctx)
        try:
            plugin.start()
            raise AssertionError("started on a taken port")
        except PluginError as exc:
            assert "cannot answer on" in str(exc)


def test_the_check_in_note_and_the_hello_answer_on_the_same_port():
    said = []
    port = _free_port()
    ctx = _ctx({"address": f"127.0.0.1:{port}", "http_address": "", "phone_note": True}, said)
    ctx.fetched["state"] = {"done": ["192.0.2.99"], "portal_url": "https://floor.example.com/checkin"}
    plugin = _plugin(ctx)
    plugin.start()
    try:
        plugin.api.refresh()
        body = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}/.well-known/captive-portal",
                                                 timeout=5).read())
        assert body == {"captive": True, "user-portal-url": "https://floor.example.com/checkin"}
        ctx.fetched["state"] = PluginError("cannot reach the hosted Floorbit")     # away: keep the last word
        plugin.api.refresh()
        assert plugin.api.answer("127.0.0.1")["captive"] is True
        ctx.fetched["state"] = HostedSaidNo("Check-in is turned off on this Floorbit.")   # off: say nothing
        plugin.api.refresh()
        assert plugin.api.answer("127.0.0.1") == {"captive": False}
        page = urllib.request.urlopen(f"http://127.0.0.1:{port}/floorbit/hello/abcdefghijklmnop1234", timeout=5)
        assert page.status == 200 and said == [("abcdefghijklmnop1234", "127.0.0.1")]
    finally:
        ctx.close()


def test_the_hosted_part_says_no_while_check_in_is_off(client, anon_client, monkeypatch):
    key = enrol(client)["key"]
    monkeypatch.setenv("CHECKIN_ENABLED", "false")
    res = anon_client.get("/api/agent/v1/plugins/front-door/state", headers=head(key))
    assert res.status_code == 409 and "Check-in is turned off" in res.get_json()["error"]
