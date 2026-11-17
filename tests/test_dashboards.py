"""Dashboards: widgets on a grid, each a pane or split panes (floorbit/dashboards.py)."""

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
    assert saved["fit"] is True   # an old one-tree layout fills the screen
    root = saved["sections"][0]["panels"][0]["node"]
    assert saved["sections"][0]["panels"][0] == {"x": 0, "y": 0, "w": 24, "h": 12, "node": root}
    assert root["sizes"] == [60, 40]
    right = root["children"][1]
    assert right["sizes"] == [50, 50]   # missing sizes share the split evenly
    assert right["children"][0]["pane"] == {"kind": "plan", "title": "VIP", "hall": "", "preset": "ops", "show": "all",
                                            "labels": "auto", "area": {"kind": "zone", "id": "z-vip"}}
    assert client.get("/api/dashboards/main-hall").get_json()["name"] == "Main hall wall"
    client.put("/api/dashboards/main-hall", json={**MIXED, "name": "Wall"})
    listed = client.get("/api/dashboards").get_json()
    assert [x["name"] for x in listed["layouts"]] == ["Wall", "Kiosk"]
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
    assert saved["sections"][0]["panels"][0]["node"]["sizes"] == [25, 75]
    assert saved["cycle"] == 30


def test_text_pane(client):
    text = {"kind": "text", "title": "Welcome", "hide_title": True, "size": "xl",
            "text": "# Doors open 18:00\r\n\n- **Wi-Fi**: LAN\x07"}
    saved = client.put("/api/dashboards/info", json={"name": "Info", "root": {"pane": text}}).get_json()
    pane = saved["sections"][0]["panels"][0]["node"]["pane"]
    assert pane == {"kind": "text", "title": "Welcome", "hide_title": True,
                    "text": "# Doors open 18:00\n\n- **Wi-Fi**: LAN", "size": "xl", "align": "start"}
    body = {"name": "Info", "root": {"pane": {**text, "size": "huge"}}}
    assert client.put("/api/dashboards/info", json=body).status_code == 400
    body = {"name": "Info", "root": {"pane": {**text, "text": "x" * 2001}}}
    assert client.put("/api/dashboards/info", json=body).status_code == 400


def _panel(x, y, w, h, kind="empty"):
    return {"x": x, "y": y, "w": w, "h": h, "node": {"pane": {"kind": kind}}}


def test_grid_sections(client):
    body = {"name": "Ops desk", "sections": [
        {"panels": [_panel(12, 0, 12, 6, "text"), _panel(0, 0, 12, 6)]},
        {"title": "Network", "folded": True, "panels": [_panel(0, 0, 24, 8)]},
        {"panels": []},   # a plain divider
    ]}
    saved = client.put("/api/dashboards/desk", json=body).get_json()
    assert saved["fit"] is False
    first, network, divider = saved["sections"]
    assert [p["x"] for p in first["panels"]] == [0, 12]   # reading order
    assert network["title"] == "Network" and network["folded"] is True
    assert divider == {"panels": []}

    def put(*sections):
        return client.put("/api/dashboards/desk", json={"name": "Desk", "sections": list(sections)}).status_code

    assert put({"panels": [_panel(0, 0, 12, 6), _panel(6, 3, 12, 6)]}) == 400   # overlap
    assert put({"panels": [_panel(20, 0, 8, 6)]}) == 400   # past the last column
    assert put({"panels": [_panel(0, 0, 0, 6)]}) == 400
    assert put({"panels": [_panel(0, 0, 4, 1.5)]}) == 400
    assert put() == 400
    assert put(*[{"panels": [_panel(0, 0, 1, 1)]}] * 13) == 400
    assert put({"panels": [_panel(n, 0, 1, 1) for n in range(24)] + [_panel(0, 1, 1, 1)]}) == 400   # 25 panels


def test_old_layouts_read_as_one_panel(app_module, client):
    from floorbit import dashboards, store
    data = store.load_data()
    data["dashboards"] = [{"id": "old", "name": "Old", "root": {"pane": {"kind": "empty"}}}]
    store.save_data(data)
    old = client.get("/api/dashboards/old").get_json()
    assert old["fit"] is True and "root" not in old
    assert old["sections"][0]["panels"][0]["node"] == {"pane": {"kind": "empty"}}
    assert dashboards.get("old")["sections"]


def test_kiosk_is_ready_made_until_replaced(client):
    kiosk = client.get("/api/dashboards/kiosk").get_json()
    assert kiosk["builtin"] is True and kiosk["fit"] is True
    assert kiosk["sections"][0]["panels"][0]["node"]["pane"]["kind"] == "plan"
    assert client.delete("/api/dashboards/kiosk").status_code == 404   # nothing saved to remove
    mine = {"name": "Kiosk", "sections": [{"panels": [_panel(0, 0, 24, 12, "text")]}], "fit": True}
    assert client.put("/api/dashboards/kiosk", json=mine).status_code == 200
    listed = client.get("/api/dashboards").get_json()["layouts"]
    assert [x.get("builtin") for x in listed if x["id"] == "kiosk"] == [None]
    assert client.delete("/api/dashboards/kiosk").status_code == 200
    assert client.get("/api/dashboards/kiosk").get_json()["builtin"] is True


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
    assert put(sections=[{"panels": [{**_panel(0, 0, 8, 4), "node": many}, {**_panel(8, 0, 8, 4), "node": many},
                                     {**_panel(16, 0, 8, 4), "node": many}]}]) == 400   # 48 panes
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
