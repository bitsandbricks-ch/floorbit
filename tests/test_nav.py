"""The sidebar on every crew page (floorbit/nav.py, templates/_nav.html)."""
import json
import re

from tests.test_rbac import sign_in_as

SERVER_PAGES = ("/plan", "/problems")   # the React app, served through templates/spa.html


def boot(html):
    raw = re.search(r'<script id="fb-nav-data" type="application/json">(.*?)</script>', html, re.S).group(1)
    return json.loads(raw)


def test_the_server_pages_carry_the_sidebar(client):
    for path in SERVER_PAGES:
        html = client.get(path).get_data(as_text=True)
        assert 'class="fb-has-nav' in html, path
        assert boot(html)["pages"] == client.get("/api/pages").get_json()["pages"], path


def test_the_sidebar_lists_what_this_role_may_open(app_module):
    # Same list as "Go to", so the sidebar never offers a page the server refuses or misses one.
    for who, role in (("ad1", "admin"), ("vi1", "viewer"), ("te1", "tech")):
        crew = sign_in_as(app_module, who, role)
        data = boot(crew.get("/plan").get_data(as_text=True))
        assert data["pages"] == crew.get("/api/pages").get_json()["pages"], role
        assert data["user"]["username"] == who and data["signOut"] is True
    viewer = boot(sign_in_as(app_module, "vi2", "viewer").get("/plan").get_data(as_text=True))
    assert "/settings" not in {p["href"] for p in viewer["pages"]}


def test_every_page_has_its_own_name(client):
    # Issue #240: /plan and /seat-mapping were both "Seats", also for screen readers.
    pages = boot(client.get("/plan").get_data(as_text=True))["pages"]
    labels = [p["label"] for p in pages]
    assert "Seat mapping" in labels and len(labels) == len(set(labels))


def test_react_pages_get_the_sidebar_data(client, monkeypatch):
    from floorbit import spa
    monkeypatch.setattr(spa, "assets", lambda entry=spa.ENTRY: {"js": ["/static/app/x.js"], "css": []})
    html = client.get("/problems").get_data(as_text=True)
    assert boot(html)["pages"] and 'class="fb-has-nav"' in html
    # The React app draws the sidebar itself: no second one from the server.
    assert 'id="fb-nav"' not in html


def test_favourites_and_folding_are_kept_with_the_account(app_module):
    crew = sign_in_as(app_module, "fav1", "tech")
    assert crew.get("/api/auth/me/nav").get_json() == {"favourites": [], "accordion": True}
    saved = crew.put("/api/auth/me/nav", json={"favourites": ["problems", "problems", "../x", 7, "settings"],
                                               "accordion": False, "colour": "red"})
    assert saved.get_json() == {"favourites": ["problems", "settings"], "accordion": False}
    assert boot(crew.get("/plan").get_data(as_text=True))["prefs"] == {"favourites": ["problems", "settings"],
                                                                     "accordion": False}
    other = sign_in_as(app_module, "fav2", "viewer")
    assert other.get("/api/auth/me/nav").get_json()["favourites"] == []


def test_dashboards_can_be_pinned_to_the_sidebar(app_module):
    crew = sign_in_as(app_module, "pin1", "tech")
    saved = crew.put("/api/auth/me/nav", json={"favourites": ["dashboard:hall-b", "dashboard:../x", "dashboard:"]})
    assert saved.get_json()["favourites"] == ["dashboard:hall-b"]


def test_the_overview_and_dashboards_open_inside_the_app(client):
    assert {"href": "/overview", "id": "overview", "label": "Overview"} in client.get("/api/pages").get_json()["pages"]
    for path in ("/overview", "/dashboards/view/overview"):
        res = client.get(path)
        assert res.status_code in (200, 503) and 'class="fb-has-nav"' in res.get_data(as_text=True), path


def test_only_a_signed_in_account_keeps_sidebar_settings(anon_client):
    assert anon_client.get("/api/auth/me/nav").status_code == 400
    assert anon_client.put("/api/auth/me/nav", json={"favourites": ["problems"]}).status_code == 401


SHELL = {
    "pinned": ["floorPlan"], "tabs": ["floorPlan"], "sections": [],
    "icons": {"page": {"*": "<svg></svg>"}, "tab": {"*": "<svg></svg>"}, "section": {}, "search": "<svg></svg>",
              "chevron": "<svg></svg>", "collapse": "<svg></svg>", "expand": "<svg></svg>", "menu": "<svg></svg>",
              "dots": "<svg></svg>"},
    "texts": {"en": {"nav": {"label": "Main", "home": "Floor plan", "goTo": "Go to…", "account": "Account",
                             "collapse": "Collapse", "expand": "Expand", "menu": "Menu", "quick": "Main pages",
                             "sections": {"more": "More"}},
                     "pages": {}, "signedInAs": "Signed in as {{username}}"}},
}


def test_the_first_paint_has_the_admins_own_sections(app_module, monkeypatch):
    import copy

    from floorbit import nav
    shell = copy.deepcopy(SHELL)
    monkeypatch.setattr(nav, "_shell", lambda: shell)
    custom = [{"id": "hall", "name": "<i>Hall</i>", "icon": "star", "links": [
        {"kind": "url", "href": "/stats", "label": "Stats", "external": False},
        {"kind": "url", "href": "https://example.com", "label": "Out", "external": True}]}]
    boot = {"pages": [{"href": "/plan", "id": "floorPlan", "label": "Floor plan"}], "custom": custom}
    with app_module.app.test_request_context("/stats"):
        # A build from before these sections has no icons for them: they wait for the script.
        assert "Hall" not in str(nav.markup(boot))
        shell["icons"]["custom"] = {"star": "<svg class=star></svg>", "folder": "<svg></svg>"}
        shell["icons"]["link"] = {"dashboard": "<svg></svg>", "url": "<svg></svg>", "external": "<svg></svg>"}
        html = str(nav.markup(boot))
    assert "&lt;i&gt;Hall&lt;/i&gt;" in html and "<i>Hall</i>" not in html
    # The page on screen is in it, so it is open with that row lit.
    assert 'aria-expanded="true"><svg class=star></svg>' in html
    assert '<a href="/stats" class="fb-nav-row" aria-current="page">' in html
    assert 'href="https://example.com" class="fb-nav-row" target="_blank" rel="noopener noreferrer"' in html
