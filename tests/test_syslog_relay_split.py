"""Syslog in a group that splits its devices (#1441): only a device's owner sends its lines."""
import importlib.util
import pathlib

from floorbit.plugins.agent import MemoryContext

BLOCK = {"sends": {"lines": {"privacy": "device"}}}


def _agent_part(ctx):
    path = pathlib.Path(__file__).parent.parent / "floorbit" / "builtin_plugins" / "syslog-relay" / "agent.py"
    spec = importlib.util.spec_from_file_location("syslog_relay_agent_split", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.AgentPlugin(ctx)


class FakeRelay:
    def __init__(self, send, port, bind, log=None, keep=None):
        self.port, self.keep, self.lines, self.held, self.taken = port, keep, [], [], []
        self.received = 0

    def start(self):
        return self.port

    def stop(self):
        pass

    def take_over(self, keep):
        self.keep = keep
        self.taken.append(keep)
        return 0


class OldRelay:
    """The agent's Relay before the split: no ``keep``, no ``take_over``."""
    keep = None

    def __init__(self, send, port, bind, log=None):
        self.port, self.lines, self.received = port, [], 0

    def start(self):
        return self.port

    def stop(self):
        pass


def _started(monkeypatch, relay, settings):
    from floorbit_agent import syslog_relay
    monkeypatch.setattr(syslog_relay, "Relay", relay)
    ctx = MemoryContext("syslog-relay", settings, BLOCK)
    plugin = _agent_part(ctx)
    plugin.start()
    return plugin, ctx


def test_lines_of_another_agents_device_are_held(monkeypatch):
    plugin, _ctx = _started(monkeypatch, FakeRelay, {"port": 5514, "others": ["192.0.2.12", "sw-theirs"]})
    assert plugin.relay.keep("192.0.2.11") and not plugin.relay.keep("192.0.2.12")


def test_new_owners_keep_the_relay_running_and_take_over(monkeypatch):
    plugin, _ctx = _started(monkeypatch, FakeRelay, {"port": 5514, "others": ["192.0.2.12"]})
    relay = plugin.relay
    assert plugin.configure({"port": 5514, "others": []}) is True
    assert plugin.relay is relay and relay.keep("192.0.2.12")
    assert plugin.configure({"port": 5515}) is False  # a new port: the host restarts the plugin


def test_an_agent_from_before_the_split_sends_every_line(monkeypatch):
    plugin, _ctx = _started(monkeypatch, OldRelay, {"port": 5514, "others": ["192.0.2.12"]})
    assert plugin.relay.keep is None
    assert plugin.configure({"port": 5514, "others": []}) is False


def test_the_hosted_part_names_the_devices_another_agent_owns(monkeypatch):
    from floorbit import agent_link
    from floorbit.telemetry import targets
    spec = importlib.util.spec_from_file_location(
        "syslog_relay_hosted_split",
        pathlib.Path(__file__).parent.parent / "floorbit" / "builtin_plugins" / "syslog-relay" / "plugin.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(agent_link.tunnel, "connected_agents", lambda now=None: {"a", "b"})
    monkeypatch.setattr(targets, "listing", lambda: [])
    monkeypatch.setattr(targets, "for_agent", lambda devices, agent, connected: [
        {"name": "sw-mine", "address": "192.0.2.11", "split": True, "mine": True},
        {"name": "sw-theirs", "address": "192.0.2.12", "split": True, "mine": False},
        {"name": "sw-alone", "address": "192.0.2.13"},
    ])
    plugin = module.Plugin.__new__(module.Plugin)
    got = plugin.agent_settings({"port": 5514}, agent_id="a")
    assert got == {"port": 5514, "others": ["192.0.2.12", "sw-theirs"]}
    assert plugin.agent_settings({"port": 5514}) == {"port": 5514}
