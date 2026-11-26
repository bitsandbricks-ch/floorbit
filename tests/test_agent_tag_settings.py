"""Plugin settings for every agent with a tag, inherited like the inventory (issue #1591,
floorbit/agent_settings.py): the agent, then its tags in order, then the plugin's default."""
import pytest

from floorbit import agent_link, audit, sources
from tests.test_agent import enrol, head


@pytest.fixture(autouse=True)
def clean_tunnel():
    agent_link.tunnel.reset()
    agent_link._forget_cache()
    yield
    agent_link.tunnel.reset()
    agent_link._forget_cache()


@pytest.fixture
def relay_on(monkeypatch):
    monkeypatch.setattr(sources.registry, "enabled", lambda spec: spec.id == "netflow-relay")


def _port(anon_client, agent):
    config = anon_client.get("/api/agent/v1/plugins", headers=head(agent["key"])).get_json()
    return config["plugins"]["netflow-relay"]["settings"]["port"]


def _tag(client, tag, **values):
    return client.patch(f"/api/agents/tags/{tag}/settings", json={"plugins": {"netflow-relay": values}})


def test_a_tag_sets_a_plugin_setting_for_every_agent_with_it(client, anon_client, relay_on):
    hall = client.post("/api/inventory/tags", json={"name": "Hall A"}).get_json()["id"]
    lab = client.post("/api/inventory/tags", json={"name": "Lab"}).get_json()["id"]
    a, b, c = enrol(client, "Hall A one"), enrol(client, "Hall A two"), enrol(client, "Elsewhere")
    for agent in (a, b):
        assert client.patch(f"/api/agents/{agent['id']}", json={"tags": [hall, lab]}).status_code == 200

    page = _tag(client, hall, port=2060).get_json()
    relay = next(p for p in page["plugins"] if p["id"] == "netflow-relay")
    assert relay["values"] == {"port": 2060} and page["tag"]["name"] == "Hall A"
    assert {x["name"] for x in page["agents"]} == {"Hall A one", "Hall A two"}
    assert _port(anon_client, a) == _port(anon_client, b) == 2060
    assert _port(anon_client, c) == 2055                                   # no tag: the default

    # The first tag wins over a later one, and the agent's own value over both.
    _tag(client, lab, port=2070, bind="192.0.2.5")
    client.patch(f"/api/agents/{b['id']}/settings", json={"plugins": {"netflow-relay": {"port": 2080}}})
    assert _port(anon_client, a) == 2060 and _port(anon_client, b) == 2080
    mine = client.get(f"/api/agents/{a['id']}/settings").get_json()
    inherited = next(p for p in mine["plugins"] if p["id"] == "netflow-relay")["inherited"]
    assert inherited["port"] == {"value": 2060, "tag": hall, "name": "Hall A"}
    assert inherited["bind"]["tag"] == lab

    # Cleared on the tag: the default again.
    _tag(client, hall, port=None)
    _tag(client, lab, port=None)
    assert _port(anon_client, a) == 2055
    entries, _total = audit.read(limit=20, area="agents")
    assert any(e["target"] == "Hall A" and "tag" in e["action"] for e in entries)


def test_a_tag_takes_only_known_settings(client, relay_on):
    tag = client.post("/api/inventory/tags", json={"name": "Hall B"}).get_json()["id"]
    assert _tag(client, tag, nope=1).status_code == 400
    assert client.patch("/api/agents/tags/no-such-tag/settings", json={"plugins": {}}).status_code == 404
    assert client.get("/api/agents/tags/no-such-tag/settings").status_code == 404


def test_only_admins_change_a_tags_settings(kiosk_client):
    assert kiosk_client.patch("/api/agents/tags/x/settings", json={"plugins": {}}).status_code in (401, 403)
