"""Switch logins (SSH shell, port actions) go to a group's VRRP primary, and every method the hosted
side asks the agent for is one the tunnel lets through."""
import pytest

from floorbit import agent_link


def _agent(aid, vrrp=None):
    return {"id": aid, "name": aid.upper(), "connected": True, "tags": [],
            "report": {"vrrp": vrrp} if vrrp is not None else {}}


@pytest.fixture
def two_agents(monkeypatch):
    def use(agents):
        ids = {a["id"] for a in agents}
        monkeypatch.setattr(agent_link, "_routing", lambda: ({}, sorted(ids), {}))
        monkeypatch.setattr(agent_link, "_pinned_agent", lambda *a: None)
        monkeypatch.setattr(agent_link.tunnel, "connected_agents", lambda now=None: set(ids))
        monkeypatch.setattr(agent_link, "all_agents", lambda now=None: agents)
    return use


def test_a_switch_login_goes_to_the_primary_not_the_smallest_id(two_agents):
    two_agents([_agent("a", vrrp={"primary": False, "holds": []}),
                _agent("b", vrrp={"primary": True, "holds": ["192.0.2.10/24"]})])
    assert agent_link.agent_for("sw-1") == "b"


def test_without_vrrp_the_smallest_id_keeps_the_switch(two_agents):
    two_agents([_agent("b"), _agent("a")])
    assert agent_link.agent_for("sw-1") == "a"


def test_the_primary_away_its_standby_takes_the_login(two_agents):
    two_agents([_agent("a", vrrp={"primary": False, "holds": []})])
    assert agent_link.agent_for("sw-1") == "a"


@pytest.mark.parametrize("method", ["check_probe", "firewall_feeds"])
def test_methods_the_hosted_side_asks_for_are_let_through(method):
    # Services' own checks (services.py) and the firewall range import (firewalls.py) ask these.
    with pytest.raises(agent_link.AgentUnavailable):
        agent_link.tunnel.call_here(method, [], timeout=0.01)
