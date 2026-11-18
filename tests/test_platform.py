"""The platform admin page: adding, changing and suspending tenants (floorbit/blueprints/platform.py)."""
import pytest

from floorbit import hosting, store, tenancy


@pytest.fixture(autouse=True)
def _fresh_status():
    hosting._status_cache.clear()
    yield
    hosting._status_cache.clear()


def _as(monkeypatch, tenant):
    monkeypatch.setenv(store.TENANT_ENV, tenant)
    tenancy.forget()
    hosting._status_cache.clear()


def test_the_default_tenant_s_admins_see_the_platform(client):
    resp = client.get("/api/platform/tenants")
    assert resp.status_code == 200
    default = {"id": "default", "name": "", "url": "", "status": "active"}
    assert resp.get_json() == {"here": "default", "tenants": [default]}


def test_adding_a_tenant_with_its_first_admin(client):
    resp = client.post("/api/platform/tenants", json={"id": "club-b", "name": "Club B",
                                                      "url": "https://club-b.example.com", "admin": "boss"})
    assert resp.status_code == 201, resp.get_json()
    made = resp.get_json()
    assert made["tenant"] == {"id": "club-b", "name": "Club B", "url": "https://club-b.example.com", "status": "active"}
    assert made["admin"] == "boss" and len(made["password"]) >= 12
    users = hosting.tenant_data("club-b")["auth_users"]
    assert users["boss"]["role"] == "admin"
    assert "boss" not in (store.read_json(store.DATA_FILE, {}).get("auth_users") or {})
    assert [t["id"] for t in client.get("/api/platform/tenants").get_json()["tenants"]] == ["default", "club-b"]
    assert client.get("/api/settings/audit").get_json()  # recorded (shape checked in test_audit)


def test_bad_tenants_are_refused_and_leave_nothing_behind(client):
    for body in ({"id": "default"}, {"id": "../x"}, {"id": "club-c", "url": "javascript:x"},
                 {"id": "club-c", "admin": "no spaces allowed"}):
        assert client.post("/api/platform/tenants", json=body).status_code == 400, body
    assert [t["id"] for t in hosting.tenants()] == ["default"]
    resp = client.post("/api/platform/tenants", json={"id": "Bad Name"}, headers={"Accept-Language": "de-CH"})
    assert resp.get_json()["error"].startswith("Ein Mandanten-Name")


def test_the_default_tenant_can_not_be_suspended(client):
    resp = client.patch("/api/platform/tenants/default", json={"status": "suspended"})
    assert resp.status_code == 400
    assert client.patch("/api/platform/tenants/nobody", json={"status": "suspended"}).status_code == 404


def test_a_suspended_tenant_answers_nothing_but_health(client, anon_client, monkeypatch):
    hosting.add("club-b", "Club B")
    assert client.patch("/api/platform/tenants/club-b", json={"status": "suspended"}).status_code == 200
    _as(monkeypatch, "club-b")
    for path in ("/login", "/", "/api/switches", "/api/agent/v1/hello", "/status"):
        resp = anon_client.get(path, headers={"Accept-Language": "de-CH"})
        assert resp.status_code == 503, path
    assert anon_client.get("/api/switches").get_json()["code"] == "tenant_suspended"
    assert "gesperrt" in anon_client.get("/login", headers={"Accept-Language": "de-CH"}).get_data(as_text=True)
    assert anon_client.get("/healthz").status_code != 503
    # Taken back, it answers again.
    _as(monkeypatch, "default")
    assert client.patch("/api/platform/tenants/club-b", json={"status": "active"}).status_code == 200
    _as(monkeypatch, "club-b")
    assert anon_client.get("/login").status_code == 200


def test_other_tenants_and_other_roles_never_see_the_platform(app_module, client, monkeypatch):
    hosting.add("club-b")
    app_module.app.extensions["auth"].users.add("lead-1", "lead-password-1", role="lead")
    lead = app_module.app.test_client()
    lead.post("/login", data={"username": "lead-1", "password": "lead-password-1"})
    assert lead.get("/api/platform/tenants").status_code == 403
    token = client.post("/api/settings/api-tokens", json={"name": "Script", "role": "admin"}).get_json()["secret"]
    assert app_module.app.test_client().get(
        "/api/platform/tenants", headers={"Authorization": f"Bearer {token}"}).status_code == 403
    # An admin of another tenant: the platform isn't there at all.
    _as(monkeypatch, "club-b")
    monkeypatch.setattr(app_module.app.extensions["auth"].users, "path", store.tenant_file)
    app_module.app.extensions["auth"].users.add("boss", "boss-password-1", role="admin")
    boss = app_module.app.test_client()
    boss.post("/login", data={"username": "boss", "password": "boss-password-1"})
    assert boss.get("/api/settings/api-tokens").status_code == 200     # an admin there
    assert boss.get("/api/platform/tenants").status_code == 404
    assert boss.post("/api/platform/tenants", json={"id": "club-x"}).status_code == 404
    assert boss.patch("/api/platform/tenants/default", json={"name": "x"}).status_code == 404
    _as(monkeypatch, "default")


def test_the_page_is_in_the_sidebar_only_on_the_default_tenant(client, monkeypatch):
    from floorbit import page_index
    ctx = {"feature_on": lambda name: True}
    can = lambda permission: True  # noqa: E731
    show = {r[0]: r for r in page_index.PAGES}["/settings/tenants"][3]
    assert show(ctx, can)
    _as(monkeypatch, "club-b")
    assert not show(ctx, can)
    _as(monkeypatch, "default")
