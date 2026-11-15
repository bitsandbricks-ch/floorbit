"""Switch commands (issue #94): saved templates on many switches, role-gated, audited, no stored login."""
import json

import pytest

from floorbit import audit, commands, ports
from tests.test_ports import FakeShell, FakeSwitch

SWITCHES = [{"name": "sw-a-01", "mgmt_ip": "198.51.100.4", "role": "switch"},
            {"name": "sw-a-02", "mgmt_ip": "198.51.100.5", "role": "switch"}]


@pytest.fixture(autouse=True)
def fresh_ports():
    for state in (ports._last, ports._failures, ports._busy):
        state.clear()


@pytest.fixture
def switches(client):
    for s in SWITCHES:
        assert client.post("/api/inventory", json=s).status_code in (200, 201)


def sign_in(app_module, username, role):
    app_module.app.extensions["auth"].users.add(username, "role-password-1", role=role)
    c = app_module.app.test_client()
    assert c.post("/login", data={"username": username, "password": "role-password-1"}).status_code == 302
    return c


def audit_lines(area="commands"):
    try:
        with open(audit.path(), encoding="utf-8") as f:
            return [e for e in (json.loads(line) for line in f) if e["area"] == area]
    except FileNotFoundError:
        return []


def run(c, template, **extra):
    return c.post("/api/commands/run", json={"template": template, "switches": ["sw-a-01", "sw-a-02"], **extra})


def test_templates_are_role_gated(app_module, client, switches):
    client.put("/api/settings/plugins/demo", json={"enabled": True})
    viewer = sign_in(app_module, "watcher", "viewer")
    assert viewer.get("/api/commands").status_code == 403
    tech = sign_in(app_module, "fixer", "tech")
    info = tech.get("/api/commands").get_json()
    assert info["available"] and info["needs_login"] is False and "sw-a-01" in info["switches"]
    assert {t["kind"] for t in info["templates"]} == {"show"}
    resp = run(tech, "clear_counters", port="Gi1/0/3", confirm=True)
    assert resp.status_code == 403
    lead = sign_in(app_module, "boss", "lead")
    assert "clear_counters" in [t["id"] for t in lead.get("/api/commands").get_json()["templates"]]
    # A change template asks a second time before it runs.
    first = run(lead, "clear_counters", port="Gi1/0/3")
    assert first.status_code == 409 and first.get_json()["confirm"] is True
    assert run(lead, "clear_counters", port="Gi1/0/3", confirm=True).status_code == 200


def test_demo_runs_on_many_switches_side_by_side_and_audits_each(client, switches):
    client.put("/api/settings/plugins/demo", json={"enabled": True})
    resp = run(client, "port_macs", port="Gi1/0/1")
    body = resp.get_json()
    assert resp.status_code == 200, body
    assert body["commands"] == ["show mac address-table interface Gi1/0/1"]
    assert [r["switch"] for r in body["results"]] == ["sw-a-01", "sw-a-02"]
    assert all(r["ok"] for r in body["results"]) and "0200.0000.0000" in body["results"][0]["output"]
    entries = audit_lines()
    assert [(e["action"], e["target"]) for e in entries] == [("Ran MAC addresses on a port", "sw-a-01 Gi1/0/1"),
                                                             ("Ran MAC addresses on a port", "sw-a-02 Gi1/0/1")]
    assert "0200" not in json.dumps(entries)          # the output stays out of the audit log


def test_requests_are_checked(client, switches):
    client.put("/api/settings/plugins/demo", json={"enabled": True})
    assert run(client, "nope").status_code == 404
    assert run(client, "port_status").status_code == 400                       # no port
    assert run(client, "port_status", port="Gi1/0/1; reload").status_code == 400
    assert client.post("/api/commands/run", json={"template": "version", "switches": []}).status_code == 400
    assert client.post("/api/commands/run", json={"template": "version", "switches": ["core-99"]}).status_code == 400
    many = [f"sw-{i}" for i in range(commands.MAX_SWITCHES + 1)]
    assert client.post("/api/commands/run", json={"template": "version", "switches": many}).status_code == 400


def test_no_plugin_no_commands(client, switches):
    assert client.get("/api/commands").get_json()["available"] is False
    assert run(client, "version").status_code == 409


def test_custom_templates(app_module, client, switches):
    client.put("/api/settings/plugins/demo", json={"enabled": True})
    # A show template can only read.
    bad = client.put("/api/commands/templates/uplinks", json={"label": "Uplinks", "kind": "show",
                                                              "commands": ["configure terminal"]})
    assert bad.status_code == 400 and "change template" in bad.get_json()["error"]
    assert client.put("/api/commands/templates/version", json={"label": "x", "kind": "show",
                                                               "commands": ["show clock"]}).status_code == 400
    assert client.put("/api/commands/templates/x", json={"label": "x", "kind": "show",
                                                         "commands": ["show {vlan}"]}).status_code == 400
    ok = client.put("/api/commands/templates/uplinks", json={"label": "Uplinks", "kind": "show",
                                                             "commands": "show interfaces {port}\nshow version"})
    assert ok.status_code == 200 and ok.get_json()["template"]["commands"] == ["show interfaces {port}",
                                                                                "show version"]
    tpl = next(t for t in client.get("/api/commands").get_json()["templates"] if t["id"] == "uplinks")
    assert tpl["needs_port"] is True and tpl["builtin"] is False
    lead = sign_in(app_module, "boss", "lead")
    assert lead.put("/api/commands/templates/other", json={"label": "o", "kind": "show",
                                                           "commands": ["show clock"]}).status_code == 403
    assert client.delete("/api/commands/templates/uplinks").status_code == 200
    assert client.delete("/api/commands/templates/uplinks").status_code == 404


# ── The SSH plugin, against a fake switch ────────────────────────────────────────────────

class ShowShell(FakeShell):
    def send(self, text):
        command = text.strip()
        self.switch.sent.append(command)
        answer = {"show version": "Example IOS 17.9\r\nuptime is 3 days\r\n",
                  "terminal length 0": ""}.get(command, "% Invalid input detected at '^' marker.\r\n")
        self.pending = f"{command}\r\n{answer}sw-a-01#"


class ShowSwitch(FakeSwitch):
    def invoke_shell(self, **kw):
        return ShowShell(self)


@pytest.fixture
def ssh(client, app_module, switches, monkeypatch):
    import sys
    registry = app_module.app.extensions["floorbit_plugins"]
    module = sys.modules[registry.specs["ssh-ports"].plugin_class().__module__]
    monkeypatch.setattr(module.paramiko, "SSHClient", ShowSwitch)
    ShowSwitch.key = b"key-one"
    client.put("/api/settings/plugins/ssh-ports", json={"enabled": True})
    yield registry
    client.post("/api/plugins/ssh-ports/actions/forget_hosts", json={})


def test_ssh_runs_show_commands_with_the_techs_login_and_keeps_no_password(client, ssh):
    assert run(client, "version").status_code == 400                            # no login
    resp = client.post("/api/commands/run", json={"template": "version", "switches": ["sw-a-01"],
                                                  "username": "kim", "password": FakeSwitch.password})
    body = resp.get_json()
    assert resp.status_code == 200, body
    result = body["results"][0]
    assert result["ok"] and result["output"] == "Example IOS 17.9\nuptime is 3 days"
    assert ShowSwitch.last.sent == ["terminal length 0", "show version"]
    kept = [json.dumps(audit_lines()), json.dumps(ssh.state_of("ssh-ports"))]
    from floorbit import store
    for path in (ssh.path(), store.DATA_FILE):
        with open(path, encoding="utf-8") as f:
            kept.append(f.read())
    assert not any(FakeSwitch.password in text for text in kept)


def test_ssh_refused_command_and_wrong_login(client, ssh):
    resp = client.post("/api/commands/run", json={"template": "all_ports", "switches": ["sw-a-01"],
                                                  "username": "kim", "password": FakeSwitch.password})
    result = resp.get_json()["results"][0]
    assert result["ok"] is False and "refused" in result["error"] and "Invalid input" in result["output"]
    for _ in range(ports.LOGIN_FAILURES):
        resp = client.post("/api/commands/run", json={"template": "version", "switches": ["sw-a-01"],
                                                      "username": "kim", "password": "wrong"})
        assert "refused the login" in resp.get_json()["results"][0]["error"]
    resp = client.post("/api/commands/run", json={"template": "version", "switches": ["sw-a-01"],
                                                  "username": "kim", "password": FakeSwitch.password})
    assert resp.status_code == 429
