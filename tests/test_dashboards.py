"""Dashboards: screens split into panes (floorbit/dashboards.py)."""

MIXED = {
    "name": "Main hall wall",
    "root": {"split": "row", "sizes": [60, 40], "children": [
        {"pane": {"kind": "plan", "hall": "", "area": {"kind": "hall"}, "preset": "overview"}},
        {"split": "column", "children": [
            {"pane": {"kind": "plan", "area": {"kind": "zone", "id": "z-vip"}, "preset": "ops", "title": "VIP"}},
            {"pane": {"kind": "plan", "area": {"kind": "box", "x": 0, "y": 0, "w": 800, "h": 500},
                      "preset": "network", "labels": "none"}},
        ]},
    ]},
}


def _login(app_module, name, role):
    app_module.app.extensions["auth"].users.add(name, f"{name}-password-1", role=role)
    c = app_module.app.test_client()
    assert c.post("/login", data={"username": name, "password": f"{name}-password-1"}).status_code == 302
    return c


def test_save_read_replace_delete(client):
    r = client.put("/api/dashboards/main-hall", json=MIXED)
    assert r.status_code == 200, r.get_json()
    saved = r.get_json()
    assert saved["root"]["sizes"] == [60, 40]
    right = saved["root"]["children"][1]
    assert right["sizes"] == [50, 50]   # missing sizes share the split evenly
    assert right["children"][0]["pane"] == {"kind": "plan", "title": "VIP", "hall": "", "preset": "ops", "show": "all",
                                            "labels": "auto", "area": {"kind": "zone", "id": "z-vip"}}
    assert client.get("/api/dashboards/main-hall").get_json()["name"] == "Main hall wall"
    client.put("/api/dashboards/main-hall", json={**MIXED, "name": "Wall"})
    listed = client.get("/api/dashboards").get_json()
    assert [x["name"] for x in listed["layouts"]] == ["Wall"]
    assert "health" in listed["pages"]
    assert client.delete("/api/dashboards/main-hall").status_code == 200
    assert client.delete("/api/dashboards/main-hall").status_code == 404
    assert client.get("/api/dashboards/main-hall").status_code == 404


def test_other_panes(client):
    body = {"name": "Ops", "cycle": 30, "root": {"split": "column", "sizes": [1, 3], "children": [
        {"pane": {"kind": "tile", "tile": "demo/w/dhcp"}},
        {"split": "row", "children": [
            {"pane": {"kind": "dashboard", "layout": "ops-desk"}},
            {"pane": {"kind": "page", "page": "health"}},
            {"pane": {"kind": "view", "view": "lancache"}},
            {"pane": {"kind": "empty"}},
        ]},
    ]}}
    saved = client.put("/api/dashboards/ops", json=body).get_json()
    assert saved["root"]["sizes"] == [25, 75]
    assert saved["cycle"] == 30


def test_checks(client):
    def put(**change):
        return client.put("/api/dashboards/wall", json={**MIXED, **change}).status_code

    assert client.put("/api/dashboards/Bad%20Id", json=MIXED).status_code == 400
    assert put(name=" ") == 400
    assert put(root={"pane": {"kind": "iframe", "url": "https://example.com"}}) == 400
    assert put(root={"pane": {"kind": "page", "page": "https://example.com"}}) == 400
    assert put(root={"pane": {"kind": "plan", "preset": "everything"}}) == 400
    assert put(root={"pane": {"kind": "plan", "area": {"kind": "block"}}}) == 400
    assert put(root={"pane": {"kind": "plan", "area": {"kind": "box", "x": 0, "y": 0, "w": "nan", "h": 5}}}) == 400
    assert put(root={"pane": {"kind": "tile", "tile": "../etc"}}) == 400
    assert put(root={"split": "row", "children": [{"pane": {"kind": "empty"}}]}) == 400
    assert put(root={"split": "diagonal", "children": [{"pane": {"kind": "empty"}}] * 2}) == 400
    assert put(cycle=3) == 400
    many = {"split": "row", "children": [{"split": "column", "children": [{"pane": {"kind": "empty"}}] * 4}] * 4}
    assert put(root=many) == 400   # 16 panes
    deep = {"pane": {"kind": "empty"}}
    for _ in range(5):
        deep = {"split": "row", "children": [deep, {"pane": {"kind": "empty"}}]}
    assert put(root=deep) == 400


def test_viewers_read_editors_write(app_module, client):
    client.put("/api/dashboards/wall", json=MIXED)
    viewer = _login(app_module, "vic", "viewer")
    assert viewer.get("/api/dashboards").status_code == 200
    assert viewer.get("/api/dashboards/wall").status_code == 200
    assert viewer.put("/api/dashboards/wall", json=MIXED).status_code == 403
    assert viewer.delete("/api/dashboards/wall").status_code == 403
