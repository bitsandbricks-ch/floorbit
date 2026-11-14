"""Backup and restore (Settings > Backup and restore)."""


def place_things(client):
    sw = client.post("/api/switches", json={"name": "sw-demo-01", "x": 10, "y": 20}).get_json()
    block = client.post("/api/seat-blocks", json={"x": 30, "y": 40, "cols": 4, "rows": 2, "label": "A"}).get_json()
    assert client.put("/api/settings", json={
        "theme.preset": "ops", "theme.name": "Example LAN", "netbox.token": "secret-token-123",
    }).status_code == 200
    return sw, block


def test_backup_has_layout_and_settings_but_no_secrets(client):
    place_things(client)
    resp = client.get("/api/settings/backup")
    assert resp.status_code == 200
    assert 'attachment; filename="floorbit-backup-' in resp.headers["Content-Disposition"]
    backup = resp.get_json()
    assert backup["format"] == "floorbit-backup" and backup["version"] == 1
    assert [s["name"] for s in backup["layout"]["switches"]] == ["sw-demo-01"]
    assert len(backup["layout"]["seat_blocks"]) == 1
    assert backup["settings"]["theme.preset"] == "ops"
    text = resp.get_data(as_text=True)
    assert "secret-token-123" not in text and "netbox.token" not in text
    assert "auth_users" not in text and "auth_secret_key" not in text


def test_restore_replaces_layout_and_keeps_secrets_and_accounts(client):
    place_things(client)
    backup = client.get("/api/settings/backup").get_json()

    # Change everything after the backup was taken.
    client.post("/api/switches", json={"name": "sw-demo-02", "x": 50, "y": 50})
    for b in client.get("/api/seat-blocks").get_json():
        client.delete(f"/api/seat-blocks/{b['id']}")
    client.put("/api/settings", json={"theme.preset": "classic"})

    resp = client.post("/api/settings/backup", json=backup)
    assert resp.status_code == 200, resp.data
    assert resp.get_json()["restored"]["seat_blocks"] == 1

    assert [s["name"] for s in client.get("/api/switches").get_json()] == ["sw-demo-01"]
    assert len(client.get("/api/seat-blocks").get_json()) == 1
    values = client.get("/api/settings").get_json()["values"]
    assert values["theme.preset"]["value"] == "ops"
    assert values["netbox.token"]["is_set"]   # the token survived a backup that never had it
    assert client.get("/api/settings").status_code == 200   # still signed in: accounts untouched


def test_restore_ignores_secrets_smuggled_into_a_backup(client):
    backup = client.get("/api/settings/backup").get_json()
    backup["settings"]["netbox.token"] = "planted"
    backup["settings"]["not.a.setting"] = 1
    resp = client.post("/api/settings/backup", json=backup)
    assert resp.status_code == 200
    assert resp.get_json()["skipped_settings"] == ["netbox.token", "not.a.setting"]
    assert not client.get("/api/settings").get_json()["values"]["netbox.token"]["is_set"]


def test_bad_backups_change_nothing(client):
    sw, _ = place_things(client)
    good = client.get("/api/settings/backup").get_json()
    bad = [
        {"hello": "world"},
        {**good, "version": 99},
        {**good, "layout": {"switches": "nope"}},
        {**good, "layout": {"switches": [{"name": "no id"}]}},
        {**good, "layout": {"accounts": []}},
        {**good, "layout": {}, "settings": {"theme.accent": "pink"}},   # bad value: nothing written
    ]
    for backup in bad:
        resp = client.post("/api/settings/backup", json=backup)
        assert resp.status_code == 400, backup
        assert resp.get_json()["error"]
    assert client.post("/api/settings/backup", data="not json",
                       content_type="application/json").status_code == 400
    assert [s["id"] for s in client.get("/api/switches").get_json()] == [sw["id"]]


def test_backup_is_admin_only(anon_client, client, app_module):
    assert anon_client.get("/api/settings/backup").status_code == 401
    assert anon_client.post("/api/settings/backup", json={}).status_code == 401
    users = app_module.app.extensions["auth"].users
    users.add("ed", "editor-password-1", role="editor")
    editor = app_module.app.test_client()
    assert editor.post("/login", data={"username": "ed", "password": "editor-password-1"}).status_code == 302
    assert editor.get("/api/settings/backup").status_code == 403


def test_settings_page_offers_backup(client):
    page = client.get("/settings").get_data(as_text=True)
    assert 'href="/api/settings/backup"' in page and "/static/js/backup.js" in page
