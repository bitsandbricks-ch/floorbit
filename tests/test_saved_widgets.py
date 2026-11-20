"""Saved widgets: a tile pane kept under a name for any dashboard (floorbit/saved_widgets.py, #1009)."""
from test_dashboards import _login

DOWN = {"kind": "tile", "tile": "floorbit/w/down", "type": "table"}


def _board(widget, **pane):
    return {"name": "Wall", "public": True, "fit": True, "sections": [{"panels": [
        {"x": 0, "y": 0, "w": 12, "h": 12, "node": {"pane": {"kind": "widget", "widget": widget, **pane}}}]}]}


def test_create_read_replace_delete(client):
    r = client.post("/api/widgets", json={"name": "  Down   switches ", "pane": DOWN})
    assert r.status_code == 201, r.get_json()
    made = r.get_json()
    assert made["id"] == "down-switches" and made["name"] == "Down switches"
    assert made["pane"]["kind"] == "tile" and made["pane"]["tile"] == "floorbit/w/down"
    assert "title" not in made["pane"]   # the name is the title

    # The same name again gets an id of its own: a copy.
    assert client.post("/api/widgets", json={"name": "Down switches", "pane": DOWN}).get_json()["id"] \
        == "down-switches-2"

    seats = {**DOWN, "tile": "floorbit/w/seats"}
    r = client.put("/api/widgets/down-switches", json={"name": "Down now", "pane": seats})
    assert r.status_code == 200 and r.get_json()["pane"]["tile"] == "floorbit/w/seats"
    listed = client.get("/api/widgets").get_json()["widgets"]
    assert [(w["id"], w["name"], w["used_on"]) for w in listed] == [
        ("down-switches", "Down now", []), ("down-switches-2", "Down switches", [])]

    assert client.put("/api/widgets/nope", json={"name": "X", "pane": DOWN}).status_code == 404
    assert client.delete("/api/widgets/down-switches-2").status_code == 200
    assert client.delete("/api/widgets/down-switches-2").status_code == 404


def test_checks(client):
    assert client.post("/api/widgets", json=[]).status_code == 400
    r = client.post("/api/widgets", json={"name": " ", "pane": DOWN})
    assert r.get_json()["error"] == "Give the widget a name."
    assert client.post("/api/widgets", json={"name": "X"}).get_json()["error"] == "Pick what the widget shows."
    assert client.post("/api/widgets", json={"name": "X", "pane": {"kind": "tile", "tile": "bad"}}).status_code == 400
    r = client.put("/api/dashboards/wall", json=_board("Not An Id"))
    assert r.status_code == 400 and r.get_json()["error"] == "Pick a saved widget."


def test_a_dashboard_follows_its_saved_widget(client):
    client.post("/api/widgets", json={"name": "Down", "pane": DOWN})
    assert client.put("/api/dashboards/wall", json=_board("down", title="Here")).status_code == 200
    pane = client.get("/api/dashboards/wall").get_json()["sections"][0]["panels"][0]["node"]["pane"]
    assert pane["widget"] == "down" and pane["title"] == "Here"
    assert pane["saved"]["name"] == "Down" and pane["saved"]["pane"]["type"] == "table"

    client.put("/api/widgets/down", json={"name": "Down", "pane": {**DOWN, "type": "list"}})
    pane = client.get("/api/dashboards/wall").get_json()["sections"][0]["panels"][0]["node"]["pane"]
    assert pane["saved"]["pane"]["type"] == "list"
    # Saving the dashboard back as read keeps only the reference.
    board = client.get("/api/dashboards/wall").get_json()
    assert client.put("/api/dashboards/wall", json=board).status_code == 200
    from floorbit import dashboards
    stored = next(x for x in dashboards._saved() if x["id"] == "wall")
    assert stored["sections"][0]["panels"][0]["node"]["pane"] == {"kind": "widget", "widget": "down", "title": "Here"}

    # Shown somewhere: it stays until it is cloned there or taken off.
    r = client.delete("/api/widgets/down")
    assert r.status_code == 409 and "Wall" in r.get_json()["error"]
    assert client.get("/api/widgets").get_json()["widgets"][0]["used_on"] == ["Wall"]
    client.delete("/api/dashboards/wall")
    assert client.delete("/api/widgets/down").status_code == 200


def test_a_public_screen_gets_the_tile_pane(client, anon_client):
    client.post("/api/widgets", json={"name": "Down", "pane": DOWN})
    client.post("/api/widgets", json={"name": "Crew", "pane": {"kind": "tile", "tile": "floorbit/w/problems"}})
    board = _board("down")
    board["sections"][0]["panels"].append(
        {"x": 12, "y": 0, "w": 12, "h": 12, "node": {"pane": {"kind": "widget", "widget": "crew"}}})
    client.put("/api/dashboards/wall", json=board)
    body = anon_client.get("/api/dashboards/wall/public").get_json()
    panes = [p["node"]["pane"] for p in body["board"]["sections"][0]["panels"]]
    assert panes[0]["kind"] == "tile" and panes[0]["tile"] == "floorbit/w/down" and panes[0]["title"] == "Down"
    assert panes[1] == {"kind": "private"}
    assert "widget" not in str(panes)
    assert anon_client.get("/api/dashboards/wall/public/tiles/down").status_code == 200
    assert anon_client.get("/api/dashboards/wall/public/tiles/problems").status_code == 404


def test_viewers_read_editors_write(app_module, client):
    client.post("/api/widgets", json={"name": "Down", "pane": DOWN})
    viewer = _login(app_module, "vic", "viewer")
    assert viewer.get("/api/widgets").status_code == 200
    assert viewer.post("/api/widgets", json={"name": "X", "pane": DOWN}).status_code == 403
    assert viewer.put("/api/widgets/down", json={"name": "X", "pane": DOWN}).status_code == 403
    assert viewer.delete("/api/widgets/down").status_code == 403
