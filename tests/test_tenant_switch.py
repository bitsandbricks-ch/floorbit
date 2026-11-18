"""The tenant switcher: hand-offs between tenants (floorbit/tenant_switch.py, blueprints/tenant_switch.py)."""
from urllib.parse import parse_qs, urlsplit

import pytest
from conftest import TEST_USER

from floorbit import hosting, store, tenancy, tenant_switch
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
    # Every tenant's accounts are its own data.json, as in a real process of that tenant.
    store_ = app_module.app.extensions["auth"].users
    monkeypatch.setattr(store_, "path", store.tenant_file)
    return store_


def _as(monkeypatch, tenant):
    monkeypatch.setenv(store.TENANT_ENV, tenant)
    tenancy.forget()
    hosting._status_cache.clear()
    switch_bp._known.clear()


def _account(tenant, username, role="viewer", **identities):
    from auth.users import UserStore
    with store.using(tenant=store.tenant_folder(tenant), event=""):
        UserStore(store.tenant_file).add(username, "long-enough-pass-1", role=role, identities=identities)


def _tenants():
    hosting.add("club-b", "Club B", "https://club-b.example.com")
    hosting.add("club-c", "Club C", "https://club-c.example.com")
    hosting.add("club-d", "Club D")                          # no address: nowhere to send anyone
    hosting.update("club-c", status="suspended")


def _ticket(url):
    return parse_qs(urlsplit(url).query)["ticket"][0]


def test_one_tenant_shows_no_switcher(client):
    assert client.get("/api/tenant/mine").get_json() == {"here": "default", "tenants": []}


def test_platform_admins_reach_every_active_tenant_with_an_address(client, users):
    _tenants()
    got = client.get("/api/tenant/mine").get_json()
    assert got["tenants"] == [
        {"id": "club-b", "name": "Club B", "url": "https://club-b.example.com", "how": "platform"}]


def test_a_platform_admin_visits_a_tenant_without_an_account_there(client, anon_client, users, monkeypatch):
    _tenants()
    resp = client.post("/api/tenant/switch", json={"tenant": "club-b"})
    assert resp.status_code == 200, resp.get_json()
    url = resp.get_json()["url"]
    assert url.startswith("https://club-b.example.com/switch/arrive?ticket=")
    _as(monkeypatch, "club-b")
    arrived = anon_client.get(f"/switch/arrive?ticket={_ticket(url)}")
    assert arrived.status_code == 302 and arrived.headers["Location"].endswith("/")
    me = anon_client.get("/api/auth/me").get_json()["user"]
    assert me["username"] == f"platform:{TEST_USER}" and me["role"] == "admin" and me["platform"]
    assert anon_client.get("/api/settings/audit").status_code == 200        # an admin there
    assert users.get(f"platform:{TEST_USER}") is None                       # and no account made
    page = anon_client.get("/problems").get_data(as_text=True)
    assert '"platform": true' in page or '"platform":true' in page             # the sidebar says so
    log = anon_client.get("/api/settings/audit").get_json()
    assert any(e.get("action") == "Came in from another tenant" and e.get("user") == f"platform:{TEST_USER}"
               for e in log.get("entries", log if isinstance(log, list) else []))
    # A visitor can't hop on to a third tenant from there.
    assert anon_client.get("/api/tenant/mine").get_json()["tenants"] == []
    assert anon_client.post("/api/tenant/switch", json={"tenant": "default"}).status_code == 403
    # The ticket worked once.
    other = anon_client.application.test_client()
    assert other.get(f"/switch/arrive?ticket={_ticket(url)}").headers["Location"].endswith("/login")
    assert other.get("/api/auth/me").get_json()["user"] is None


def test_a_visit_ends_when_the_platform_admin_loses_the_right(client, anon_client, users, monkeypatch):
    _tenants()
    url = client.post("/api/tenant/switch", json={"tenant": "club-b"}).get_json()["url"]
    _as(monkeypatch, "club-b")
    anon_client.get(f"/switch/arrive?ticket={_ticket(url)}")
    assert anon_client.get("/api/auth/me").get_json()["user"]
    _as(monkeypatch, "default")
    users.add("other-admin", "long-enough-pass-1", role="admin")
    users.update(TEST_USER, role="viewer")
    _as(monkeypatch, "club-b")
    assert anon_client.get("/api/auth/me").get_json()["user"] is None
    assert anon_client.get("/api/settings/audit").status_code in (302, 401)


def test_old_and_made_up_tickets_get_nobody_in(client, anon_client, users, monkeypatch):
    _tenants()
    url = client.post("/api/tenant/switch", json={"tenant": "club-b"}).get_json()["url"]
    _as(monkeypatch, "club-b")
    import time
    assert tenant_switch.take(_ticket(url), now=time.time() + tenant_switch.TICKET_TTL + 1) is None
    for bad in ("", "x", "../../data", "a" * 500, _ticket(url)):
        resp = anon_client.get("/switch/arrive", query_string={"ticket": bad})
        assert resp.headers["Location"].endswith("/login"), bad
    assert anon_client.get("/api/auth/me").get_json()["user"] is None


def test_a_ticket_only_works_in_the_tenant_it_was_written_for(client, anon_client, users, monkeypatch):
    hosting.add("club-b", "Club B", "https://club-b.example.com")
    hosting.add("club-e", "Club E", "https://club-e.example.com")
    url = client.post("/api/tenant/switch", json={"tenant": "club-b"}).get_json()["url"]
    _as(monkeypatch, "club-e")
    assert anon_client.get(f"/switch/arrive?ticket={_ticket(url)}").headers["Location"].endswith("/login")


def test_a_linked_account_switches_into_its_account_there(app_module, users, monkeypatch):
    hosting.add("club-b", "Club B", "https://club-b.example.com")
    hosting.add("club-e", "Club E", "https://club-e.example.com")
    users.add("anna", "long-enough-pass-1", role="lead", identities={"discord": "111"})
    _account("club-b", "anna-b", role="tech", discord="111")
    anna = app_module.app.test_client()
    anna.post("/login", data={"username": "anna", "password": "long-enough-pass-1"})
    assert anna.get("/api/tenant/mine").get_json()["tenants"] == [
        {"id": "club-b", "name": "Club B", "url": "https://club-b.example.com", "how": "account"}]
    assert anna.post("/api/tenant/switch", json={"tenant": "club-e"}).status_code == 403   # not hers
    url = anna.post("/api/tenant/switch", json={"tenant": "club-b"}).get_json()["url"]
    _as(monkeypatch, "club-b")
    there = app_module.app.test_client()
    there.get(f"/switch/arrive?ticket={_ticket(url)}")
    me = there.get("/api/auth/me").get_json()["user"]
    assert me["username"] == "anna-b" and me["role"] == "tech" and not me.get("platform")


def test_api_tokens_never_switch(client, app_module, users):
    _tenants()
    token = client.post("/api/settings/api-tokens", json={"name": "Script", "role": "admin"}).get_json()["secret"]
    script = app_module.app.test_client()
    headers = {"Authorization": f"Bearer {token}"}
    assert script.post("/api/tenant/switch", json={"tenant": "club-b"}, headers=headers).status_code == 403
    assert script.get("/api/tenant/mine", headers=headers).get_json()["tenants"] == []


def test_a_suspension_leaves_the_switcher_at_once(client, users):
    hosting.add("tenant-x", "Tenant X", "https://tenant-x.example.com")
    assert [t["id"] for t in client.get("/api/tenant/mine").get_json()["tenants"]] == ["tenant-x"]
    assert client.patch("/api/platform/tenants/tenant-x", json={"status": "suspended"}).status_code == 200
    assert client.get("/api/tenant/mine").get_json()["tenants"] == []
