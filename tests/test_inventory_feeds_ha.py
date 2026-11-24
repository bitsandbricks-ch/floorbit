"""A pair of agents (the same tags) feeds NetBox once, under one id that survives a failover."""
from test_agent import clean_tunnel  # noqa: F401  # autouse there

from floorbit import agent_ha, agent_link


def agent(aid, tags, lease=None):
    return {"id": aid, "name": f"Agent {aid}", "connected": True, "tags": list(tags),
            "report": {"lease": lease} if lease is not None else {}}


def setup(monkeypatch, agents, connected, answers):
    asked = []
    monkeypatch.setattr(agent_link, "_routing", lambda: ({a["id"]: frozenset(a["tags"]) for a in agents},
                                                        [a["id"] for a in agents], {}))
    monkeypatch.setattr(agent_link, "all_agents", lambda now=None: agents)
    monkeypatch.setattr(agent_link, "load_data", lambda: {agent_link.KEY: agents})
    monkeypatch.setattr(agent_link.tunnel, "connected_agents", lambda now=None: set(connected))

    def call(method, args, timeout, targets):
        (aid,) = targets
        asked.append(aid)
        if isinstance(answers[aid], Exception):
            raise answers[aid]
        return answers[aid]
    monkeypatch.setattr(agent_link.tunnel, "call", call)
    return asked


FEED = [{"plugin": "netbox", "name": "NetBox", "items": [{"id": "1", "name": "sw-01"}]}]


def test_a_pair_is_asked_once_its_primary_first(monkeypatch):
    agents = [agent("a", ["h1"], lease=False), agent("b", ["h1"], lease=True), agent("c", ["h2"])]
    asked = setup(monkeypatch, agents, {"a", "b", "c"}, {"a": FEED, "b": FEED, "c": FEED})
    feeds = agent_link.inventory_feeds()
    assert sorted(asked) == ["b", "c"]
    assert sorted(f["plugin"] for f in feeds) == ["netbox.a", "netbox.c"]   # the pair's smallest id


def test_the_feed_keeps_its_id_when_the_other_agent_answers(monkeypatch):
    agents = [agent("a", ["h1"]), agent("b", ["h1"])]
    asked = setup(monkeypatch, agents, {"b"}, {"b": FEED})
    assert [f["plugin"] for f in agent_link.inventory_feeds()] == ["netbox.a"] and asked == ["b"]


def test_the_next_agent_of_the_pair_answers_when_the_first_fails(monkeypatch):
    agents = [agent("a", ["h1"], lease=True), agent("b", ["h1"])]
    asked = setup(monkeypatch, agents, {"a", "b"},
                  {"a": agent_link.AgentUnavailable("gone"), "b": FEED})
    feeds = agent_link.inventory_feeds()
    assert asked == ["a", "b"] and [f["plugin"] for f in feeds] == ["netbox.a"]
    assert "error" not in feeds[0]


def test_one_per_group_keeps_unknown_agents(monkeypatch):
    monkeypatch.setattr(agent_link, "all_agents", lambda now=None: [agent("a", ["h1"])])
    assert agent_ha.one_per_group({"a", "x"}) == [("a", ["a"]), ("x", ["x"])]
