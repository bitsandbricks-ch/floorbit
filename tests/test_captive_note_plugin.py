"""The check-in note as an agent plugin: the agent part answers RFC 8908 from what the hosted
part says, says nothing when check-in is off there, and keeps the last word when it is away."""
import importlib.util
import json
import pathlib
import socket
import urllib.request

from test_agent import enrol, head

from floorbit.plugins.agent import HostedSaidNo, MemoryContext
from floorbit.plugins.base import PluginError

BLOCK = {"sends": {}, "fetches": ["state"]}


def _plugin(ctx):
    path = pathlib.Path(__file__).parent.parent / "floorbit" / "builtin_plugins" / "captive-note" / "agent.py"
    spec = importlib.util.spec_from_file_location("captive_note_agent", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.AgentPlugin(ctx)


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_off_without_an_address():
    ctx = MemoryContext("captive-note", {}, BLOCK)
    plugin = _plugin(ctx)
    plugin.start()
    assert ctx.health_.report()["status"] == "off"


def test_it_answers_from_the_hosted_part():
    port = _free_port()
    ctx = MemoryContext("captive-note", {"address": f"127.0.0.1:{port}"}, BLOCK)
    ctx.fetched["state"] = {"done": ["192.0.2.99"], "portal_url": "https://floor.example.com/checkin"}
    plugin = _plugin(ctx)
    plugin.start()
    try:
        plugin.api.refresh()
        url = f"http://127.0.0.1:{port}/.well-known/captive-portal"
        body = json.loads(urllib.request.urlopen(url, timeout=5).read())
        assert body == {"captive": True, "user-portal-url": "https://floor.example.com/checkin"}
        ctx.fetched["state"] = PluginError("cannot reach the hosted Floorbit")     # away: keep the last word
        plugin.api.refresh()
        assert plugin.api.loaded and plugin.api.answer("127.0.0.1")["captive"] is True
        ctx.fetched["state"] = HostedSaidNo("Check-in is turned off on this Floorbit.")   # off: say nothing
        plugin.api.refresh()
        assert plugin.api.answer("127.0.0.1") == {"captive": False}
    finally:
        ctx.close()


def test_the_hosted_part_says_no_while_check_in_is_off(client, anon_client, monkeypatch):
    key = enrol(client)["key"]
    client.put("/api/settings/plugins/captive-note", json={"enabled": True})
    try:
        monkeypatch.setenv("CHECKIN_ENABLED", "false")
        res = anon_client.get("/api/agent/v1/plugins/captive-note/state", headers=head(key))
        assert res.status_code == 409 and "Check-in is turned off" in res.get_json()["error"]
    finally:
        client.put("/api/settings/plugins/captive-note", json={"enabled": False})
