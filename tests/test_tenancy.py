"""Tenants and events (issue #466): where each one's documents live. See docs/tenancy.md."""
import json

import pytest

from floorbit import database, store, tenancy


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.delenv(database.ENV, raising=False)
    monkeypatch.setattr(store, "DATA_FILE", str(tmp_path / "data.json"))
    tenancy.forget()
    yield tmp_path
    tenancy.forget()


def _events(tmp_path, events):
    (tmp_path / "tenant.json").write_text(json.dumps({"events": events}))
    tenancy.forget()


def test_without_tenant_json_everything_stays_where_it_was(state):
    assert tenancy.events() == [{"id": "main", "name": "", "status": "live", "folder": ""}]
    assert store.event_file() == store.DATA_FILE
    assert store.tenant_file() == store.DATA_FILE
    assert store.event_path("halls") == str(state / "halls")
    assert store.tenant_path("plugins.json") == str(state / "plugins.json")
    # A file someone configured (CHECKIN_FILE and so on) is left exactly as it was.
    assert store.event_file("/elsewhere/checkins.json") == "/elsewhere/checkins.json"


def test_a_later_live_event_gets_its_own_folder(state):
    store.save_data({"seat_blocks": [{"id": "A"}], "auth_users": {"mike": {}}})
    _events(state, [{"id": "main", "status": "closed"}, {"id": "lan-2027", "status": "live", "name": "LAN 2027"}])
    assert tenancy.live()["folder"] == "event-data/lan-2027"
    assert store.event_path("halls") == str(state / "event-data" / "lan-2027" / "halls")
    assert store.event_file("/elsewhere/checkins.json") == str(state / "event-data" / "lan-2027" / "checkins.json")
    # Tenant documents stay in the tenant's folder.
    assert store.tenant_file() == store.DATA_FILE
    assert store.tenant_path("plugins.json") == str(state / "plugins.json")

    assert store.load_data()["seat_blocks"] == []      # the new event starts empty
    store.save_data({"seat_blocks": [{"id": "B"}]})
    assert json.loads((state / "event-data" / "lan-2027" / "data.json").read_text()) == {"seat_blocks": [{"id": "B"}]}
    # The first event's plan (and the accounts beside it) are untouched.
    assert json.loads((state / "data.json").read_text())["seat_blocks"] == [{"id": "A"}]


def test_using_picks_an_event_for_a_block(state):
    store.save_data({"seat_blocks": [{"id": "A"}]})
    _events(state, [{"id": "main", "status": "planning"}, {"id": "next", "status": "live"}])
    with tenancy.using_event(tenancy.find("main")):
        assert store.load_data()["seat_blocks"] == [{"id": "A"}]
    assert store.load_data()["seat_blocks"] == []


def test_the_event_list_is_made_safe(state):
    _events(state, [
        {"id": "main", "status": "live"},
        {"id": "../../etc", "status": "live"},          # becomes a folder name: refused
        {"id": "b", "status": "live", "folder": "/tmp"},  # the folder comes from the id, never the file
        {"id": "b", "status": "planning"},               # a second "b": dropped
        {"id": "c", "status": "whatever"},
        "not an event",
    ])
    assert [(e["id"], e["status"], e["folder"]) for e in tenancy.events()] == [
        ("main", "live", ""), ("b", "planning", "event-data/b"), ("c", "planning", "event-data/c")]


def test_no_live_event_means_the_first_one(state):
    _events(state, [{"id": "a", "status": "closed"}, {"id": "b", "status": "planning"}])
    assert tenancy.live()["id"] == "a"


def test_a_broken_tenant_json_falls_back_to_the_default(state):
    (state / "tenant.json").write_text("[1, 2]")
    tenancy.forget()
    assert tenancy.live()["id"] == "main"


def test_events_in_a_database_are_kept_apart(state, monkeypatch):
    monkeypatch.setenv(database.ENV, f"sqlite:///{state / 'floorbit.db'}")
    try:
        store.save_data({"seat_blocks": [{"id": "A"}]})
        store.write_json(store.tenant_path(tenancy.TENANT_FILE),
                         {"events": [{"id": "main", "status": "planning"}, {"id": "x", "status": "live"}]})
        tenancy.forget()
        store.save_data({"seat_blocks": [{"id": "X"}]})
        db = database.backend()
        assert json.loads(db.get_text("event-data/x/data.json")) == {"seat_blocks": [{"id": "X"}]}
        assert json.loads(db.get_text("data.json")) == {"seat_blocks": [{"id": "A"}]}
    finally:
        database.backend().close()


def test_accounts_and_settings_read_the_tenant_file(state):
    from auth.users import UserStore
    from floorbit.settings import SettingsStore
    store.write_json(store.DATA_FILE, {"auth_users": {"mike": {"username": "mike"}}, "app_settings": {}})
    _events(state, [{"id": "main", "status": "closed"}, {"id": "next", "status": "live"}])
    # Built the way create_app builds them: they follow the tenant, not the live event.
    users = UserStore(store.tenant_file)
    assert users.path == store.DATA_FILE and "mike" in users._users()
    assert SettingsStore(store.tenant_file, environ={}).data_file == store.DATA_FILE


# ── Events through the API (request context, copying) ────────────────────────────────────────

@pytest.fixture
def two_events(client, app_module):
    tenancy.forget()
    store.save_data({**store.load_data(), "seat_blocks": [{"id": "A", "name": "A"}], "incidents": [{"id": "i1"}]})
    made = client.post("/api/tenant/events", json={"name": "LAN 2027", "copy_from": "main"})
    assert made.status_code == 201, made.get_json()
    yield made.get_json()["event"]
    tenancy.forget()


def test_a_new_event_starts_from_a_copy_of_the_plan(client, two_events):
    assert two_events["id"] == "lan-2027" and two_events["status"] == "planning"
    listing = client.get("/api/tenant/events").get_json()
    assert [e["id"] for e in listing["events"]] == ["main", "lan-2027"]
    assert listing["live"] == "main" and listing["current"] == "main"
    with tenancy.using_event(tenancy.find("lan-2027")):
        data = store.load_data()
    assert data["seat_blocks"] == [{"id": "A", "name": "A"}]
    assert "incidents" not in data       # what happened at an event is never copied


def test_event_query_and_cookie_pick_the_event(client, two_events):
    r = client.get("/api/tenant/events?event=lan-2027")
    assert r.headers["X-Floorbit-Event"] == "lan-2027" and r.get_json()["current"] == "lan-2027"
    # The cookie keeps it for the next request; the live event is unchanged.
    assert client.get("/api/tenant/events").get_json()["current"] == "lan-2027"
    assert client.put("/api/tenant/current", json={"event": None}).status_code == 200
    assert client.get("/api/tenant/events").get_json()["current"] == "main"
    assert client.put("/api/tenant/current", json={"event": "nope"}).status_code == 404


def test_saving_in_another_event_keeps_accounts_in_the_tenant(client, two_events, app_module):
    client.put("/api/tenant/current", json={"event": "lan-2027"})
    with tenancy.using_event(tenancy.find("lan-2027")):
        data = store.load_data()
        assert "auth_users" in data          # the tenant's parts are there to read
        data["seat_blocks"].append({"id": "B"})
        data["app_settings"] = {**(data.get("app_settings") or {}), "theme.name": "Club"}
        store.save_data(data)
        event_doc = store.read_json(store.event_file(), {})
    assert "auth_users" not in event_doc and "app_settings" not in event_doc
    assert [b["id"] for b in event_doc["seat_blocks"]] == ["A", "B"]
    tenant_doc = store.read_json(store.tenant_file(), {})
    assert tenant_doc["app_settings"]["theme.name"] == "Club"
    assert [b["id"] for b in tenant_doc["seat_blocks"]] == ["A"]      # the first event's plan


def test_network_actions_need_the_live_event(client, two_events):
    client.put("/api/tenant/current", json={"event": "lan-2027"})
    r = client.post("/api/commands/run", json={})
    assert r.status_code == 409 and "isn't live" in r.get_json()["error"]


def test_making_an_event_live(client, two_events):
    r = client.patch("/api/tenant/events/lan-2027", json={"status": "live"})
    assert r.status_code == 200 and r.get_json()["event"]["status"] == "live"
    statuses = {e["id"]: e["status"] for e in client.get("/api/tenant/events").get_json()["events"]}
    assert statuses == {"main": "planning", "lan-2027": "live"}
    # One event is always live.
    assert client.patch("/api/tenant/events/lan-2027", json={"status": "closed"}).status_code == 409
    assert client.patch("/api/tenant/events/main", json={"name": ""}).status_code == 400


def test_copy_into_an_existing_event_previews_then_merges(client, two_events):
    with tenancy.using_event(tenancy.find("lan-2027")):
        data = store.load_data()
        data["seat_blocks"] = [{"id": "A", "name": "renamed"}, {"id": "Z", "name": "Z"}]
        store.save_data(data)
    body = {"to": "lan-2027", "parts": ["seats"], "mode": "merge", "preview": True}
    preview = client.post("/api/tenant/events/main/copy", json=body).get_json()
    assert preview["changes"] == {"seats": {"added": 0, "changed": 1, "removed": 0}}
    with tenancy.using_event(tenancy.find("lan-2027")):
        assert store.load_data()["seat_blocks"][0]["name"] == "renamed"   # a preview saves nothing
    body.pop("preview")
    assert client.post("/api/tenant/events/main/copy", json=body).status_code == 200
    with tenancy.using_event(tenancy.find("lan-2027")):
        assert store.load_data()["seat_blocks"] == [{"id": "A", "name": "A"}, {"id": "Z", "name": "Z"}]
    body["mode"] = "replace"
    client.post("/api/tenant/events/main/copy", json=body)
    with tenancy.using_event(tenancy.find("lan-2027")):
        assert store.load_data()["seat_blocks"] == [{"id": "A", "name": "A"}]
    assert client.post("/api/tenant/events/main/copy", json={**body, "parts": ["x"]}).status_code == 400
    assert client.post("/api/tenant/events/main/copy", json={**body, "to": "main"}).status_code == 400


def test_only_admins_change_events():
    from auth import roles
    assert roles.needed_for("/api/tenant/events", "POST") == "settings.manage"
    assert roles.needed_for("/api/tenant/events/x/copy", "POST") == "settings.manage"
    assert roles.needed_for("/api/tenant/current", "PUT") == "floorplan.view"


def test_a_request_reads_and_writes_the_picked_event(client, two_events):
    with tenancy.using_event(tenancy.find("lan-2027")):
        data = store.load_data()
        data["seat_blocks"] = [{"id": "Z", "name": "Z", "x": 0, "y": 0, "rows": 1, "cols": 1}]
        store.save_data(data)
    assert [b["id"] for b in client.get("/api/seat-blocks?event=lan-2027").get_json()] == ["Z"]
    client.put("/api/tenant/current", json={"event": None})
    assert [b["id"] for b in client.get("/api/seat-blocks").get_json()] == ["A"]
    # The context ends with the request: code after it is back on the live event.
    assert store.event_dir() == ""


# ── Hosted: one process per tenant, sharing a state folder or database and Redis ───────────────

def test_without_floorbit_tenant_a_process_serves_the_default_tenant(state, monkeypatch):
    monkeypatch.delenv(store.TENANT_ENV, raising=False)
    assert store.current_tenant() == store.DEFAULT_TENANT == "default"
    # Its documents are where every install always kept them: nothing moves on the upgrade.
    assert store.tenant_file() == store.DATA_FILE
    assert store.event_path("halls") == str(state / "halls")
    monkeypatch.setenv(store.TENANT_ENV, "default")             # naming it changes nothing
    assert store.tenant_file() == store.DATA_FILE


def test_the_default_tenant_never_reaches_into_the_other_tenants(state, monkeypatch):
    monkeypatch.setenv(store.TENANT_ENV, "club-a")
    store.save_data({"seat_blocks": [{"id": "A"}]})
    store.write_json(store.tenant_path("secret.json"), {"x": 1})
    monkeypatch.delenv(store.TENANT_ENV)
    tenancy.forget()
    assert store.load_data()["seat_blocks"] == []
    assert "secret.json" not in store.list_json(store.tenant_path())
    assert not (state / "secret.json").exists()


def test_another_tenant_reads_the_default_tenant_by_name(state, monkeypatch):
    from floorbit import hosting
    store.write_json(store.DATA_FILE, {"app_settings": {"name": "Home"}})
    monkeypatch.setenv(store.TENANT_ENV, "club-a")
    assert hosting.tenant_data("default")["app_settings"] == {"name": "Home"}
    assert hosting.tenant_data("club-a") == {}

def test_a_hosted_tenant_keeps_its_documents_in_its_own_folder(state, monkeypatch):
    monkeypatch.setenv(store.TENANT_ENV, "club-a")
    assert store.tenant_file() == str(state / "tenants" / "club-a" / "data.json")
    assert store.event_path("halls") == str(state / "tenants" / "club-a" / "halls")
    store.save_data({"seat_blocks": [{"id": "A"}]})
    monkeypatch.setenv(store.TENANT_ENV, "club-b")
    tenancy.forget()
    assert store.load_data()["seat_blocks"] == []       # club-b sees nothing of club-a
    assert not (state / "data.json").exists()           # nor does anything land beside them


def test_hosted_tenants_share_one_database_apart(state, monkeypatch):
    monkeypatch.setenv(database.ENV, f"sqlite:///{state / 'floorbit.db'}")
    try:
        for name in ("club-a", "club-b"):
            monkeypatch.setenv(store.TENANT_ENV, name)
            tenancy.forget()
            store.save_data({"seat_blocks": [{"id": name}]})
            tenancy.create("Next year")
        db = database.backend()
        assert json.loads(db.get_text("tenants/club-a/data.json")) == {"seat_blocks": [{"id": "club-a"}]}
        assert json.loads(db.get_text("tenants/club-b/data.json")) == {"seat_blocks": [{"id": "club-b"}]}
        assert "tenants/club-a/tenant.json" in db.keys("tenants/club-a/")
        monkeypatch.setenv(store.TENANT_ENV, "club-a")
        tenancy.forget()
        assert [e["id"] for e in tenancy.events()] == ["main", "next-year"]
    finally:
        database.backend().close()


def test_a_wrong_tenant_name_is_refused(state, monkeypatch):
    monkeypatch.setenv(store.TENANT_ENV, "../other")
    with pytest.raises(ValueError):
        store.tenant_dir()


def test_hosted_tenants_share_one_redis_apart(monkeypatch):
    from conftest import FakeRedis

    from floorbit import cache
    shared = FakeRedis()
    monkeypatch.setenv(store.TENANT_ENV, "club-a")
    a = cache._scoped(shared)
    a.setex("arp:sw-01", 60, "[1]")
    monkeypatch.setenv(store.TENANT_ENV, "club-b")
    b = cache._scoped(shared)
    assert b.get("arp:sw-01") is None and a.get("arp:sw-01") == "[1]"
    assert list(a.scan_iter(match="arp:*")) == ["arp:sw-01"] and list(b.scan_iter(match="arp:*")) == []
    assert a.dbsize() == 1 and b.dbsize() == 0
    monkeypatch.delenv(store.TENANT_ENV)
    d = cache._scoped(shared)                         # self-hosted is the default tenant: prefixed too
    assert d.get("arp:sw-01") is None and d.dbsize() == 0
    d.setex("arp:sw-01", 60, "[2]")
    assert sorted(shared.store) == ["club-a:arp:sw-01", "default:arp:sw-01"]


# ── The hosted platform: its tenants and people in several of them ─────────────────────────────

def _account(tenant, username, **identities):
    from auth.users import UserStore
    with store.using(tenant=store.tenant_folder(tenant), event=""):
        UserStore(store.tenant_file).add(username, identities=identities)


def test_every_platform_starts_with_the_default_tenant(state):
    from floorbit import hosting
    default = {"id": "default", "name": "", "url": "", "status": "active"}
    assert hosting.tenants() == [default] and not hosting.several()   # no platform.json needed
    hosting.add("club-a")
    assert hosting.several()
    assert store.read_json(hosting.path(), {})["tenants"][0] == default   # written down with the second


def test_a_platform_admin_adds_tenants(state):
    from floorbit import hosting
    hosting.add("club-a", "Club A", "https://a.example.com/")
    hosting.add("club-b")
    assert hosting.tenants() == [{"id": "default", "name": "", "url": "", "status": "active"},
                                 {"id": "club-a", "name": "Club A", "url": "https://a.example.com", "status": "active"},
                                 {"id": "club-b", "name": "", "url": "", "status": "active"}]
    for bad in (("club-a",), ("default",), ("../x",), ("club-c", "", "http://c.example.com"),
                ("club-c", "", "javascript:x")):
        with pytest.raises(hosting.HostingError):
            hosting.add(*bad)


def test_the_same_outside_login_links_accounts_across_tenants(state, monkeypatch):
    from floorbit import hosting
    for name in ("club-a", "club-b", "club-c"):
        hosting.add(name, name.title(), f"https://{name}.example.com")
    _account("club-a", "anna", discord="111")
    _account("club-b", "anna-b", discord="111")
    _account("club-c", "anna", discord="222")             # the same username is not the same person
    monkeypatch.setenv(store.TENANT_ENV, "club-a")
    me = {"identities": {"discord": "111"}}
    assert hosting.memberships(me) == [
        {"id": "club-b", "name": "Club-B", "url": "https://club-b.example.com", "username": "anna-b"}]
    assert hosting.memberships({"identities": {}}) == []  # a password account matches nobody
    monkeypatch.delenv(store.TENANT_ENV)                  # the default tenant links the same way
    assert [t["id"] for t in hosting.memberships(me)] == ["club-a", "club-b"]
    _account("default", "anna", discord="111")
    monkeypatch.setenv(store.TENANT_ENV, "club-c")
    assert [t["id"] for t in hosting.memberships({"identities": {"discord": "222"}})] == []
    monkeypatch.setenv(store.TENANT_ENV, "club-b")
    assert [t["id"] for t in hosting.memberships(me)] == ["default", "club-a"]


def test_an_oidc_login_only_links_at_the_same_issuer(state, monkeypatch):
    from floorbit import hosting
    hosting.add("club-a")
    hosting.add("club-b")
    hosting.add("club-c")
    for name, issuer in (("club-a", "https://id.example.com"), ("club-b", "https://id.example.com"),
                         ("club-c", "https://other.example.com")):
        store.write_json(str(state / "tenants" / name / "data.json"),
                         {"auth_oidc": {"oidc": {"issuer": issuer}}})
        _account(name, "anna", oidc="sub-1")
    monkeypatch.setenv(store.TENANT_ENV, "club-a")
    assert [t["id"] for t in hosting.memberships({"identities": {"oidc": "sub-1"}})] == ["club-b"]


def test_tenants_add_on_the_command_line(app_module, monkeypatch):
    from floorbit import hosting
    runner = app_module.app.test_cli_runner()
    out = runner.invoke(args=["tenants", "add", "club-b", "--name", "Club B", "--url", "https://b.example.com",
                              "--admin", "boss", "--password", "long-enough-1"])
    assert out.exit_code == 0, out.output
    assert [t["id"] for t in hosting.tenants()] == ["default", "club-b"]
    users = hosting.tenant_data("club-b")["auth_users"]
    assert users["boss"]["role"] == "admin"
    assert "boss" not in (store.read_json(store.DATA_FILE, {}).get("auth_users") or {})   # not here
    assert runner.invoke(args=["tenants", "add", "club-b"]).exit_code != 0
    assert "club-b" in runner.invoke(args=["tenants", "list"]).output


def test_the_account_menu_asks_for_other_tenants(client):
    resp = client.get("/api/tenant/mine")
    assert resp.status_code == 200
    assert resp.get_json() == {"here": "default", "tenants": []}
