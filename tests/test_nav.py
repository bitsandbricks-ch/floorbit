"""The sidebar on every crew page (floorbit/nav.py, templates/_nav.html)."""
import json
import re

import pytest

from tests.test_rbac import sign_in_as

SERVER_PAGES = ("/", "/settings", "/settings/users", "/settings/audit")


def boot(html):
    raw = re.search(r'<script id="fb-nav-data" type="application/json">(.*?)</script>', html, re.S).group(1)
    return json.loads(raw)


def test_the_server_pages_carry_the_sidebar(client):
    for path in SERVER_PAGES:
        html = client.get(path).get_data(as_text=True)
        assert 'id="fb-nav"' in html and 'class="fb-has-nav' in html, path
        assert boot(html)["pages"] == client.get("/api/pages").get_json()["pages"], path


def test_the_sidebar_lists_what_this_role_may_open(app_module):
    # Same list as "Go to", so the sidebar never offers a page the server refuses or misses one.
    for who, role in (("ad1", "admin"), ("vi1", "viewer"), ("te1", "tech")):
        crew = sign_in_as(app_module, who, role)
        data = boot(crew.get("/").get_data(as_text=True))
        assert data["pages"] == crew.get("/api/pages").get_json()["pages"], role
        assert data["user"]["username"] == who and data["signOut"] is True
    viewer = boot(sign_in_as(app_module, "vi2", "viewer").get("/").get_data(as_text=True))
    assert "/settings" not in {p["href"] for p in viewer["pages"]}


def test_every_page_has_its_own_name(client):
    # Issue #240: /plan and /seat-mapping were both "Seats", also for screen readers.
    pages = boot(client.get("/").get_data(as_text=True))["pages"]
    labels = [p["label"] for p in pages]
    assert "Seat mapping" in labels and len(labels) == len(set(labels))


def test_the_floor_plan_top_bar_keeps_only_its_own_tools(client):
    # The page links used to crowd the top bar (issue #238); now they are all in the sidebar.
    page = client.get("/").get_data(as_text=True)
    top = page[page.index('<header class="topbar">'):page.index('</header>', page.index('<header class="topbar">'))]
    assert 'id="hall-select"' in top and 'id="btn-refresh-all"' in top
    assert 'href="/problems"' not in top and 'action="/logout"' not in top and 'href="/settings"' not in top


@pytest.mark.parametrize("built", [True, False])
def test_the_sidebar_loads_the_build_or_falls_back_to_links(client, monkeypatch, built):
    from floorbit import spa
    fake = {"js": ["/static/app/assets/nav.js"], "css": ["/static/app/assets/nav.css"]}
    monkeypatch.setattr(spa, "assets", lambda entry=spa.ENTRY: fake if built else None)
    html = client.get("/settings").get_data(as_text=True)
    assert ('/static/app/assets/nav.js' in html) is built
    # Without a frontend build every page is still a plain link away.
    assert ('class="fb-nav-fallback"' in html) is not built
    if not built:
        assert 'href="/problems"' in html


def test_the_folded_sidebar_keeps_its_width_from_the_cookie(client):
    assert 'data-state="full"' in client.get("/").get_data(as_text=True)
    client.set_cookie("floorbit_nav", "rail")
    assert 'id="fb-nav" class="fb-nav-slot" data-state="rail"' in client.get("/").get_data(as_text=True)


def test_react_pages_get_the_sidebar_data(client, monkeypatch):
    from floorbit import spa
    monkeypatch.setattr(spa, "assets", lambda entry=spa.ENTRY: {"js": ["/static/app/x.js"], "css": []})
    html = client.get("/problems").get_data(as_text=True)
    assert boot(html)["pages"] and 'class="fb-has-nav"' in html
    # The React app draws the sidebar itself: no second one from the server.
    assert 'id="fb-nav"' not in html
