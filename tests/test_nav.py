"""The sidebar on every crew page (floorbit/nav.py, templates/_nav.html)."""
import json
import re

import pytest

from tests.test_rbac import sign_in_as

SERVER_PAGES = ("/editor/classic",)   # the older floor plan editor; every other crew page is the React app


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
        data = boot(crew.get("/editor/classic").get_data(as_text=True))
        assert data["pages"] == crew.get("/api/pages").get_json()["pages"], role
        assert data["user"]["username"] == who and data["signOut"] is True
    viewer = boot(sign_in_as(app_module, "vi2", "viewer").get("/editor/classic").get_data(as_text=True))
    assert "/settings" not in {p["href"] for p in viewer["pages"]}


def test_every_page_has_its_own_name(client):
    # Issue #240: /plan and /seat-mapping were both "Seats", also for screen readers.
    pages = boot(client.get("/editor/classic").get_data(as_text=True))["pages"]
    labels = [p["label"] for p in pages]
    assert "Seat mapping" in labels and len(labels) == len(set(labels))


def test_the_floor_plan_top_bar_keeps_only_its_own_tools(client):
    # The page links used to crowd the top bar (issue #238); now they are all in the sidebar.
    page = client.get("/editor/classic").get_data(as_text=True)
    top = page[page.index('<header class="topbar">'):page.index('</header>', page.index('<header class="topbar">'))]
    assert 'id="hall-select"' in top and 'id="btn-refresh-all"' in top
    assert 'href="/problems"' not in top and 'action="/logout"' not in top and 'href="/settings"' not in top


@pytest.mark.parametrize("built", [True, False])
def test_the_sidebar_loads_the_build_or_falls_back_to_links(client, monkeypatch, built):
    from floorbit import spa
    fake = {"js": ["/static/app/assets/nav.js"], "css": ["/static/app/assets/nav.css"]}
    monkeypatch.setattr(spa, "assets", lambda entry=spa.ENTRY: fake if built else None)
    html = client.get("/editor/classic").get_data(as_text=True)
    assert ('/static/app/assets/nav.js' in html) is built
    # Without a frontend build every page is still a plain link away.
    assert ('class="fb-nav-fallback"' in html) is not built
    if not built:
        assert 'href="/problems"' in html


def test_the_folded_sidebar_keeps_its_width_from_the_cookie(client):
    assert 'data-state="full"' in client.get("/editor/classic").get_data(as_text=True)
    client.set_cookie("floorbit_nav", "rail")
    assert 'id="fb-nav" class="fb-nav-slot" data-state="rail"' in client.get("/editor/classic").get_data(as_text=True)


def test_react_pages_get_the_sidebar_data(client, monkeypatch):
    from floorbit import spa
    monkeypatch.setattr(spa, "assets", lambda entry=spa.ENTRY: {"js": ["/static/app/x.js"], "css": []})
    html = client.get("/problems").get_data(as_text=True)
    assert boot(html)["pages"] and 'class="fb-has-nav"' in html
    # The React app draws the sidebar itself: no second one from the server.
    assert 'id="fb-nav"' not in html


SHELL = {
    "pinned": ["floorPlan", "seats", "problems"], "tabs": ["floorPlan", "seats", "problems"],
    "sections": [{"id": "admin", "pages": ["settings", "users"]}],
    "icons": {"page": {"*": "<svg class=\"fb-nav-icon\"></svg>"}, "tab": {"*": "<svg></svg>"},
              "section": {"admin": "<svg></svg>"}, "search": "<svg></svg>", "chevron": "<svg></svg>",
              "collapse": "<svg></svg>", "expand": "<svg></svg>", "menu": "<svg></svg>", "dots": "<svg></svg>"},
    "texts": {
        "en": {"nav": {"label": "Main", "home": "Floor plan", "goTo": "Go to…", "account": "Account",
                       "collapse": "Collapse", "expand": "Expand", "menu": "Menu", "quick": "Main pages",
                       "sections": {"admin": "Settings", "more": "More"}},
               "pages": {"floorPlan": "Floor plan"}, "signedInAs": "Signed in as {{username}}"},
        "de-CH": {"nav": {"label": "Haupt", "home": "Saalplan", "goTo": "Gehe zu…", "account": "Konto",
                          "collapse": "Einklappen", "expand": "Ausklappen", "menu": "Menü", "quick": "Hauptseiten",
                          "sections": {"admin": "Einstellungen", "more": "Mehr"}},
                  "pages": {"floorPlan": "Saalplan"}, "signedInAs": "Angemeldet als {{username}}"},
    },
}


@pytest.fixture
def shell(monkeypatch):
    from floorbit import nav, spa
    monkeypatch.setattr(spa, "assets", lambda entry=spa.ENTRY: {"js": ["/static/app/assets/nav.js"], "css": []})
    monkeypatch.setattr(nav, "_shell", lambda: SHELL)
    return SHELL


def test_the_sidebar_is_in_the_page_before_the_floor_plan(client, shell):
    # Mike: the plan showed up before the sidebar. The sidebar's markup now comes from the server,
    # ahead of the plan's own markup and scripts, so it is in the very first paint.
    html = client.get("/editor/classic").get_data(as_text=True)
    slot = html.index('id="fb-nav"')
    assert slot < html.index('<nav class="fb-nav"') < html.index('<header class="topbar">')
    assert html.index('<nav class="fb-nav"') < html.index('/static/js/editor/main.js')
    first = html[html.index('<nav class="fb-nav"'):html.index('<nav class="fb-tabbar"')]
    assert '<a href="/plan" class="fb-nav-row"' in first and "Floor plan" in first
    assert "fb-nav-fallback" not in html


def test_the_first_paint_speaks_the_browsers_language(client, shell):
    client.set_cookie("floorbit_lang", "de-CH")
    assert "Gehe zu…" in client.get("/editor/classic").get_data(as_text=True)
    client.delete_cookie("floorbit_lang")
    html = client.get("/editor/classic", headers={"Accept-Language": "de-CH,de;q=0.9"}).get_data(as_text=True)
    assert "Saalplan" in html and "Gehe zu…" in html
    assert "Go to…" in client.get("/editor/classic", headers={"Accept-Language": "fr,en;q=0.8"}).get_data(as_text=True)


def test_the_first_paint_keeps_the_fold_and_escapes_the_brand(client, shell, monkeypatch):
    from floorbit import nav
    real = nav.boot
    monkeypatch.setattr(nav, "boot", lambda ctx: {**real(ctx), "brand": {"logo": None, "name": "<b>LAN</b>"}})
    html = client.get("/editor/classic").get_data(as_text=True)
    assert "&lt;b&gt;LAN&lt;/b&gt;" in html and "<b>LAN</b>" not in html
    client.set_cookie("floorbit_nav", "rail")
    assert '<nav class="fb-nav" data-state="rail"' in client.get("/editor/classic").get_data(as_text=True)


def test_without_a_build_shell_the_slot_waits_for_the_script(client, monkeypatch):
    from floorbit import nav, spa
    monkeypatch.setattr(spa, "assets", lambda entry=spa.ENTRY: {"js": ["/static/app/assets/nav.js"], "css": []})
    monkeypatch.setattr(nav, "_shell", lambda: None)
    html = client.get("/editor/classic").get_data(as_text=True)
    assert 'id="fb-nav"' in html and '<nav class="fb-nav"' not in html


def test_favourites_and_folding_are_kept_with_the_account(app_module, shell):
    crew = sign_in_as(app_module, "fav1", "tech")
    assert crew.get("/api/auth/me/nav").get_json() == {"favourites": [], "accordion": True}
    saved = crew.put("/api/auth/me/nav", json={"favourites": ["problems", "problems", "../x", 7, "settings"],
                                               "accordion": False, "colour": "red"})
    assert saved.get_json() == {"favourites": ["problems", "settings"], "accordion": False}
    assert boot(crew.get("/editor/classic").get_data(as_text=True))["prefs"] == {"favourites": ["problems", "settings"],
                                                                     "accordion": False}
    other = sign_in_as(app_module, "fav2", "viewer")
    assert other.get("/api/auth/me/nav").get_json()["favourites"] == []


def test_the_first_paint_lists_the_favourites_first(app_module, shell, monkeypatch):
    texts = shell["texts"]["en"]["nav"]
    monkeypatch.setitem(texts, "favourites", "Favourites")
    monkeypatch.setitem(texts, "favAdd", "Add {{page}} to favourites")
    monkeypatch.setitem(texts, "favRemove", "Remove {{page}} from favourites")
    monkeypatch.setitem(shell["icons"], "star", "<svg class=star></svg>")
    monkeypatch.setitem(shell["icons"], "starFilled", "<svg class=filled></svg>")
    crew = sign_in_as(app_module, "fav3", "admin")
    crew.put("/api/auth/me/nav", json={"favourites": ["problems"]})
    html = crew.get("/editor/classic").get_data(as_text=True)
    side = html[html.index('<nav class="fb-nav"'):html.index('<nav class="fb-tabbar"')]
    favs = side[side.index('class="fb-nav-favs"'):side.index('</ul>')]
    assert 'href="/problems"' in favs and 'aria-label="Remove Problems from favourites"' in favs
    assert side.index('class="fb-nav-favs"') < side.index('<a href="/plan" class="fb-nav-row"')
    assert 'aria-label="Add Floor plan to favourites"' in side


def test_only_a_signed_in_account_keeps_sidebar_settings(anon_client):
    assert anon_client.get("/api/auth/me/nav").status_code == 400
    assert anon_client.put("/api/auth/me/nav", json={"favourites": ["problems"]}).status_code == 401


def test_the_first_paint_has_the_admins_own_sections(client, shell, monkeypatch):
    client.put("/api/settings/sidebar", json={"sections": [
        {"name": "<i>Hall</i>", "icon": "star", "links": [
            {"kind": "url", "href": "/editor/classic", "label": "Classic"},
            {"kind": "url", "href": "https://example.com", "label": "Out"}]}]})
    # A build from before these sections has no icons for them: they wait for the script.
    old = client.get("/editor/classic").get_data(as_text=True)
    assert "Hall" not in old[old.index('<nav class="fb-nav"'):old.index('<nav class="fb-tabbar"')]
    monkeypatch.setitem(shell["icons"], "custom", {"star": "<svg class=star></svg>", "folder": "<svg></svg>"})
    monkeypatch.setitem(shell["icons"], "link", {"dashboard": "<svg></svg>", "url": "<svg class=url></svg>",
                                                 "external": "<svg class=out></svg>"})
    html = client.get("/editor/classic").get_data(as_text=True)
    first = html[html.index('<nav class="fb-nav"'):html.index('<nav class="fb-tabbar"')]
    assert "&lt;i&gt;Hall&lt;/i&gt;" in first and "<i>Hall</i>" not in first
    # The page on screen is in it, so it is open with that row lit.
    assert 'aria-expanded="true"><svg class=star></svg>' in first
    assert '<a href="/editor/classic" class="fb-nav-row" aria-current="page">' in first
    assert 'href="https://example.com" class="fb-nav-row" target="_blank" rel="noopener noreferrer"' in first
