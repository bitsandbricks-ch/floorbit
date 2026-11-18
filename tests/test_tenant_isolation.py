"""Tenants on one platform never reach each other's data (issue #466, docs/tenancy.md).

On a hosted platform each tenant runs its own processes, sharing the database, Redis, often the
S3 bucket and SECRET_KEY. Here one test process plays several tenants by switching FLOORBIT_TENANT
between requests, and every test tries to read or act across the line."""
import hashlib
import hmac

import pytest

from floorbit import agent_link, incidents, s3_backup, store, tenancy

PASSWORD = "long-enough-password-1"


@pytest.fixture
def tenants(app_module, monkeypatch):
    """``switch(name)`` makes the next requests those of tenant ``name`` ('' for the default)."""
    auth = app_module.app.extensions["auth"]
    # The test app keeps accounts in one fixed file; a real one reads the tenant's.
    monkeypatch.setattr(auth.users, "path", store.tenant_file)

    def switch(name):
        if name:
            monkeypatch.setenv(store.TENANT_ENV, name)
        else:
            monkeypatch.delenv(store.TENANT_ENV, raising=False)
        tenancy.forget()
        agent_link._forget_cache()

    def admin(name, username="boss"):
        switch(name)
        auth.users.add(username, PASSWORD, role="admin")
        c = app_module.app.test_client()
        assert c.post("/login", data={"username": username, "password": PASSWORD}).status_code == 302
        return c

    switch.admin = admin
    yield switch
    switch("")


def _signed_in(c):
    return c.get("/api/agents").status_code == 200


def test_a_session_only_counts_in_the_tenant_that_signed_it_in(tenants):
    a = tenants.admin("club-a")
    tenants.admin("club-b")             # the same username, the same SECRET_KEY, another tenant
    tenants("club-a")
    assert _signed_in(a)
    tenants("club-b")
    assert not _signed_in(a)            # club-a's cookie taken to club-b's address
    tenants("club-a")
    assert not _signed_in(a)            # and it was dropped, not just refused once


def test_sessions_from_before_tenants_stay_signed_in_on_the_default_tenant(client):
    with client.session_transaction() as s:
        s.pop("tenant")                 # a cookie made before sessions named their tenant
    assert _signed_in(client)


def test_a_session_from_before_tenants_is_not_one_of_a_hosted_tenant(tenants):
    a = tenants.admin("club-a")
    with a.session_transaction() as s:
        s.pop("tenant")
    assert not _signed_in(a)


def test_one_tenant_s_floor_plan_is_not_another_s(tenants):
    a = tenants.admin("club-a")
    assert a.post("/api/switches", json={"name": "sw-a-01", "x": 1, "y": 1}).status_code in (200, 201)
    b = tenants.admin("club-b")
    assert all(s.get("name") != "sw-a-01" for s in b.get("/api/switches").get_json())
    assert b.get("/api/seat-blocks").get_json() == []


def test_an_api_token_only_opens_its_own_tenant(tenants):
    a = tenants.admin("club-a")
    secret = a.post("/api/settings/api-tokens", json={"name": "Script", "role": "viewer"}).get_json()["secret"]
    tenants.admin("club-b")
    anon = a.application.test_client()
    tenants("club-a")
    assert anon.get("/api/switches", headers={"Authorization": f"Bearer {secret}"}).status_code == 200
    tenants("club-b")
    assert anon.get("/api/switches", headers={"Authorization": f"Bearer {secret}"}).status_code == 401


def test_an_agent_key_only_connects_to_its_own_tenant(tenants):
    a = tenants.admin("club-a")
    key = a.post("/api/agents", json={"name": "Hall A"}).get_json()["key"]
    tenants.admin("club-b")
    anon = a.application.test_client()
    head = {"Floorbit-Agent-Key": key, "Floorbit-Agent-Version": "1.2.3"}
    tenants("club-b")
    assert anon.get("/api/agent/v1/hello", headers=head).status_code == 401
    tenants("club-a")
    assert anon.get("/api/agent/v1/hello", headers=head).status_code == 200


@pytest.fixture
def bucket(monkeypatch):
    from test_s3_backup import ACCESS, SECRET, FakeBucket
    fake = FakeBucket()
    monkeypatch.setattr(s3_backup.requests, "request", fake)
    # One set of S3_BACKUP_* for the whole platform: the likely setup on a hosted one.
    for key, value in {"S3_BACKUP_ENDPOINT": "https://s3.example.com", "S3_BACKUP_BUCKET": "backups",
                       "S3_BACKUP_ACCESS_KEY": ACCESS, "S3_BACKUP_SECRET_KEY": SECRET,
                       "S3_BACKUP_PREFIX": "lan/"}.items():
        monkeypatch.setenv(key, value)
    return fake


def test_tenants_sharing_a_bucket_keep_their_backups_apart(tenants, bucket):
    home = tenants.admin("")
    mine = home.post("/api/settings/backup/s3").get_json()["name"]
    a = tenants.admin("club-a")
    theirs = a.post("/api/settings/backup/s3").get_json()["name"]
    assert sorted(bucket.objects) == sorted(["lan/" + mine, "lan/tenants/club-a/" + theirs])
    # Each lists only its own: the default tenant's folder holds the others' below it.
    other = "lan/tenants/club-a/" + theirs
    assert [b["key"] for b in a.get("/api/settings/backup/s3").get_json()["backups"]] == [other]
    tenants("")
    assert [b["key"] for b in home.get("/api/settings/backup/s3").get_json()["backups"]] == ["lan/" + mine]
    # Nor restores or downloads another's.
    assert home.post("/api/settings/backup/s3/restore", json={"key": other}).status_code == 400
    assert home.get("/api/settings/backup/s3/download", query_string={"key": other}).status_code == 400
    tenants("club-a")
    assert a.post("/api/settings/backup/s3/restore", json={"key": "lan/" + mine}).status_code == 400


def test_a_seat_help_link_only_checks_out_in_its_own_tenant(app_module, tenants):
    with app_module.app.app_context():
        tenants("")
        home = incidents.signature("A-1")
        secret = app_module.app.config["SECRET_KEY"].encode()
        # Cards printed before tenants keep working on the default tenant.
        assert home == hmac.new(secret, b"helpdesk:A-1", hashlib.sha256).hexdigest()[:incidents.SIGNATURE_LENGTH]
        tenants("club-a")
        assert not incidents.signed("A-1", home)
        assert incidents.signed("A-1", incidents.signature("A-1"))


def test_a_configured_monitoring_cache_file_is_still_per_tenant(tmp_path, monkeypatch):
    from floorbit.sources import lastgood
    state = tmp_path
    monkeypatch.setattr(store, "DATA_FILE", str(state / "data.json"))
    tenancy.forget()
    monkeypatch.setenv("MONITORING_CACHE_FILE", str(state / "monitoring.json"))
    assert lastgood.path() == str(state / "monitoring.json")
    monkeypatch.setenv(store.TENANT_ENV, "club-a")
    tenancy.forget()
    assert lastgood.path() == str(state / "tenants" / "club-a" / "monitoring.json")


def test_every_tenant_has_its_own_redis_keys_and_live_channel(monkeypatch):
    from floorbit import cache
    monkeypatch.setenv(store.TENANT_ENV, "club-a")
    a = cache.redis_prefix()
    monkeypatch.setenv(store.TENANT_ENV, "club-b")
    assert a == "club-a:" and cache.redis_prefix() == "club-b:"
