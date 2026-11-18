"""Sign-in: who can see and change what, sessions, and the provider hooks for SSO later."""

from urllib.parse import parse_qs, urlsplit

import pytest
from conftest import TEST_PASSWORD, TEST_USER, login_error, login_page, stored

from auth.providers import AuthError, Identity, RedirectProvider


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
    assert login_page(anon_client)["password_login"]


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


@pytest.mark.parametrize("path", ["/api/inventory", "/api/firewalls/seats", "/api/incidents.csv", "/api/report",
                                  "/api/replay/event.json", "/api/past-events", "/api/cables.csv", "/api/dns",
                                  "/api/game-servers", "/api/seats/heatmap", "/api/power", "/api/plan",
                                  "/api/plan/seats/A-1"])
def test_signed_out_reads_are_only_what_the_kiosk_draws(anon_client, kiosk_client, path):
    # Management IPs, the firewall per seat, incidents and reports need an account, even a kiosk one.
    assert anon_client.get(path).status_code == 401
    assert kiosk_client.get(path).status_code != 401


def test_the_kiosk_view_still_loads_signed_out(anon_client):
    for path in ("/api/config", "/api/switches", "/api/seat-blocks", "/api/seats", "/api/halls", "/api/plan-marks",
                 "/api/seats/occupancy", "/api/status/snapshot", "/api/stats/seats"):
        assert anon_client.get(path).status_code == 200, path


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


def test_auth_can_be_switched_off(anon_client, auth, monkeypatch, built):
    monkeypatch.setattr(auth, "enabled", False)
    assert anon_client.get("/plan").status_code == 200
    assert anon_client.post("/api/switches", json={"name": "sw", "x": 1, "y": 1}).status_code == 201


# ── Signing in and out ─────────────────────────────────────────────────────────

def test_sign_in_and_out(anon_client, user, built):
    resp = sign_in(anon_client, next="/settings")
    assert resp.status_code == 302
    assert resp.headers["Location"] == "/settings"

    page = anon_client.get("/plan")
    assert page.status_code == 200
    # The sidebar's account menu: name and "Sign out" (templates/_nav.html).
    assert b'"name": "Test Person"' in page.data and b'"signOut": true' in page.data
    assert anon_client.get("/api/auth/me").get_json()["user"]["username"] == TEST_USER
    assert anon_client.post("/api/switches", json={"name": "sw", "x": 1, "y": 1}).status_code == 201

    assert anon_client.post("/logout").status_code == 302
    assert anon_client.post("/api/switches", json={"name": "sw", "x": 1, "y": 1}).status_code == 401


def test_username_is_not_case_sensitive(anon_client, user):
    assert sign_in(anon_client, username=TEST_USER.upper()).status_code == 302


def test_wrong_password(anon_client, user):
    resp = sign_in(anon_client, password="not-the-password")
    assert resp.status_code == 401
    assert login_error(anon_client) == "Wrong username or password."
    assert sign_in(anon_client, username="nobody").status_code == 401


def test_next_never_leaves_the_site(anon_client, user):
    for target in ("//evil.example.com/", "https://evil.example.com/", "javascript:alert(1)"):
        anon_client.post("/logout")
        resp = sign_in(anon_client, next=target)
        assert resp.headers["Location"] == "/"


def test_a_next_with_a_line_break_goes_home_instead_of_a_500(anon_client, user):
    for target in ("/a\nb", "/a\r\nSet-Cookie: x=1", "/plan\x7f"):
        anon_client.post("/logout")
        assert sign_in(anon_client, next=target).headers["Location"] == "/"
        # Signed in already: /login sends on at once, which raised building the header.
        resp = anon_client.get("/login", query_string={"next": target})
        assert resp.status_code == 302 and resp.headers["Location"] == "/"
    assert anon_client.get("/login", query_string={"next": "/plan?hall=main"}).headers["Location"] == "/plan?hall=main"


def test_repeated_failures_lock_the_username_for_a_while(anon_client, user):
    for _ in range(5):
        assert sign_in(anon_client, password="wrong-password").status_code == 401
    resp = sign_in(anon_client)
    assert resp.status_code == 429
    assert "Too many failed attempts" in login_error(anon_client)


def test_a_guesser_behind_a_trusted_proxy_locks_only_themself(anon_client, app_module, user, monkeypatch):
    monkeypatch.setenv("CHECKIN_TRUST_PROXY", "true")
    guesser = {"environ_overrides": {"HTTP_X_FORWARDED_FOR": "192.0.2.66"}}
    for _ in range(5):
        assert anon_client.post("/login", data={"username": TEST_USER, "password": "wrong-password"},
                                **guesser).status_code == 401
    assert anon_client.post("/login", data={"username": TEST_USER, "password": TEST_PASSWORD},
                            **guesser).status_code == 429
    crew = app_module.app.test_client()
    resp = crew.post("/login", data={"username": TEST_USER, "password": TEST_PASSWORD},
                     environ_overrides={"HTTP_X_FORWARDED_FOR": "192.0.2.7"})
    assert resp.status_code == 302


def test_failed_sign_ins_dont_pile_up_forever(app_module, monkeypatch):
    import auth as auth_pkg
    guard = app_module.app.extensions["auth"]
    monkeypatch.setattr(auth_pkg, "MAX_FAILURE_KEYS", 50)
    with app_module.app.test_request_context("/login", method="POST"):
        for n in range(50):
            guard.record_failure(f"made-up-{n}")
        for key in guard._failures:            # all of them long ago
            guard._failures[key] = [t - auth_pkg.FAILURE_WINDOW for t in guard._failures[key]]
        guard.record_failure("x" * 5000)
        # The new name, plus this address's own count across names (MAX_ADDRESS_FAILURES).
        assert {name for _, name in guard._failures} == {"x" * 200, None}


def test_one_address_trying_many_names_is_slowed_down_too(anon_client, app_module, user, monkeypatch):
    # Each made-up name had its own five tries, so one machine could keep the password hashing busy:
    # 48 threads of it took the crew's pages from 6 ms to 600 ms.
    import auth as auth_pkg
    monkeypatch.setattr(auth_pkg, "MAX_ADDRESS_FAILURES", 8)
    guesser = {"environ_base": {"REMOTE_ADDR": "192.0.2.66"}}
    for n in range(8):
        assert anon_client.post("/login", data={"username": f"made-up-{n}", "password": "x"},
                                **guesser).status_code == 401
    assert anon_client.post("/login", data={"username": "another-one", "password": "x"},
                            **guesser).status_code == 429
    crew = app_module.app.test_client()
    resp = crew.post("/login", data={"username": TEST_USER, "password": TEST_PASSWORD},
                     environ_base={"REMOTE_ADDR": "192.0.2.7"})
    assert resp.status_code == 302


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
    raw = stored(auth.users.path)
    assert TEST_PASSWORD not in raw
    assert "scrypt:" in raw or "pbkdf2:" in raw


# ── Managing accounts ──────────────────────────────────────────────────────────

def test_cli_manages_users(app_module, auth):
    runner = app_module.app.test_cli_runner()
    result = runner.invoke(args=["users", "add", "root", "--password", "long-enough-pw"])
    assert "as admin" in result.output  # the first account
    result = runner.invoke(args=["users", "add", "alice", "--password", "long-enough-pw"])
    assert result.exit_code == 0, result.output
    assert auth.users.verify("alice", "long-enough-pw")["role"] == "lead"  # was "editor" before #41
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
    assert login_page(anon_client)["no_users"]


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
    assert [p["label"] for p in login_page(anon_client)["providers"]] == ["Fake SSO"]


def test_unlinked_outside_login_is_refused(anon_client, fake_sso):
    state = start_sso(anon_client)
    resp = anon_client.get(f"/auth/fake/callback?state={state}&code=42")
    assert resp.status_code == 403
    assert "No account here is linked" in login_error(anon_client)


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


def test_viewer_can_look_but_not_change(signed_in_as, built):
    viewer = signed_in_as("viewer")
    assert viewer.get("/plan").status_code == 200
    resp = viewer.post("/api/switches", json={"name": "sw", "x": 1, "y": 1})
    assert resp.status_code == 403
    assert resp.get_json()["permission_needed"] == "floorplan.edit"


def test_editor_can_change_the_floor_plan_but_not_settings(signed_in_as):
    editor = signed_in_as("editor")
    assert editor.post("/api/switches", json={"name": "sw", "x": 1, "y": 1}).status_code == 201
    assert editor.get("/api/settings").status_code == 403
    assert editor.get("/api/users").status_code == 403
    page = editor.get("/settings")
    assert page.status_code == 403 and b"Not allowed" in page.data


def test_admin_can_do_everything(signed_in_as, tmp_path, monkeypatch):
    from tests.test_spa import _manifest
    _manifest(tmp_path, monkeypatch, {"index.html": {"file": "assets/index.js"}})   # the React pages are built
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
    assert [r["id"] for r in body["roles"]] == ["admin", "lead", "tech", "viewer", "kiosk"]

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


# ── The React sign-in page's API (issue #46) ───────────────────────────────────

def test_json_sign_in_answers_where_to_go(anon_client, user):
    resp = anon_client.post("/api/auth/login", json={"username": TEST_USER, "password": "nope", "next": "/inventory"})
    assert resp.status_code == 401 and resp.get_json()["error"] == "Wrong username or password."
    for target, expected in (("/inventory", "/inventory"), ("//evil.example", "/"), ("/\\evil.example", "/"),
                             ("https://evil.example/", "/")):
        resp = anon_client.post("/api/auth/login", json={"username": TEST_USER, "password": TEST_PASSWORD,
                                                         "next": target})
        assert resp.status_code == 200 and resp.get_json()["next"] == expected
        anon_client.post("/logout")
    assert anon_client.get("/api/auth/login-options?next=/\\evil.example").get_json()["next"] == "/"


def test_the_last_error_is_shown_once_and_in_german(anon_client, user):
    sign_in(anon_client, password="not-the-password")
    page = anon_client.get("/api/auth/login-options", headers={"Accept-Language": "de-CH"}).get_json()
    assert page["error"] == "Falscher Benutzername oder falsches Passwort." and page["username"] == TEST_USER
    assert login_error(anon_client) == ""


def test_the_check_in_page_and_the_landing_link_follow_check_in(anon_client, monkeypatch, tmp_path):
    from tests.test_spa import _manifest
    _manifest(tmp_path, monkeypatch, {"index.html": {"file": "assets/index.js"}})
    assert anon_client.get("/checkin").status_code == 404
    assert login_page(anon_client)["checkin_url"] is None
    monkeypatch.setenv("CHECKIN_ENABLED", "1")
    page = anon_client.get("/checkin")
    assert page.status_code == 200 and b"Seat check-in" in page.data
    assert login_page(anon_client)["checkin_url"] == "/checkin"


def test_a_huge_body_without_signing_in_is_refused_before_it_is_parsed(anon_client, client):
    # A 30 MB JSON array took a worker from 90 to 600 MB with four requests at once.
    big = {"username": "pixel", "seat": "A-1", "pad": [0] * 600_000}      # about 1.8 MB
    r = anon_client.post("/api/checkin", json=big, headers={"Origin": "http://localhost"})
    assert r.status_code == 413 and r.get_json()["code"] == "too_large"
    r = anon_client.post("/api/checkin", json=big, headers={"Origin": "http://localhost", "Accept-Language": "de"})
    assert r.get_json()["error"] == "Das sind zu viele Daten für eine Anfrage."
    small = anon_client.post("/api/checkin", json={"username": "pixel", "seat": "A-1"},
                             headers={"Origin": "http://localhost"})
    assert small.status_code != 413
    # The crew, signed in, and the agents (their key is checked first) keep the usual limit.
    assert client.post("/api/checkin", json=big).status_code != 413
    assert anon_client.post("/api/agent/v1/syslog", json=big).status_code == 401
