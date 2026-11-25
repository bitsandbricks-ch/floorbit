"""What an agent can do (its ``capabilities`` list), and the fallback for one from before the list."""
from floorbit import agent_ha
from floorbit.agent_link import tunnel

SPLIT = {"plugins": {"telemetry": {"metrics": {"split": 1}}}}


def test_an_agent_lists_what_it_can_do():
    report = {"capabilities": ["lease", "split", "syslog_hold", "something_new"], "lease": False, **SPLIT}
    assert agent_ha.capabilities(report) == ["lease", "split", "syslog_hold"]


def test_an_older_agent_is_worked_out_from_its_report():
    assert agent_ha.capabilities({"lease": True, **SPLIT}) == ["lease", "split"]
    assert agent_ha.capabilities({}) == [] and agent_ha.capabilities(None) == []


def test_split_needs_the_telemetry_plugin_too():
    # A new agent host on a telemetry plugin that polls everything: no split, the primary does it all.
    assert not agent_ha.can({"capabilities": ["lease", "split"]}, "split")
    # The plugin follows, but the agent says it can't (an agent that turned it off): no split either.
    assert not agent_ha.can({"capabilities": ["lease"], **SPLIT}, "split")


def test_the_report_keeps_a_clean_list(app_module):
    tunnel.report("cap-1", {"capabilities": ["lease", "Bad Name", 3, "x" * 40, "split"]})
    assert tunnel.reported("cap-1")["capabilities"] == ["lease", "split"]
    tunnel.report("cap-2", {"capabilities": "lease"})
    assert "capabilities" not in tunnel.reported("cap-2")
