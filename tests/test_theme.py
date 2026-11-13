"""Themes: presets, ?theme= per screen, custom colours and the event logo."""
import base64

import pytest

from floorbit import theme

SVG = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><rect width="10" height="10"/></svg>'
SVG_URL = "data:image/svg+xml;base64," + base64.b64encode(SVG).decode()


@pytest.fixture(autouse=True)
def _no_theme_env(monkeypatch):
    for name in ("FLOORBIT_THEME", "FLOORBIT_EVENT_NAME"):
        monkeypatch.delenv(name, raising=False)


def html_tag(resp):
    page = resp.get_data(as_text=True)
    return page[page.index("<html"):page.index(">", page.index("<html")) + 1]


def test_default_theme_and_kiosk_preset(client):
    tag = html_tag(client.get("/"))
    assert 'data-preset="floorbit"' in tag and "data-theme-lock" not in tag
    # The big screen gets the kiosk preset, dark only, unless told otherwise.
    tag = html_tag(client.get("/kiosk"))
    assert 'data-preset="kiosk"' in tag and 'data-theme-lock="dark"' in tag


def test_theme_query_is_remembered_per_browser(client):
    resp = client.get("/?theme=ops")
    assert 'data-preset="ops"' in html_tag(resp)
    assert "floorbit_theme=ops" in resp.headers["Set-Cookie"]
    assert 'data-preset="ops"' in html_tag(client.get("/settings"))   # cookie, no query
    assert 'data-preset="ops"' in html_tag(client.get("/kiosk"))

    resp = client.get("/?theme=default")
    assert 'data-preset="floorbit"' in html_tag(resp)
    assert 'data-preset="floorbit"' in html_tag(client.get("/settings"))
    assert 'data-preset="floorbit"' in html_tag(client.get("/?theme=nonsense"))


def test_custom_theme_derives_missing_colours(client):
    resp = client.put("/api/settings", json={
        "theme.preset": "custom", "theme.accent": "#FF3B6B", "theme.background": "#0a0a12",
        "theme.name": "Example LAN",
    })
    assert resp.status_code == 200, resp.data
    page = client.get("/").get_data(as_text=True)
    tag = html_tag(client.get("/"))
    assert 'data-preset="custom"' in tag and 'data-theme-lock="dark"' in tag
    assert "--theme-accent:#ff3b6b" in tag and "--theme-bg:#0a0a12" in tag
    assert "--theme-surface:#" in tag and "--theme-fg:#f4f4f5" in tag
    assert "--theme-on-accent:#0b0b0f" in tag   # ink reads better than white on this pink
    assert "Example LAN" in page
    # The site preset applies to the kiosk too, so an event can brand the big screen.
    assert 'data-preset="custom"' in html_tag(client.get("/kiosk"))


def test_light_custom_background_locks_light():
    seeds, scheme = theme.custom_seeds({"background": "#fafafa", "accent": "#1d4ed8"})
    assert scheme == "light" and seeds["--theme-fg"] == "#111118"
    assert seeds["--theme-on-accent"] == "#ffffff"


@pytest.mark.parametrize("change", [
    {"theme.preset": "rainbow"},
    {"theme.accent": "red"},
    {"theme.background": "#12345"},
    {"theme.logo": "data:text/html;base64," + base64.b64encode(b"<script>").decode()},
    {"theme.logo": "data:image/png;base64," + base64.b64encode(b"x" * (300 * 1024)).decode()},
])
def test_appearance_settings_are_validated(client, change):
    assert client.put("/api/settings", json=change).status_code == 400


def test_event_logo_is_served_safely(client, anon_client):
    assert anon_client.get("/brand/logo").status_code == 404
    assert client.put("/api/settings", json={"theme.logo": SVG_URL}).status_code == 200

    page = client.get("/").get_data(as_text=True)
    assert 'class="fb-brand-logo" src="/brand/logo?v=' in page
    resp = anon_client.get("/brand/logo")   # public, so the sign-in page and kiosk can show it
    assert resp.status_code == 200 and resp.data == SVG
    assert resp.mimetype == "image/svg+xml"
    assert "sandbox" in resp.headers["Content-Security-Policy"]
    assert resp.headers["X-Content-Type-Options"] == "nosniff"


def test_every_page_loads_the_theme(client, anon_client):
    pages = [(client, p) for p in ("/", "/kiosk", "/settings", "/settings/users")]
    pages.append((anon_client, "/login"))   # check-in is off unless configured
    for c, path in pages:
        resp = c.get(path)
        assert resp.status_code == 200, path
        assert "/static/css/brand/tokens.css" in resp.get_data(as_text=True), path
        assert "data-preset=" in html_tag(resp), path
