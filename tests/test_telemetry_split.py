"""Two or more agents of one group split the devices nobody was given (issue #1441)."""
import time

import pytest

from floorbit import agent_ha
from floorbit.telemetry import targets, telegraf

DEVICES = [{"name": f"sw-{i:03}", "agent": "", "address": f"192.0.2.{i}", "drivers": ["snmp"]} for i in range(1, 201)]
TAGS = {"a": {"hall-1"}, "b": {"hall-1"}, "c": {"hall-1"}, "x": {"hall-2"}}


def test_an_agent_floorbit_no_longer_knows_owns_nothing():
    assert agent_ha.split_members("a", {"a", "gone"}, {"a": set()}) == ["a"]


SPLITS = {"plugins": {"telemetry": {"metrics": {"split": 1}}}}
REPORTS = dict.fromkeys("abcx", SPLITS)


def given(agent, connected, reports=REPORTS):
    return targets.for_agent(DEVICES, agent, connected, TAGS, reports)


def owned(agent, connected, reports=REPORTS):
    return {t["name"] for t in given(agent, connected, reports) if t.get("mine")}


def test_every_device_has_exactly_one_owner_in_the_group():
    a, b = owned("a", {"a", "b"}), owned("b", {"a", "b"})
    assert not a & b and len(a | b) == len(DEVICES)
    assert 70 < len(a) < 130        # roughly half each


def test_only_the_leaving_agents_devices_move():
    before = {g: owned(g, {"a", "b", "c"}) for g in "abc"}
    after = {g: owned(g, {"a", "b"}) for g in "ab"}
    assert before["a"] <= after["a"] and before["b"] <= after["b"]
    assert after["a"] | after["b"] == {t["name"] for t in DEVICES}


def test_another_groups_agent_doesnt_count():
    assert owned("x", {"a", "x"}) == set()          # x is alone in hall-2: nothing split, nothing "mine"
    got = given("x", {"a", "x"})
    assert len(got) == len(DEVICES) and not any(t.get("split") for t in got)


def test_a_primary_polls_only_its_own_share_when_split():
    got = given("a", {"a", "b"})
    conf = telegraf.render(got, "http://agent:8186/write", "t", poll=True)
    mine = [t for t in got if t["mine"]]
    theirs = [t for t in got if not t["mine"]]
    assert all(f'{t["address"]}:161' in conf for t in mine)
    assert not any(f'"udp://{t["address"]}:161"' in conf for t in theirs)


def test_alone_the_primary_polls_everything_as_before():
    got = given("a", {"a"})
    assert all(telegraf.collects(t, True) for t in got)
    assert not any(telegraf.collects(t, False) for t in got)


def test_the_owner_is_the_same_everywhere():
    assert agent_ha.split_owner("SW-001", ["b", "a"]) == agent_ha.split_owner("sw-001", ["a", "b"])
    assert agent_ha.split_owner("sw-001", []) is None


def test_no_split_while_one_agent_of_the_group_is_too_old_to_follow_it():
    got = given("a", {"a", "b"}, {"a": SPLITS, "b": {"plugins": {"telemetry": {"metrics": {}}}}})
    assert not any(t.get("split") for t in got)
    assert all(telegraf.collects(t, True) for t in got)      # the primary polls everything, as before


def test_switch_logins_go_to_the_devices_owner(monkeypatch):
    from floorbit import agent_link
    agents = [{"id": "a", "name": "A", "connected": True, "tags": ["hall-1"], "report": {"lease": True}},
              {"id": "b", "name": "B", "connected": True, "tags": ["hall-1"], "report": {"lease": False}}]
    monkeypatch.setattr(agent_link, "_routing", lambda: ({}, ["a", "b"], {}))
    monkeypatch.setattr(agent_link, "_pinned_agent", lambda *a: None)
    monkeypatch.setattr(agent_link.tunnel, "connected_agents", lambda now=None: {"a", "b"})
    monkeypatch.setattr(agent_link, "all_agents", lambda now=None: agents)
    monkeypatch.setattr(agent_link.tunnel, "reported", lambda agent, now=None: SPLITS)
    owners = {f"sw-{i}": agent_link.agent_for(f"sw-{i}") for i in range(40)}
    assert set(owners.values()) == {"a", "b"}                  # both log in, each to its own switches
    assert all(agent_ha.split_owner(n, ["a", "b"]) == o for n, o in owners.items())
    # One of them too old to follow: the primary keeps every login, as before.
    monkeypatch.setattr(agent_link.tunnel, "reported", lambda agent, now=None: SPLITS if agent == "a" else {})
    assert {agent_link.agent_for(f"sw-{i}") for i in range(40)} == {"a"}


def test_the_lease_names_the_split_so_the_agent_knows_its_devices():
    agents = [{"id": "a", "connected": True, "tags": ["hall-1"], "report": {"lease": True, **SPLITS}},
              {"id": "b", "connected": True, "tags": ["hall-1"], "report": {"lease": False, **SPLITS}}]
    assert agent_ha.lease_for("b", agents) == {"primary": False, "members": 2, "split": ["a", "b"], "me": "b"}
    agents[1]["report"] = {"lease": False}           # b too old: no split
    assert agent_ha.lease_for("a", agents) == {"primary": True, "members": 2}


# ── the agent part: traps and streams of another agent's devices ────────────────────────────────

def _agent(tmp_path, monkeypatch, targets):
    import importlib

    from test_telemetry_problems import AgentCtx

    from floorbit.telemetry import supervisor
    agent = importlib.import_module("floorbit.builtin_plugins.telemetry.agent")
    monkeypatch.setattr(supervisor, "binary", lambda: None)
    ctx = AgentCtx("telemetry", {"targets": targets}, {}, state_dir=str(tmp_path))
    plugin = agent.AgentPlugin(ctx)
    plugin.start()
    return plugin, ctx


@pytest.fixture
def started(tmp_path, monkeypatch):
    from floorbit.telemetry import state
    state.state.reset()
    made = []

    def make(targets):
        made.append(_agent(tmp_path, monkeypatch, targets))
        return made[-1]
    yield make
    for plugin, ctx in made:
        ctx.stopping.set()
        plugin.stop()
    state.state.reset()
    state.state.problems = None


MINE = {"name": "sw-mine", "address": "192.0.2.11", "drivers": ["traps"], "mine": True, "split": True}
THEIRS = {"name": "sw-theirs", "address": "192.0.2.12", "drivers": ["traps"], "mine": False, "split": True}
TRAP = 'snmp_trap,source={src},driver=traps,name=linkDown ifIndex=3i {ns}'


def test_the_owner_handles_a_trap_the_other_keeps_it_a_minute(started):
    plugin, _ctx = started([MINE, THEIRS])
    now = time.time()
    ns = int(now * 1e9)
    plugin.take(TRAP.format(src="192.0.2.11", ns=ns), now)
    plugin.take(TRAP.format(src="192.0.2.12", ns=ns), now)
    assert "sw-mine" in plugin.state.devices and plugin.state.devices["sw-mine"].seen
    assert not getattr(plugin.state.devices.get("sw-theirs"), "seen", 0)
    assert [name for _at, name, _p in plugin.held] == ["sw-theirs"]
    # The other agent went: Floorbit makes sw-theirs this agent's own, and the last minute counts.
    plugin.configure({"targets": [MINE, {**THEIRS, "mine": True}]})
    assert plugin.state.devices["sw-theirs"].seen and not plugin.held


def test_held_points_expire_after_a_minute(started):
    from floorbit.builtin_plugins.telemetry import agent
    plugin, _ctx = started([MINE, THEIRS])
    old = time.time() - agent.HOLD_OTHERS - 5
    plugin.take(TRAP.format(src="192.0.2.12", ns=int(old * 1e9)), old)
    plugin.take(TRAP.format(src="192.0.2.11", ns=int(time.time() * 1e9)), time.time())
    assert not plugin.held
    plugin.configure({"targets": [MINE, {**THEIRS, "mine": True}]})
    assert not getattr(plugin.state.devices.get("sw-theirs"), "seen", 0)


def test_without_a_split_everything_is_taken_as_before(started):
    plugin, _ctx = started([{**THEIRS, "split": False, "mine": False}])
    now = time.time()
    plugin.take(TRAP.format(src="192.0.2.12", ns=int(now * 1e9)), now)
    assert plugin.state.devices["sw-theirs"].seen and not plugin.held


def test_the_agent_says_it_follows_the_split_only_when_its_host_does(started):
    plugin, ctx = started([MINE])
    plugin.report(time.time())
    assert "split" not in ctx.health_.gauges  # an older agent host: Floorbit keeps the primary doing it all
    ctx.owns = lambda device: True
    plugin.report(time.time())
    assert ctx.health_.gauges["split"] == 1
