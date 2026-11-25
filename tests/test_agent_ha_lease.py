"""Floorbit picks each group's primary (issue #1405): a sticky lease, VRRP optional."""
from test_agent import clean_tunnel, enrol, head  # noqa: F401  # clean_tunnel is autouse there

from floorbit import agent_ha, agent_link


def agent(aid, connected=True, tags=(), lease=None, vrrp=None):
    report = {**({"lease": lease} if lease is not None else {}), **({"vrrp": vrrp} if vrrp else {})}
    return {"id": aid, "name": aid.upper(), "connected": connected, "tags": list(tags), "report": report}


def test_the_smallest_connected_id_gets_the_lease_without_vrrp():
    assert agent_ha.lease_holder([agent("b"), agent("a")]) == "a"
    assert agent_ha.lease_holder([agent("b"), agent("a", connected=False)]) == "b"
    assert agent_ha.lease_holder([agent("a", connected=False)]) is None


def test_the_holder_keeps_it_while_connected():
    assert agent_ha.lease_holder([agent("a", lease=False), agent("b", lease=True)]) == "b"
    # Two say so for a moment (a handover in flight): the smallest id.
    assert agent_ha.lease_holder([agent("c", lease=True), agent("b", lease=True)]) == "b"


def test_a_vrrp_primary_gets_the_lease_when_nobody_holds_it():
    assert agent_ha.lease_holder([agent("a", vrrp={"primary": False}), agent("b", vrrp={"primary": True})]) == "b"


def test_each_group_has_its_own_lease():
    agents = [agent("a", tags=["h1"]), agent("b", tags=["h1"]), agent("c", tags=["h2"])]
    assert agent_ha.lease_for("a", agents) == {"primary": True, "members": 2}
    assert agent_ha.lease_for("b", agents) == {"primary": False, "members": 2}
    assert agent_ha.lease_for("c", agents) == {"primary": True, "members": 1}
    assert agent_ha.lease_for("nope", agents) is None


def test_the_page_shows_the_lease_holder_as_primary_without_vrrp():
    group = agent_ha.groups([agent("a", lease=False), agent("b", lease=True)])[0]
    assert (group["state"], group["primary"]) == ("ok", "b")
    assert [a["role"] for a in group["agents"]] == ["standby", "primary"]


def test_switch_logins_follow_the_lease(monkeypatch):
    agents = [agent("a", lease=False), agent("b", lease=True)]
    monkeypatch.setattr(agent_link, "_routing", lambda: ({}, ["a", "b"], {}))
    monkeypatch.setattr(agent_link, "_pinned_agent", lambda *a: None)
    monkeypatch.setattr(agent_link.tunnel, "connected_agents", lambda now=None: {"a", "b"})
    monkeypatch.setattr(agent_link, "all_agents", lambda now=None: agents)
    assert agent_link.agent_for("sw-1") == "b"


def test_a_primary_that_leaves_hands_the_lease_on_at_once(client, anon_client, monkeypatch):
    from floorbit import agent_plugins
    reloads = []
    monkeypatch.setattr(agent_plugins, "reload_agents", lambda: reloads.append(1))
    first, second = enrol(client, "Agent one"), enrol(client, "Agent two")
    low, high = sorted([first, second], key=lambda a: a["id"])
    for made in (low, high):
        agent_link.tunnel.seen(agent=made["id"])
        assert anon_client.post("/api/agent/v1/report", json={"report": {"lease": made is low}},
                                headers=head(made["key"])).status_code == 200
    cfg = anon_client.get("/api/agent/v1/plugins", headers=head(high["key"])).get_json()
    assert cfg["ha"]["lease"] == {"primary": False, "members": 2}
    agent_link.tunnel.linked(low["id"])
    reloads.clear()
    agent_link.tunnel.unlinked(low["id"])
    assert reloads, "the standby must hear it now, not at its next pull"
    cfg = anon_client.get("/api/agent/v1/plugins", headers=head(high["key"])).get_json()
    assert cfg["ha"]["lease"] == {"primary": True, "members": 2}
    # Back again, its old report must not win the lease back.
    agent_link.tunnel.seen(agent=low["id"])
    back = anon_client.get("/api/agent/v1/plugins", headers=head(low["key"])).get_json()
    assert back["ha"]["lease"]["primary"] is False


def test_agents_of_a_group_share_their_certificate_names(client):
    from floorbit import agent_settings
    a, b = enrol(client, "A"), enrol(client, "B")
    agent_settings.update(a["id"], settings={"cert_names": ["agents.example.com", "192.0.2.10"]})
    agent_settings.update(b["id"], settings={"cert_names": ["agent-b.example.com"]})
    assert agent_settings.agent_block(b["id"])["cert"]["names"] == [
        "agent-b.example.com", "agents.example.com", "192.0.2.10"]
    assert agent_settings.agent_block(a["id"])["cert"]["names"] == [
        "agents.example.com", "192.0.2.10", "agent-b.example.com"]


def test_the_lease_goes_to_an_agent_that_runs_every_plugin():
    # agent-b has telemetry turned off: as primary it would leave the group's devices unpolled.
    b = {**agent("b", lease=True), "plugins_off": ["telemetry"]}
    assert agent_ha.lease_holder([agent("a"), b]) == "a"
    assert agent_ha.lease_holder([{**agent("a", connected=False)}, b]) == "b"
    assert agent_ha.lease_holder([{**agent("a"), "plugins_off": ["x"]}, b]) == "b"


def test_a_restart_waits_a_minute_for_the_last_holder(monkeypatch):
    # agent-b held the lease before this Floorbit restarted, which forgot every report.
    assert agent_ha.lease_holder([agent("a"), agent("b", lease=True)]) == "b"

    def restart():
        monkeypatch.setattr(agent_ha, "_started", agent_ha.time.monotonic())
        agent_ha._back.clear()
    restart()
    # agent-a reconnects first: it must not take the lease while agent-b may still come back.
    assert agent_ha.lease_holder([agent("a"), agent("b", connected=False)]) is None
    # agent-b is back and hasn't reported yet: it keeps the lease.
    assert agent_ha.lease_holder([agent("a"), agent("b")]) == "b"
    # It was back once: when it leaves again, agent-a takes over at once.
    assert agent_ha.lease_holder([agent("a"), agent("b", connected=False)]) == "a"
    # agent-b holds it again; then a restart, and agent-b never comes back: a minute on, agent-a.
    assert agent_ha.lease_holder([agent("a"), agent("b", lease=True)]) == "b"
    restart()
    assert agent_ha.lease_holder([agent("a"), agent("b", connected=False)]) is None
    monkeypatch.setattr(agent_ha, "_started", -10 * agent_ha.STARTUP_GRACE)
    assert agent_ha.lease_holder([agent("a"), agent("b", connected=False)]) == "a"


def test_the_last_holder_is_kept_in_the_data(client, monkeypatch):
    monkeypatch.undo()      # the real store, not the fixture's dict
    agent_ha._remember("h1|h2", "b")
    assert agent_ha._remembered("h1|h2") == "b"
    agent_ha._remember("h1|h2", "a")
    assert agent_ha._remembered("h1|h2") == "a"


def test_after_a_restart_the_page_shows_the_remembered_holder(monkeypatch):
    # No agent has reported since the restart: the group still counts as one that takes leases.
    agent_ha._remember("", "b")
    monkeypatch.setattr(agent_ha, "_started", agent_ha.time.monotonic())
    plain = [{"id": i, "name": i, "connected": True, "tags": [], "report": None} for i in ("a", "b")]
    (group,) = agent_ha.groups(plain)
    assert group["primary"] == "b"
    assert [a["role"] for a in group["agents"]] == ["standby", "primary"]
