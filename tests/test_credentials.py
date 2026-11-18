"""Stored switch logins (issue #474): encrypted at rest, write-only, opened only to use."""
import base64
import json
import os
import sys

import pytest
from conftest import stored

from floorbit import credentials, ports, store, vault
from tests.test_ports import SWITCH, FakeSwitch, audit_lines, bounce

# These run the plugins the way the local agent does (tests/conftest.py, lan_here).
pytestmark = pytest.mark.usefixtures("lan_here")


def key_file(path):
    path.write_bytes(base64.b64encode(os.urandom(32)))
    return str(path)


@pytest.fixture(autouse=True)
def secret_key(tmp_path, monkeypatch):
    monkeypatch.setenv("FLOORBIT_SECRET_KEY_FILE", key_file(tmp_path / "key"))
    monkeypatch.delenv("FLOORBIT_SECRET_OLD_KEY_FILES", raising=False)
    for state in (ports._last, ports._failures, ports._busy):
        state.clear()


@pytest.fixture
def ssh(client, app_module, monkeypatch):
    registry = app_module.app.extensions["floorbit_plugins"]
    assert client.post("/api/inventory", json=SWITCH).status_code in (200, 201)
    module = sys.modules[registry.specs["ssh-ports"].plugin_class().__module__]
    monkeypatch.setattr(module.paramiko, "SSHClient", FakeSwitch)
    monkeypatch.setattr(module.time, "sleep", lambda s: None)
    FakeSwitch.key = b"key-one"
    client.put("/api/settings/plugins/ssh-ports", json={"enabled": True})
    yield registry
    client.post("/api/plugins/ssh-ports/actions/forget_hosts", json={})
    for c in client.get("/api/settings/credentials").get_json()["credentials"]:
        client.delete(f"/api/settings/credentials/{c['id']}")


def test_sealed_values_open_only_in_their_own_slot():
    sealed = vault.seal("ssh:a", "pa55word")
    assert "pa55word" not in sealed and vault.open_("ssh:a", sealed) == "pa55word"
    with pytest.raises(vault.VaultError):
        vault.open_("ssh:b", sealed)          # copied into another slot: doesn't open
    assert vault.seal("ssh:a", "pa55word") != sealed     # a new nonce every time


def test_without_a_key_file_one_is_made_next_to_the_data(tmp_path, monkeypatch):
    monkeypatch.delenv("FLOORBIT_SECRET_KEY_FILE")
    monkeypatch.setattr(vault, "default_key_file", lambda: str(tmp_path / "secret.key"))
    sealed = vault.seal("ssh:a", "x")
    assert os.stat(tmp_path / "secret.key").st_mode & 0o777 == 0o600
    assert vault.open_("ssh:a", sealed) == "x"


def test_rotation_writes_everything_again_with_the_new_key(client, tmp_path, monkeypatch):
    client.put("/api/settings/credentials/ssh", json={"scope": "*", "username": "ops", "password": "old-key-secret"})
    old = os.environ["FLOORBIT_SECRET_KEY_FILE"]
    monkeypatch.setenv("FLOORBIT_SECRET_KEY_FILE", key_file(tmp_path / "new"))
    with pytest.raises(credentials.CredentialError):
        credentials.ssh_login_for("sw-a-01")           # the old key is gone
    monkeypatch.setenv("FLOORBIT_SECRET_OLD_KEY_FILES", old)
    assert credentials.ssh_login_for("sw-a-01")["password"] == "old-key-secret"
    assert credentials.rotate() == 1 and credentials.rotate() == 0
    monkeypatch.delenv("FLOORBIT_SECRET_OLD_KEY_FILES")
    assert credentials.ssh_login_for("sw-a-01")["password"] == "old-key-secret"
    client.delete(f"/api/settings/credentials/{credentials.listing()[0]['id']}")


def test_set_list_replace_and_remove_never_show_the_password(client):
    r = client.put("/api/settings/credentials/ssh", json={"scope": "sw-a-*", "username": "ops", "password": "hunter22"})
    assert r.status_code == 200 and "password" not in r.get_json()
    again = client.put("/api/settings/credentials/ssh", json={"scope": "SW-A-*", "username": "ops2", "password": "x"})
    assert again.get_json()["id"] == r.get_json()["id"]                       # replaced, not a second one
    listed = client.get("/api/settings/credentials").get_json()["credentials"]
    assert [(c["scope"], c["username"]) for c in listed] == [("SW-A-*", "ops2")]
    assert "hunter22" not in json.dumps(listed) and "hunter22" not in stored(store.DATA_FILE)
    url = "/api/settings/credentials/ssh"
    assert client.put(url, json={"scope": "a b", "username": "u", "password": "p"}).status_code == 400
    # $ let a final newline through to the switch login; \Z doesn't.
    assert client.put(url, json={"scope": "*", "username": "ops\n", "password": "p"}).status_code == 400
    assert client.put(url, json={"scope": "*", "username": "u", "password": ""}).status_code == 400
    assert client.delete(f"/api/settings/credentials/{listed[0]['id']}").get_json() == {"ok": True}
    assert client.get("/api/settings/credentials").get_json()["credentials"] == []
    actions = [e["action"] for e in audit_lines() if e["area"] == "credentials"]
    assert actions[-3:] == ["Set the switch login for sw-a-*", "Set the switch login for SW-A-*",
                            "Removed the switch login for SW-A-*"]


def test_the_most_specific_login_wins():
    rows = [{"scope": "*", "id": "d"}, {"scope": "sw-*", "id": "p1"}, {"scope": "sw-a-*", "id": "p2"},
            {"scope": "sw-a-07", "id": "x"}]
    assert credentials._match(rows, "sw-a-07.example.com")["id"] == "x"
    assert credentials._match(rows, "sw-a-01")["id"] == "p2"
    assert credentials._match(rows, "sw-b-01")["id"] == "p1"
    assert credentials._match(rows, "core-01")["id"] == "d"
    assert credentials._match(rows[1:], "core-01") is None


def test_a_port_action_uses_the_stored_login_and_says_so(client, ssh):
    client.put("/api/settings/credentials/ssh", json={"scope": "*", "username": "ops", "password": FakeSwitch.password})
    info = client.get("/api/ports").get_json()
    assert info["needs_login"] is False and info["stored_login"] is True     # pages stop asking
    resp = bounce(client)
    assert resp.status_code == 200, resp.data
    assert FakeSwitch.last.logins == ["ops"]
    used = [e for e in audit_lines() if e["area"] == "credentials"][-1]
    assert used["action"] == "Used the stored login for *" and used["target"] == "sw-a-01"
    # A typed login still wins.
    ports._last.clear()
    assert bounce(client, username="kim", password=FakeSwitch.password).status_code == 200
    assert FakeSwitch.last.logins == ["kim"]


def test_a_wrong_stored_password_does_not_lock_the_tech_out(client, ssh):
    client.put("/api/settings/credentials/ssh", json={"scope": "*", "username": "ops", "password": "wrong"})
    assert bounce(client).status_code == 502
    # Blocked after one refusal, so the switch account isn't locked by retries (inventory_scope.py).
    for _ in range(ports.LOGIN_FAILURES + 1):
        ports._last.clear()
        r = bounce(client)
        assert r.status_code == 409 and "failed before" in r.get_json()["error"]
    assert bounce(client, username="kim", password=FakeSwitch.password).status_code == 200
    dev = client.get("/api/inventory").get_json()["devices"][0]
    assert client.post("/api/inventory/blocks/clear", json={"device_id": dev["id"]}).get_json() == {"cleared": 1}
    ports._last.clear()
    assert bounce(client).status_code == 502          # tried again once cleared


def test_only_admins_set_logins(app_module):
    from tests.test_rbac import sign_in_as
    tech = sign_in_as(app_module, "te6", "tech")
    assert tech.get("/api/settings/credentials").status_code == 403
    assert tech.put("/api/settings/credentials/ssh", json={"username": "u", "password": "p"}).status_code == 403
