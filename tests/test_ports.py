"""Port actions (issue #16): bounce a seat's port through a plugin, with the tech's own login."""
import json

import pytest

from floorbit import audit, ports

SWITCH = {"name": "sw-a-01", "mgmt_ip": "198.51.100.4", "role": "switch"}


@pytest.fixture(autouse=True)
def fresh_ports():
    for state in (ports._last, ports._failures, ports._busy):
        state.clear()


@pytest.fixture
def registry(app_module):
    return app_module.app.extensions["floorbit_plugins"]


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
            return [json.loads(line) for line in f]
    except FileNotFoundError:
        return []


def test_needs_ports_act(app_module, client):
    viewer = sign_in(app_module, "watcher", "viewer")
    assert viewer.get("/api/ports").status_code == 403
    assert viewer.post("/api/ports/bounce", json={"seat": "A-1"}).status_code == 403
    tech = sign_in(app_module, "fixer", "tech")
    assert tech.get("/api/ports").get_json() == {"available": False, "needs_login": False, "plugin": None}


def test_no_plugin_no_bounce(client, switch):
    resp = client.post("/api/ports/bounce", json={"switch": "sw-a-01", "port": "Gi1/0/3"})
    assert resp.status_code == 409 and "Settings > Plugins" in resp.get_json()["error"]


def test_demo_bounce_takes_the_port_down_and_is_audited(client, switch):
    client.put("/api/settings/plugins/demo", json={"enabled": True})
    assert client.get("/api/ports").get_json()["needs_login"] is False
    resp = client.post("/api/ports/bounce", json={"switch": "sw-a-01", "port": "Gi1/0/3"})
    assert resp.status_code == 200, resp.data
    assert resp.get_json()["port"] == "Gi1/0/3"
    from floorbit import sources
    assert sources.monitoring().port_stats("sw-a-01.example.com", "Gi1/0/3")["state"] == "down"
    again = client.post("/api/ports/bounce", json={"switch": "sw-a-01", "port": "Gi1/0/3"})
    assert again.status_code == 429
    entries = [e for e in audit_lines() if e["area"] == "ports"]
    assert [(e["action"], e.get("ok", True)) for e in entries] == [("Bounced port", True),
                                                                   ("Bounced port: failed", False)]
    assert entries[0]["target"] == "sw-a-01 Gi1/0/3"


def test_a_seat_is_resolved_by_the_server(client, switch, monkeypatch):
    client.put("/api/settings/plugins/demo", json={"enabled": True})
    from integrations import seat_sources
    monkeypatch.setattr(seat_sources, "load", lambda *a, **k: {"A-1": {"ip_address": "192.0.2.10"}})
    resp = client.post("/api/ports/bounce", json={"seat": "a-1", "switch": "core-01", "port": "Gi9/9/9"})
    body = resp.get_json()
    assert resp.status_code == 200, body
    # The switch and port the browser sent are ignored: the seat decides.
    assert (body["switch"], body["port"], body["seat"]) == ("sw-a-01", "Gi1/0/1", "A-1")
    assert client.post("/api/ports/bounce", json={"seat": "Z-9"}).status_code == 400



def test_a_seat_without_an_ip_uses_the_port_description(client, switch, app_module, monkeypatch):
    # An offline seat often has no IP yet; its port is still known from the switch's descriptions.
    client.put("/api/settings/plugins/demo", json={"enabled": True})
    from integrations import seat_sources
    monkeypatch.setattr(seat_sources, "load", lambda *a, **k: {})
    watch = app_module.app.extensions["floorbit_attention"]
    monkeypatch.setattr(watch, "port_seats", {("sw-a-01", "Gi1/0/7"): "A-7"}, raising=False)
    body = client.post("/api/ports/bounce", json={"seat": "A-7"}).get_json()
    assert (body["switch"], body["port"], body["seat"]) == ("sw-a-01", "Gi1/0/7", "A-7")
    assert "no IP or MAC" in client.post("/api/ports/bounce", json={"seat": "A-8"}).get_json()["error"]

@pytest.mark.parametrize("port", ["Gi1/0/1\nreload", "Gi1/0/1; reload", "", " ", "x" * 60, "-shutdown"])
def test_port_names_are_checked(client, switch, port):
    client.put("/api/settings/plugins/demo", json={"enabled": True})
    assert client.post("/api/ports/bounce", json={"switch": "sw-a-01", "port": port}).status_code == 400


def test_the_switch_must_be_in_the_inventory_with_an_address(client):
    client.put("/api/settings/plugins/demo", json={"enabled": True})
    resp = client.post("/api/ports/bounce", json={"switch": "sw-b-02", "port": "Gi1/0/1"})
    assert resp.status_code == 400 and "inventory" in resp.get_json()["error"]
    client.post("/api/inventory", json={"name": "sw-b-02", "role": "switch"})
    resp = client.post("/api/ports/bounce", json={"switch": "sw-b-02", "port": "Gi1/0/1"})
    assert resp.status_code == 400 and "management IP" in resp.get_json()["error"]


# ── The SSH plugin, against a fake switch ────────────────────────────────────────────────

class FakeKey:
    def __init__(self, blob):
        self.blob = blob

    def get_name(self):
        return "ssh-ed25519"

    def asbytes(self):
        return self.blob


class FakeShell:
    def __init__(self, switch):
        self.switch, self.pending = switch, "sw-a-01#"

    def settimeout(self, t):
        pass

    def recv_ready(self):
        return bool(self.pending)

    def recv(self, n):
        out, self.pending = self.pending, ""
        return out.encode()

    def send(self, text):
        self.switch.sent.append(text.strip())
        bad = text.strip().startswith("interface Bogus")
        self.pending = text + ("% Invalid input detected at '^' marker.\r\n" if bad else "") + "sw-a-01(config)#"


class FakeSwitch:
    """Stands in for paramiko.SSHClient: one SSH server with a host key and one account."""
    key = b"key-one"
    password = "s3cret-switch-pass"

    def __init__(self):
        self.sent, self.policy, self.logins = [], None, []
        FakeSwitch.last = self

    def set_missing_host_key_policy(self, policy):
        self.policy = policy

    def connect(self, host, port, username, password, **kw):
        assert kw["look_for_keys"] is False and kw["allow_agent"] is False
        self.policy.missing_host_key(self, host, FakeKey(FakeSwitch.key))
        self.logins.append(username)
        if password != FakeSwitch.password:
            import paramiko
            raise paramiko.AuthenticationException("Authentication failed.")

    def invoke_shell(self, **kw):
        return FakeShell(self)

    def close(self):
        pass


@pytest.fixture
def ssh(client, registry, switch, monkeypatch):
    import sys
    module = sys.modules[registry.specs["ssh-ports"].plugin_class().__module__]
    monkeypatch.setattr(module.paramiko, "SSHClient", FakeSwitch)
    monkeypatch.setattr(module.time, "sleep", lambda s: None)
    FakeSwitch.key = b"key-one"
    client.put("/api/settings/plugins/ssh-ports", json={"enabled": True})
    yield module
    client.post("/api/plugins/ssh-ports/actions/forget_hosts", json={})


def bounce(c, **extra):
    return c.post("/api/ports/bounce", json={"switch": "sw-a-01", "port": "Gi1/0/3", **extra})


def test_ssh_needs_the_techs_login(client, ssh):
    assert client.get("/api/ports").get_json() == {"available": True, "needs_login": True,
                                                   "plugin": "SSH port actions"}
    assert bounce(client).status_code == 400
    assert bounce(client, username="kim", password="").status_code == 400


def test_ssh_bounce_runs_the_platform_commands_and_keeps_no_password(client, ssh, registry):
    resp = bounce(client, username="kim", password=FakeSwitch.password)
    assert resp.status_code == 200, resp.data
    assert FakeSwitch.last.sent == ["configure terminal", "interface Gi1/0/3", "shutdown", "end",
                                    "configure terminal", "interface Gi1/0/3", "no shutdown", "end"]
    assert FakeSwitch.last.logins == ["kim"]
    # The password is nowhere Floorbit keeps anything.
    kept = [json.dumps(audit_lines()), json.dumps(registry.state_of("ssh-ports")),
            json.dumps(client.get("/api/settings/plugins/ssh-ports/log").get_json() or {})]
    from floorbit import store
    for path in (registry.path(), store.DATA_FILE):
        with open(path, encoding="utf-8") as f:
            kept.append(f.read())
    assert not any(FakeSwitch.password in text for text in kept)
    assert list(registry.state_of("ssh-ports")["hosts"]) == ["198.51.100.4"]


def test_ssh_refuses_a_changed_host_key(client, ssh):
    assert bounce(client, username="kim", password=FakeSwitch.password).status_code == 200
    ports._last.clear()
    FakeSwitch.key = b"key-two"
    resp = bounce(client, username="kim", password=FakeSwitch.password)
    assert resp.status_code == 502 and "host key" in resp.get_json()["error"]
    assert FakeSwitch.last.sent == []                 # nothing was sent to the impostor


def test_ssh_failed_logins_pause_the_account(client, ssh):
    for _ in range(ports.LOGIN_FAILURES):
        resp = bounce(client, username="kim", password="wrong")
        assert resp.status_code == 502 and "refused the login" in resp.get_json()["error"]
    resp = bounce(client, username="kim", password=FakeSwitch.password)
    assert resp.status_code == 429


def test_ssh_reports_a_refused_command(client, ssh, switch):
    resp = client.post("/api/ports/bounce", json={"switch": "sw-a-01", "port": "Bogus1",
                                                    "username": "kim", "password": FakeSwitch.password})
    assert resp.status_code == 502 and "refused" in resp.get_json()["error"]
    assert "shutdown" not in FakeSwitch.last.sent       # stopped before taking anything down
