"""Game servers (issue #472): the queries against fake servers on localhost, the list, RCON."""
import base64
import json
import os
import socket
import struct
import threading
import time

import pytest
from conftest import stored

from floorbit import agent_link, game_query, game_servers, store
from tests.test_ports import audit_lines

# These run the plugins the way the local agent does (tests/conftest.py, lan_here).
pytestmark = pytest.mark.usefixtures("lan_here")


@pytest.fixture(autouse=True)
def secret_key(tmp_path, monkeypatch):
    path = tmp_path / "key"
    path.write_bytes(base64.b64encode(os.urandom(32)))
    monkeypatch.setenv("FLOORBIT_SECRET_KEY_FILE", str(path))
    game_servers.poller.reset()
    yield
    game_servers.poller.reset()


def _thread(target):
    threading.Thread(target=target, daemon=True).start()


def a2s_server(challenge=True, players=7):
    """A UDP server answering A2S_INFO like a Source game does."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    info = (b"\xff\xff\xff\xffI\x11" + b"Hall A 5on5\x00" + b"de_example\x00" + b"cs\x00" + b"Counter-Strike\x00"
            + struct.pack("<h", 730) + bytes([players, 10, 2]) + b"dlwv" + b"1.40.0.0\x00")

    def run():
        while True:
            data, addr = sock.recvfrom(1400)
            if challenge and not data.endswith(b"abcd"):
                sock.sendto(b"\xff\xff\xff\xffAabcd", addr)
            else:
                sock.sendto(info, addr)
    _thread(run)
    return sock.getsockname()[1]


def tcp_server(handle):
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen(5)

    def run():
        while True:
            conn, _ = sock.accept()
            _thread(lambda c=conn: handle(c))
    _thread(run)
    return sock.getsockname()[1]


def minecraft_server():
    def handle(conn):
        with conn:
            conn.recv(1024)
            text = json.dumps({"version": {"name": "1.21.4"}, "players": {"online": 3, "max": 20},
                               "description": {"text": "Crew ", "extra": [{"text": "build"}]}}).encode()
            body = b"\x00" + game_query._varint(len(text)) + text
            conn.sendall(game_query._varint(len(body)) + body)
    return tcp_server(handle)


def rcon_server(password="example-rcon", log=None):
    def read(conn):
        size = struct.unpack("<i", game_query._read_exact(conn, 4))[0]
        data = game_query._read_exact(conn, size)
        req_id, kind = struct.unpack("<ii", data[:8])
        return req_id, kind, data[8:-2].decode()

    def handle(conn):
        with conn:
            req_id, _, body = read(conn)
            conn.sendall(game_query._packet(req_id, 0, ""))
            conn.sendall(game_query._packet(req_id if body == password else -1, 2, ""))
            if body != password:
                return
            req_id, _, command = read(conn)
            if log is not None:
                log.append(command)
            if command == "status":     # a long answer, in two packets
                conn.sendall(game_query._packet(req_id, 0, "hostname: Hall A\n")
                             + game_query._packet(req_id, 0, "players: 7"))
            elif command == "list":     # Minecraft colours its answers
                conn.sendall(game_query._packet(req_id, 0, "\u00a76There are \u00a7c3\u00a76 players online"))
            else:
                conn.sendall(game_query._packet(req_id, 0, f"ran {command}"))
    return tcp_server(handle)


def test_the_queries_read_what_the_servers_say():
    a2s = game_query.query("a2s", "127.0.0.1", a2s_server())
    assert (a2s["name"], a2s["map"], a2s["players"], a2s["max_players"], a2s["bots"], a2s["version"]) == (
        "Hall A 5on5", "de_example", 7, 10, 2, "1.40.0.0")
    assert game_query.query("a2s", "127.0.0.1", a2s_server(challenge=False))["game"] == "Counter-Strike"
    mc = game_query.query("minecraft", "127.0.0.1", minecraft_server())
    assert (mc["name"], mc["players"], mc["max_players"], mc["version"]) == ("Crew build", 3, 20, "1.21.4")
    assert game_query.query("tcp", "127.0.0.1", minecraft_server())["ping_ms"] >= 0
    closed = socket.socket()
    closed.bind(("127.0.0.1", 0))
    port = closed.getsockname()[1]
    closed.close()
    with pytest.raises(game_query.QueryError):
        game_query.query("tcp", "127.0.0.1", port, timeout=0.5)
    with pytest.raises(game_query.QueryError, match="No answer"):
        game_query.query("a2s", "127.0.0.1", port, timeout=0.3)


def test_rcon_logs_in_and_reads_long_answers():
    port = rcon_server()
    assert game_query.rcon("127.0.0.1", port, "example-rcon", "status") == "hostname: Hall A\nplayers: 7"
    with pytest.raises(game_query.QueryError, match="refused"):
        game_query.rcon("127.0.0.1", port, "wrong", "status")


def _add(client, **extra):
    body = {"name": "CS Hall A", "game": "Counter-Strike 2", "host": "127.0.0.1", "port": a2s_server(),
            "query": "a2s", **extra}
    r = client.post("/api/game-servers", json=body)
    assert r.status_code == 201, r.get_json()
    return r.get_json()


def test_servers_are_listed_with_their_state_and_the_password_never_comes_back(client):
    rcon_port = rcon_server()
    server = _add(client, rcon_port=rcon_port, rcon_password="example-rcon")
    assert server["rcon"] is True and "rcon_password" not in server
    assert "example-rcon" not in stored(store.DATA_FILE)
    body = client.get("/api/game-servers").get_json()
    [row] = body["servers"]
    assert row["status"] == "up" and row["info"]["map"] == "de_example" and row["info"]["players"] == 7
    assert body["counts"]["up"] == 1 and body["players"] == 7 and len(row["history"]) >= 1
    assert "rcon_password" not in json.dumps(body)
    # Changing it without a password keeps the password; clear_rcon removes it.
    assert client.put(f"/api/game-servers/{server['id']}", json={"name": "CS Hall A1"}).get_json()["rcon"] is True
    assert client.put(f"/api/game-servers/{server['id']}", json={"clear_rcon": True}).get_json()["rcon"] is False
    same_name = {"name": "cs hall a1", "host": "127.0.0.1", "port": 1}
    assert client.post("/api/game-servers", json=same_name).status_code == 409
    assert client.post("/api/game-servers", json={"name": "X", "host": "-bad", "port": 1}).status_code == 400
    assert client.post("/api/game-servers", json={"name": "X", "host": "a.example.com", "port": 0}).status_code == 400
    assert client.delete(f"/api/game-servers/{server['id']}").status_code == 200
    assert client.get("/api/game-servers").get_json()["servers"] == []


def test_a_server_that_does_not_answer_is_down_and_on_the_health_wall(client):
    closed = socket.socket()
    closed.bind(("127.0.0.1", 0))
    port = closed.getsockname()[1]
    closed.close()
    client.post("/api/game-servers", json={"name": "Minecraft", "host": "127.0.0.1", "port": port, "query": "tcp"})
    [row] = client.get("/api/game-servers").get_json()["servers"]
    assert row["status"] == "down" and row["error"]
    [tile] = [c for c in game_servers.health_checks() if c["kind"] == "game"]
    assert tile["status"] == "down" and tile["link"] == "/game-servers"


def test_rcon_runs_commands_asks_before_destructive_ones_and_audits(client):
    log = []
    server = _add(client, rcon_port=rcon_server(log=log), rcon_password="example-rcon")
    url = f"/api/game-servers/rcon/{server['id']}"
    r = client.post(url, json={"command": "status"})
    assert r.status_code == 200 and r.get_json()["answer"].startswith("hostname")
    assert client.post(url, json={"command": "list"}).get_json()["answer"] == "There are 3 players online"
    r = client.post(url, json={"command": "changelevel de_other"})
    assert r.status_code == 409 and r.get_json()["confirm"] is True and log == ["status", "list"]
    r = client.post(url, json={"command": "changelevel de_other", "confirm": True})
    assert r.get_json()["answer"] == "ran changelevel de_other"
    client.post(url, json={"command": "sv_password example-secret", "confirm": True})
    assert client.post(url, json={"command": "a\nb"}).status_code == 400
    actions = [e["action"] for e in audit_lines() if e.get("area") == "games"]
    assert "RCON: status" in actions and "RCON: changelevel de_other" in actions
    assert "RCON: sv_password …" in actions
    assert "example-secret" not in json.dumps(audit_lines())


def test_rcon_needs_a_password_and_tells_when_the_server_refuses(client):
    server = _add(client)
    r = client.post(f"/api/game-servers/rcon/{server['id']}", json={"command": "status"})
    assert r.status_code == 409
    client.put(f"/api/game-servers/{server['id']}", json={"rcon_port": rcon_server(password="other"),
                                                          "rcon_password": "example-rcon"})
    r = client.post(f"/api/game-servers/rcon/{server['id']}", json={"command": "status"})
    assert r.status_code == 502 and "refused" in r.get_json()["error"]
    assert audit_lines()[-1]["ok"] is False


def test_with_an_agent_the_agent_asks(client, monkeypatch):
    calls = []

    def call(method, args=(), timeout=None, targets=None):
        calls.append((method, list(args)))
        return {"name": "Remote", "players": 4, "max_players": 16, "ping_ms": 3.2, "extra": "dropped"}
    monkeypatch.setattr(game_servers, "_via_agent", lambda: True)
    monkeypatch.setattr(agent_link.tunnel, "call", call)
    client.post("/api/game-servers", json={"name": "Valheim", "host": "192.0.2.50", "port": 2457})
    [row] = client.get("/api/game-servers").get_json()["servers"]
    assert calls[-1] == ("game_query", ["a2s", "192.0.2.50", 2457])
    assert row["status"] == "up" and row["info"]["players"] == 4 and "extra" not in row["info"]
    assert client.get("/api/game-servers").get_json()["via_agent"] is True


def test_who_may_do_what(app_module):
    from tests.test_rbac import sign_in_as
    tech = sign_in_as(app_module, "te7", "tech")
    viewer = sign_in_as(app_module, "vi7", "viewer")
    assert viewer.get("/api/game-servers").status_code == 200
    assert viewer.post("/api/game-servers/rcon/x", json={"command": "status"}).status_code == 403
    assert tech.post("/api/game-servers/rcon/x", json={"command": "status"}).status_code == 404
    assert tech.post("/api/game-servers", json={"name": "X", "host": "a.example.com", "port": 1}).status_code == 403


def test_rotation_seals_rcon_passwords_again(client, tmp_path, monkeypatch):
    server = _add(client, rcon_port=rcon_server(), rcon_password="example-rcon")
    old = os.environ["FLOORBIT_SECRET_KEY_FILE"]
    new = tmp_path / "new-key"
    new.write_bytes(base64.b64encode(os.urandom(32)))
    monkeypatch.setenv("FLOORBIT_SECRET_KEY_FILE", str(new))
    monkeypatch.setenv("FLOORBIT_SECRET_OLD_KEY_FILES", old)
    assert game_servers.rotate() == 1
    monkeypatch.delenv("FLOORBIT_SECRET_OLD_KEY_FILES")
    r = client.post(f"/api/game-servers/rcon/{server['id']}", json={"command": "status"})
    assert r.status_code == 200


def answering(text):
    """A Minecraft port that answers the status ping with ``text`` as its JSON."""
    def handle(conn):
        with conn:
            conn.recv(1024)
            body = b"\x00" + game_query._varint(len(text)) + text
            conn.sendall(game_query._varint(len(body)) + body)
    return tcp_server(handle)


@pytest.mark.parametrize("text", [
    b"[1, 2]", b'"hi"', b"[" * 100000 + b"]" * 100000, b"\xff\xfe",
])
def test_a_minecraft_answer_that_is_not_a_status_is_down_not_an_error(text):
    with pytest.raises(game_query.QueryError, match="not a Minecraft status"):
        game_query.query("minecraft", "127.0.0.1", answering(text), timeout=1)


@pytest.mark.parametrize("status", [
    {"players": [1]}, {"players": {"online": "many", "max": 20}}, {"players": {"online": 1e300}},
    {"version": "x"}, {"description": {"text": "a", "extra": 5}}, {"description": {"text": 5}},
])
def test_odd_fields_in_a_minecraft_status_read_as_nothing(status):
    # Each of these raised AttributeError, ValueError, OverflowError or TypeError, and took the
    # whole poll down with it: every other server kept its old state.
    found = game_query.query("minecraft", "127.0.0.1", answering(json.dumps(status).encode()), timeout=1)
    assert 0 <= found["players"] <= 1_000_000 and isinstance(found["name"], str)


def test_a_message_of_the_day_nested_deep_is_cut_not_a_crash():
    # Over the wire, as deep as every Python's JSON decoder takes (3.11 stops near 1000 levels).
    deep = '{"description":' + '{"text":"a","extra":[' * 200 + '"b"' + "]}" * 200 + "}"
    found = game_query.query("minecraft", "127.0.0.1", answering(deep.encode()), timeout=1)
    assert found["name"].startswith("aaa") and len(found["name"]) <= 120
    # Deeper than the recursion limit: the old recursive walk raised RecursionError here.
    motd = "b"
    for _ in range(5000):
        motd = {"text": "a", "extra": [motd]}
    assert game_query._motd(motd).startswith("aaa")
    assert game_query._motd({"text": "Crew ", "extra": [{"text": "build", "extra": [" night"]}, "!"]}) \
        == "Crew build night!"


def test_a_varint_that_runs_off_the_packet_is_refused():
    with pytest.raises(game_query.QueryError):
        game_query.parse_minecraft_status(b"\x00\xff\xff")


def test_an_rcon_server_that_never_stops_sending_lets_go():
    def chatter(conn, after_login):
        try:
            conn.recv(1024)
            if after_login:
                conn.sendall(game_query._packet(1, 2, ""))
                conn.recv(1024)
            while True:
                conn.sendall(game_query._packet(7, 0, "noise"))
                time.sleep(0.01)
        except OSError:
            pass

    start = time.monotonic()
    with pytest.raises(game_query.QueryError, match="never answered the RCON login"):
        game_query.rcon("127.0.0.1", tcp_server(lambda c: chatter(c, False)), "pw", "status", timeout=1)
    game_query.rcon("127.0.0.1", tcp_server(lambda c: chatter(c, True)), "pw", "status", timeout=1)
    assert time.monotonic() - start < 5       # before: both held the thread for as long as the server sent


def test_one_odd_server_does_not_stop_the_poll(client, monkeypatch):
    for name in ("Hall A", "Hall B"):
        assert client.post("/api/game-servers", json={"name": name, "query": "minecraft", "host": "192.0.2.5",
                                                      "port": 25565}).status_code == 201

    def ask(method, protocol, host, port):
        raise KeyError("something nobody thought of")
    monkeypatch.setattr(game_servers, "_ask", ask)
    game_servers.poller.poll_once()
    states = [game_servers.poller.state(s["id"]) for s in game_servers._all()]
    assert [s["status"] for s in states] == ["down", "down"]
    assert states[0]["error"] == game_servers.UNREADABLE and game_servers.poller.last_poll
