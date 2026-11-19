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
                                            "labels": "auto", "marks": "all", "area": {"kind": "zone", "id": "z-vip"}}
    assert client.get("/api/dashboards/main-hall").get_json()["name"] == "Main hall wall"
    client.put("/api/dashboards/main-hall", json={**MIXED, "name": "Wall"})
    listed = client.get("/api/dashboards").get_json()
    names = [x["name"] for x in listed["layouts"]]
    assert names[:2] == ["Wall", "Kiosk"] and {"Network", "Services", "Traffic", "Event in numbers"} <= set(names)
    assert "pages" not in listed
    assert client.delete("/api/dashboards/main-hall").status_code == 200
    assert client.delete("/api/dashboards/main-hall").status_code == 404
    assert client.get("/api/dashboards/main-hall").status_code == 404


def test_other_panes(client):
    body = {"name": "Ops", "cycle": 30, "root": {"split": "column", "sizes": [1, 3], "children": [
        {"pane": {"kind": "tile", "tile": "demo/w/dhcp"}},
        {"split": "row", "children": [
            {"pane": {"kind": "view", "view": "health", "expanded": True}},
            {"pane": {"kind": "view", "view": "lancache", "expanded": 0}},
            {"pane": {"kind": "empty"}},
        ]},
    ]}}
    saved = client.put("/api/dashboards/ops", json=body).get_json()
    node = saved["sections"][0]["panels"][0]["node"]
    assert node["sizes"] == [25, 75] and saved["cycle"] == 30
    assert [c["pane"] for c in node["children"][1]["children"][:2]] == [
        {"kind": "view", "view": "health", "expanded": True}, {"kind": "view", "view": "lancache"}]
    # The tile dashboard and the page panes are gone: widgets do their job.
    for gone in ({"kind": "dashboard", "layout": "ops-desk"}, {"kind": "page", "page": "health"}):
        assert client.put("/api/dashboards/ops", json={"name": "Ops", "root": {"pane": gone}}).status_code == 400


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
    """Moved once by floorbit/upgrades.py, like every older shape."""
    from floorbit import dashboards, store, upgrades
    data = store.load_data()
    data["dashboards"] = [{"id": "old", "name": "Old", "root": {"pane": {"kind": "empty"}}}]
    data[upgrades.KEY] = upgrades.STEPS.index(upgrades._dashboards)    # saved before the grid
    store.write_json(store.DATA_FILE, dict(data))
    upgrades.run_at_start(log=lambda *_: None)
    old = client.get("/api/dashboards/old").get_json()
    assert old["fit"] is True and "root" not in old
    assert old["sections"][0]["panels"][0]["node"] == {"pane": {"kind": "empty"}}
    assert dashboards.get("old")["sections"]


def test_kiosk_is_ready_made_until_replaced(client):
    kiosk = client.get("/api/dashboards/kiosk").get_json()
    assert kiosk["builtin"] is True and kiosk["fit"] is True
    panes = [p["node"]["pane"] for p in kiosk["sections"][0]["panels"]]
    assert panes[0]["kind"] == "plan" and panes[0]["marks"] == "public"   # often in a public place
    assert [p.get("tile") for p in panes[1:]] == ["floorbit/w/switches", "floorbit/w/seats", "floorbit/w/down"]
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
    assert put(root={"pane": {"kind": "plan", "marks": "secret"}}) == 400
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


def test_public_dashboards_open_without_an_account(client, anon_client, monkeypatch):
    from integrations import seat_sources
    monkeypatch.setenv("SEAT_SOURCES", "manual")
    seat_sources.invalidate()
    client.post("/api/seat-blocks", json={"name": "D", "x": 40, "y": 50, "cols": 4, "rows": 2})
    client.post("/api/switches", json={"name": "sw-d-01", "x": 30, "y": 50})
    client.put("/api/seat-map/D-6", json={"ip": "198.51.100.7", "nick": "player-six"})
    client.put("/api/plan/seats/D-6/note", json={"text": "cable loose"})
    seat_sources.invalidate()
    wall = {"name": "Hall", "public": True, "fit": True, "sections": [{"panels": [
        {"x": 0, "y": 0, "w": 12, "h": 12, "node": {"pane": {"kind": "plan", "preset": "ops"}}},
        {"x": 12, "y": 0, "w": 6, "h": 6, "node": {"pane": {"kind": "tile", "tile": "floorbit/w/down"}}},
        {"x": 12, "y": 6, "w": 6, "h": 6, "node": {"pane": {"kind": "tile", "tile": "floorbit/w/problems",
                                                            "title": "Crew"}}},
        {"x": 18, "y": 0, "w": 6, "h": 6, "node": {"pane": {"kind": "view", "view": "health"}}},
        {"x": 18, "y": 6, "w": 6, "h": 6, "node": {"pane": {"kind": "view", "view": "event-numbers"}}},
    ]}]}
    assert client.put("/api/dashboards/hall", json=wall).get_json()["public"] is True
    assert anon_client.get("/dashboards/hall").status_code in (200, 503)   # 503: no frontend build in CI

    body = anon_client.get("/api/dashboards/hall/public").get_json()
    assert body["account"] is False
    panes = [p["node"]["pane"] for p in body["board"]["sections"][0]["panels"]]
    assert panes[0]["kind"] == "plan" and panes[0]["marks"] == "public"   # "all" turns public
    assert panes[1]["tile"] == "floorbit/w/down"
    assert panes[2] == {"kind": "private"} and panes[3] == {"kind": "private", "title": "Crew"}   # by row
    assert panes[4] == {"kind": "view", "view": "event-numbers"}   # the stats wall is public itself
    assert client.get("/api/dashboards/hall/public").get_json()["account"] is True

    plan = anon_client.get("/api/dashboards/hall/public/plan").get_json()
    seat = plan["seats"]["D-6"]
    assert seat.get("taken") is True and "note" not in seat and "problems" not in seat
    assert set(plan["switches"][0]) == {"id", "name", "status", "x", "y"}
    assert "198.51.100.7" not in str(plan) and "player-six" not in str(plan)
    assert anon_client.get("/api/dashboards/hall/public/tiles/down").get_json()["type"] == "status"
    assert anon_client.get("/api/dashboards/hall/public/tiles/problems").status_code == 404
    assert anon_client.get("/api/dashboards/hall/public/tiles/switches").status_code == 404   # not on it

    # Not public: nothing to see signed out, and the page asks for an account.
    assert client.put("/api/dashboards/hall", json={**wall, "public": False}).status_code == 200
    assert anon_client.get("/api/dashboards/hall/public").get_json()["board"] is None
    assert anon_client.get("/api/dashboards/hall/public/plan").status_code == 404
    assert anon_client.get("/api/dashboards/hall/public/tiles/down").status_code == 404
    assert anon_client.get("/dashboards/hall").status_code == 302
    assert anon_client.get("/api/dashboards/hall").status_code == 401


def test_the_ready_made_kiosk_is_public(anon_client):
    board = anon_client.get("/api/dashboards/kiosk/public").get_json()["board"]
    assert board["name"] == "Kiosk" and board["public"] is True
    assert anon_client.get("/api/dashboards/kiosk/public/plan").status_code == 200
    seats = anon_client.get("/api/dashboards/kiosk/public/tiles/seats").get_json()
    assert seats["type"] == "stat" and seats["link"] == ""   # its page needs an account


def test_a_screen_account_limited_to_some_dashboards(client, kiosk_client):
    """Settings > Users can limit an account to some dashboards (#702): it lists and opens only those
    and starts on the first; without a list it opens every one, as before."""
    client.put("/api/dashboards/hall-b", json={**MIXED, "name": "Hall B wall"})
    client.put("/api/dashboards/noc", json={**MIXED, "name": "NOC"})
    from floorbit.dashboards import BUILTIN
    assert len(kiosk_client.get("/api/dashboards").get_json()["layouts"]) == 2 + len(BUILTIN)
    r = client.patch("/api/users/screen-1", json={"dashboards": ["hall-b", "hall-b"]})
    assert r.status_code == 200, r.get_json()
    assert next(u for u in r.get_json()["users"] if u["username"] == "screen-1")["dashboards"] == ["hall-b"]
    listed = kiosk_client.get("/api/dashboards").get_json()
    assert [x["id"] for x in listed["layouts"]] == ["hall-b"] and listed["limited"] is True
    assert kiosk_client.get("/api/dashboards/hall-b").status_code == 200
    assert kiosk_client.get("/api/dashboards/noc").status_code == 404
    assert kiosk_client.get("/").headers["Location"].endswith("/dashboards/hall-b")
    r = kiosk_client.get("/dashboards/noc")
    assert r.status_code == 302 and r.headers["Location"].endswith("/dashboards/hall-b")
    # The ready-made Kiosk dashboard is public: a screen may still open it.
    assert kiosk_client.get("/dashboards/kiosk").status_code in (200, 503)
    assert kiosk_client.get("/api/dashboards/kiosk").status_code == 200    # what that page then reads
    # Other accounts aren't touched.
    assert len(client.get("/api/dashboards").get_json()["layouts"]) == 2 + len(BUILTIN)
    # Unknown ids are refused, in German too; an empty list lifts the limit.
    bad = client.patch("/api/users/screen-1", json={"dashboards": ["nope"]}, headers={"Accept-Language": "de-CH"})
    assert bad.status_code == 400 and bad.get_json()["error"] == 'Es gibt kein Dashboard «nope».'
    assert client.patch("/api/users/screen-1", json={"dashboards": "noc"}).status_code == 400
    assert client.patch("/api/users/screen-1", json={"dashboards": []}).status_code == 200
    from floorbit.dashboards import BUILTIN
    assert len(kiosk_client.get("/api/dashboards").get_json()["layouts"]) == 2 + len(BUILTIN)
    assert kiosk_client.get("/").headers["Location"].endswith("/plan")


def test_ready_made_dashboards_use_known_widgets(client):
    """The ready-made dashboards replace the old pages and walls; each one saves through clean()
    unchanged, so the editor can open and save it, and the stats wall's is public."""
    import re
    from pathlib import Path

    from floorbit.dashboards import BUILTIN, clean
    source = (Path(__file__).parent.parent / "frontend/src/widgets/views.ts").read_text()
    views = set(re.findall(r"id: '([\w-]+)'", source))
    for layout_id, layout in BUILTIN.items():
        assert clean(layout)["sections"] == layout["sections"], layout_id
        for sec in layout["sections"]:
            for panel in sec["panels"]:
                pane = panel["node"].get("pane", {})
                if pane.get("kind") == "view":
                    assert pane["view"] in views, (layout_id, pane)
    assert client.get("/api/dashboards/network").get_json()["builtin"] is True
    assert BUILTIN["event"]["public"] is True


def test_the_widget_gallery_needs_an_account(client, anon_client, app_module, monkeypatch):
    assert client.get("/widgets").status_code in (200, 503)   # 503: no frontend build in CI
    monkeypatch.setattr(app_module.app.extensions["auth"], "public_read", False)
    assert anon_client.get("/widgets").status_code in (302, 401)


def test_a_tile_pane_keeps_its_widget_type_and_size(client):
    def save(pane):
        body = {"name": "Types", "sections": [{"panels": [{"x": 0, "y": 0, "w": 6, "h": 4, "node": {"pane": pane}}]}]}
        return client.put("/api/dashboards/types", json=body)
    r = save({"kind": "tile", "tile": "floorbit/w/switch_states", "type": "status", "level": "m"})
    assert r.status_code == 200
    assert r.get_json()["sections"][0]["panels"][0]["node"]["pane"] == {
        "kind": "tile", "tile": "floorbit/w/switch_states", "type": "status", "level": "m"}
    # The defaults stay out of the saved layout.
    r = save({"kind": "tile", "tile": "floorbit/w/seats", "type": "auto", "level": "auto"})
    assert r.get_json()["sections"][0]["panels"][0]["node"]["pane"] == {"kind": "tile", "tile": "floorbit/w/seats"}
    for kind in ("gauge", "bar", "column", "histogram", "pie"):
        assert save({"kind": "tile", "tile": "floorbit/w/seats", "type": kind}).status_code == 200
    r = save({"kind": "tile", "tile": "floorbit/w/traffic", "stack": "percent", "style": "area", "trend": "linear"})
    assert r.get_json()["sections"][0]["panels"][0]["node"]["pane"] == {
        "kind": "tile", "tile": "floorbit/w/traffic", "stack": "percent", "style": "area", "trend": "linear"}
    r = save({"kind": "tile", "tile": "floorbit/w/traffic", "stack": "none", "style": "line", "trend": "none"})
    assert r.get_json()["sections"][0]["panels"][0]["node"]["pane"] == {"kind": "tile", "tile": "floorbit/w/traffic"}
    assert "option trend" in save({"kind": "tile", "tile": "floorbit/w/traffic", "trend": "cubic"}).get_json()["error"]
    assert "widget type" in save({"kind": "tile", "tile": "floorbit/w/seats", "type": "pie3d"}).get_json()["error"]
    assert "widget size" in save({"kind": "tile", "tile": "floorbit/w/seats", "level": "xl"}).get_json()["error"]
