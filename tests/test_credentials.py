"""Stored switch logins (issue #474): the inventory's SSH credentials, encrypted at rest, write-only,
opened only to use."""
import base64
import os
import sys

import pytest
from conftest import stored

from floorbit import credentials, inventory_scope, ports, store, upgrades, vault
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
    for c in client.get("/api/inventory/credentials").get_json()["credentials"]:
        client.delete(f"/api/inventory/credentials/{c['id']}")


def store_login(client, username, password, **where):
    body = {"owner_type": "defaults", "kind": "ssh", "username": username, "secret": password, **where}
    r = client.put("/api/inventory/credentials", json=body)
    assert r.status_code == 200, r.get_json()
    return r.get_json()


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
    client.post("/api/inventory", json=SWITCH)
    store_login(client, "ops", "old-key-secret")
    old = os.environ["FLOORBIT_SECRET_KEY_FILE"]
    monkeypatch.setenv("FLOORBIT_SECRET_KEY_FILE", key_file(tmp_path / "new"))
    with pytest.raises(credentials.CredentialError):
        credentials.ssh_login_for("sw-a-01")           # the old key is gone
    monkeypatch.setenv("FLOORBIT_SECRET_OLD_KEY_FILES", old)
    assert credentials.ssh_login_for("sw-a-01")["password"] == "old-key-secret"
    assert inventory_scope.rotate() == 1 and inventory_scope.rotate() == 0
    monkeypatch.delenv("FLOORBIT_SECRET_OLD_KEY_FILES")
    assert credentials.ssh_login_for("sw-a-01")["password"] == "old-key-secret"
    assert "old-key-secret" not in stored(store.DATA_FILE)


def test_a_switch_outside_the_inventory_has_no_stored_login(client):
    store_login(client, "ops", "pa55word")
    assert credentials.any_set() and credentials.has_default()
    assert not credentials.covers("sw-nowhere-01") and credentials.ssh_login_for("sw-nowhere-01") is None


def test_the_old_switch_logins_page_opens_the_inventory(client):
    r = client.get("/settings/credentials")
    assert r.status_code == 302 and r.headers["Location"].endswith("/inventory")
    assert client.get("/api/settings/credentials").status_code == 404


def test_switch_logins_become_inventory_credentials(client):
    """Settings > Switch logins (by name pattern) moved into the inventory once (Mike, 2026-11-18)."""
    for name in ("sw-a-01", "sw-a-02", "sw-b-01", "core-01"):
        client.post("/api/inventory", json={"name": name, "role": "switch"})
    data = store.load_data()

    def old(scope, user, password):
        entry = {"id": f"id{len(data.setdefault('credentials', []))}", "kind": "ssh", "scope": scope,
                 "username": user, "set_at": 1.0, "set_by": "admin"}
        entry["password"] = vault.seal(f"ssh:{entry['id']}", password)
        data["credentials"].append(entry)
    old("*", "ops", "every-pw")
    old("sw-a-*", "ops-a", "hall-a-pw")
    old("core-01", "root", "core-pw")
    old("sw-gone-*", "x", "y")                     # matches nothing yet: a tag nobody has
    data[upgrades.KEY] = upgrades.STEPS.index(upgrades._switch_logins)
    store.write_json(store.DATA_FILE, dict(data))
    upgrades.run_at_start(log=lambda *_: None)

    data = store.load_data()
    assert "credentials" not in data
    assert {t["name"] for t in inventory_scope.tags(data)} == {"sw-a-*", "sw-gone-*"}
    got = {n: credentials.ssh_login_for(n) for n in ("sw-a-01", "sw-a-02", "sw-b-01", "core-01")}
    assert {n: (c["username"], c["password"]) for n, c in got.items()} == {
        "sw-a-01": ("ops-a", "hall-a-pw"), "sw-a-02": ("ops-a", "hall-a-pw"),
        "sw-b-01": ("ops", "every-pw"), "core-01": ("root", "core-pw")}
    assert not any(pw in stored(store.DATA_FILE) for pw in ("every-pw", "hall-a-pw", "core-pw"))


def test_a_port_action_uses_the_stored_login_and_says_so(client, ssh):
    store_login(client, "ops", FakeSwitch.password)
    info = client.get("/api/ports").get_json()
    assert info["needs_login"] is False and info["stored_login"] is True     # pages stop asking
    resp = bounce(client)
    assert resp.status_code == 200, resp.data
    assert FakeSwitch.last.logins == ["ops"]
    used = [e for e in audit_lines() if e["area"] == "credentials"][-1]
    assert used["action"] == "Used the stored ssh login set on defaults All devices" and used["target"] == "sw-a-01"
    # A typed login still wins.
    ports._last.clear()
    assert bounce(client, username="kim", password=FakeSwitch.password).status_code == 200
    assert FakeSwitch.last.logins == ["kim"]


def test_a_wrong_stored_password_does_not_lock_the_tech_out(client, ssh):
    store_login(client, "ops", "wrong")
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
    body = {"owner_type": "defaults", "kind": "ssh", "username": "u", "secret": "p"}
    assert tech.put("/api/inventory/credentials", json=body).status_code == 403
