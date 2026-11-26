"""Plugin pages: a plugin's own page of tiles in the sidebar's Plugins section."""
import pytest
from test_plugin_panels import turn_on
from test_plugins import write_plugin

from floorbit.plugins import _load, validate

YAML = """
id: pagething
name: Page thing
icon: gamepad
version: "1.0"
uses: [pages, widgets, actions]
widgets:
  - {id: load, label: Load}
  - {id: secret, label: Secret, permission: settings.manage}
actions:
  - {id: clear, label: Clear the cache, role: editor}
pages:
  - {id: overview, label: Game servers, widgets: [load, secret], actions: [clear], columns: 3}
  - {id: admin, label: Admin only, widgets: [secret], permission: settings.manage}
"""

PY = """
from floorbit.plugins.base import Plugin as Base

class Plugin(Base):
    def widget_load(self):
        return {'type': 'stat', 'value': 3}

    def widget_secret(self):
        return {'type': 'stat', 'value': 42}

    def run_clear(self, params):
        return {'message': 'cleared'}
"""

BASE = {'id': 'demo-x', 'name': 'X', 'version': '1.0.0', 'uses': ['pages', 'widgets'],
        'widgets': [{'id': 'load'}]}


@pytest.fixture
def thing(tmp_path, app_module):
    registry = app_module.app.extensions["floorbit_plugins"]
    spec = _load(write_plugin(tmp_path, "pagething", YAML, PY), "development", registry.version)
    assert spec.error == ""
    registry.specs[spec.id] = spec
    yield spec
    registry.specs.pop(spec.id, None)


@pytest.mark.parametrize("pages, error", [
    ([{"id": "x", "widgets": ["nope"]}], "only ids from the plugin's own widgets"),
    ([{"id": "x", "actions": ["load"]}], "only ids from the plugin's own actions"),
    ([{"id": "x"}], "1 to 24 widgets and actions"),
    ([{"id": "x", "widgets": "load"}], "only ids from"),
    ([{"id": "x", "widgets": ["load"], "columns": 5}], "columns is 1, 2 or 3"),
    ([{"id": "x", "widgets": ["load"], "html": "<b>"}], "unknown key(s) html"),
    ([{"id": "x", "widgets": ["load"]}, {"id": "x", "widgets": ["load"]}], "duplicate"),
])
def test_bad_pages_are_refused(pages, error):
    assert error in validate({**BASE, "pages": pages})


def test_pages_need_the_area():
    assert "not under uses" in validate({**BASE, "uses": ["widgets"], "pages": [{"id": "x", "widgets": ["load"]}]})


def test_the_sidebar_lists_the_pages_this_account_may_open(client, thing, kiosk_client):
    assert not [p for p in client.get("/api/pages").get_json()["pages"] if p["id"].startswith("plugin:")]   # off
    turn_on(client, "pagething")
    mine = [p for p in client.get("/api/pages").get_json()["pages"] if p["id"].startswith("plugin:")]
    assert mine == [
        {"href": "/plugins/pagething/overview", "id": "plugin:pagething:overview", "label": "Game servers",
         "icon": "gamepad", "plugin": "Page thing"},
        {"href": "/plugins/pagething/admin", "id": "plugin:pagething:admin", "label": "Admin only",
         "icon": "gamepad", "plugin": "Page thing"}]
    kiosk = [p["id"] for p in kiosk_client.get("/api/pages").get_json()["pages"] if p["id"].startswith("plugin:")]
    assert kiosk == ["plugin:pagething:overview"]


def test_a_page_has_the_tiles_this_account_may_see(client, thing, kiosk_client, anon_client):
    turn_on(client, "pagething")
    body = client.get("/api/plugins/pagething/pages/overview").get_json()
    assert (body["label"], body["columns"], body["icon"]) == ("Game servers", 3, "gamepad")
    assert [(t["id"], t.get("kind")) for t in body["tiles"]] == [("load", None), ("secret", None), ("clear", "action")]
    assert body["tiles"][0]["url"] == "/api/plugins/pagething/widgets/load"
    # A kiosk sees the page, without the tile and the action it may not use.
    assert [t["id"] for t in kiosk_client.get("/api/plugins/pagething/pages/overview").get_json()["tiles"]] == ["load"]
    assert kiosk_client.get("/api/plugins/pagething/pages/admin").status_code == 403
    assert anon_client.get("/api/plugins/pagething/pages/overview").status_code == 401
    assert client.get("/api/plugins/pagething/pages/nope").status_code == 404
    assert client.get("/api/plugins/nothing/pages/overview").status_code == 404


def test_the_page_itself_is_the_react_app(client, thing):
    turn_on(client, "pagething")
    res = client.get("/plugins/pagething/overview")
    # 503 is the same page saying how to build the frontend: CI's pytest jobs run without a build.
    assert res.status_code in (200, 503) and b"<html" in res.data.lower()
