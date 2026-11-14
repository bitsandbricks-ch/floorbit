"""OIDC sign-in (issue #44) against a fake issuer with its own keys; nothing leaves the test."""
import base64
import hashlib
import time
from urllib.parse import parse_qs, urlsplit

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from auth import oidc
from floorbit import audit

ISSUER = "https://id.example.com/app"
CLIENT_ID = "floorbit-client"


class FakeResponse:
    def __init__(self, body, status=200):
        self._body, self.status_code = body, status

    def json(self):
        return self._body


class FakeIssuer:
    """Discovery, JWKS and a token endpoint that hands out ID tokens we sign ourselves."""

    def __init__(self):
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.kid = "key-1"
        self.claims = {}            # extra / overriding ID token claims for the next sign-in
        self.token_calls = []
        self.userinfo = None
        self.alg = "RS256"

    def jwks(self):
        jwk = jwt.algorithms.RSAAlgorithm.to_jwk(self.key.public_key(), as_dict=True)
        return {"keys": [{**jwk, "kid": self.kid, "use": "sig", "alg": "RS256"}]}

    def config(self):
        return {"issuer": ISSUER, "authorization_endpoint": ISSUER + "/authorize",
                "token_endpoint": ISSUER + "/token", "jwks_uri": ISSUER + "/jwks",
                "userinfo_endpoint": ISSUER + "/userinfo", "code_challenge_methods_supported": ["S256"],
                "id_token_signing_alg_values_supported": ["RS256"]}

    def get(self, url, **kwargs):
        if url == ISSUER + "/.well-known/openid-configuration":
            return FakeResponse(self.config())
        if url == ISSUER + "/jwks":
            return FakeResponse(self.jwks())
        if url == ISSUER + "/userinfo" and self.userinfo is not None:
            return FakeResponse(self.userinfo)
        return FakeResponse({}, 404)

    def id_token(self, nonce):
        now = int(time.time())
        claims = {"iss": ISSUER, "aud": CLIENT_ID, "sub": "user-123", "iat": now, "exp": now + 300,
                  "nonce": nonce, "preferred_username": "sam", "name": "Sam Example", "groups": ["fb-techs"]}
        claims.update(self.claims)
        claims = {k: v for k, v in claims.items() if v is not None}
        if self.alg == "HS256":
            secret = "client-secret-value-for-the-tests-only"
            return jwt.encode(claims, secret, algorithm="HS256", headers={"kid": self.kid})
        return jwt.encode(claims, self.key, algorithm="RS256", headers={"kid": self.kid})

    def post(self, url, data=None, auth=None, **kwargs):
        self.token_calls.append({"url": url, "data": data, "auth": auth})
        return FakeResponse({"access_token": "at", "token_type": "Bearer", "id_token": self.id_token(self.nonce)})


@pytest.fixture
def issuer(monkeypatch):
    fake = FakeIssuer()
    monkeypatch.setattr(oidc.requests, "get", fake.get)
    monkeypatch.setattr(oidc.requests, "post", fake.post)
    monkeypatch.setenv("OIDC_IDP_CLIENT_SECRET", "client-secret-value-for-the-tests-only")
    oidc._discovery.clear()
    yield fake
    oidc._discovery.clear()


def add_provider(client, mapping=(), **extra):
    body = {"name": "Example ID", "issuer": ISSUER, "client_id": CLIENT_ID,
            "role_mapping": [{"value": v, "role": r} for v, r in mapping], **extra}
    resp = client.put("/api/settings/oidc/idp", json=body)
    assert resp.status_code == 200, resp.data
    return resp.get_json()


def sign_in(app_module, issuer, **callback_args):
    browser = app_module.app.test_client()
    resp = browser.get("/auth/oidc-idp/start?next=/inventory")
    assert resp.status_code == 302, resp.data
    query = parse_qs(urlsplit(resp.headers["Location"]).query)
    issuer.nonce = query["nonce"][0]
    issuer.start_query = query
    args = {"code": "the-code", "state": query["state"][0], **callback_args}
    return browser, browser.get("/auth/oidc-idp/callback", query_string=args)


# ── Settings ───────────────────────────────────────────────────────────────────

def test_provider_settings_never_hold_the_secret(client, app_module, issuer):
    body = add_provider(client)
    [p] = body["providers"]
    assert p["secret_env"] == "OIDC_IDP_CLIENT_SECRET" and p["secret_set"] is True
    assert p["callback_url"].endswith("/auth/oidc-idp/callback")
    assert "client-secret-value-for-the-tests-only" not in str(body)
    with open(app_module.app.extensions["auth"].users.path) as f:
        assert "client-secret-value-for-the-tests-only" not in f.read()


@pytest.mark.parametrize("change, error", [
    ({"issuer": "http://id.example.com"}, "https"),
    ({"issuer": "https://id.example.com/?x=1"}, "issuer"),
    ({"client_id": ""}, "client ID"),
    ({"scopes": "profile email"}, "openid"),
    ({"name": "<b>"}, "name"),
    ({"role_mapping": [{"value": "x", "role": "root"}]}, "Role must be"),
])
def test_bad_provider_settings_are_refused(client, change, error):
    body = {"name": "Example ID", "issuer": ISSUER, "client_id": CLIENT_ID, **change}
    resp = client.put("/api/settings/oidc/idp", json=body)
    assert resp.status_code == 400 and error in resp.get_json()["error"]


def test_localhost_issuer_is_allowed_for_development(client):
    assert client.put("/api/settings/oidc/dev", json={"name": "Dev", "issuer": "http://localhost:9000",
                                                      "client_id": "x"}).status_code == 200


def test_provider_settings_need_settings_manage(app_module):
    app_module.app.extensions["auth"].users.add("le1", "lead-password-1", role="lead")
    lead = app_module.app.test_client()
    lead.post("/login", data={"username": "le1", "password": "lead-password-1"})
    assert lead.get("/api/settings/oidc").status_code == 403
    assert lead.put("/api/settings/oidc/idp", json={}).status_code == 403


def test_button_shows_only_with_a_secret(client, anon_client, issuer, monkeypatch):
    add_provider(client)
    assert b"Sign in with Example ID" in anon_client.get("/login").data
    monkeypatch.delenv("OIDC_IDP_CLIENT_SECRET")
    assert b"Sign in with Example ID" not in anon_client.get("/login").data
    assert anon_client.get("/auth/oidc-idp/start").status_code == 404


def test_secret_can_come_from_a_docker_secret_file(tmp_path, monkeypatch):
    monkeypatch.delenv("OIDC_IDP_CLIENT_SECRET", raising=False)
    secret = tmp_path / "secret"
    secret.write_text("from-a-file\n")
    monkeypatch.setenv("OIDC_IDP_CLIENT_SECRET_FILE", str(secret))
    assert oidc.client_secret("idp") == "from-a-file"


def test_test_button_reports_discovery(client, issuer):
    add_provider(client)
    body = client.post("/api/settings/oidc/idp/test").get_json()
    assert body["ok"] is True and body["keys"] == 1


# ── The flow ───────────────────────────────────────────────────────────────────

def test_mapped_group_signs_in_and_creates_an_account(client, app_module, issuer):
    add_provider(client, mapping=[("fb-techs", "tech"), ("fb-leads", "lead")])
    browser, resp = sign_in(app_module, issuer)
    assert resp.status_code == 302 and resp.headers["Location"].endswith("/inventory")
    # PKCE: the verifier sent to the token endpoint hashes to the challenge sent to the browser.
    verifier = issuer.token_calls[0]["data"]["code_verifier"]
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    assert issuer.start_query["code_challenge"] == [challenge]
    assert issuer.start_query["code_challenge_method"] == ["S256"]
    assert issuer.token_calls[0]["auth"] == (CLIENT_ID, "client-secret-value-for-the-tests-only")
    me = browser.get("/api/auth/me").get_json()["user"]
    assert me["username"] == "sam" and me["role"] == "tech"
    rows, _ = audit.read(area="sign-in")
    assert rows[0]["action"] == "Signed in" and rows[0]["target"] == "oidc-idp"


def test_highest_mapped_role_wins(client, app_module, issuer):
    add_provider(client, mapping=[("fb-techs", "tech"), ("fb-leads", "lead")])
    issuer.claims = {"groups": ["fb-techs", "fb-leads"]}
    browser, _ = sign_in(app_module, issuer)
    assert browser.get("/api/auth/me").get_json()["user"]["role"] == "lead"


def test_without_mapping_only_linked_accounts_get_in(client, app_module, issuer):
    add_provider(client)
    _, resp = sign_in(app_module, issuer)
    assert resp.status_code == 403 and b"No account here is linked" in resp.data
    client.post("/api/users", json={"username": "sam1", "password": "sam-password-1", "role": "viewer"})
    link = {"identity": {"provider": "oidc-idp", "subject": "user-123"}}
    assert client.patch("/api/users/sam1", json=link).status_code == 200
    browser, resp = sign_in(app_module, issuer)
    assert resp.status_code == 302
    assert browser.get("/api/auth/me").get_json()["user"]["username"] == "sam1"
    rows, _ = audit.read(area="sign-in")
    assert any(r["action"] == "Sign-in failed" and r["target"] == "oidc-idp" for r in rows)


def test_linking_only_to_known_providers(client):
    client.post("/api/users", json={"username": "sam1", "password": "sam-password-1", "role": "viewer"})
    resp = client.patch("/api/users/sam1", json={"identity": {"provider": "oidc-nope", "subject": "x"}})
    assert resp.status_code == 400


def test_account_stops_working_without_a_mapped_group(client, app_module, issuer):
    add_provider(client, mapping=[("fb-techs", "tech")])
    sign_in(app_module, issuer)
    issuer.claims = {"groups": ["somewhere-else"]}
    _, resp = sign_in(app_module, issuer)
    assert resp.status_code == 403 and b"no longer in a group" in resp.data


def test_groups_from_userinfo_when_the_id_token_has_none(client, app_module, issuer):
    add_provider(client, mapping=[("fb-techs", "tech")])
    issuer.claims = {"groups": None}
    issuer.userinfo = {"sub": "user-123", "groups": ["fb-techs"]}
    _, resp = sign_in(app_module, issuer)
    assert resp.status_code == 302
    issuer.userinfo = {"sub": "someone-else", "groups": ["fb-techs"]}   # about another person: ignored
    issuer.claims = {"groups": None, "sub": "user-456", "preferred_username": "kim"}
    _, resp = sign_in(app_module, issuer)
    assert resp.status_code == 403


@pytest.mark.parametrize("claims", [
    {"iss": "https://evil.example.com"},
    {"aud": "another-client"},
    {"aud": [CLIENT_ID, "another-client"]},                           # several audiences, no azp
    {"exp": int(time.time()) - 3600},
    {"nonce": "replayed"},
    {"sub": None},
])
def test_bad_id_tokens_are_refused(client, app_module, issuer, claims):
    add_provider(client, mapping=[("fb-techs", "tech")])
    issuer.claims = claims
    browser, resp = sign_in(app_module, issuer)
    assert resp.status_code == 403
    assert browser.get("/api/auth/me").get_json()["user"] is None


def test_token_signed_with_another_key_or_hs256_is_refused(client, app_module, issuer):
    add_provider(client, mapping=[("fb-techs", "tech")])
    issuer.alg = "HS256"
    _, resp = sign_in(app_module, issuer)
    assert resp.status_code == 403
    issuer.alg = "RS256"
    real_jwks = issuer.jwks()
    issuer.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)   # signs with a key...
    issuer.jwks = lambda: real_jwks                                                  # ...it doesn't publish
    _, resp = sign_in(app_module, issuer)
    assert resp.status_code == 403


def test_state_must_match(client, app_module, issuer):
    add_provider(client, mapping=[("fb-techs", "tech")])
    _, resp = sign_in(app_module, issuer, state="forged")
    assert resp.status_code == 400


def test_issuer_naming_another_issuer_is_refused(client, app_module, issuer, monkeypatch):
    add_provider(client, mapping=[("fb-techs", "tech")])
    monkeypatch.setattr(issuer, "config", lambda: {**FakeIssuer.config(issuer), "issuer": "https://evil.example.com"})
    browser = app_module.app.test_client()
    resp = browser.get("/auth/oidc-idp/start")
    assert resp.status_code == 502 and b"different issuer" in resp.data


def test_local_sign_in_works_while_the_issuer_is_down(client, app_module, monkeypatch, issuer):
    add_provider(client, mapping=[("fb-techs", "tech")])

    def down(*a, **k):
        raise oidc.requests.ConnectionError("down")
    monkeypatch.setattr(oidc.requests, "get", down)
    resp = app_module.app.test_client().get("/auth/oidc-idp/start")
    assert resp.status_code == 502 and b"could not be reached" in resp.data
    from conftest import TEST_PASSWORD, TEST_USER
    fresh = app_module.app.test_client()
    assert fresh.post("/login", data={"username": TEST_USER, "password": TEST_PASSWORD}).status_code == 302
