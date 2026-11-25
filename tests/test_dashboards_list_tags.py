"""Tags, a group and "shows on" for the dashboards list (#897)."""
import pytest

BODY = {"name": "NOC", "fit": True, "sections": [{"panels": []}]}


def test_tags_and_group_are_kept_and_tidied(client):
    body = {**BODY, "tags": ["NOC", "hall a", "noc"], "group": "  Network crew "}
    saved = client.put("/api/dashboards/noc", json=body)
    assert saved.status_code == 200
    body = saved.get_json()
    assert body["tags"] == ["noc", "hall-a"]
    assert body["group"] == "Network crew"
    listed = next(b for b in client.get("/api/dashboards").get_json()["layouts"] if b["id"] == "noc")
    assert listed["tags"] == ["noc", "hall-a"] and listed["group"] == "Network crew"


def test_no_tags_or_group_leaves_them_out(client):
    body = client.put("/api/dashboards/noc", json={**BODY, "tags": [], "group": ""}).get_json()
    assert "tags" not in body and "group" not in body


@pytest.mark.parametrize("tags", ["noc", ["no/c"], ["x" * 25], [f"t{i}" for i in range(9)]])
def test_bad_tags_are_refused(client, tags):
    res = client.put("/api/dashboards/noc", json={**BODY, "tags": tags})
    assert res.status_code == 400


def test_the_group_is_cut_to_40_characters(client):
    body = client.put("/api/dashboards/noc", json={**BODY, "group": "g" * 80}).get_json()
    assert body["group"] == "g" * 40


def test_a_public_screen_does_not_get_tags_or_group(client, anon_client):
    client.put("/api/dashboards/hall", json={**BODY, "public": True, "tags": ["hall"], "group": "Hall"})
    board = anon_client.get("/api/dashboards/hall/public").get_json()["board"]
    assert "tags" not in board and "group" not in board


def test_the_list_counts_the_screen_accounts_on_a_dashboard(app_module, client):
    client.put("/api/dashboards/noc", json=BODY)
    users = app_module.app.extensions["auth"].users
    users.add("wall-1", "wall-password-1", role="kiosk")
    users.add("wall-2", "wall-password-2", role="kiosk")
    users.update("wall-1", dashboards=["noc"])
    users.update("wall-2", dashboards=["noc", "kiosk"])
    layouts = {b["id"]: b for b in client.get("/api/dashboards").get_json()["layouts"]}
    assert layouts["noc"]["screens"] == 2
    assert layouts["kiosk"]["screens"] == 1
    assert all("screens" not in b for i, b in layouts.items() if i not in ("noc", "kiosk"))


def test_a_limited_screen_account_gets_no_counts(app_module, client, anon_client):
    users = app_module.app.extensions["auth"].users
    users.add("wall-1", "wall-password-1", role="kiosk")
    users.update("wall-1", dashboards=["kiosk"])
    anon_client.post("/login", data={"username": "wall-1", "password": "wall-password-1"})
    layouts = anon_client.get("/api/dashboards").get_json()["layouts"]
    assert [b["id"] for b in layouts] == ["kiosk"]
    assert "screens" not in layouts[0]
