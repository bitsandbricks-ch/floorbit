"""The attendees' front door as an agent plugin (docs/agent.md, "Attendees through the agent"): the
agent part answers on the event network with the agent's own address and key for Floorbit."""
import importlib.util
import pathlib
import socket
import urllib.error
import urllib.request
from types import SimpleNamespace

from floorbit.plugins.agent import MemoryContext
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


def _ctx(settings):
    ctx = MemoryContext("front-door", settings, {"sends": {}, "fetches": []})
    # Nothing listens on port 9 here: every request it hands on fails, which is all this test needs.
    ctx.host = SimpleNamespace(agent=SimpleNamespace(url="http://127.0.0.1:9", key="fba_test_key"))
    return ctx


def test_off_without_an_address():
    ctx = _ctx({})
    plugin = _plugin(ctx)
    plugin.start()
    assert ctx.health_.report()["status"] == "off" and plugin.check().startswith("off")


def test_it_answers_with_the_agents_link(monkeypatch):
    monkeypatch.delenv("FLOORBIT_AGENT_TLS_CERT", raising=False)
    port = _free_port()
    ctx = _ctx({"address": f"127.0.0.1:{port}", "proxies": ""})
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
        ctx = _ctx({"address": f"127.0.0.1:{taken.getsockname()[1]}"})
        plugin = _plugin(ctx)
        try:
            plugin.start()
            raise AssertionError("started on a taken port")
        except PluginError as exc:
            assert "cannot answer on" in str(exc)
