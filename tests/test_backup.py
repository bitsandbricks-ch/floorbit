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
    assert [s["name"] for s in backup["layout"]["inventory"]] == ["sw-demo-01"]
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


def test_a_backup_with_broken_seat_blocks_or_marks_is_refused(client):
    # Restored as they were, these turned the plan, incidents and problems into 500s for everybody.
    _, block = place_things(client)
    good = client.get("/api/settings/backup").get_json()
    broken = [
        ("seat_blocks", [{"id": "b1"}]),
        ("seat_blocks", [{"id": "b2", "name": 3, "x": "a", "y": 1, "cols": -1, "rows": "x"}]),
        ("seat_blocks", [{"id": "b3", "x": 1, "y": 1, "cols": 2, "rows": 2, "seat_width": "wide"}]),
        ("seat_blocks", [{"id": "b4", "x": 1, "y": 1, "cols": 2, "rows": 2, "rotation": "left"}]),
        ("plan_marks", [{"id": "m1", "kind": 9}]),
        ("plan_marks", [{"id": "m2", "kind": "text", "x": 1, "y": 1}]),
    ]
    for part, value in broken:
        backup = {**good, "layout": {**good["layout"], part: value}}
        resp = client.post("/api/settings/backup", json=backup)
        assert resp.status_code == 400, value
        assert value[0]["id"] in resp.get_json()["error"]
    assert [b["id"] for b in client.get("/api/seat-blocks").get_json()] == [block["id"]]
    assert client.get("/api/plan").status_code == 200


def test_a_good_backup_keeps_its_blocks_and_marks_as_they_were(client):
    place_things(client)
    hall = client.get("/api/halls").get_json()["halls"][0]["id"]
    assert client.post("/api/plan-marks", json={"kind": "text", "text": "Stage", "x": 5, "y": 5,
                                                "hall_id": hall}).status_code in (200, 201)
    before = client.get("/api/settings/backup").get_json()["layout"]
    resp = client.post("/api/settings/backup", json=client.get("/api/settings/backup").get_json())
    assert resp.status_code == 200, resp.data
    after = client.get("/api/settings/backup").get_json()["layout"]
    assert after["seat_blocks"] == before["seat_blocks"]
    assert after["plan_marks"] == before["plan_marks"]


def test_backup_is_admin_only(anon_client, client, app_module):
    assert anon_client.get("/api/settings/backup").status_code == 401
    assert anon_client.post("/api/settings/backup", json={}).status_code == 401
    users = app_module.app.extensions["auth"].users
    users.add("ed", "editor-password-1", role="editor")
    editor = app_module.app.test_client()
    assert editor.post("/login", data={"username": "ed", "password": "editor-password-1"}).status_code == 302
    assert editor.get("/api/settings/backup").status_code == 403


def test_settings_page_is_the_react_app(client):
    # The backup panel itself is tested in frontend/src/pages/Settings.test.tsx.
    page = client.get("/settings").get_data(as_text=True)
    assert '<div id="root">' in page and "<title>Settings" in page


def test_a_backup_keeps_where_the_background_sits_and_the_scale(client):
    png = ('data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAA'
           'SUVORK5CYII=')
    client.put('/api/halls/main/background', json={'image': png})
    client.patch('/api/halls/main/background', json={'frame': {'x': 5, 'y': 5, 'w': 90, 'h': 60}, 'opacity': 0.5})
    client.put('/api/halls/main/scale', json={'seat_m': 0.75})
    backup = client.get('/api/settings/backup').get_json()
    client.patch('/api/halls/main/background', json={'frame': None, 'opacity': None})
    client.put('/api/halls/main/scale', json={'seat_m': None})
    assert client.post('/api/settings/backup', json=backup).status_code == 200
    (hall,) = client.get('/api/halls').get_json()['halls']
    assert hall['background_frame'] == {'x': 5, 'y': 5, 'w': 90, 'h': 60}
    assert hall['background_opacity'] == 0.5 and hall['seat_m'] == 0.75
    backup['layout']['halls'][0]['opacity'] = 7
    assert client.post('/api/settings/backup', json=backup).status_code == 400


def cable_things(client):
    """Cabling and power on the plan: a panel, a cable through it, a drawn route, an uplink, a board
    with a circuit, and a port area (issue #810)."""
    sw, block = place_things(client)
    dist = client.post("/api/switches", json={"name": "dist-01", "x": 10, "y": 60}).get_json()
    panel = {"name": "PP-1", "x": 20, "y": 20, "ports": 12}
    assert client.post("/api/cable-plan/panels", json=panel).status_code == 201
    assert client.post("/api/cables", json={"switch": "sw-demo-01", "port": "Gi1/0/1", "seat": "A-1",
                                            "panel": "PP-1", "panel_port": "3", "type": "cat6"}).status_code == 201
    assert client.put("/api/cable-plan/routes", json={"routes": {"lan:sw-demo-01|Gi1/0/1": {
        "points": [[12, 22], [25, 22]], "corners": "round"}}}).status_code == 200
    assert client.post("/api/links", json={"a": "sw-demo-01", "a_port": "Te1/1/1", "b": "dist-01",
                                           "b_port": "Te1/0/1", "type": "fiber-sm", "speed": 10}).status_code == 201
    board = client.post("/api/power/boards", json={"name": "DB-1", "x": 5, "y": 40}).get_json()
    assert client.post("/api/power/circuits", json={
        "board": board["id"], "name": "A row", "blocks": [{"block": block["id"]}],
        "switches": [sw["id"], dist["id"]]}).status_code == 201
    assert client.post("/api/port-areas/batch", json={"switch": "sw-demo-01", "size": 4,
                                                      "starts": ["1"]}).status_code == 200
    return sw, block, dist


def _plan_state(client):
    plan = client.get("/api/power").get_json()
    return {
        "cables": [(c["label"], c["switch"], c["port"], c["panel"], c["panel_port"])
                   for c in client.get("/api/cables").get_json()["cables"]],
        "links": [(x["a"], x["a_port"], x["b"], x["b_port"], x["speed"])
                  for x in client.get("/api/links").get_json()["links"]],
        "panels": [(p["name"], p["ports"]) for p in client.get("/api/plan").get_json()["panels"]],
        "boards": [b["name"] for b in plan["boards"]],
        "circuits": [(c["name"], len(c["switches"])) for c in plan["circuits"]],
        "areas": [(a["switch"], a["first"], a["last"], a["label"])
                  for a in client.get("/api/port-areas").get_json()["areas"]],
    }


def test_cabling_and_power_round_trip_and_replace_what_came_after(client, tmp_path):
    cable_things(client)
    before = _plan_state(client)
    assert all(before.values()), before
    backup = client.get("/api/settings/backup").get_json()
    for key in ("patch_panels", "links", "cables", "cable_routes", "power", "port_areas"):
        assert backup["layout"][key], key

    # Things added after the backup are gone after the restore; nothing stale is kept.
    client.post("/api/cables", json={"switch": "sw-demo-01", "port": "Gi1/0/2", "seat": "A-2"})
    client.post("/api/cable-plan/panels", json={"name": "PP-late", "x": 30, "y": 30})
    client.post("/api/power/boards", json={"name": "DB-late"})
    client.delete("/api/port-areas?switch=sw-demo-01")

    resp = client.post("/api/settings/backup", json=backup)
    assert resp.status_code == 200, resp.data
    result = resp.get_json()
    assert result["kept"] == [] and result["restored"]["cables"] == 1 and result["restored"]["patch_panels"] == 1
    assert _plan_state(client) == before
    from floorbit.store import load_data
    route = load_data()["cable_routes"]["lan:sw-demo-01|gi1/0/1"]
    assert route["points"] == [[12, 22], [25, 22]] and route["corners"] == "round"


def test_an_empty_plan_in_a_backup_empties_the_cabling(client):
    backup = client.get("/api/settings/backup").get_json()   # nothing cabled yet
    assert backup["layout"]["cables"] == [] and backup["layout"]["power"] == {"boards": [], "circuits": []}
    cable_things(client)
    result = client.post("/api/settings/backup", json=backup).get_json()
    assert result["kept"] == []
    state = _plan_state(client)
    assert not any(state.values()), state


def test_an_older_backup_without_cabling_keeps_it_and_says_so(client):
    cable_things(client)
    before = _plan_state(client)
    backup = client.get("/api/settings/backup").get_json()
    for key in ("patch_panels", "links", "cables", "cable_routes", "power", "port_areas"):
        del backup["layout"][key]
    result = client.post("/api/settings/backup", json=backup).get_json()
    assert result["kept"] == ["patch_panels", "links", "cables", "cable_routes", "power", "port_areas"]
    assert _plan_state(client) == before


def test_broken_cabling_in_a_backup_is_refused_and_changes_nothing(client):
    cable_things(client)
    before = _plan_state(client)
    good = client.get("/api/settings/backup").get_json()
    lay = good["layout"]

    def with_(key, value):
        return {**good, "layout": {**lay, key: value}}

    cable = lay["cables"][0]
    link = lay["links"][0]
    circuit = lay["power"]["circuits"][0]
    bad = [
        with_("cables", "nope"),
        with_("cables", [{**cable, "id": "../x"}]),
        with_("cables", [cable, {**cable, "id": "other", "label": "C-9"}]),          # the same ports twice
        with_("cables", [{**cable, "panel_port": "40"}]),                            # PP-1 has 12 ports
        with_("cables", [{**cable, "length_m": "nan"}]),
        with_("links", [{**link, "b": "not-in-the-backup"}]),
        with_("links", [link, {**link, "id": "l2"}]),
        with_("patch_panels", [{**lay["patch_panels"][0], "x": "inf"}]),
        with_("patch_panels", [{**lay["patch_panels"][0], "hall_id": "nowhere"}]),
        with_("cable_routes", {"lan:x|y": {"points": [[1e999, 0]]}}),
        with_("cable_routes", {"rm -rf": {}}),
        with_("power", {"boards": [], "circuits": [circuit]}),                        # its board is missing
        with_("power", {**lay["power"], "circuits": [{**circuit, "switches": 5}]}),
        with_("power", []),
        with_("port_areas", [{**lay["port_areas"][0], "first": "1"}]),
        with_("port_areas", [{**lay["port_areas"][0], "seats": []}]),
        # The cabled switch is not in the restored inventory: its uplink can't be checked.
        {**good, "layout": {**lay, "inventory": [d for d in lay["inventory"] if d["name"] != "dist-01"]}},
    ]
    for backup in bad:
        resp = client.post("/api/settings/backup", json=backup)
        assert resp.status_code == 400, (resp.data, backup["layout"])
        assert resp.get_json()["error"]
    assert _plan_state(client) == before


def test_a_cable_to_a_panel_only_the_backup_has_is_fine(client):
    cable_things(client)
    backup = client.get("/api/settings/backup").get_json()
    client.delete("/api/cables/" + client.get("/api/cables").get_json()["cables"][0]["id"])
    client.delete("/api/cable-plan/panels/PP-1")
    assert client.post("/api/settings/backup", json=backup).status_code == 200
    assert _plan_state(client)["panels"] == [("PP-1", 12)]
