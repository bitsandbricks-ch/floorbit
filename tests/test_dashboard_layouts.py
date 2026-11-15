"""Saved dashboard layouts (issue #103)."""


def _login(app_module, name, role):
    app_module.app.extensions["auth"].users.add(name, f"{name}-password-1", role=role)
    c = app_module.app.test_client()
    assert c.post("/login", data={"username": name, "password": f"{name}-password-1"}).status_code == 302
    return c


def test_save_list_replace_delete(client):
    body = {"name": "Ops desk", "tiles": ["demo/w/dhcp", "demo/a/check", "demo/w/dhcp"], "columns": 2}
    r = client.put("/api/dashboard/layouts/ops-desk", json=body)
    assert r.status_code == 200
    assert r.get_json()["tiles"] == ["demo/w/dhcp", "demo/a/check"]
    client.put("/api/dashboard/layouts/ops-desk", json={**body, "name": "Ops"})
    layouts = client.get("/api/dashboard/layouts").get_json()["layouts"]
    assert [(x["id"], x["name"], x["columns"]) for x in layouts] == [("ops-desk", "Ops", 2)]
    assert client.delete("/api/dashboard/layouts/ops-desk").status_code == 200
    assert client.delete("/api/dashboard/layouts/ops-desk").status_code == 404
    assert client.get("/api/dashboard/layouts").get_json()["layouts"] == []


def test_checks(client):
    ok = {"name": "Wall", "tiles": ["demo/w/dhcp"], "columns": 3}
    assert client.put("/api/dashboard/layouts/Bad%20Id", json=ok).status_code == 400
    assert client.put("/api/dashboard/layouts/wall", json={**ok, "name": " "}).status_code == 400
    assert client.put("/api/dashboard/layouts/wall", json={**ok, "tiles": []}).status_code == 400
    assert client.put("/api/dashboard/layouts/wall", json={**ok, "tiles": ["../etc"]}).status_code == 400
    assert client.put("/api/dashboard/layouts/wall", json={**ok, "columns": 9}).status_code == 400


def test_viewers_read_editors_write(app_module, client):
    client.put("/api/dashboard/layouts/wall", json={"name": "Wall", "tiles": ["demo/w/dhcp"]})
    viewer = _login(app_module, "vic", "viewer")
    assert viewer.get("/api/dashboard/layouts").status_code == 200
    assert viewer.put("/api/dashboard/layouts/wall", json={"name": "x", "tiles": ["a/w/b"]}).status_code == 403
    assert viewer.delete("/api/dashboard/layouts/wall").status_code == 403
