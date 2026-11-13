"""Sign-in: who can see and change what, sessions, and the provider hooks for SSO later."""

from urllib.parse import parse_qs, urlsplit

import pytest

from auth.providers import AuthError, Identity, RedirectProvider
from conftest import TEST_PASSWORD, TEST_USER


@pytest.fixture
def auth(app_module):
    return app_module.app.extensions["auth"]


@pytest.fixture
def user(auth):
    return auth.users.add(TEST_USER, TEST_PASSWORD, display_name="Test Person")


def sign_in(client, username=TEST_USER, password=TEST_PASSWORD, **extra):
    return client.post("/login", data={"username": username, "password": password, **extra})


# ── What is open and what is not ───────────────────────────────────────────────

def test_editor_and_settings_pages_redirect_to_login(anon_client):
    for path in ("/", "/settings"):
        resp = anon_client.get(path)
        assert resp.status_code == 302
        assert resp.headers["Location"].startswith("/login?next=")


def test_login_page_is_open(anon_client):
    resp = anon_client.get("/login")
    assert resp.status_code == 200
    assert b"Sign in" in resp.data


def test_reads_stay_open_for_kiosk_screens(anon_client):
    assert anon_client.get("/api/config").status_code == 200
    assert anon_client.get("/api/switches").status_code == 200


def test_changes_need_a_signed_in_user(anon_client):
    resp = anon_client.post("/api/switches", json={"name": "sw-x", "x": 1, "y": 1})
    assert resp.status_code == 401
    assert resp.get_json()["login_url"] == "/login"


def test_settings_api_is_never_open(anon_client):
    assert anon_client.get("/api/settings").status_code == 401
    assert anon_client.put("/api/settings", json={}).status_code == 401


def test_public_read_can_be_turned_off(anon_client, auth, monkeypatch):
    monkeypatch.setattr(auth, "public_read", False)
    assert anon_client.get("/api/switches").status_code == 401


def test_check_in_and_kiosk_paths_are_open(app_module, auth):
    def public(path, method="GET"):
        with app_module.app.test_request_context(path, method=method):
            return auth.is_public()

    assert public("/checkin")
    assert public("/api/checkin", "POST")
    assert public("/kiosk")
    assert public("/kiosk/hall-a")
    # A path that only starts with the same letters is not covered.
    assert not public("/api/checkins/A1", "DELETE")
    assert not public("/kioskadmin")


def test_auth_can_be_switched_off(anon_client, auth, monkeypatch):
    monkeypatch.setattr(auth, "enabled", False)
    assert anon_client.get("/").status_code == 200
    assert anon_client.post("/api/switches", json={"name": "sw", "x": 1, "y": 1}).status_code == 201


# ── Signing in and out ─────────────────────────────────────────────────────────

def test_sign_in_and_out(anon_client, user):
    resp = sign_in(anon_client, next="/settings")
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/settings"

    page = anon_client.get("/")
    assert page.status_code == 200
    assert b"Test Person" in page.data and b"Sign out" in page.data
    assert anon_client.get("/api/auth/me").get_json()["user"]["username"] == TEST_USER
    assert anon_client.post("/api/switches", json={"name": "sw", "x": 1, "y": 1}).status_code == 201

    assert anon_client.post("/logout").status_code == 302
    assert anon_client.post("/api/switches", json={"name": "sw", "x": 1, "y": 1}).status_code == 401


def test_username_is_not_case_sensitive(anon_client, user):
    assert sign_in(anon_client, username=TEST_USER.upper()).status_code == 302


def test_wrong_password(anon_client, user):
    resp = sign_in(anon_client, password="not-the-password")
    assert resp.status_code == 401
    assert b"Wrong username or password" in resp.data
    assert sign_in(anon_client, username="nobody").status_code == 401


def test_next_never_leaves_the_site(anon_client, user):
    for target in ("//evil.example.com/", "https://evil.example.com/", "javascript:alert(1)"):
        anon_client.post("/logout")
        resp = sign_in(anon_client, next=target)
        assert resp.headers["Location"] == "/"


def test_repeated_failures_lock_the_username_for_a_while(anon_client, user):
    for _ in range(5):
        assert sign_in(anon_client, password="wrong-password").status_code == 401
    resp = sign_in(anon_client)
    assert resp.status_code == 429
    assert b"Too many failed attempts" in resp.data


def test_password_change_signs_out_existing_sessions(client, auth):
    assert client.post("/api/switches", json={"name": "sw", "x": 1, "y": 1}).status_code == 201
    auth.users.set_password(TEST_USER, "a-brand-new-password")
    assert client.post("/api/switches", json={"name": "sw", "x": 1, "y": 1}).status_code == 401


def test_cross_site_posts_are_refused(client):
    resp = client.post("/api/switches", json={"name": "sw", "x": 1, "y": 1},
                       headers={"Origin": "https://evil.example.com"})
    assert resp.status_code == 403
    resp = client.post("/api/switches", json={"name": "sw", "x": 1, "y": 1},
                       headers={"Origin": "http://localhost"})
    assert resp.status_code == 201


def test_accounts_survive_floor_plan_saves(client, auth):
    # The floor plan and the accounts share data.json; saving one must keep the other.
    client.post("/api/switches", json={"name": "sw", "x": 1, "y": 1})
    client.post("/api/seat-blocks", json={"name": "A", "x": 5, "y": 5})
    assert auth.users.verify(TEST_USER, TEST_PASSWORD)


def test_passwords_are_hashed(auth, user):
    with open(auth.users.path) as f:
        raw = f.read()
    assert TEST_PASSWORD not in raw
    assert "scrypt:" in raw or "pbkdf2:" in raw


# ── Managing accounts ──────────────────────────────────────────────────────────

def test_cli_manages_users(app_module, auth):
    runner = app_module.app.test_cli_runner()
    result = runner.invoke(args=["users", "add", "alice", "--password", "long-enough-pw"])
    assert result.exit_code == 0, result.output
    assert auth.users.verify("alice", "long-enough-pw")

    assert "alice" in runner.invoke(args=["users", "list"]).output
    assert runner.invoke(args=["users", "add", "alice", "--password", "long-enough-pw"]).exit_code != 0
    assert runner.invoke(args=["users", "add", "bob", "--password", "short"]).exit_code != 0

    assert runner.invoke(args=["users", "passwd", "alice", "--password", "another-long-pw"]).exit_code == 0
    assert auth.users.verify("alice", "another-long-pw")
    assert runner.invoke(args=["users", "remove", "alice"]).exit_code == 0
    assert auth.users.get("alice") is None


def test_login_page_explains_how_to_create_the_first_account(anon_client):
    assert b"No accounts exist yet" in anon_client.get("/login").data


# ── Outside logins (SSO / Discord later) ───────────────────────────────────────

class FakeOAuth(RedirectProvider):
    """Stands in for an OIDC or Discord provider."""
    id = "fake"
    label = "Fake SSO"

    def start(self, callback_url, state):
        return f"https://sso.example.com/authorize?state={state}&redirect_uri={callback_url}"

    def finish(self, request, callback_url):
        if request.args.get("error"):
            raise AuthError("The provider said no.")
        return Identity(provider=self.id, subject=request.args["code"], username="Some.Player",
                        display_name="Some Player")


@pytest.fixture
def fake_sso(auth):
    provider = FakeOAuth()
    auth.providers.register(provider)
    yield provider
    auth.providers._providers.pop(provider.id, None)


def start_sso(client, next_path="/"):
    resp = client.get(f"/auth/fake/start?next={next_path}")
    assert resp.status_code == 302
    return parse_qs(urlsplit(resp.headers["Location"]).query)["state"][0]


def test_redirect_provider_shows_on_login_page(anon_client, fake_sso):
    assert b"Sign in with Fake SSO" in anon_client.get("/login").data


def test_unlinked_outside_login_is_refused(anon_client, fake_sso):
    state = start_sso(anon_client)
    resp = anon_client.get(f"/auth/fake/callback?state={state}&code=42")
    assert resp.status_code == 403
    assert b"No account here is linked" in resp.data


def test_linked_outside_login_signs_in(anon_client, auth, user, fake_sso):
    auth.users.link_identity(TEST_USER, "fake", "42")
    state = start_sso(anon_client, "/settings")
    resp = anon_client.get(f"/auth/fake/callback?state={state}&code=42")
    assert resp.status_code == 302 and resp.headers["Location"] == "/settings"
    assert anon_client.get("/api/auth/me").get_json()["user"]["username"] == TEST_USER


def test_outside_login_can_create_accounts_when_allowed(anon_client, auth, fake_sso, monkeypatch):
    monkeypatch.setattr(fake_sso, "auto_create_users", True)
    state = start_sso(anon_client)
    assert anon_client.get(f"/auth/fake/callback?state={state}&code=7").status_code == 302
    created = auth.users.find_by_identity("fake", "7")
    assert created["username"] == "Some.Player"
    assert created["password_hash"] is None


def test_callback_needs_the_matching_state(anon_client, auth, user, fake_sso):
    auth.users.link_identity(TEST_USER, "fake", "42")
    start_sso(anon_client)
    assert anon_client.get("/auth/fake/callback?state=forged&code=42").status_code == 400
