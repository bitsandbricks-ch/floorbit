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
            {"pane": {"kind": "text", "text": "Doors"}},
            {"pane": {"kind": "empty"}},
        ]},
    ]}}
    saved = client.put("/api/dashboards/ops", json=body).get_json()
    node = saved["sections"][0]["panels"][0]["node"]
    assert node["sizes"] == [25, 75] and saved["cycle"] == 30
    assert [c["pane"]["kind"] for c in node["children"][1]["children"]] == ["text", "empty"]
    # The tile dashboard, the page panes and the rich widgets (views) are gone: tiles do their job.
    for gone in ({"kind": "dashboard", "layout": "ops-desk"}, {"kind": "page", "page": "health"},
                 {"kind": "view", "view": "health"}):
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


def test_kiosk_is_ready_made_until_changed_and_resets(client):
    kiosk = client.get("/api/dashboards/kiosk").get_json()
    assert kiosk["builtin"] is True and kiosk["fit"] is True
    panes = [p["node"]["pane"] for p in kiosk["sections"][0]["panels"]]
    assert panes[0]["kind"] == "plan" and panes[0]["marks"] == "public"   # often in a public place
    assert [p.get("tile") for p in panes[1:]] == ["floorbit/w/switches", "floorbit/w/seats", "floorbit/w/down"]
    assert client.delete("/api/dashboards/kiosk").status_code == 404   # nothing saved to remove
    mine = {"name": "Kiosk", "sections": [{"panels": [_panel(0, 0, 24, 12, "text")]}], "fit": True}
    assert client.put("/api/dashboards/kiosk", json=mine).status_code == 200
    listed = client.get("/api/dashboards").get_json()["layouts"]
    assert [(x.get("builtin"), x.get("changed")) for x in listed if x["id"] == "kiosk"] == [(None, True)]
    # Reset to default: the saved one goes, the ready-made one is back.
    assert client.delete("/api/dashboards/kiosk").status_code == 200
    back = client.get("/api/dashboards/kiosk").get_json()
    assert back["builtin"] is True and "changed" not in back
    # A dashboard of one's own is never "changed".
    assert client.put("/api/dashboards/mine", json=mine).status_code == 200
    assert "changed" not in client.get("/api/dashboards/mine").get_json()


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
        {"x": 18, "y": 0, "w": 6, "h": 6, "node": {"pane": {"kind": "tile", "tile": "floorbit/w/service_health"}}},
        {"x": 18, "y": 6, "w": 6, "h": 6, "node": {"pane": {"kind": "tile", "tile": "floorbit/w/event_games"}}},
    ]}]}
    assert client.put("/api/dashboards/hall", json=wall).get_json()["public"] is True
    assert anon_client.get("/dashboards/hall").status_code in (200, 503)   # 503: no frontend build in CI

    body = anon_client.get("/api/dashboards/hall/public").get_json()
    assert body["account"] is False
    panes = [p["node"]["pane"] for p in body["board"]["sections"][0]["panels"]]
    assert panes[0]["kind"] == "plan" and panes[0]["marks"] == "public"   # "all" turns public
    assert panes[1]["tile"] == "floorbit/w/down"
    assert panes[2] == {"kind": "private"} and panes[3] == {"kind": "private", "title": "Crew"}   # by row
    assert panes[4]["tile"] == "floorbit/w/event_games"   # the stats wall's numbers are public themselves
    assert client.get("/api/dashboards/hall/public").get_json()["account"] is True

    plan = anon_client.get("/api/dashboards/hall/public/plan").get_json()
    seat = plan["seats"]["D-6"]
    assert seat.get("taken") is True and "note" not in seat and "problems" not in seat
    assert set(plan["switches"][0]) == {"id", "name", "status", "x", "y"}
    assert "198.51.100.7" not in str(plan) and "player-six" not in str(plan)
    assert anon_client.get("/api/dashboards/hall/public/tiles/down").get_json()["type"] == "status"
    # A row's inventory id is crew data: the open feed leaves it out (#925).
    from floorbit.blueprints import plugins as tiles
    monkeypatch.setitem(tiles.CORE_TILES, "down", lambda _q: {"type": "list", "items": [
        {"label": "sw-a-01", "value": "7 min", "tone": "err", "device": "demo-sw-a-01"}]})
    assert anon_client.get("/api/dashboards/hall/public/tiles/down").get_json()["items"] == [
        {"label": "sw-a-01", "value": "7 min", "tone": "err"}]
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
    from floorbit.dashboards import BUILTIN, clean
    for layout_id, layout in BUILTIN.items():
        assert clean(layout)["sections"] == layout["sections"], layout_id
    assert client.get("/api/dashboards/network").get_json()["builtin"] is True
    assert BUILTIN["event"]["public"] is True


def test_the_crew_dashboards_are_built_from_tiles_only():
    """Views drew page sections that didn't fit a pane (#1045); the ready-made dashboards use
    tiles, and the pages keep the actions."""
    from floorbit.dashboards import BUILTIN
    for layout_id, layout in BUILTIN.items():
        kinds = {p["node"]["pane"]["kind"] for s in layout["sections"] for p in s["panels"]}
        assert kinds <= {"tile", "plan"}, (layout_id, kinds)


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


def test_a_tile_pane_draws_more_sources_grouped_and_calculated(client, anon_client):
    def save(pane, public=False):
        body = {"name": "Mixed", "public": public,
                "sections": [{"panels": [{"x": 0, "y": 0, "w": 6, "h": 4, "node": {"pane": pane}}]}]}
        return client.put("/api/dashboards/mixed", json=body)
    pane = {"kind": "tile", "tile": "floorbit/w/switches", "also": ["floorbit/w/seats"], "group_by": "state",
            "reduce": "avg", "legend": ["max", "avg"]}
    r = save(pane)
    assert r.status_code == 200
    assert r.get_json()["sections"][0]["panels"][0]["node"]["pane"] == pane
    r = save({"kind": "tile", "tile": "floorbit/w/seats", "also": [], "group_by": "", "reduce": "", "legend": []})
    assert r.get_json()["sections"][0]["panels"][0]["node"]["pane"] == {"kind": "tile", "tile": "floorbit/w/seats"}
    def error(**extra):
        return save({"kind": "tile", "tile": "floorbit/w/seats", **extra}).get_json()["error"]
    more = ["floorbit/w/a", "floorbit/w/b", "floorbit/w/c", "floorbit/w/d"]
    assert "at most 3" in error(also=more)
    assert "once" in error(also=["floorbit/w/seats"])
    assert "once" in error(also=["nope"])
    assert "calculation" in error(reduce="median")
    assert "calculation" in error(legend=["avg", "avg"])
    assert "column" in error(group_by="a b")
    # Public only when every source is public, and then each source reads signed out.
    save({"kind": "tile", "tile": "floorbit/w/switches", "also": ["floorbit/w/seats"]}, public=True)
    assert anon_client.get("/api/dashboards/mixed/public/tiles/seats").status_code == 200
    save({"kind": "tile", "tile": "floorbit/w/switches", "also": ["floorbit/w/problems"]}, public=True)
    board = anon_client.get("/api/dashboards/mixed/public").get_json()["board"]
    assert board["sections"][0]["panels"][0]["node"]["pane"]["kind"] == "private"
    assert anon_client.get("/api/dashboards/mixed/public/tiles/switches").status_code == 404


def test_a_tile_pane_keeps_how_it_shows_its_numbers(client):
    def save(**extra):
        body = {"name": "Display", "sections": [{"panels": [{"x": 0, "y": 0, "w": 6, "h": 4, "node": {
            "pane": {"kind": "tile", "tile": "floorbit/w/seats", **extra}}}]}]}
        return client.put("/api/dashboards/display", json=body)
    shown = {"thresholds": [{"at": 80, "tone": "warn"}, {"at": 95, "tone": "err"}], "threshold_mode": "percent",
             "mappings": [{"from": 0, "to": 0, "text": "Nobody", "tone": "err"}], "unit": "seats", "decimals": 1,
             "short": True, "sort": "value-desc", "limit": 5, "hide_zero": True}
    r = save(**shown)
    assert r.status_code == 200, r.get_json()
    pane = r.get_json()["sections"][0]["panels"][0]["node"]["pane"]
    assert pane == {"kind": "tile", "tile": "floorbit/w/seats", **shown}
    r = save(thresholds=[], mappings=[], unit="", short=False, sort="", hide_zero=False, threshold_mode="value")
    assert r.get_json()["sections"][0]["panels"][0]["node"]["pane"] == {"kind": "tile", "tile": "floorbit/w/seats"}

    def error(**extra):
        return save(**extra).get_json()["error"]
    assert "colour steps" in error(thresholds=[{"at": i, "tone": "ok"} for i in range(6)])
    assert "must be a number" in error(thresholds=[{"at": "high", "tone": "ok"}])
    assert "colour is one of" in error(thresholds=[{"at": 1, "tone": "pink"}])
    assert "percent of the max" in error(thresholds=[{"at": 1, "tone": "ok"}], threshold_mode="log")
    assert "whole number" in error(decimals=9)
    assert "whole number" in error(limit=0)
    assert "Sort" in error(sort="random")
    assert "mappings" in error(mappings=[{"text": "x"}] * 11)


def test_a_tile_pane_keeps_its_axis_and_series_settings(client):
    def save(**extra):
        body = {"name": "Axis", "sections": [{"panels": [{"x": 0, "y": 0, "w": 6, "h": 4, "node": {
            "pane": {"kind": "tile", "tile": "floorbit/w/traffic", **extra}}}]}]}
        return client.put("/api/dashboards/axis", json=body)
    shown = {"y_min": 1, "y_max": 10e9, "y_log": True, "overrides": [
        {"match": "Download", "name": "Down", "colour": "cyan"}, {"match": "Upload", "hide": True}]}
    r = save(**shown)
    assert r.status_code == 200, r.get_json()
    pane = r.get_json()["sections"][0]["panels"][0]["node"]["pane"]
    assert pane == {"kind": "tile", "tile": "floorbit/w/traffic", **shown}
    # A setting that changes nothing is dropped.
    r = save(overrides=[{"match": "Upload", "name": " "}], y_log=False)
    assert r.get_json()["sections"][0]["panels"][0]["node"]["pane"] == {"kind": "tile", "tile": "floorbit/w/traffic"}

    def error(**extra):
        return save(**extra).get_json()["error"]
    assert "above its minimum" in error(y_min=5, y_max=5)
    assert "above 0" in error(y_log=True, y_min=0)
    assert "must be a number" in error(y_max="lots")
    assert "series colour" in error(overrides=[{"match": "Download", "colour": "red"}])
    assert "Pick the series" in error(overrides=[{"name": "x"}])
    assert "series settings" in error(overrides=[{"match": "a", "hide": True}] * 11)


def test_a_tile_pane_keeps_its_time_range(client):
    def save(**extra):
        body = {"name": "Range", "sections": [{"panels": [{"x": 0, "y": 0, "w": 6, "h": 4, "node": {
            "pane": {"kind": "tile", "tile": "floorbit/w/traffic", **extra}}}]}]}
        return client.put("/api/dashboards/range", json=body)
    pane = save(range="6h", compare="day").get_json()["sections"][0]["panels"][0]["node"]["pane"]
    assert pane["range"] == "6h" and pane["compare"] == "day"
    assert "time range" in save(range="week").get_json()["error"]
    assert "Compare" in save(compare="lastyear").get_json()["error"]
    assert "nothing to compare" in save(range="event", compare="day").get_json()["error"]


def test_a_tile_pane_keeps_showing_events(client):
    body = {"name": "Events", "sections": [{"panels": [{"x": 0, "y": 0, "w": 6, "h": 4, "node": {
        "pane": {"kind": "tile", "tile": "floorbit/w/traffic", "events": True}}}]}]}
    pane = client.put("/api/dashboards/events", json=body).get_json()["sections"][0]["panels"][0]["node"]["pane"]
    assert pane["events"] is True


def test_a_tile_pane_sets_its_refresh_text_size_and_stat_extras(client):
    def put(**extra):
        body = {"name": "Extras", "sections": [{"panels": [{"x": 0, "y": 0, "w": 6, "h": 4, "node": {
            "pane": {"kind": "tile", "tile": "floorbit/w/traffic", **extra}}}]}]}
        return client.put("/api/dashboards/extras", json=body)
    r = put(refresh=30, text_size="l", spark=True, change=True)
    assert r.status_code == 200, r.get_json()
    pane = r.get_json()["sections"][0]["panels"][0]["node"]["pane"]
    assert (pane["refresh"], pane["text_size"], pane["spark"], pane["change"]) == (30, "l", True, True)
    assert "text_size" not in put(text_size="m").get_json()["sections"][0]["panels"][0]["node"]["pane"]
    assert put(refresh=5).get_json()["error"] == "Refresh every 10, 30, 60 or 300 seconds."
    assert put(refresh=True).status_code == 400
    assert put(text_size="xl").get_json()["error"] == "Text size is small, normal or large."


def test_a_dashboard_sets_the_time_its_graphs_show(client):
    body = {"name": "Times", "public": True, "range": "6h", "sections": [{"panels": [{"x": 0, "y": 0, "w": 6, "h": 4,
            "node": {"pane": {"kind": "tile", "tile": "floorbit/w/traffic"}}}]}]}
    r = client.put("/api/dashboards/times", json=body)
    assert r.status_code == 200 and r.get_json()["range"] == "6h"
    assert client.get("/api/dashboards/times/public").get_json()["board"]["range"] == "6h"
    assert client.put("/api/dashboards/times", json={**body, "range": "week"}).status_code == 400
    assert "range" not in client.put("/api/dashboards/times", json={**body, "range": ""}).get_json()


def test_a_dashboard_can_hide_its_full_screen_header(client):
    body = {"name": "Wall", "public": True, "sections": [{"panels": [{"x": 0, "y": 0, "w": 6, "h": 4,
            "node": {"pane": {"kind": "text", "text": "Hi"}}}]}]}
    # On by default: nothing is stored until a dashboard switches it off.
    assert "frame" not in client.put("/api/dashboards/wall", json=body).get_json()
    assert client.put("/api/dashboards/wall", json={**body, "frame": False}).get_json()["frame"] is False
    assert client.get("/api/dashboards/wall/public").get_json()["board"]["frame"] is False


def test_a_pane_can_show_one_row(client):
    """#1078: a block holds rows, and a plan pane can show just one of them."""
    layout = {"name": "Row", "root": {"pane": {"kind": "plan", "area": {"kind": "row", "id": "blk-1:2"}}}}
    saved = client.put("/api/dashboards/row-wall", json=layout).get_json()
    pane = saved["sections"][0]["panels"][0]["node"]["pane"]
    assert pane["area"] == {"kind": "row", "id": "blk-1:2"}
    bad = client.put("/api/dashboards/row-wall", json={"name": "Row", "root": {"pane": {
        "kind": "plan", "area": {"kind": "row", "id": ""}}}})
    assert bad.status_code == 400 and "row" in bad.get_json()["error"]
