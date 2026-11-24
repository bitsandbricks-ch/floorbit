"""Managing the local agents: a new key with a grace period, renaming, plugins left off per agent,
and high availability: groups per hall, who is primary, and this Floorbit's own state."""
import time

from test_agent import clean_tunnel, enrol, head  # noqa: F401  # clean_tunnel is autouse there

from floorbit import agent_ha, agent_link


def report(client, key, vrrp=None):
    body = {"up_seconds": 5, **({"vrrp": vrrp} if vrrp else {})}
    assert client.post("/api/agent/v1/report", json={"report": body}, headers=head(key)).status_code == 200


def test_a_new_key_works_and_the_old_one_until_the_new_one_is_used(client, anon_client):
    made = enrol(client, "Hall agent")
    res = client.post(f"/api/agents/{made['id']}/rotate")
    assert res.status_code == 200
    new = res.get_json()["key"]
    assert new != made["key"] and new.startswith(f"fba_{made['id']}_")
    listed = client.get("/api/agents").get_json()["agents"][0]
    assert listed["old_works_until"] > time.time() and listed["renewed_at"] >= made["created_at"]
    assert anon_client.get("/api/agent/v1/hello", headers=head(made["key"])).status_code == 200   # grace
    assert anon_client.get("/api/agent/v1/hello", headers=head(new)).status_code == 200
    assert anon_client.get("/api/agent/v1/hello", headers=head(made["key"])).status_code == 401   # now gone
    assert client.get("/api/agents").get_json()["agents"][0]["old_works_until"] is None
    actions = [e["action"] for e in client.get("/api/settings/audit").get_json()["entries"]]
    assert "Made a new key for a local agent" in actions
    assert client.post("/api/agents/nope/rotate").status_code == 404


def test_the_old_key_stops_after_the_grace_period(client, anon_client):
    made = enrol(client)
    agent_link.rotate(made["id"], now=time.time() - agent_link.ROTATE_GRACE - 1)
    assert anon_client.get("/api/agent/v1/hello", headers=head(made["key"])).status_code == 401


def test_rename_and_plugins_left_off(client, anon_client, app_module):
    made = enrol(client, "Old name")
    res = client.patch(f"/api/agents/{made['id']}",
                       json={"name": "Hall B agent", "plugins_off": ["netflow-relay", "BAD id"]})
    assert res.get_json() == {"id": made["id"], "name": "Hall B agent", "plugins_off": ["netflow-relay"]}
    assert client.patch(f"/api/agents/{made['id']}", json={"name": ""}).status_code == 400
    assert client.patch(f"/api/agents/{made['id']}", json={"plugins_off": "netflow-relay"}).status_code == 400
    registry = app_module.app.extensions["floorbit_plugins"]
    registry.set_enabled("netflow-relay", True)
    try:
        cfg = anon_client.get("/api/agent/v1/plugins", headers=head(made["key"])).get_json()
        assert "netflow-relay" not in cfg["plugins"]
        other = enrol(client, "Other")
        got = anon_client.get("/api/agent/v1/plugins", headers=head(other["key"])).get_json()
        assert "netflow-relay" in got["plugins"]
    finally:
        registry.set_enabled("netflow-relay", False)
    actions = [e["action"] for e in client.get("/api/settings/audit").get_json()["entries"]]
    assert "Renamed a local agent: Old name" in actions


def agent(aid, connected=True, tags=(), vrrp=None):
    return {"id": aid, "name": aid.upper(), "connected": connected, "tags": list(tags),
            "report": {"vrrp": vrrp} if vrrp is not None else {}}


def test_groups_say_who_is_primary_and_how_the_hall_stands():
    one = agent_ha.groups([agent("a")])[0]
    assert (one["state"], one["primary"], one["mode"]) == ("single", "a", None)
    passive = agent_ha.groups([agent("a", vrrp={"primary": True, "holds": ["192.0.2.10/24", "192.0.2.11/24"]}),
                               agent("b", vrrp={"primary": False, "holds": []})])[0]
    assert (passive["state"], passive["mode"], passive["primary"]) == ("ok", "active-passive", "a")
    assert [a["role"] for a in passive["agents"]] == ["primary", "standby"]
    assert passive["vips"] == ["192.0.2.10/24", "192.0.2.11/24"]
    active = agent_ha.groups([agent("a", vrrp={"primary": True, "holds": ["192.0.2.10/24"]}),
                              agent("b", vrrp={"primary": False, "holds": ["192.0.2.11/24"]})])[0]
    assert active["mode"] == "active-active"
    states = {
        "down": [agent("a", connected=False)],
        "split": [agent("a", vrrp={"primary": True}), agent("b", vrrp={"primary": True})],
        "no_vrrp": [agent("a"), agent("b")],
        "no_primary": [agent("a", vrrp={"primary": False}), agent("b", vrrp={"primary": False})],
        "degraded": [agent("a", vrrp={"primary": True}), agent("b", connected=False)],
    }
    for state, agents in states.items():
        assert agent_ha.groups(agents)[0]["state"] == state, state


def test_groups_follow_the_tags():
    got = agent_ha.groups([agent("a", tags=["h2"]), agent("b"), agent("c", tags=["h2"])], {"h2": "Site 2"})
    assert [(g["id"], g["label"], [a["id"] for a in g["agents"]]) for g in got] == [
        ("*", "", ["b"]), ("h2", "Site 2", ["a", "c"])]


def test_a_standby_keeps_out_of_the_traffic_page_while_the_primary_reports(client, anon_client, monkeypatch):
    from floorbit.blueprints import agent as agent_bp
    first, second = enrol(client, "Primary"), enrol(client, "Standby")
    for made, primary in ((first, True), (second, False)):
        anon_client.get("/api/agent/v1/hello", headers=head(made["key"]))
        report(anon_client, made["key"], {"primary": primary, "holds": ["192.0.2.10/24"] if primary else []})
    published = []
    monkeypatch.setattr("floorbit.flows.store.publish",
                        lambda snap: published.append(snap["agent"]))
    assert agent_bp.take_flow_summary({"id": second["id"], "name": "Standby"}, {"updated": 1})
    assert published == ["Standby"]          # no primary summary yet: the standby's is better than none
    assert agent_bp.take_flow_summary({"id": first["id"], "name": "Primary"}, {"updated": 1})
    assert agent_bp.take_flow_summary({"id": second["id"], "name": "Standby"}, {"updated": 1})
    assert published == ["Standby", "Primary"]


def test_the_page_shows_groups_and_this_floorbit(client, anon_client):
    made = enrol(client)
    anon_client.get("/api/agent/v1/hello", headers=head(made["key"]))
    report(anon_client, made["key"], {"primary": True, "holds": ["192.0.2.10/24"]})
    page = client.get("/api/agents").get_json()
    assert page["groups"][0]["agents"][0]["role"] == "primary"
    hosted = page["hosted"]
    assert hosted["mode"] == "single" and hosted["pods"][0]["me"] and hosted["pods"][0]["leader"]
    assert "ok" in hosted["database"] and "ok" in hosted["redis"]


def test_a_split_group_keeps_one_primary_the_smallest_id():
    both = [agent("b2", vrrp={"primary": True}), agent("a1", vrrp={"primary": True}),
            agent("c3", tags=["side"], vrrp={"primary": True})]       # other tags: not a rival
    assert agent_ha.stand_by_for("a1", both) is None
    assert agent_ha.stand_by_for("b2", both) == "a1"
    assert agent_ha.stand_by_for("c3", both) is None
    healed = [agent("a1", vrrp={"primary": True}), agent("b2", vrrp={"primary": False})]
    assert agent_ha.stand_by_for("b2", healed) is None
    gone = [agent("a1", connected=False, vrrp={"primary": True}), agent("b2", vrrp={"primary": True})]
    assert agent_ha.stand_by_for("b2", gone) is None      # the winner must be there to poll
    assert agent_ha.stand_by_for("a1", [agent("a1")]) is None   # no VRRP: nothing to settle


def test_the_split_reaches_the_agents_with_their_plugin_config(client, anon_client, monkeypatch):
    from floorbit import agent_plugins
    reloads = []
    monkeypatch.setattr(agent_plugins, "reload_agents", lambda: reloads.append(1))
    first, second = enrol(client, "Agent one"), enrol(client, "Agent two")
    low, high = sorted([first, second], key=lambda a: a["id"])
    for made in (first, second):
        anon_client.get("/api/agent/v1/hello", headers=head(made["key"]))
        agent_link.tunnel.seen(agent=made["id"])
    report(anon_client, low["key"], vrrp={"primary": True, "holds": ["192.0.2.10/24"]})
    report(anon_client, high["key"], vrrp={"primary": False, "holds": ["192.0.2.11/24"]})
    cfg = anon_client.get("/api/agent/v1/plugins", headers=head(high["key"])).get_json()
    assert cfg["ha"] == {}
    reloads.clear()
    report(anon_client, high["key"], vrrp={"primary": True, "holds": ["192.0.2.10/24", "192.0.2.11/24"]})
    assert reloads, "a new primary must reach the agents now"
    split = anon_client.get("/api/agent/v1/plugins", headers=head(high["key"]))
    assert split.get_json()["ha"] == {"stand_by_for": low["id"]}
    assert split.get_json()["etag"] != cfg["etag"]
    assert anon_client.get("/api/agent/v1/plugins", headers=head(low["key"])).get_json()["ha"] == {}


def test_a_plugin_action_goes_to_one_agent_per_hall(monkeypatch):
    agents = [agent("a", tags=["h1"], vrrp={"primary": True, "holds": ["192.0.2.10/24"]}),
              agent("b", tags=["h1"], vrrp={"primary": False, "holds": []}),
              agent("c", tags=["h2"]),                                   # other tags, alone
              agent("d", tags=["h3"]), agent("e", tags=["h3"]),         # no VRRP: both stay
              agent("f", tags=["h4"], vrrp={"primary": True}), agent("g", tags=["h4"], vrrp={"primary": True})]
    monkeypatch.setattr("floorbit.agent_link.all_agents", lambda now=None: agents)
    assert agent_ha.action_targets([a["id"] for a in agents]) == ["a", "c", "d", "e", "f", "g"]
    # The primary away: its standby takes the action.
    assert agent_ha.action_targets(["b", "c"]) == ["b", "c"]
