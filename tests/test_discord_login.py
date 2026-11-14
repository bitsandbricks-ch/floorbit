"""Sign in with Discord, against a fake Discord API (no calls to discord.com)."""
from urllib.parse import parse_qs, urlsplit

import pytest
from conftest import TEST_PASSWORD, TEST_USER

from auth.providers import discord as discord_provider
from floorbit import audit

SERVER = "111111111111111111"
ORGA_ROLE = "222222222222222222"
TECH_ROLE = "333333333333333333"
PLAYER_ID = "444444444444444444"


class FakeResponse:
    def __init__(self, status, body=None):
        self.status_code = status
        self._body = body or {}

    def json(self):
        return self._body


class FakeDiscord:
    """Answers the three calls the provider makes: token, /users/@me and the server member."""

    def __init__(self):
        self.member = {"roles": [], "nick": None}   # None: not on the server
        self.token_status = 200
        self.calls = []

    def __call__(self, method, url, **kwargs):
        path = url.removeprefix(discord_provider.API)
        self.calls.append((method, path, kwargs))
        if path == "/oauth2/token":
            if self.token_status != 200:
                return FakeResponse(self.token_status, {"error": "invalid_grant"})
            assert kwargs["data"]["code"] == "good-code"
            return FakeResponse(200, {"access_token": "fake-access-token", "token_type": "Bearer"})
        assert kwargs["headers"]["Authorization"] == "Bearer fake-access-token"
        if path == "/users/@me":
            return FakeResponse(200, {"id": PLAYER_ID, "username": "some.player", "global_name": "Some Player"})
        if path == f"/users/@me/guilds/{SERVER}/member":
            return FakeResponse(404) if self.member is None else FakeResponse(200, self.member)
        raise AssertionError(f"unexpected call {method} {path}")


@pytest.fixture
def auth(app_module):
    return app_module.app.extensions["auth"]


@pytest.fixture
def settings(app_module):
    return app_module.app.extensions["floorbit_settings"]


@pytest.fixture
def fake_discord(monkeypatch, settings):
    fake = FakeDiscord()
    monkeypatch.setattr(discord_provider.requests, "request", fake)
    settings.update({"signin.discord_client_id": "555555555555555555",
                     "signin.discord_client_secret": "example-client-secret"})
    return fake


def discord_sign_in(client, code="good-code", next_path="/"):
    resp = client.get(f"/auth/discord/start?next={next_path}")
    assert resp.status_code == 302
    query = parse_qs(urlsplit(resp.headers["Location"]).query)
    return client.get(f"/auth/discord/callback?state={query['state'][0]}&code={code}"), query


def whoami(client):
    return client.get("/api/auth/me").get_json()["user"]


def test_button_only_shows_when_set_up(anon_client, settings):
    assert b"Sign in with Discord" not in anon_client.get("/login").data
    assert anon_client.get("/auth/discord/start").status_code == 404
    settings.update({"signin.discord_client_id": "555555555555555555",
                     "signin.discord_client_secret": "example-client-secret"})
    assert b"Sign in with Discord" in anon_client.get("/login").data


def test_start_asks_discord_for_the_right_things(anon_client, fake_discord, settings):
    resp = anon_client.get("/auth/discord/start")
    url = urlsplit(resp.headers["Location"])
    query = parse_qs(url.query)
    assert url.netloc == "discord.com" and query["client_id"] == ["555555555555555555"]
    assert query["scope"] == ["identify"]
    assert query["redirect_uri"] == ["http://localhost/auth/discord/callback"]
    assert "example-client-secret" not in resp.headers["Location"]

    settings.update({"signin.discord_guild_id": SERVER})
    query = parse_qs(urlsplit(anon_client.get("/auth/discord/start").headers["Location"]).query)
    assert query["scope"] == ["identify guilds.members.read"]


def test_public_url_sets_the_redirect(anon_client, fake_discord, settings):
    settings.update({"integrations.public_url": "https://floor.example.com/"})
    query = parse_qs(urlsplit(anon_client.get("/auth/discord/start").headers["Location"]).query)
    assert query["redirect_uri"] == ["https://floor.example.com/auth/discord/callback"]


def test_without_a_server_only_linked_accounts_get_in(anon_client, auth, fake_discord):
    resp, _ = discord_sign_in(anon_client)
    assert resp.status_code == 403 and b"No account here is linked" in resp.data

    auth.users.add(TEST_USER, TEST_PASSWORD, role="editor")
    auth.users.link_identity(TEST_USER, "discord", PLAYER_ID)
    resp, _ = discord_sign_in(anon_client, next_path="/settings")
    assert resp.status_code == 302 and resp.headers["Location"] == "/settings"
    assert whoami(anon_client)["username"] == TEST_USER
    token_call = fake_discord.calls[-2]
    assert token_call[2]["auth"] == ("555555555555555555", "example-client-secret")


def test_server_members_get_an_account_with_their_role(anon_client, auth, fake_discord, settings):
    settings.update({"signin.discord_guild_id": SERVER, "signin.discord_admin_roles": [ORGA_ROLE],
                     "signin.discord_editor_roles": [TECH_ROLE]})
    fake_discord.member = {"roles": [TECH_ROLE], "nick": "Tech Lead"}
    resp, _ = discord_sign_in(anon_client)
    assert resp.status_code == 302
    me = whoami(anon_client)
    assert (me["username"], me["display_name"], me["role"]) == ("some.player", "Tech Lead", "editor")
    created = auth.users.get("some.player")
    assert created["created_by"] == "discord" and created["password_hash"] is None


def test_members_without_a_listed_role_are_refused(anon_client, auth, fake_discord, settings):
    settings.update({"signin.discord_guild_id": SERVER, "signin.discord_admin_roles": [ORGA_ROLE]})
    fake_discord.member = {"roles": [TECH_ROLE]}
    resp, _ = discord_sign_in(anon_client)
    assert resp.status_code == 403 and b"not in a server role" in resp.data
    assert auth.users.count() == 0


def test_no_role_lists_lets_every_member_look(anon_client, fake_discord, settings):
    settings.update({"signin.discord_guild_id": SERVER})
    resp, _ = discord_sign_in(anon_client)
    assert resp.status_code == 302 and whoami(anon_client)["role"] == "viewer"


def test_strangers_are_refused(anon_client, auth, fake_discord, settings):
    settings.update({"signin.discord_guild_id": SERVER})
    fake_discord.member = None
    resp, _ = discord_sign_in(anon_client)
    assert resp.status_code == 403 and auth.users.count() == 0


def test_leaving_the_server_ends_discord_made_accounts(anon_client, auth, fake_discord, settings):
    settings.update({"signin.discord_guild_id": SERVER})
    assert discord_sign_in(anon_client)[0].status_code == 302
    anon_client.post("/logout")
    fake_discord.member = None
    resp, _ = discord_sign_in(anon_client)
    assert resp.status_code == 403 and b"no longer" in resp.data


def test_hand_linked_accounts_do_not_need_the_server(anon_client, auth, fake_discord, settings):
    settings.update({"signin.discord_guild_id": SERVER, "signin.discord_admin_roles": [ORGA_ROLE]})
    fake_discord.member = None
    auth.users.add(TEST_USER, TEST_PASSWORD, role="admin")
    auth.users.link_identity(TEST_USER, "discord", PLAYER_ID)
    assert discord_sign_in(anon_client)[0].status_code == 302


def test_discord_errors_are_shown_not_raised(anon_client, fake_discord):
    fake_discord.token_status = 401
    resp, _ = discord_sign_in(anon_client)
    assert resp.status_code == 403 and b"Discord sign-in failed" in resp.data
    resp = anon_client.get("/auth/discord/start")
    state = parse_qs(urlsplit(resp.headers["Location"]).query)["state"][0]
    resp = anon_client.get(f"/auth/discord/callback?state={state}&error=access_denied")
    assert resp.status_code == 403 and b"cancelled" in resp.data


def test_sign_ins_are_audited(anon_client, client, auth, fake_discord, settings):
    settings.update({"signin.discord_guild_id": SERVER})
    discord_sign_in(anon_client)
    rows = audit.read(area="sign-in")[0]
    assert (rows[0]["action"], rows[0]["user"], rows[0]["target"]) == ("Signed in", "some.player", "discord")
    other = client.application.test_client()
    fake_discord.member = None
    discord_sign_in(other)
    assert audit.read(area="sign-in")[0][0]["action"] == "Sign-in failed"


def test_admin_links_and_unlinks_a_discord_id(client, auth, fake_discord):
    auth.users.add("helper1", "helper-password-1", role="editor")
    resp = client.patch("/api/users/helper1", json={"discord_id": PLAYER_ID})
    assert resp.status_code == 200 and resp.get_json()["discord"] is True
    assert auth.users.find_by_identity("discord", PLAYER_ID)["username"] == "helper1"
    assert client.patch("/api/users/helper1", json={"discord_id": "not-an-id"}).status_code == 400
    assert client.patch(f"/api/users/{TEST_USER}", json={"discord_id": PLAYER_ID}).status_code == 400   # taken
    assert client.patch("/api/users/helper1", json={"discord_id": ""}).status_code == 200
    assert auth.users.find_by_identity("discord", PLAYER_ID) is None


def test_client_secret_is_never_shown(client, fake_discord):
    values = client.get("/api/settings").get_json()["values"]
    assert values["signin.discord_client_secret"]["is_set"]
    assert "example-client-secret" not in client.get("/api/settings").get_data(as_text=True)
    assert "example-client-secret" not in client.get("/api/settings/backup").get_data(as_text=True)
