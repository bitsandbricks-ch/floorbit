"""The hosted side of the local agent (issue #2): keys, the call tunnel and the agent-fed source.

The "agent" here is a thread using the Flask test client, so nothing leaves the process."""
import threading
import time

import pytest

from floorbit import agent_link, sources
from tests.test_rbac import sign_in_as


@pytest.fixture(autouse=True)
def clean_tunnel():
    agent_link.tunnel.reset()
    agent_link._forget_cache()
    sources._agent = None
    yield
    agent_link.tunnel.reset()
    agent_link._forget_cache()
    sources._agent = None


def enrol(client, name="Demo LAN 2026"):
    res = client.post("/api/agents", json={"name": name})
    assert res.status_code == 201
    return res.get_json()


def head(key):
    return {"Floorbit-Agent-Key": key, "Floorbit-Agent-Version": "1.2.3"}


def test_enrol_list_and_revoke(client, anon_client):
    made = enrol(client)
    assert made["key"].startswith("fba_") and made["connected"] is False
    listed = client.get("/api/agents").get_json()
    assert [a["name"] for a in listed["agents"]] == ["Demo LAN 2026"]
    assert "key" not in str(listed) and "hash" not in listed["agents"][0]
    assert client.post("/api/agents", json={"name": ""}).status_code == 400

    res = anon_client.get("/api/agent/v1/hello", headers=head(made["key"]))
    assert res.status_code == 200 and res.get_json()["name"] == "Demo LAN 2026"
    seen = client.get("/api/agents").get_json()
    assert seen["agents"][0]["connected"] and seen["agents"][0]["version"] == "1.2.3" and seen["connected"]

    assert anon_client.get("/api/agent/v1/hello", headers=head(made["key"][:-2] + "xx")).status_code == 401
    assert anon_client.get("/api/agent/v1/hello").status_code == 401
    assert client.delete(f"/api/agents/{made['id']}").status_code == 200
    assert anon_client.get("/api/agent/v1/hello", headers=head(made["key"])).status_code == 401
    assert client.delete(f"/api/agents/{made['id']}").status_code == 404


def test_agents_are_for_admins(app_module, client):
    lead = sign_in_as(app_module, "le1", "lead")
    assert lead.get("/api/agents").status_code == 403
    assert lead.post("/api/agents", json={"name": "x"}).status_code == 403
    token = client.post("/api/settings/api-tokens", json={"name": "Script", "role": "admin"}).get_json()["secret"]
    assert client.application.test_client().get(
        "/api/agents", headers={"Authorization": f"Bearer {token}"}).status_code == 403


def answer_like_librenms(anon_client, key, stop):
    """A minimal agent: take calls, answer devices and device_details, fail anything else."""
    while not stop.is_set():
        got = anon_client.get("/api/agent/v1/calls?wait=0.5", headers=head(key)).get_json()["calls"]
        out = []
        for c in got:
            if c["method"] == "devices":
                out.append({"id": c["id"], "ok": True, "result": [{"hostname": "sw-a-01", "status": 1}]})
            elif c["method"] == "device_details":
                out.append({"id": c["id"], "ok": True, "result": {"status": "online", "hostname": c["args"][0]}})
            else:
                out.append({"id": c["id"], "ok": False, "error": "LibreNMS said no"})
        if out:
            # No same-origin header: the agent isn't a browser.
            assert anon_client.post("/api/agent/v1/answers", json={"answers": out},
                                    headers=head(key)).get_json()["taken"] == len(out)


def test_monitoring_goes_through_the_agent(client, app_module):
    key = enrol(client)["key"]
    assert sources.monitoring().name == "agent"
    # Not connected yet: no waiting, the page says unknown.
    assert sources.monitoring().device_details("sw-a-01")["status"] == "unknown"
    stop = threading.Event()
    agent = threading.Thread(target=answer_like_librenms, args=(app_module.app.test_client(), key, stop), daemon=True)
    agent.start()
    try:
        deadline = time.time() + 5
        while not agent_link.tunnel.connected() and time.time() < deadline:
            time.sleep(0.05)
        assert sources.monitoring().devices() == [{"hostname": "sw-a-01", "status": 1}]
        assert sources.monitoring().device_details("sw-a-01") == {"status": "online", "hostname": "sw-a-01"}
        assert sources.monitoring().resolve_ip("192.0.2.10") is None   # the agent's error: no answer
    finally:
        stop.set()
        agent.join(5)


def test_unanswered_calls_time_out():
    agent_link.tunnel.seen()
    started = time.time()
    with pytest.raises(agent_link.AgentUnavailable):
        agent_link.tunnel.call("devices", timeout=0.2)
    assert time.time() - started < 2
    assert agent_link.tunnel.take(wait=0) == []          # the timed-out call isn't handed out later
    with pytest.raises(agent_link.AgentError):
        agent_link.tunnel.call("delete_everything")
    assert agent_link.tunnel.answer("999", True, []) is False


def test_without_an_agent_the_plugins_answer(client):
    assert sources.monitoring().name != "agent"
