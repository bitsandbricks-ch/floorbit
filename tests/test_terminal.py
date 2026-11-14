"""Browser terminal (issue #95): one switch, the tech's own login, every typed line audited."""
import json

import pytest

from floorbit import audit, ports, terminal
from tests.test_ports import FakeSwitch

SWITCH = {"name": "sw-a-01", "mgmt_ip": "198.51.100.4", "role": "switch"}


@pytest.fixture(autouse=True)
def fresh():
    for state in (ports._last, ports._failures, ports._busy):
        state.clear()
    yield
    for s in list(terminal._sessions.values()):
        s.end("test over")


@pytest.fixture
def switch(client):
    assert client.post("/api/inventory", json=SWITCH).status_code in (200, 201)


def sign_in(app_module, username, role):
    app_module.app.extensions["auth"].users.add(username, "role-password-1", role=role)
    c = app_module.app.test_client()
    assert c.post("/login", data={"username": username, "password": "role-password-1"}).status_code == 302
    return c


def audit_lines():
    try:
        with open(audit.path(), encoding="utf-8") as f:
            return [e for e in (json.loads(line) for line in f) if e["area"] == "terminal"]
    except FileNotFoundError:
        return []


def read_until(c, sid, text, after=0):
    out = ""
    for _ in range(50):
        body = c.get(f"/api/terminal/{sid}/output?after={after}&wait=0.2").get_json()
        out += body["data"]
        after = body["next"]
        if text in out or body["closed"]:
            return out, after, body["closed"]
    return out, after, None


def test_needs_terminal_open(app_module, client, switch):
    client.put("/api/settings/plugins/demo", json={"enabled": True})
    tech = sign_in(app_module, "fixer", "tech")
    assert tech.get("/api/terminal").status_code == 403
    assert tech.post("/api/terminal", json={"switch": "sw-a-01"}).status_code == 403
    lead = sign_in(app_module, "boss", "lead")
    info = lead.get("/api/terminal").get_json()
    assert info["available"] and "sw-a-01" in info["switches"] and info["sessions"] == []


def test_demo_session_records_every_typed_line(app_module, client, switch):
    client.put("/api/settings/plugins/demo", json={"enabled": True})
    resp = client.post("/api/terminal", json={"switch": "sw-a-01"})
    assert resp.status_code == 201, resp.data
    sid = resp.get_json()["id"]
    out, after, _ = read_until(client, sid, "sw-a-01#")
    # Typed in pieces, with a typo fixed by backspace, like a keyboard does.
    for piece in ("show verx", "\x7f", "sion", "\r"):
        assert client.post(f"/api/terminal/{sid}/input", json={"data": piece}).status_code == 200
    out, after, _ = read_until(client, sid, "Version", after)
    assert "Example Switch Software" in out
    # Someone else can't read or type into it.
    other = sign_in(app_module, "boss", "lead")
    assert other.get(f"/api/terminal/{sid}/output?wait=0").status_code == 404
    assert other.post(f"/api/terminal/{sid}/input", json={"data": "x"}).status_code == 404
    assert client.get("/api/terminal").get_json()["sessions"][0]["switch"] == "sw-a-01"
    assert client.delete(f"/api/terminal/{sid}").status_code == 200
    assert client.get(f"/api/terminal/{sid}/output?wait=0").status_code == 404
    entries = [(e["action"], e["target"]) for e in audit_lines()]
    assert entries == [("Opened terminal", "sw-a-01"), ("Typed", "sw-a-01: show version"),
                       ("Closed terminal", "sw-a-01: Closed by the tech.")]


def test_exit_ends_the_session(client, switch):
    client.put("/api/settings/plugins/demo", json={"enabled": True})
    sid = client.post("/api/terminal", json={"switch": "sw-a-01"}).get_json()["id"]
    client.post(f"/api/terminal/{sid}/input", json={"data": "exit\r"})
    _out, _after, closed = read_until(client, sid, "never")
    assert closed == "The switch closed the connection."


def test_idle_sessions_close_and_limits_hold(client, switch, monkeypatch):
    client.put("/api/settings/plugins/demo", json={"enabled": True})
    monkeypatch.setattr(terminal, "MAX_PER_ACCOUNT", 1)
    sid = client.post("/api/terminal", json={"switch": "sw-a-01"}).get_json()["id"]
    assert client.post("/api/terminal", json={"switch": "sw-a-01"}).status_code == 429
    terminal.prune(now=terminal._sessions[sid].last_input + terminal.idle_seconds() + 1)
    assert sid not in terminal._sessions
    assert client.post("/api/terminal", json={"switch": "core-99"}).status_code == 400


def test_no_plugin_no_terminal(client, switch):
    assert client.get("/api/terminal").get_json()["available"] is False
    assert client.post("/api/terminal", json={"switch": "sw-a-01"}).status_code == 409


# ── The SSH plugin, against a fake switch ────────────────────────────────────────────────

class FakeChannel:
    def __init__(self):
        self.closed, self.sent, self.pending, self.size = False, [], b"sw-a-01#", None

    def recv_ready(self):
        return bool(self.pending)

    def recv(self, n):
        out, self.pending = self.pending, b""
        return out

    def exit_status_ready(self):
        return self.closed

    def sendall(self, data):
        self.sent.append(data)
        if data.strip() == b"enable":
            self.pending += b"\r\nPassword: "

    def resize_pty(self, width, height):
        self.size = (width, height)


class ShellSwitch(FakeSwitch):
    def invoke_shell(self, **kw):
        assert kw["term"] == "xterm"
        self.channel = FakeChannel()
        return self.channel

    def close(self):
        if hasattr(self, "channel"):
            self.channel.closed = True


@pytest.fixture
def ssh(client, app_module, switch, monkeypatch):
    import sys
    registry = app_module.app.extensions["floorbit_plugins"]
    module = sys.modules[registry.specs["ssh-ports"].plugin_class().__module__]
    monkeypatch.setattr(module.paramiko, "SSHClient", ShellSwitch)
    ShellSwitch.key = b"key-one"
    client.put("/api/settings/plugins/ssh-ports", json={"enabled": True})
    yield registry
    client.post("/api/plugins/ssh-ports/actions/forget_hosts", json={})


def test_ssh_terminal_hides_what_is_typed_at_a_password_prompt(client, ssh):
    assert client.post("/api/terminal", json={"switch": "sw-a-01"}).status_code == 400      # no login
    resp = client.post("/api/terminal", json={"switch": "sw-a-01", "username": "kim",
                                              "password": FakeSwitch.password, "cols": 100, "rows": 30})
    assert resp.status_code == 201, resp.data
    sid = resp.get_json()["id"]
    read_until(client, sid, "sw-a-01#")
    client.post(f"/api/terminal/{sid}/input", json={"data": "enable\r"})
    read_until(client, sid, "Password:")
    client.post(f"/api/terminal/{sid}/input", json={"data": "enable-secret-9\r"})
    assert client.post(f"/api/terminal/{sid}/resize", json={"cols": 140, "rows": 40}).status_code == 200
    assert ShellSwitch.last.channel.size == (140, 40)
    assert ShellSwitch.last.channel.sent == [b"enable\r", b"enable-secret-9\r"]
    client.delete(f"/api/terminal/{sid}")
    kept = json.dumps(audit_lines()) + json.dumps(ssh.state_of("ssh-ports"))
    assert "enable-secret-9" not in kept and FakeSwitch.password not in kept
    assert "(hidden: the switch asked for a password)" in kept


def test_ssh_terminal_wrong_login(client, ssh):
    resp = client.post("/api/terminal", json={"switch": "sw-a-01", "username": "kim", "password": "wrong"})
    assert resp.status_code == 502 and "refused the login" in resp.get_json()["error"]
    assert audit_lines()[-1]["action"] == "Opened terminal: failed"
