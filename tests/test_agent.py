"""The hosted side of the local agent (issue #2): keys, the call tunnel and the agent-fed source.

The "agent" here is a thread using the Flask test client, so nothing leaves the process."""
import contextlib
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
    assert seen["agents"][0]["transport"] == "poll" and seen["newest_version"] == "1.2.3"
    assert client.get(f"/settings/agents/{made['id']}").status_code in (200, 503)   # 503: no React build

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


def test_the_agent_is_the_way_to_the_lan_even_before_one_is_enrolled(client):
    assert sources.monitoring().name == "agent"
    assert sources.monitoring().device_details("sw-a-01")["status"] == "unknown"   # nobody connected


def test_in_the_agent_process_the_plugins_answer(client, lan_here):
    assert sources.monitoring().name != "agent"


def test_the_page_is_for_admins(app_module, client):
    assert client.get("/settings/agents").status_code in (200, 503)   # 503: no frontend build (CI)
    lead = sign_in_as(app_module, "le2", "lead")
    assert lead.get("/settings/agents").status_code in (302, 403)


def test_an_older_agent_is_flagged(client, anon_client, app_module):
    """By protocol: the agent has its own releases, so its version says nothing next to Floorbit's."""
    assert agent_link.outdated(1, 2) and not agent_link.outdated(2, 2) and not agent_link.outdated(3, 2)
    assert not agent_link.outdated(None, 2) and not agent_link.outdated("1", 2)
    key = enrol(client)['key']
    h = {"Floorbit-Agent-Key": key, "Floorbit-Agent-Version": "0.1.0"}
    anon_client.get("/api/agent/v1/hello", headers=h)                      # no header: protocol 1
    listed = client.get("/api/agents").get_json()
    assert listed["protocol"] == agent_link.PROTOCOL == 2
    assert listed["agents"][0]["protocol"] == 1 and listed["agents"][0]["outdated"] is True
    anon_client.get("/api/agent/v1/hello", headers={**h, "Floorbit-Agent-Protocol": "2"})
    listed = client.get("/api/agents").get_json()
    assert listed["agents"][0]["protocol"] == 2 and listed["agents"][0]["outdated"] is False


def test_an_agent_answers_only_its_own_calls(client, anon_client):
    """With two agents, one can't answer (or spoil) a call the other took."""
    first, second = enrol(client, "Hall 1"), enrol(client, "Hall 2")
    anon_client.get("/api/agent/v1/hello", headers=head(first["key"]))
    got = {}

    def ask():
        got["answer"] = agent_link.tunnel.call("devices", timeout=5)

    asker = threading.Thread(target=ask)
    asker.start()
    calls = []
    deadline = time.time() + 5
    while not calls and time.time() < deadline:
        calls = anon_client.get("/api/agent/v1/calls?wait=0.2", headers=head(first["key"])).get_json()["calls"]
    wrong = {"answers": [{"id": calls[0]["id"], "ok": True, "result": ["from the wrong hall"]}]}
    assert anon_client.post("/api/agent/v1/answers", json=wrong, headers=head(second["key"])).get_json()["taken"] == 0
    right = {"answers": [{"id": calls[0]["id"], "ok": True, "result": ["sw-a-01"]}]}
    assert anon_client.post("/api/agent/v1/answers", json=right, headers=head(first["key"])).get_json()["taken"] == 1
    asker.join(5)
    assert got["answer"] == ["sw-a-01"]


# ── Protocol 2: the WebSocket link ──────────────────────────────────────────────────────────────

@pytest.fixture
def live_server(app_module):
    """The app on a real local port: the test client can't open a WebSocket."""
    from werkzeug.serving import make_server
    server = make_server("127.0.0.1", 0, app_module.app, threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"127.0.0.1:{server.server_port}"
    server.shutdown()


def link_to(address, key):
    import simple_websocket
    return simple_websocket.Client.connect(f"ws://{address}/api/agent/v2/link", headers=head(key))


def test_hello_offers_the_link(client, anon_client):
    made = enrol(client)
    hello = anon_client.get("/api/agent/v1/hello", headers=head(made["key"])).get_json()
    assert hello["protocols"] == [1, 2] and hello["link"] == "/api/agent/v2/link"
    # Agents of protocol 1 keep working: the link is an addition.
    assert anon_client.get("/api/agent/v1/hello", headers={**head(made["key"]), "Floorbit-Agent-Protocol": "1"}
                           ).status_code == 200


def test_calls_and_answers_over_the_link(client, live_server):
    import json

    made = enrol(client)
    ws = link_to(live_server, made["key"])
    try:
        first = json.loads(ws.receive(timeout=5))
        assert first == {"type": "hello", "name": "Demo LAN 2026", "protocol": 2}
        assert agent_link.tunnel.connected(agent=made["id"])

        got = {}
        caller = threading.Thread(target=lambda: got.update(r=agent_link.tunnel.call("devices", timeout=10)))
        caller.start()
        message = json.loads(ws.receive(timeout=5))
        assert message["type"] == "calls" and message["calls"][0]["method"] == "devices"
        call_id = message["calls"][0]["id"]
        ws.send(json.dumps({"type": "answers", "answers": [{"id": call_id, "ok": True, "result": [{"name": "sw-1"}]}]}))
        caller.join(5)
        assert got["r"] == [{"name": "sw-1"}]
        assert agent_link.tunnel.stats(made["id"])["calls"] == 1
    finally:
        ws.close()


def test_the_link_refuses_a_wrong_key(client, live_server):
    import simple_websocket

    made = enrol(client)
    with pytest.raises(simple_websocket.ConnectionError) as refused:
        link_to(live_server, made["key"][:-2] + "xx")
    assert refused.value.status_code == 401
    client.delete(f"/api/agents/{made['id']}")
    with pytest.raises(simple_websocket.ConnectionError):
        link_to(live_server, made["key"])


def test_revoking_a_key_ends_its_open_link(client, live_server):
    import json

    import simple_websocket

    made = enrol(client)
    ws = link_to(live_server, made["key"])
    try:
        assert json.loads(ws.receive(timeout=5))["type"] == "hello"
        assert client.delete(f"/api/agents/{made['id']}").status_code == 200
        started = time.time()
        with pytest.raises(simple_websocket.ConnectionClosed):
            while time.time() - started < 15:
                ws.receive(timeout=1)
        assert time.time() - started < 10           # within a take cycle, not at the next reconnect
    finally:
        with contextlib.suppress(simple_websocket.ConnectionClosed):
            ws.close()


def test_the_agent_reports_about_itself(client, anon_client, live_server):
    import json

    made = enrol(client)
    sent = {"report": {"up_seconds": 3600, "reconnects": 2, "syslog_received": 120, "syslog_dropped": 0,
                       "evil": "<script>", "syslog_backlog": -5, "link_drops": True, "flows_packets": "9",
                       "captive_shown": 40, "captive_done": 12}}
    assert anon_client.post("/api/agent/v1/report", json=sent, headers=head(made["key"])).status_code == 200
    [listed] = client.get("/api/agents").get_json()["agents"]
    report = listed["report"]
    # Only known keys with plain, non-negative numbers are kept.
    assert {k: v for k, v in report.items() if k != "at"} == {"up_seconds": 3600, "reconnects": 2,
                                                             "syslog_received": 120, "syslog_dropped": 0,
                                                             "captive_shown": 40, "captive_done": 12}
    unknown = head("fba_00000000_" + "x" * 30)
    assert anon_client.post("/api/agent/v1/report", json=sent, headers=unknown).status_code == 401

    # Over the link it is a message of its own.
    ws = link_to(live_server, made["key"])
    try:
        ws.receive(timeout=5)
        ws.send(json.dumps({"type": "report", "report": {"up_seconds": 7200}}))
        deadline = time.time() + 5
        while time.time() < deadline and agent_link.tunnel.reported(made["id"]).get("up_seconds") != 7200:
            time.sleep(0.05)
        assert agent_link.tunnel.reported(made["id"])["up_seconds"] == 7200
    finally:
        ws.close()


def test_an_old_report_is_not_shown():
    agent_link.tunnel.report("a1", {"up_seconds": 10}, now=1000)
    assert agent_link.tunnel.reported("a1", now=1000 + agent_link.REPORT_FRESH - 1)["up_seconds"] == 10
    assert agent_link.tunnel.reported("a1", now=1000 + agent_link.REPORT_FRESH + 1) is None


def test_calls_an_agent_could_not_deliver_go_back():
    agent_link.tunnel.seen(agent="a1")
    got = {}
    caller = threading.Thread(target=lambda: got.update(r=agent_link.tunnel.call("devices", timeout=5)))
    caller.start()
    taken = agent_link.tunnel.take(2, agent="a1")
    assert [c["method"] for c in taken] == ["devices"]
    agent_link.tunnel.give_back(taken)
    again = agent_link.tunnel.take(2, agent="a2")
    assert again == taken
    assert agent_link.tunnel.answer(again[0]["id"], True, ["sw-1"], agent="a2")
    caller.join(5)
    assert got["r"] == ["sw-1"]


def test_a_dropped_link_ends_the_wait_at_once(client, live_server):
    """A killed agent (or a cut line) must not hold every page for CALL_TIMEOUT until CONNECTED_FOR
    runs out: once its link closes, it counts as gone and its calls fail straight away."""
    import json

    made = enrol(client)
    ws = link_to(live_server, made["key"])
    assert json.loads(ws.receive(timeout=5))["type"] == "hello"
    got = {}

    def ask():
        try:
            agent_link.tunnel.call("devices", timeout=30)
        except agent_link.AgentUnavailable as exc:
            got["error"] = str(exc)
    asker = threading.Thread(target=ask)
    asker.start()
    assert json.loads(ws.receive(timeout=5))["type"] == "calls"     # taken, then the agent dies
    started = time.time()
    import socket
    ws.sock.shutdown(socket.SHUT_RDWR)                                # no close frame, like kill -9
    ws.sock.close()
    asker.join(10)
    assert "went away" in got["error"] and time.time() - started < 5     # not CALL_TIMEOUT per page
    deadline = time.time() + 3
    while agent_link.tunnel.connected(agent=made["id"]) and time.time() < deadline:
        time.sleep(0.05)
    assert not agent_link.tunnel.connected(agent=made["id"])
    started = time.time()
    with pytest.raises(agent_link.AgentUnavailable):
        agent_link.tunnel.call("devices", timeout=30)
    assert time.time() - started < 1


def test_a_second_link_keeps_the_agent_when_the_first_drops():
    tunnel = agent_link.Tunnel()
    tunnel.linked("a1")
    tunnel.seen(agent="a1")
    tunnel.linked("a1")                  # it reconnected before the old link noticed
    assert tunnel.unlinked("a1") is False and tunnel.connected(agent="a1")
    assert tunnel.unlinked("a1") is True and not tunnel.connected(agent="a1")


def test_a_frozen_agent_is_given_up_within_seconds(client, live_server):
    """A cut line or a frozen agent sends no close. Holding a call without a word, it is asked;
    no answer, and the link is closed, so pages stop waiting on it."""
    import json

    made = enrol(client)
    ws = link_to(live_server, made["key"])
    assert json.loads(ws.receive(timeout=5))["type"] == "hello"
    got = {}

    def ask():
        try:
            agent_link.tunnel.call("devices", timeout=60)
        except agent_link.AgentUnavailable as exc:
            got["error"] = str(exc)
    started = time.time()
    asker = threading.Thread(target=ask)
    asker.start()
    assert json.loads(ws.receive(timeout=5))["type"] == "calls"     # and then nothing, ever
    asker.join(20)
    assert "went away" in got["error"] and time.time() - started < 15
    assert not agent_link.tunnel.connected(agent=made["id"])
    with contextlib.suppress(Exception):
        ws.close()


def test_a_slow_answer_on_a_live_link_is_waited_for(client, live_server):
    import json

    made = enrol(client)
    ws = link_to(live_server, made["key"])
    assert json.loads(ws.receive(timeout=5))["type"] == "hello"
    got = {}
    asker = threading.Thread(target=lambda: got.update(r=agent_link.tunnel.call("devices", timeout=30)))
    asker.start()
    call_id = json.loads(ws.receive(timeout=5))["calls"][0]["id"]
    deadline = time.time() + 12               # a 12 s call: the agent answers the probe meanwhile
    while time.time() < deadline:
        try:
            message = json.loads(ws.receive(timeout=0.5) or "null")
        except Exception:  # noqa: BLE001
            message = None
        if message and message.get("type") == "ping":
            ws.send(json.dumps({"type": "ping"}))
    ws.send(json.dumps({"type": "answers", "answers": [{"id": call_id, "ok": True, "result": ["sw-1"]}]}))
    asker.join(5)
    assert got["r"] == ["sw-1"]
    ws.close()


def test_a_long_poll_agent_that_stopped_asking_is_given_up(client, anon_client, monkeypatch):
    """The HTTPS long poll has no link to close: an agent that died between two polls is noticed
    because nobody takes its calls, and the calls after that fail at once."""
    monkeypatch.setattr(agent_link, "TAKE_GRACE", 0.5)
    monkeypatch.setattr(agent_link, "ASKED_RECENTLY", 1)
    made = enrol(client)
    assert anon_client.get("/api/agent/v1/calls?wait=0", headers=head(made["key"])).status_code == 200
    time.sleep(1.2)                                   # it never asks again
    started = time.time()
    with pytest.raises(agent_link.AgentUnavailable, match="not connected"):
        agent_link.tunnel.call("devices", timeout=8)
    assert time.time() - started < 2
    started = time.time()
    with pytest.raises(agent_link.AgentUnavailable):
        agent_link.tunnel.call("devices", timeout=8)
    assert time.time() - started < 0.2
    # Back with its next poll.
    assert anon_client.get("/api/agent/v1/calls?wait=0", headers=head(made["key"])).status_code == 200
    assert agent_link.tunnel.connected(agent=made["id"])


def test_an_agent_busy_between_polls_is_waited_for(client, anon_client, monkeypatch):
    monkeypatch.setattr(agent_link, "TAKE_GRACE", 0.3)
    made = enrol(client)
    anon_client.get("/api/agent/v1/calls?wait=0", headers=head(made["key"]))    # asked just now
    got = {}

    def agent():
        time.sleep(0.8)                               # posting a big answer, then polls again
        calls = anon_client.get("/api/agent/v1/calls?wait=2", headers=head(made["key"])).get_json()["calls"]
        anon_client.post("/api/agent/v1/answers", headers=head(made["key"]),
                         json={"answers": [{"id": calls[0]["id"], "ok": True, "result": ["sw-1"]}]})
    t = threading.Thread(target=agent)
    t.start()
    got["r"] = agent_link.tunnel.call("devices", timeout=8)
    t.join(5)
    assert got["r"] == ["sw-1"]


def test_a_killed_agent_shows_as_gone_at_once_not_a_minute_later(client):
    a = enrol(client)
    agent_link.check(a["key"], version="1.2.3")          # it asked for work: last seen now
    agent_link.tunnel.linked(a["id"])
    assert client.get("/api/agents").get_json()["agents"][0]["connected"]
    agent_link.tunnel.unlinked(a["id"])                    # its link closed: killed
    assert not client.get("/api/agents").get_json()["agents"][0]["connected"]
    # On its way out it posts the syslog it still held: that doesn't make it reachable again.
    anon = client.application.test_client()
    for path, body in (("/api/agent/v1/syslog", {"lines": []}), ("/api/agent/v1/report", {"report": {}})):
        assert anon.post(path, json=body, headers={"Floorbit-Agent-Key": a["key"]}).status_code < 400
    anon.get("/api/agent/v1/plugins", headers={"Floorbit-Agent-Key": a["key"]})      # and its plugins'
    anon.post("/api/agent/v1/answers", json={"answers": []}, headers={"Floorbit-Agent-Key": a["key"]})
    assert not client.get("/api/agents").get_json()["agents"][0]["connected"]
    assert a["id"] not in agent_link.tunnel.connected_agents()


def test_a_lookup_takes_the_first_agent_that_knows_and_does_not_wait_for_the_other(monkeypatch):
    """Two agents for the same halls: one was just killed and holds the call until it times out."""
    def call(method, args=(), timeout=agent_link.CALL_TIMEOUT, targets=None):
        if targets == {"dead"}:
            time.sleep(3)
            raise agent_link.AgentUnavailable("went away before it answered")
        return {"hostname": "sw-a-01", "port": "Gi1/0/1"}
    monkeypatch.setattr(agent_link.tunnel, "call", call)
    monkeypatch.setattr(agent_link.tunnel, "connected_agents", lambda now=None: {"dead", "alive"})
    started = time.time()
    found = agent_link._ask_all("resolve_ip", ["192.0.2.10"], ["dead", "alive"])
    assert found["port"] == "Gi1/0/1" and time.time() - started < 1


def test_two_agents_for_one_hall_ask_librenms_once_per_lookup(monkeypatch):
    asked = []

    def call(method, args=(), timeout=agent_link.CALL_TIMEOUT, targets=None):
        asked.extend(targets)
        if targets == {"hung"}:
            time.sleep(1)
            raise agent_link.AgentUnavailable("went away before it answered")
        if targets == {"other-hall"}:
            return None
        return {"hostname": "sw-a-01", "port": "Gi1/0/1"}
    monkeypatch.setattr(agent_link.tunnel, "call", call)
    monkeypatch.setattr(agent_link, "HEDGE_AFTER", 0.2)
    monkeypatch.setattr(agent_link, "_last_knew", [None])
    monkeypatch.setattr(agent_link.tunnel, "connected_agents", lambda now=None: {"a", "b"})
    for _ in range(3):
        assert agent_link._ask_all("resolve_ip", ["192.0.2.10"], ["a", "b"])["port"] == "Gi1/0/1"
    assert asked == ["a", "a", "a"]
    # One that doesn't know (another hall's agent) hands over at once.
    asked.clear()
    monkeypatch.setattr(agent_link.tunnel, "connected_agents", lambda now=None: {"other-hall", "b"})
    monkeypatch.setattr(agent_link, "_last_knew", ["other-hall"])
    assert agent_link._ask_all("resolve_ip", ["192.0.2.10"], ["other-hall", "b"])["port"] == "Gi1/0/1"
    assert asked == ["other-hall", "b"] and agent_link._last_knew == ["b"]
    # One that hangs is passed over after HEDGE_AFTER, not CALL_TIMEOUT.
    monkeypatch.setattr(agent_link.tunnel, "connected_agents", lambda now=None: {"hung", "b"})
    monkeypatch.setattr(agent_link, "_last_knew", ["hung"])
    started = time.time()
    assert agent_link._ask_all("resolve_ip", ["192.0.2.10"], ["hung", "b"])["port"] == "Gi1/0/1"
    assert time.time() - started < 0.8


def test_transport_and_newest_version():
    tunnel = agent_link.Tunnel()
    assert tunnel.transport("a1") is None                 # never seen here
    tunnel.seen(agent="a1")
    assert tunnel.transport("a1") == "poll"
    tunnel.linked("a1")
    assert tunnel.transport("a1") == "websocket"
    tunnel.unlinked("a1")
    assert tunnel.transport("a1") is None
    agents = [{"version": "0.9.0"}, {"version": "0.10.1"}, {"version": None}, {"version": "v0.10.0"}]
    assert agent_link.newest_version(agents) == "0.10.1"
    assert agent_link.newest_version([{"version": None}]) is None
