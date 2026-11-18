"""Secret settings (API tokens, plugins' passwords) are sealed at rest with the vault, like switch
logins: data.json, the database and its backups hold nothing readable (docs/credentials.md)."""
import base64
import os

import pytest
from conftest import stored

from floorbit import settings as settings_mod
from floorbit import store, vault

TOKEN = "token-example-1234"


def key_file(path):
    path.write_bytes(base64.b64encode(os.urandom(32)))
    return str(path)


@pytest.fixture(autouse=True)
def secret_key(tmp_path, monkeypatch):
    monkeypatch.setenv("FLOORBIT_SECRET_KEY_FILE", key_file(tmp_path / "key"))
    monkeypatch.delenv("FLOORBIT_SECRET_OLD_KEY_FILES", raising=False)


def settings_store(app_module):
    return app_module.app.extensions["floorbit_plugins"].settings_store


def test_a_saved_token_is_sealed_and_still_works(client, app_module):
    resp = client.put("/api/settings", json={"librenms.url": "https://librenms.example.com",
                                             "librenms.token": TOKEN})
    assert resp.status_code == 200, resp.data
    assert TOKEN not in stored(store.DATA_FILE)
    saved = store.read_json(store.DATA_FILE)["app_settings"]["librenms.token"]
    assert settings_mod.is_sealed(saved) and saved["sealed"].startswith("v1:")
    assert settings_store(app_module).get("librenms.token") == TOKEN
    value = client.get("/api/settings").get_json()["values"]["librenms.token"]
    assert value["is_set"] is True and "value" not in value and "unreadable" not in value


def test_a_sealed_value_only_opens_in_its_own_slot(client, app_module):
    client.put("/api/settings", json={"librenms.url": "https://librenms.example.com", "librenms.token": TOKEN})
    data = store.read_json(store.DATA_FILE)
    # Copied into another secret's slot (someone with write access to the data), it doesn't open.
    data["app_settings"]["netbox.token"] = data["app_settings"]["librenms.token"]
    store.write_json(store.DATA_FILE, data)
    s = settings_store(app_module)
    s.reload()
    assert s.get("netbox.token") == "" and s.get("librenms.token") == TOKEN
    value = client.get("/api/settings").get_json()["values"]["netbox.token"]
    assert value["is_set"] is False and value["unreadable"] is True


def test_a_token_saved_in_clear_before_still_reads_and_is_sealed_on_the_next_save(client, app_module):
    data = store.read_json(store.DATA_FILE)
    data["app_settings"] = {"netbox.url": "https://netbox.example.com", "netbox.token": TOKEN}
    store.write_json(store.DATA_FILE, data)
    s = settings_store(app_module)
    s.reload()
    assert s.get("netbox.token") == TOKEN
    assert client.put("/api/settings", json={"theme.name": "Example LAN"}).status_code == 200
    assert TOKEN not in stored(store.DATA_FILE)
    assert s.get("netbox.token") == TOKEN


def test_a_lost_key_means_set_it_again_not_a_crash(client, app_module, tmp_path, monkeypatch):
    client.put("/api/settings", json={"librenms.url": "https://librenms.example.com", "librenms.token": TOKEN})
    monkeypatch.setenv("FLOORBIT_SECRET_KEY_FILE", key_file(tmp_path / "other"))
    s = settings_store(app_module)
    s.reload()
    assert s.get("librenms.token") == ""
    assert client.get("/api/settings").status_code == 200
    # Saving it again works with the new key.
    assert client.put("/api/settings", json={"librenms.token": "token-2"}).status_code == 200
    assert s.get("librenms.token") == "token-2"


def test_rotate_seals_again_with_the_new_key(client, app_module, tmp_path, monkeypatch):
    client.put("/api/settings", json={"librenms.url": "https://librenms.example.com", "librenms.token": TOKEN})
    old = os.environ["FLOORBIT_SECRET_KEY_FILE"]
    monkeypatch.setenv("FLOORBIT_SECRET_KEY_FILE", key_file(tmp_path / "new"))
    monkeypatch.setenv("FLOORBIT_SECRET_OLD_KEY_FILES", old)
    assert settings_mod.rotate() == 1
    monkeypatch.delenv("FLOORBIT_SECRET_OLD_KEY_FILES")
    s = settings_store(app_module)
    s.reload()
    assert s.get("librenms.token") == TOKEN
    assert settings_mod.rotate() == 0
    sealed = store.read_json(store.DATA_FILE)["app_settings"]["librenms.token"]["sealed"]
    assert not vault.needs_rotation(sealed)


def test_the_backup_leaves_sealed_secrets_out(client):
    client.put("/api/settings", json={"librenms.url": "https://librenms.example.com", "librenms.token": TOKEN})
    body = client.get("/api/settings/backup").get_data(as_text=True)
    assert "librenms.token" not in body and "sealed" not in body
