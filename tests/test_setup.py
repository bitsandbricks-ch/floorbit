"""First-run setup (issue #13): the setup code, the first account, steps and the redirect."""
import pytest

from floorbit import setup, store


@pytest.fixture(autouse=True)
def fresh_install(app_module):
    store.write_json(store.DATA_FILE, {})   # conftest starts every app as set up


@pytest.fixture
def code(app_module):
    issued = []
    holder = app_module.app.extensions["floorbit_setup_code"]
    holder._log = issued.append
    holder.issue()
    return lambda: issued[-1].split("setup code ")[1].split(" ")[0]


def test_a_new_install_points_to_setup(anon_client):
    assert b'href="/setup"' in anon_client.get("/login").data
    assert anon_client.get("/setup").status_code in (200, 503)   # 503: no frontend build in tests
    assert anon_client.get("/api/setup").get_json() == {"needs_account": True, "done": False}


def test_the_first_account_needs_the_code_from_the_log(app_module, anon_client, code):
    body = {"username": "mike", "password": "first-admin-pw"}
    resp = anon_client.post("/api/setup/account", json={**body, "code": "WRONG-CODE"})
    assert resp.status_code == 403
    resp = anon_client.post("/api/setup/account", json={**body, "code": code().lower()})
    assert resp.status_code == 201
    users = app_module.app.extensions["auth"].users
    assert users.get("mike")["role"] == "admin"
    # Signed in straight away, and the code is used up: no second admin this way.
    assert anon_client.get("/api/auth/me").get_json()["user"]["username"] == "mike"
    again = app_module.app.test_client().post("/api/setup/account", json={**body, "username": "eve", "code": code()})
    assert again.status_code == 409


def test_wrong_codes_replace_the_code(app_module, anon_client, code):
    first = code()
    for _ in range(setup.MAX_CODE_TRIES):
        anon_client.post("/api/setup/account", json={"username": "x", "password": "long-enough", "code": "NOPE"})
    assert code() != first
    resp = anon_client.post("/api/setup/account", json={"username": "x", "password": "long-enough", "code": first})
    assert resp.status_code == 403


def test_a_bad_password_issues_a_new_code(anon_client, code):
    first = code()
    resp = anon_client.post("/api/setup/account", json={"username": "mike", "password": "short", "code": first})
    assert resp.status_code == 400 and resp.get_json()["new_code"] is True
    assert code() != first


def test_admins_walk_through_the_steps(client):
    assert client.get("/").headers["Location"].endswith("/setup")
    body = client.get("/api/setup").get_json()
    assert body["can_set_up"] and not body["done"] and body["switches"] == {"total": 0, "placed": 0}
    marked = client.post("/api/setup/steps/netbox", json={"state": "skipped"}).get_json()
    assert marked["steps"] == {"netbox": "skipped"}
    assert client.post("/api/setup/steps/nope", json={"state": "done"}).status_code == 400
    assert client.post("/api/setup/steps/theme", json={"state": "maybe"}).status_code == 400
    done = client.post("/api/setup/finish").get_json()
    assert done["done"] and done["by"] == "tester"
    assert client.get("/").status_code == 200


def test_only_admins_set_up(app_module, client):
    app_module.app.extensions["auth"].users.add("watcher", "role-password-1", role="viewer")
    viewer = app_module.app.test_client()
    viewer.post("/login", data={"username": "watcher", "password": "role-password-1"})
    assert viewer.get("/").status_code == 200          # not sent to setup
    assert viewer.get("/api/setup").get_json() == {"needs_account": False, "done": False}
    assert viewer.post("/api/setup/finish").status_code == 403
    assert viewer.get("/setup").status_code == 302


def test_an_install_with_content_counts_as_set_up(client):
    client.post("/api/switches", json={"name": "sw-a-01", "x": 10, "y": 10})
    setup.mark_existing()
    assert setup.state()["done"] is True
    assert client.get("/").status_code == 200


def test_saving_a_setting_during_setup_does_not_end_it(client):
    setup.mark_existing()
    assert client.put("/api/settings", json={"theme.preset": "ops"}).status_code == 200
    assert client.get("/api/setup").get_json()["done"] is False


def test_a_floor_plan_filled_before_setup_started_counts_as_set_up(client):
    # e.g. `flask users add` opened the record, then the demo hall or a restore filled the plan.
    setup.mark_existing()
    client.post("/api/seat-blocks", json={"name": "A", "x": 10, "y": 10, "cols": 2, "rows": 1})
    setup.mark_existing()
    assert setup.state()["done"] is True


def test_a_started_setup_stays_open(client):
    setup.mark_existing()
    client.post("/api/setup/steps/netbox", json={"state": "skipped"})
    client.post("/api/switches", json={"name": "sw-a-01", "x": 10, "y": 10})
    setup.mark_existing()
    assert setup.state()["done"] is False
