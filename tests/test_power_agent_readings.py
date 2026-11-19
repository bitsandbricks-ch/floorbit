"""Readings the agent's power plugins send (docs/power.md). The plugins themselves (Shelly, Home
Assistant) live in their own repositories and are tested there; here the core keeps what they hand
it for Electrics."""
import time

from floorbit import power


def test_readings_are_kept_per_plugin_and_go_stale():
    assert power.keep_agent_readings("meter-test", [{"meter": "db1-1", "watts": 2300},
                                                    {"meter": "bad meter!", "watts": 5}]) == 1
    assert power.agent_readings("meter-test") == [{"meter": "db1-1", "watts": 2300}]
    assert power.agent_readings("meter-test", now=time.time() + power.AGENT_READING_AGE + 1) == []


def test_odd_agent_readings_keep_only_numbers():
    kept = power.keep_agent_readings("odd-test", [
        {"meter": "db1-1", "amps": 1, "watts": "5"},           # text is left out
        {"meter": "db1-2", "watts": 10 ** 400},                # used to raise OverflowError
        {"meter": "db1-3", "amps": 2, "watts": [1]},
        {"meter": "db1-4", "watts": 230}])
    assert kept == 3
    assert power.agent_readings("odd-test") == [{"meter": "db1-1", "amps": 1}, {"meter": "db1-3", "amps": 2},
                                                {"meter": "db1-4", "watts": 230}]
