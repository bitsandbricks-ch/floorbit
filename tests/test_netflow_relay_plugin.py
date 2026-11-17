"""Traffic from the hall as an agent plugin: the agent part asks the hosted part for the seats
and sends its summary as the newest-only kind."""
import importlib.util
import pathlib

from floorbit.plugins.agent import MemoryContext

BLOCK = {"sends": {"summary": {"privacy": "device", "latest": True}}, "fetches": ["seats"]}


def _module():
    path = pathlib.Path(__file__).parent.parent / "floorbit" / "builtin_plugins" / "netflow-relay" / "agent.py"
    spec = importlib.util.spec_from_file_location("netflow_relay_agent", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_off_without_a_port():
    ctx = MemoryContext("netflow-relay", {"port": 0}, BLOCK)
    plugin = _module().AgentPlugin(ctx)
    plugin.start()
    assert ctx.health_.report()["status"] == "off" and plugin.check().startswith("off")


def test_the_collector_gets_seats_and_sends_summaries_through_the_plugin():
    from floorbit_agent.flows_relay import FlowsRelay
    ctx = MemoryContext("netflow-relay", {}, BLOCK)
    ctx.fetched["seats"] = {"seat_of": {"192.0.2.10": "A1"}, "area_of": {"A1": "Hall A"}}
    relay = FlowsRelay(_module()._Link(ctx), 0)
    assert relay.seats() == ({"192.0.2.10": "A1"}, {"A1": "Hall A"})
    assert relay._publish({"updated": 1, "flows": 3}) is True
    assert ctx.sent == [("summary", {"updated": 1, "flows": 3})]
