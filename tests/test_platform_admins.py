"""Who runs the platform: the platform admin flag, a tenant's admin set by the platform, and a
tenant turning platform visits off (auth/users.py, floorbit/blueprints/platform.py, tenant_switch.py)."""
from urllib.parse import parse_qs, urlsplit

import pytest
from conftest import TEST_USER

from floorbit import hosting, store, tenancy, tenant_switch, upgrades
from floorbit.blueprints import tenant_switch as switch_bp


@pytest.fixture(autouse=True)
def _fresh():
    hosting._status_cache.clear()
    switch_bp._known.clear()
    yield
    hosting._status_cache.clear()
    switch_bp._known.clear()


@pytest.fixture
def users(app_module, monkeypatch):
    found = app_module.app.extensions["auth"].users
    monkeypatch.setattr(found, "path", store.tenant_file)
    return found


def _as(monkeypatch, tenant):
    monkeypatch.setenv(store.TENANT_ENV, tenant)
    tenancy.forget()
    hosting._status_cache.clear()
    switch_bp._known.clear()


def _signed_in(app_module, username, role="admin"):
    app_module.app.extensions["auth"].users.add(username, "long-enough-pass-1", role=role)
    c = app_module.app.test_client()
    c.post("/login", data={"username": username, "password": "long-enough-pass-1"})
    return c


def test_the_first_account_runs_the_platform_and_later_admins_do_not(client, app_module, users):
    assert users.get(TEST_USER)["platform_admin"] is True
    assert client.get("/api/auth/me").get_json()["user"]["platform_admin"] is True
    crew = _signed_in(app_module, "event-admin")
    assert crew.get("/api/auth/me").get_json()["user"]["platform_admin"] is False
    # An admin of the default tenant, but not of the platform: the platform isn't there for them.
    assert crew.get("/api/platform/tenants").status_code == 404
    assert crew.get("/settings/tenants").status_code == 404
    assert crew.get("/api/tenant/mine").get_json()["tenants"] == [] or not hosting.several()
    assert client.get("/api/platform/tenants").status_code == 200


def test_a_platform_admin_gives_and_takes_the_flag(client, app_module, users):
    crew = _signed_in(app_module, "event-admin")
    # Only a platform admin can hand it out, even to themselves.
    assert crew.patch("/api/users/event-admin", json={"platform_admin": True}).status_code == 403
    assert client.get("/api/users").get_json()["platform"] is True
    assert crew.get("/api/users").get_json()["platform"] is False
    resp = client.patch("/api/users/event-admin", json={"platform_admin": True})
    assert resp.status_code == 200, resp.get_json()
    assert crew.get("/api/platform/tenants").status_code == 200
    # Only admins: a lead can't run the platform.
    _signed_in(app_module, "lead-1", role="lead")
    assert client.patch("/api/users/lead-1", json={"platform_admin": True}).status_code == 400
    # The last one keeps it, also against demotion and removal.
    assert client.patch("/api/users/event-admin", json={"platform_admin": False}).status_code == 200
    resp = client.patch(f"/api/users/{TEST_USER}", json={"platform_admin": False})
    assert resp.status_code == 400 and "last platform admin" in resp.get_json()["error"]
    assert crew.patch(f"/api/users/{TEST_USER}", json={"role": "viewer"}).status_code == 400
    assert crew.delete(f"/api/users/{TEST_USER}").status_code == 400


def test_the_flag_only_exists_in_the_default_tenant(app_module, users, monkeypatch):
    hosting.add("tenant-b", "Tenant B", "https://tenant-b.example.com")
    _as(monkeypatch, "tenant-b")
    with store.using(tenant=store.tenant_folder("tenant-b"), event=""):
        users.add("boss", "long-enough-pass-1", role="admin")      # the tenant's first account
        assert not users.get("boss").get("platform_admin")
        with pytest.raises(Exception, match="default tenant"):
            users.set_platform_admin("boss", True)
    _as(monkeypatch, "default")


def test_an_upgrade_keeps_the_admins_who_ran_the_platform(monkeypatch):
    data = {"auth_users": {"a": {"username": "a", "role": "admin"}, "b": {"username": "b", "role": "lead"}}}
    upgrades._platform_admins(data)
    assert data["auth_users"]["a"]["platform_admin"] is True and "platform_admin" not in data["auth_users"]["b"]
    other = {"auth_users": {"a": {"username": "a", "role": "admin"}}}
    with store.using(tenant=store.tenant_folder("tenant-b"), event=""):
        upgrades._platform_admins(other)
    assert "platform_admin" not in other["auth_users"]["a"]


def test_the_cli_names_platform_admins(app_module, client):
    runner = app_module.app.test_cli_runner()
    app_module.app.extensions["auth"].users.add("event-admin", "long-enough-pass-1", role="admin")
    assert runner.invoke(args=["platform-admins", "add", "event-admin"]).exit_code == 0
    assert "event-admin" in runner.invoke(args=["platform-admins", "list"]).output
    assert runner.invoke(args=["platform-admins", "remove", "event-admin"]).exit_code == 0
    assert runner.invoke(args=["platform-admins", "remove", TEST_USER]).exit_code != 0   # the last one


def test_the_platform_sets_a_tenant_s_admin(client, app_module, users, monkeypatch):
    hosting.add("tenant-b", "Tenant B", "https://tenant-b.example.com")
    resp = client.post("/api/platform/tenants/tenant-b/admin", json={"username": "boss"})
    assert resp.status_code == 200, resp.get_json()
    first = resp.get_json()
    assert first["made"] and first["admin"] == "boss" and len(first["password"]) >= 12
    again = client.post("/api/platform/tenants/tenant-b/admin", json={"username": "boss"}).get_json()
    assert not again["made"] and again["password"] != first["password"]
    assert hosting.tenant_data("tenant-b")["auth_users"]["boss"]["role"] == "admin"
    assert "boss" not in (store.read_json(store.DATA_FILE, {}).get("auth_users") or {})
    assert client.post("/api/platform/tenants/default/admin", json={"username": "x"}).status_code == 400
    assert client.post("/api/platform/tenants/nobody/admin", json={"username": "x"}).status_code == 404
    assert client.post("/api/platform/tenants/tenant-b/admin", json={"username": "no spaces"}).status_code == 400
    # The new password signs in there, and the tenant's own audit log says the platform did it.
    _as(monkeypatch, "tenant-b")
    there = app_module.app.test_client()
    assert there.post("/login", data={"username": "boss", "password": again["password"]}).status_code == 302
    entries = there.get("/api/settings/audit").get_json()["entries"]
    assert any(e["action"] == "The platform set an admin" and e.get("target") == "boss" for e in entries)
    _as(monkeypatch, "default")


def test_a_tenant_turns_platform_visits_off(client, anon_client, app_module, users, monkeypatch):
    hosting.add("tenant-b", "Tenant B", "https://tenant-b.example.com")
    assert client.get("/api/tenant/platform-access").get_json() == {"visits": True, "shown": False}
    assert client.put("/api/tenant/platform-access", json={"visits": False}).status_code == 400   # the platform's own
    url = client.post("/api/tenant/switch", json={"tenant": "tenant-b"}).get_json()["url"]
    ticket = parse_qs(urlsplit(url).query)["ticket"][0]
    _as(monkeypatch, "tenant-b")
    anon_client.get(f"/switch/arrive?ticket={ticket}")
    assert anon_client.get("/api/auth/me").get_json()["user"]["platform"]
    # The tenant's admin turns visits off: the visit under way ends, and no new one starts.
    with store.using(tenant=store.tenant_folder("tenant-b"), event=""):
        users.add("boss", "long-enough-pass-1", role="admin")
    boss = app_module.app.test_client()
    boss.post("/login", data={"username": "boss", "password": "long-enough-pass-1"})
    assert boss.get("/api/tenant/platform-access").get_json() == {"visits": True, "shown": True}
    assert boss.put("/api/tenant/platform-access", json={"visits": False}).status_code == 200
    assert anon_client.get("/api/auth/me").get_json()["user"] is None
    assert not tenant_switch.visits_allowed("tenant-b")
    _as(monkeypatch, "default")
    assert client.get("/api/tenant/mine").get_json()["tenants"] == []
    assert client.post("/api/tenant/switch", json={"tenant": "tenant-b"}).status_code == 403
