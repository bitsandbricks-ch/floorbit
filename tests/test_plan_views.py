"""Saved floor plan views (floorbit/plan_views.py): shared with the crew, private ones only for you."""

VIEW = {"name": "VIP corner", "hall": "main", "view": {"x": 10, "y": 20, "w": 300, "h": 200},
        "layers": "status,network", "fade": "network:50", "show": "problems"}


def test_save_list_update_delete(client):
    r = client.post("/api/plan-views", json=VIEW)
    assert r.status_code == 201
    saved = r.get_json()
    assert saved["view"] == {"x": 10.0, "y": 20.0, "w": 300.0, "h": 200.0} and saved["layers"] == "status,network"
    assert [v["name"] for v in client.get("/api/plan-views?hall=main").get_json()["views"]] == ["VIP corner"]
    assert client.get("/api/plan-views?hall=other").get_json()["views"] == []

    changed = client.put(f"/api/plan-views/{saved['id']}", json={**VIEW, "name": "VIP", "layers": None}).get_json()
    assert changed["name"] == "VIP" and "layers" not in changed
    assert client.delete(f"/api/plan-views/{saved['id']}").status_code == 200
    assert client.get("/api/plan-views").get_json()["views"] == []
    assert client.delete(f"/api/plan-views/{saved['id']}").status_code == 404


def test_checks(client):
    def status(**change):
        return client.post("/api/plan-views", json={**VIEW, **change}).status_code

    assert status(name="") == 400
    assert status(name="x" * 61) == 400
    assert status(hall="") == 400
    assert status(view={"x": 0, "y": 0, "w": 0, "h": 10}) == 400
    assert status(view={"x": "a", "y": 0, "w": 1, "h": 1}) == 400
    assert status(layers="status;drop") == 400
    assert status(fade="network:abc") == 400
    assert status(show="everything") == 400
    assert status() == 201
    assert status() == 400   # same name in the same hall
    assert status(hall="side") == 201


def test_private_views_only_show_to_their_owner(client):
    import floorbit.plan_views as views
    mine = views.add({**VIEW, "private": True}, "anna")
    views.add({**VIEW, "name": "Shared"}, "anna")
    assert [v["name"] for v in views.visible("anna")] == ["VIP corner", "Shared"]
    assert [v["name"] for v in views.visible("ben")] == ["Shared"]
    try:
        views.update(mine["id"], {**VIEW, "name": "Mine"}, "ben")
        raise AssertionError("ben changed anna's private view")
    except KeyError:
        pass


def test_viewers_read_editors_write(app_module, client):
    client.post("/api/plan-views", json=VIEW)
    app_module.app.extensions["auth"].users.add("vic", "viewer-password-1", role="viewer")
    viewer = app_module.app.test_client()
    viewer.post("/login", data={"username": "vic", "password": "viewer-password-1"})
    assert [v["name"] for v in viewer.get("/api/plan-views").get_json()["views"]] == ["VIP corner"]
    assert viewer.post("/api/plan-views", json={**VIEW, "name": "Mine"}).status_code == 403
