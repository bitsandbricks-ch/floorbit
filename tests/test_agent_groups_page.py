"""One group of local agents on its own page (#1441): who is primary, who owns how many devices."""
from floorbit import agent_ha, agent_link
from floorbit.telemetry import targets

SPLITS = {"plugins": {"telemetry": {"metrics": {"split": 1}}}}
DEVICES = [{"name": f"sw-{i:03}", "agent": "", "address": f"192.0.2.{i}"} for i in range(1, 101)]


def _hall(monkeypatch, b_report):
    agents = [
        {"id": "a", "name": "Rack A", "connected": True, "tags": ["hall-1"], "address": "192.0.2.201",
         "report": {"lease": True, **SPLITS}},
        {"id": "b", "name": "Rack B", "connected": True, "tags": ["hall-1"], "address": "192.0.2.202",
         "report": {"lease": False, **b_report}},
        {"id": "x", "name": "Other hall", "connected": True, "tags": ["hall-2"], "report": {"lease": True, **SPLITS}},
    ]
    monkeypatch.setattr(agent_link, "all_agents", lambda data=None, now=None: agents)
    monkeypatch.setattr(agent_link.tunnel, "connected_agents", lambda now=None: {"a", "b", "x"})
    monkeypatch.setattr(targets, "listing", lambda data=None: DEVICES)
    monkeypatch.setattr(agent_ha, "lease_holder", lambda members: "a")


def test_a_split_group_shows_each_agents_share(client, monkeypatch):
    _hall(monkeypatch, SPLITS)
    got = client.get("/api/agents/groups/hall-1").get_json()
    rows = {r["id"]: r for r in got["agents"]}
    assert got["split"] and set(rows) == {"a", "b"} and got["primary"] == "a"
    owners = [agent_ha.split_owner(d["name"], ["a", "b"]) for d in DEVICES]
    assert rows["a"]["owns"] == owners.count("a") and rows["b"]["owns"] == owners.count("b")
    assert got["devices"] == 100 and rows["b"]["address"] == "192.0.2.202" and rows["b"]["follows_split"]


def test_unsplit_the_primary_has_them_all(client, monkeypatch):
    _hall(monkeypatch, {})                        # b too old to follow the split
    got = client.get("/api/agents/groups/hall-1").get_json()
    rows = {r["id"]: r for r in got["agents"]}
    assert not got["split"] and rows["a"]["owns"] == 100 and rows["b"]["owns"] == 0
    assert not rows["b"]["follows_split"]


def test_a_group_nobody_is_in_is_404(client, monkeypatch):
    _hall(monkeypatch, SPLITS)
    assert client.get("/api/agents/groups/nowhere").status_code == 404


def test_only_admins_see_it(anon_client):
    assert anon_client.get("/api/agents/groups/hall-1").status_code in (401, 403)
