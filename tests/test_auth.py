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
    return auth.users.add(TEST_USER, TEST_PASSWORD, display_name="Test Person", role="admin")


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
    assert anon_client.get("/api/users").status_code == 401


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
    result = runner.invoke(args=["users", "add", "root", "--password", "long-enough-pw"])
    assert "as admin" in result.output  # the first account
    result = runner.invoke(args=["users", "add", "alice", "--password", "long-enough-pw"])
    assert result.exit_code == 0, result.output
    assert auth.users.verify("alice", "long-enough-pw")["role"] == "editor"
    assert runner.invoke(args=["users", "role", "alice", "viewer"]).exit_code == 0
    assert auth.users.get("alice")["role"] == "viewer"
    assert runner.invoke(args=["users", "remove", "root"]).exit_code != 0  # the last admin

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


# ── Roles ──────────────────────────────────────────────────────────────────────

@pytest.fixture
def signed_in_as(app_module, auth):
    """A client signed in as a fresh account with the given role."""
    def make(role):
        auth.users.add(f"{role}-user", TEST_PASSWORD, role=role)
        test_client = app_module.app.test_client()
        assert sign_in(test_client, username=f"{role}-user").status_code == 302
        return test_client
    return make


def test_viewer_can_look_but_not_change(signed_in_as):
    viewer = signed_in_as("viewer")
    assert viewer.get("/").status_code == 200
    resp = viewer.post("/api/switches", json={"name": "sw", "x": 1, "y": 1})
    assert resp.status_code == 403
    assert resp.get_json()["role_needed"] == "editor"


def test_editor_can_change_the_floor_plan_but_not_settings(signed_in_as):
    editor = signed_in_as("editor")
    assert editor.post("/api/switches", json={"name": "sw", "x": 1, "y": 1}).status_code == 201
    assert editor.get("/api/settings").status_code == 403
    assert editor.get("/api/users").status_code == 403
    page = editor.get("/settings")
    assert page.status_code == 403 and b"Not allowed" in page.data


def test_admin_can_do_everything(signed_in_as):
    admin = signed_in_as("admin")
    assert admin.get("/api/settings").status_code == 200
    assert admin.get("/settings/users").status_code == 200
    assert admin.get("/api/users").status_code == 200


def test_accounts_from_before_roles_count_as_admin(auth, anon_client):
    auth.users.add("old-account", TEST_PASSWORD)
    users = auth.users._users()
    del users["old-account"]["role"]
    auth.users._write_users(users)
    assert auth.users.get("old-account") and auth.users.list()[0]["role"] == "admin"


def test_role_change_applies_to_open_sessions(signed_in_as, auth):
    editor = signed_in_as("editor")
    assert editor.post("/api/switches", json={"name": "sw", "x": 1, "y": 1}).status_code == 201
    auth.users.update("editor-user", role="viewer")
    assert editor.post("/api/switches", json={"name": "sw", "x": 1, "y": 1}).status_code == 403


# ── Users page API ─────────────────────────────────────────────────────────────

def test_admin_manages_accounts(client, auth):
    body = client.get("/api/users").get_json()
    assert body["me"] == TEST_USER
    assert [r["id"] for r in body["roles"]] == ["viewer", "editor", "admin"]

    resp = client.post("/api/users", json={"username": "helper1", "password": "long-enough-pw", "role": "viewer"})
    assert resp.status_code == 201
    assert auth.users.get("helper1")["role"] == "viewer"
    assert "password_hash" not in str(resp.get_json())

    assert client.post("/api/users", json={"username": "helper1", "password": "long-enough-pw"}).status_code == 400
    assert client.post("/api/users", json={"username": "x y", "password": "long-enough-pw"}).status_code == 400
    assert client.post("/api/users", json={"username": "ok", "password": "short"}).status_code == 400
    assert client.post("/api/users", json={"username": "ok", "password": "long-enough-pw",
                                           "role": "superuser"}).status_code == 400

    assert client.patch("/api/users/helper1", json={"role": "editor", "display_name": "Helper One"}).status_code == 200
    assert auth.users.get("helper1")["display_name"] == "Helper One"
    assert client.patch("/api/users/helper1", json={"password": "new-long-password"}).status_code == 200
    assert auth.users.verify("helper1", "new-long-password")

    assert client.delete("/api/users/helper1").status_code == 200
    assert auth.users.get("helper1") is None
    assert client.delete("/api/users/nobody").status_code == 400


def test_admin_cannot_lock_themselves_out(client):
    assert client.patch(f"/api/users/{TEST_USER}", json={"role": "viewer"}).status_code == 400
    assert client.delete(f"/api/users/{TEST_USER}").status_code == 400


def test_last_admin_stays_admin(auth):
    auth.users.add("only-admin", TEST_PASSWORD, role="admin")
    with pytest.raises(Exception, match="last admin"):
        auth.users.update("only-admin", role="editor")
    with pytest.raises(Exception, match="last admin"):
        auth.users.remove("only-admin")


def test_first_account_from_env_is_admin(auth, monkeypatch):
    monkeypatch.setenv("AUTH_ADMIN_USER", "boss")
    monkeypatch.setenv("AUTH_ADMIN_PASSWORD", TEST_PASSWORD)
    auth._bootstrap_admin()
    assert auth.users.get("boss")["role"] == "admin"


# ── Routes from the integrations, check-in history and kiosk ──────────────────

def test_check_in_records_need_an_editor(anon_client, signed_in_as):
    # User, IP and MAC per seat: personal data, so never public, not even as a read.
    viewer = signed_in_as("viewer")
    for path in ("/api/checkins", "/api/checkins/history", "/api/checkins/history.csv", "/checkins/history"):
        assert anon_client.get(path).status_code in (302, 401), path
        assert viewer.get(path).status_code == 403, path
    editor = signed_in_as("editor")
    assert editor.get("/api/checkins/history").status_code not in (401, 403)


def test_integration_controls_need_an_admin(anon_client, signed_in_as):
    assert anon_client.get("/api/integrations").status_code == 401
    assert signed_in_as("editor").post("/api/integrations/monitor/poll").status_code == 403
    assert signed_in_as("admin").get("/api/integrations").status_code not in (401, 403)


def test_kiosk_and_live_updates_stay_open(app_module, auth):
    for path in ("/kiosk", "/api/events", "/api/status/snapshot", "/api/checkin/me"):
        with app_module.app.test_request_context(path):
            assert auth.is_public(), path
