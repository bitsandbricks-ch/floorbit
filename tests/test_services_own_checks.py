"""Own checks on the Services page (issue #1338), service tags (#1337) and what happens without an
agent (#1339). The probes run on a fake agent; the probe functions themselves against this machine."""
import http.server
import socket
import threading

import pytest

from floorbit import agent_link, game_servers, probes, services


@pytest.fixture
def agent(client, monkeypatch):
    """The agent answers every probe; ``answers[method]`` says how."""
    services.poller.reset()
    answers, calls = {}, []
    monkeypatch.setattr(services, "_via_agent", lambda: True)

    def call(method, args=(), timeout=None, targets=None):
        calls.append((method, list(args)))
        return answers[method](*args)
    monkeypatch.setattr(agent_link.tunnel, "call", call)
    yield answers, calls
    services.poller.reset()


def _add(client, **body):
    r = client.post("/api/services/checks", json={"name": "Check", **body})
    assert r.status_code == 201, r.get_json()
    return r.get_json()


def _state(client, item_id):
    return next(c for c in client.get("/api/services").get_json()["checks"] if c["id"] == item_id)


def test_each_kind_of_check_is_kept_as_typed_and_only_what_the_agent_needs_goes_to_it(client, agent):
    answers, calls = agent
    answers["check_probe"] = lambda spec: {"kind": spec["kind"], "sent": 3, "lost": 0, "ms": 1.2}
    ping = _add(client, kind="ping", host="192.0.2.40", url="ignored")
    assert (ping["host"], ping["port"], ping["url"], ping["slow_ms"]) == ("192.0.2.40", None, "", 100)
    state = _state(client, ping["id"])
    assert (state["status"], state["latency_ms"], state["loss"]) == ("up", 1.2, 0)
    assert calls[-1] == ("check_probe", [{"kind": "ping", "host": "192.0.2.40", "port": None, "ask": "",
                                          "url": "", "contains": ""}])
    tcp = _add(client, kind="tcp", host="stream.example.com", port=8080, slow_ms=50)
    assert (tcp["port"], tcp["slow_ms"]) == (8080, 50)
    web = _add(client, kind="http", url="https://www.example.com/health", contains="ok")
    assert (web["expect"], web["cert_warn_days"], web["host"]) == ("200-399", 14, "")
    plain = _add(client, kind="http", url="http://192.0.2.41:8080/", expect="204")
    assert (plain["expect"], plain["cert_warn_days"]) == ("204", None)


@pytest.mark.parametrize("body", [
    {"kind": "smtp", "host": "192.0.2.1"},
    {"kind": "ping", "host": "not a host"},
    {"kind": "tcp", "host": "192.0.2.1", "port": 0},
    {"kind": "tcp", "host": "192.0.2.1", "port": 70000},
    {"kind": "udp", "host": "192.0.2.1", "port": 53, "ask": "snmp"},
    {"kind": "http", "url": "ftp://example.com/"},
    {"kind": "http", "url": "https://example.com/a b"},
    {"kind": "http", "url": "https://example.com/\r\nX: y"},
    {"kind": "http", "url": "https://example.com:99999/"},
    {"kind": "http", "url": "https://example.com/", "expect": "abc"},
    {"kind": "http", "url": "https://example.com/", "expect": "500-200"},
    {"kind": "http", "url": "https://example.com/", "cert_warn_days": 400},
    {"kind": "ping", "host": "192.0.2.1", "slow_ms": 0},
    {"name": "", "kind": "ping", "host": "192.0.2.1"},
])
def test_what_is_kept_is_checked(client, agent, body):
    assert client.post("/api/services/checks", json={"name": "X", **body}).status_code == 400


@pytest.mark.parametrize(("item", "got", "status", "said"), [
    ({"kind": "ping", "host": "192.0.2.1"}, {"sent": 3, "lost": 3, "ms": None}, "down", "No answer to ping."),
    ({"kind": "ping", "host": "192.0.2.1"}, {"sent": 3, "lost": 1, "ms": 2.0}, "warn", ""),
    ({"kind": "tcp", "host": "192.0.2.1", "port": 22}, {"sent": 3, "lost": 0, "ms": 250.0}, "warn", ""),
    ({"kind": "tcp", "host": "192.0.2.1", "port": 22}, {"sent": 3, "lost": 3, "ms": None}, "down",
     "Port 22 does not answer."),
    ({"kind": "udp", "host": "192.0.2.1", "port": 123, "ask": "ntp"}, {"answered": True, "ms": 3.0}, "up", ""),
    ({"kind": "udp", "host": "192.0.2.1", "port": 123, "ask": "ntp"}, {"answered": False}, "down", "No answer."),
    ({"kind": "udp", "host": "192.0.2.1", "port": 9987, "ask": "none"}, {"answered": False, "closed": False},
     "up", ""),
    ({"kind": "udp", "host": "192.0.2.1", "port": 9987, "ask": "none"}, {"closed": True}, "down",
     "Port 9987 is closed."),
    ({"kind": "http", "url": "https://example.com/"}, {"code": 200, "ms": 90.0, "cert_days": 60}, "up", ""),
    ({"kind": "http", "url": "https://example.com/"}, {"code": 503, "ms": 90.0}, "down",
     "Answered 503, expected 200-399."),
    ({"kind": "http", "url": "https://example.com/", "contains": "ok"}, {"code": 200, "ms": 9.0, "found": False},
     "down", 'The page does not contain "ok".'),
    ({"kind": "http", "url": "https://example.com/"}, {"code": 200, "ms": 9.0, "cert_days": 3}, "warn", ""),
])
def test_what_the_agent_saw_becomes_a_status(client, agent, item, got, status, said):
    answers, _calls = agent
    answers["check_probe"] = lambda spec: got
    added = _add(client, **item)
    state = _state(client, added["id"])
    assert state["status"] == status and state["error"] == said
    [tile] = [t for t in services.health_checks() if t["id"] == f"check:{added['id']}"]
    assert tile["kind"] == "check" and tile["status"] == status and tile["link"] == "/services"


def test_test_runs_once_and_keeps_nothing(client, agent):
    answers, _calls = agent
    answers["check_probe"] = lambda spec: {"code": 200, "ms": 40.0, "cert_days": 61}
    got = client.post("/api/services/checks/test", json={"name": "Site", "kind": "http",
                                                          "url": "https://example.com/"}).get_json()
    assert (got["status"], got["code"], got["cert_days"]) == ("up", 200, 61)
    assert client.get("/api/services").get_json()["checks"] == []
    assert client.post("/api/services/checks/test", json={"kind": "http", "url": "x"}).status_code == 400


def test_without_an_agent_nothing_is_sent_and_nothing_turns_red(client, monkeypatch):
    """#1339: no agent connected is grey "not checked", not "down"; the server itself sends nothing."""
    services.poller.reset()
    game_servers.poller.reset()

    def unavailable(*_a, **_k):
        raise agent_link.AgentUnavailable("no agent")
    monkeypatch.setattr(agent_link.tunnel, "call", unavailable)
    monkeypatch.setattr(services, "_via_agent", lambda: True)
    monkeypatch.setattr(game_servers, "_via_agent", lambda: True)
    sent = []
    monkeypatch.setattr(probes, "tcp", lambda *a, **k: sent.append(a))
    client.post("/api/services/sites", json={"name": "Store", "host": "store.example.com"})
    client.post("/api/services/resolvers", json={"name": "R", "address": "192.0.2.53", "lookup": "example.com"})
    _add(client, kind="ping", host="192.0.2.40")
    body = client.get("/api/services").get_json()
    for row in body["sites"] + body["resolvers"] + body["checks"]:
        assert row["status"] == "unknown" and row["error"] == services.NO_AGENT
    client.post("/api/game-servers", json={"name": "CS", "host": "192.0.2.20", "port": 27015})
    [game] = client.get("/api/game-servers").get_json()["servers"]
    assert game["status"] == "unknown" and game["error"] == game_servers.NO_AGENT
    # Demo data without an enrolled agent: still nothing from the server.
    monkeypatch.setattr(services, "_via_agent", lambda: False)
    services.poller.poll_once()
    assert sent == []
    assert all(r["status"] == "unknown" for r in client.get("/api/services").get_json()["sites"])


def test_tags_belong_to_any_service_the_page_lists(client, agent):
    answers, _calls = agent
    answers["check_probe"] = lambda spec: {"sent": 3, "lost": 0, "ms": 1.0}
    item = _add(client, kind="ping", host="192.0.2.40")
    sid = f"check:{item['id']}"
    r = client.post("/api/services/tags", json={"id": sid, "tags": [" Stage ", "stage", "Hall  B", ""]})
    assert r.status_code == 200 and r.get_json()["tags"] == ["Stage", "Hall B"]
    assert client.get("/api/services/summary").get_json()["tags"][sid] == ["Stage", "Hall B"]
    assert client.post("/api/services/tags", json={"id": "check:nope", "tags": ["x"]}).status_code == 404
    assert client.post("/api/services/tags", json={"id": sid, "tags": "Stage"}).status_code == 400
    assert client.post("/api/services/tags", json={"id": sid, "tags": ["x" * 25]}).status_code == 400
    assert client.post("/api/services/tags", json={"id": sid, "tags": [str(i) for i in range(9)]}).status_code == 400
    # Removing the service takes its tags along.
    client.delete(f"/api/services/checks/{item['id']}")
    assert sid not in services.tags()


def test_viewers_read_but_do_not_add_checks_or_tags(app_module):
    from tests.test_rbac import sign_in_as
    viewer = sign_in_as(app_module, "vi11", "viewer")
    assert viewer.post("/api/services/checks", json={"kind": "ping", "host": "192.0.2.1"}).status_code == 403
    assert viewer.post("/api/services/checks/test", json={}).status_code == 403
    assert viewer.post("/api/services/tags", json={"id": "x", "tags": []}).status_code == 403
    assert viewer.get("/api/services/summary").status_code == 200


# ── the probes themselves, against this machine ─────────────────────────────
def _free_port(kind=socket.SOCK_STREAM):
    sock = socket.socket(socket.AF_INET, kind)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def test_tcp_and_udp_probes():
    listening = socket.socket()
    listening.bind(("127.0.0.1", 0))
    listening.listen()
    port = listening.getsockname()[1]
    try:
        got = probes.check({"kind": "tcp", "host": "127.0.0.1", "port": port}, resolve=lambda h: h)
        assert got["lost"] == 0 and got["ms"] is not None
    finally:
        listening.close()
    got = probes.check({"kind": "tcp", "host": "127.0.0.1", "port": _free_port()}, resolve=lambda h: h)
    assert got["lost"] == got["sent"]
    # A closed UDP port answers "unreachable"; one that answers is up.
    assert probes.check({"kind": "udp", "host": "127.0.0.1", "port": _free_port(socket.SOCK_DGRAM)},
                        resolve=lambda h: h)["closed"] is True
    echo = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    echo.bind(("127.0.0.1", 0))
    seen = []

    def answer():
        data, addr = echo.recvfrom(2048)
        seen.append(data)
        echo.sendto(b"\x1c" + 47 * b"\x00", addr)
    threading.Thread(target=answer, daemon=True).start()
    got = probes.check({"kind": "udp", "host": "127.0.0.1", "port": echo.getsockname()[1], "ask": "ntp"},
                       resolve=lambda h: h)
    echo.close()
    assert got["answered"] is True and seen == [b"\x1b" + 47 * b"\x00"]


def test_http_probe_keeps_the_status_and_whether_the_text_is_there():
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            body = b"all ok here" if self.path == "/health" else b"nope"
            self.send_response(200 if self.path == "/health" else 404)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_a):
            pass
    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://localhost:{server.server_port}"
    asked = []

    def resolve(host):
        asked.append(host)
        return "127.0.0.1"
    try:
        got = probes.check({"kind": "http", "url": f"{base}/health", "contains": "OK"}, resolve=resolve)
        assert (got["code"], got["found"], got["cert_days"]) == (200, True, None) and asked == ["localhost"]
        assert probes.check({"kind": "http", "url": f"{base}/gone"}, resolve=resolve)["code"] == 404
    finally:
        server.shutdown()
    with pytest.raises(probes.ProbeError):
        probes.check({"kind": "http", "url": f"{base}/a b"}, resolve=resolve)
    with pytest.raises(probes.ProbeError):
        probes.check({"kind": "tcp", "host": "127.0.0.1", "port": 0}, resolve=lambda h: h)


def test_ping_says_when_this_machine_does_not_allow_it(monkeypatch):
    def refuse(*_a, **_k):
        raise PermissionError("not allowed")
    monkeypatch.setattr(probes.socket, "socket", refuse)
    with pytest.raises(probes.ProbeError, match="ping"):
        probes.ping("127.0.0.1")
