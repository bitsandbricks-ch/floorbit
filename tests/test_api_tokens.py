"""API tokens and the API's version (issue #40)."""
import time

from auth import tokens
from tests.test_rbac import sign_in_as


def _make(client, **body):
    resp = client.post("/api/settings/api-tokens", json={"name": "Scoreboard", "role": "viewer", **body})
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()


def test_a_token_reads_the_api_with_its_role_and_is_audited(app_module, client):
    made = _make(client, role="lead")
    secret = made["secret"]
    assert secret.startswith("fbt_") and "hash" not in made["token"]
    listed = client.get("/api/settings/api-tokens").get_json()["tokens"]
    assert [t["name"] for t in listed] == ["Scoreboard"] and "hash" not in listed[0]
    assert secret not in str(listed)   # shown once, never again

    bot = app_module.app.test_client()   # no session cookie
    auth = {"Authorization": f"Bearer {secret}"}
    me = bot.get("/api/auth/me", headers=auth).get_json()
    assert me["user"]["username"] == "token:Scoreboard" and me["user"]["role"] == "lead"
    resp = bot.post("/api/switches", headers=auth, json={"name": "sw-api-01", "x": 1, "y": 1})
    assert resp.status_code in (200, 201), resp.get_json()   # no Origin check: a token isn't a cookie
    assert resp.headers["Floorbit-API"] == "1"
    entries = client.get("/api/settings/audit").get_json()["entries"]
    assert any(e["action"] == "Added switch" and e["user"] == "token:Scoreboard" for e in entries)
    assert any(e["action"] == "Created API token" and e["target"] == "Scoreboard" for e in entries)
    assert client.get("/api/settings/api-tokens").get_json()["tokens"][0]["last_used_at"]

    # Its role still counts: a lead can't change settings.
    assert bot.put("/api/settings", headers=auth, json={"theme.name": "x"}).status_code == 403


def test_tokens_cant_reach_accounts_or_tokens_or_pages(app_module, client):
    secret = _make(client, role="admin")["secret"]
    bot = app_module.app.test_client()
    auth = {"Authorization": f"Bearer {secret}"}
    assert bot.get("/api/settings/features", headers=auth).status_code == 200   # admin: settings, yes
    for path in ("/api/users", "/api/roles", "/api/teams", "/api/settings/api-tokens", "/settings"):
        assert bot.get(path, headers=auth).status_code == 403, path
    assert bot.post("/api/settings/api-tokens", headers=auth, json={"name": "x", "role": "admin"}).status_code == 403


def test_read_only_wrong_expired_and_revoked_tokens(app_module, client):
    reader = _make(client, name="Wall", read_only=True)
    bot = app_module.app.test_client()
    auth = {"Authorization": f"Bearer {reader['secret']}"}
    assert bot.get("/api/switches", headers=auth).status_code == 200
    assert bot.post("/api/incidents", headers=auth, json={"title": "x"}).get_json()["error"] == \
        "This API token can only read."

    wrong = reader["secret"][:-4] + "abcd"
    for value in (f"Bearer {wrong}", "Bearer ", "Bearer fbt_nothing"):
        assert bot.get("/api/switches", headers={"Authorization": value}).status_code == 401
    # Another scheme (a reverse proxy's Basic auth) is not a token: it reads like any visitor.
    assert bot.get("/api/switches", headers={"Authorization": "Basic Zm9vOmJhcg=="}).status_code == 200

    soon = _make(client, name="Short", expires_days=1)
    record = tokens.check(soon["secret"])
    assert record and tokens.check(soon["secret"], now=time.time() + 2 * 86400) is None

    assert client.delete(f"/api/settings/api-tokens/{reader['token']['id']}").status_code == 200
    assert bot.get("/api/switches", headers=auth).status_code == 401
    assert client.delete(f"/api/settings/api-tokens/{reader['token']['id']}").status_code == 404


def test_bad_input_and_only_admins_manage_tokens(app_module, client):
    for body in ({"name": "", "role": "viewer"}, {"name": "x", "role": "nope"},
                 {"name": "x", "role": "viewer", "expires_days": 999}, {"name": "<b>", "role": "viewer"}):
        assert client.post("/api/settings/api-tokens", json=body).status_code == 400, body
    _make(client)
    assert client.post("/api/settings/api-tokens", json={"name": "scoreboard", "role": "viewer"}).status_code == 400
    lead = sign_in_as(app_module, "le1", "lead")
    assert lead.get("/api/settings/api-tokens").status_code == 403


def test_version(client):
    body = client.get("/api/version").get_json()
    assert body["api"] == 1 and body["app"]
