"""Plugins: manifest checks, the uses: limits, on/off, actions, widgets, endpoints and hooks."""
import textwrap

import pytest
from conftest import TEST_PASSWORD

from floorbit import audit
from floorbit.plugins import _load, compatible, validate
from floorbit.plugins.widgets import WidgetError, check_widget

GOOD_YAML = """
id: sample
name: Sample
version: "1.0"
floorbit: ">=0.1,<2"
uses: [settings, actions, widgets, endpoints, hooks, storage]
settings:
  - {key: greeting, type: string, default: hello}
  - {key: api_token, type: secret}
actions:
  - {id: wave, label: Wave, role: editor, params: [{key: times, type: int, default: 1, min: 1, max: 5}]}
  - {id: reboot_all, role: admin, danger: true}
  - {id: remember, role: editor}
widgets:
  - {id: count, label: Waves}
  - {id: broken}
  - {id: secret_stats, role: admin}
endpoints:
  - {id: info}
hooks:
  - {events: [change], action: remember}
"""

GOOD_PY = """
from floorbit.plugins.base import Plugin as Base, PluginError

class Plugin(Base):
    def run_wave(self, params):
        n = self.ctx.state.get('waves', 0) + params['times']
        self.ctx.set_state('waves', n)
        return {'message': f"{self.settings['greeting']} x{params['times']}", 'waves': n}

    def run_reboot_all(self, params):
        raise PluginError('Not today')

    def run_remember(self, params):
        self.ctx.set_state('last_event', params['data'])

    def widget_count(self):
        return {'type': 'stat', 'value': self.ctx.state.get('waves', 0), 'link': 'https://evil.example.com/'}

    def widget_broken(self):
        return {'type': 'stat', 'value': 1, 'tone': '<script>'}

    def widget_secret_stats(self):
        return {'type': 'stat', 'value': 7}

    def endpoint_info(self, args):
        return {'token_set': bool(self.settings['api_token']), 'args': args}

    def test(self):
        return 'All good'
"""


def write_plugin(tmp_path, name, manifest, code=None):
    folder = tmp_path / "plugins" / name
    folder.mkdir(parents=True)
    (folder / "plugin.yaml").write_text(textwrap.dedent(manifest))
    if code is not None:
        (folder / "plugin.py").write_text(textwrap.dedent(code))
    return folder


@pytest.fixture
def registry(app_module):
    return app_module.app.extensions["floorbit_plugins"]


class InlineThread:
    """Runs hooks in the test's own thread, so no hook outlives its test."""

    def __init__(self, target, args, **kwargs):
        self.target, self.args = target, args

    def start(self):
        self.target(*self.args)


@pytest.fixture
def sample(tmp_path, registry, monkeypatch):
    monkeypatch.setattr("floorbit.plugins.threading.Thread", InlineThread)
    spec = _load(write_plugin(tmp_path, "sample", GOOD_YAML, GOOD_PY), "development", registry.version)
    assert spec.error == ""
    registry.specs[spec.id] = spec
    registry._register_settings()
    yield spec
    registry.specs.pop(spec.id, None)


def turn_on(client, plugin_id="sample"):
    resp = client.put(f"/api/settings/plugins/{plugin_id}", json={"enabled": True})
    assert resp.status_code == 200, resp.data


# ── Manifest and code checks ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("change, error", [
    ({"id": "Bad_Id"}, "id:"),
    ({"uses": None}, "uses:"),
    ({"uses": ["settings", "root"]}, "unknown area"),
    ({"uses": ["settings"], "actions": [{"id": "x"}]}, '"actions" is not under uses'),
    ({"uses": ["actions"], "actions": [{"id": "x", "role": "viewer"}]}, "editor or admin"),
    ({"uses": ["settings"], "settings": [{"key": "x", "type": "file"}]}, "type must be"),
    ({"uses": ["actions", "hooks"], "actions": [{"id": "x"}], "hooks": [{"events": ["boot"], "action": "x"}]},
     "events must be"),
])
def test_bad_manifests_are_refused(change, error):
    manifest = {"id": "ok-plugin", "uses": ["settings"], **change}
    manifest = {k: v for k, v in manifest.items() if v is not None}
    assert error in validate(manifest)


def test_floorbit_version_range():
    assert compatible(">=0.1,<2", "0.1.0") == (True, "")
    assert not compatible(">=1.0", "0.1.0")[0]
    assert not compatible("soon", "0.1.0")[0]


def test_code_must_match_the_manifest(tmp_path):
    manifest = "id: sneaky\nuses: [actions]\nactions: [{id: listed}]\n"
    code = """
    from floorbit.plugins.base import Plugin as Base
    class Plugin(Base):
        def run_listed(self, params): return {}
        def run_unlisted(self, params): return {}
    """
    spec = _load(write_plugin(tmp_path, "sneaky", manifest, code), "development", "0.1.0")
    assert "run_unlisted has no matching entry" in spec.error

    spec = _load(write_plugin(tmp_path, "missing", manifest.replace("sneaky", "missing"),
                              "from floorbit.plugins.base import Plugin as Base\nclass Plugin(Base): pass\n"),
                 "development", "0.1.0")
    assert "no run_listed()" in spec.error


def test_a_broken_plugin_does_not_take_floorbit_down(tmp_path):
    spec = _load(write_plugin(tmp_path, "broken", "id: broken\nuses: [actions]\n", "raise RuntimeError('boom')"),
                 "development", "0.1.0")
    assert spec.error == "plugin.py: RuntimeError: boom"


def test_builtin_http_check_loads(registry):
    spec = registry.specs["http-check"]
    assert spec.error == "" and spec.trust == "builtin"
    assert not registry.enabled(spec)   # every plugin starts switched off


# ── Settings > Plugins ───────────────────────────────────────────────────────────────────

def test_plugins_page_and_api_are_admin_only(anon_client, client, app_module, sample):
    assert anon_client.get("/api/settings/plugins").status_code == 401
    assert anon_client.put("/api/settings/plugins/sample", json={"enabled": True}).status_code == 401
    app_module.app.extensions["auth"].users.add("ed", TEST_PASSWORD, role="editor")
    editor = app_module.app.test_client()
    editor.post("/login", data={"username": "ed", "password": TEST_PASSWORD})
    assert editor.get("/api/settings/plugins").status_code == 403
    assert editor.get("/settings/plugins").status_code == 403
    assert b"Plugins" in client.get("/settings/plugins").data


def test_turning_a_plugin_on_and_off_is_audited(client, sample):
    listed = {p["id"]: p for p in client.get("/api/settings/plugins").get_json()["plugins"]}
    assert listed["sample"]["enabled"] is False and listed["sample"]["trust"] == "development"
    assert [u["id"] for u in listed["sample"]["uses"]] == [
        "settings", "actions", "widgets", "endpoints", "hooks", "storage"]
    turn_on(client)
    listed = {p["id"]: p for p in client.get("/api/settings/plugins").get_json()["plugins"]}
    assert listed["sample"]["enabled"] is True
    row = audit.read(area="plugins")[0][0]
    assert (row["action"], row["target"], row["fields"]) == ("Changed plugin", "Sample", ["enabled"])
    assert client.put("/api/settings/plugins/nope", json={"enabled": True}).status_code == 404
    assert client.put("/api/settings/plugins/sample", json={"enabled": "yes"}).status_code == 400


def test_plugin_settings_live_on_the_settings_page(client, sample):
    body = client.get("/api/settings").get_json()
    keys = {f["key"]: f for f in body["fields"]}
    assert keys["plugin.sample.greeting"]["type"] == "text"
    assert keys["plugin.sample.api_token"]["type"] == "secret"
    # A plugin never chooses which environment variable it reads.
    assert keys["plugin.sample.api_token"]["env"] == "FLOORBIT_PLUGIN_SAMPLE_API_TOKEN"
    client.put("/api/settings", json={"plugin.sample.api_token": "example-plugin-token"})
    assert "example-plugin-token" not in client.get("/api/settings").get_data(as_text=True)


def test_a_switched_off_plugin_does_nothing(client, sample):
    assert client.post("/api/plugins/sample/actions/wave", json={}).status_code == 404
    assert client.get("/api/plugins/sample/widgets/count").status_code == 404
    assert client.get("/api/plugins/sample/endpoints/info").status_code == 404


# ── Actions ──────────────────────────────────────────────────────────────────────────────

def test_actions_run_with_checked_params_and_are_audited(client, sample):
    turn_on(client)
    resp = client.post("/api/plugins/sample/actions/wave", json={"times": 3})
    assert resp.status_code == 200
    assert resp.get_json() == {"ok": True, "message": "hello x3", "data": {"waves": 3}}
    assert client.post("/api/plugins/sample/actions/wave", json={"times": 9}).status_code == 400
    assert client.post("/api/plugins/sample/actions/wave", json={"times": "many"}).status_code == 400
    row = audit.read(area="plugins")[0][0]
    assert row["action"] == "Ran Sample: Wave" and row["fields"] == ["times"] and row["user"]


def test_plugin_errors_are_shown_and_audited_as_failed(client, sample):
    turn_on(client)
    resp = client.post("/api/plugins/sample/actions/reboot_all", json={})
    assert resp.status_code == 400 and resp.get_json()["error"] == "Not today"
    assert audit.read(area="plugins")[0][0]["ok"] is False


def test_action_roles(client, app_module, sample):
    turn_on(client)
    users = app_module.app.extensions["auth"].users
    for name, role in (("vi", "viewer"), ("ed", "editor")):
        users.add(name, TEST_PASSWORD, role=role)
    viewer, editor = app_module.app.test_client(), app_module.app.test_client()
    viewer.post("/login", data={"username": "vi", "password": TEST_PASSWORD})
    editor.post("/login", data={"username": "ed", "password": TEST_PASSWORD})
    assert viewer.post("/api/plugins/sample/actions/wave", json={}).status_code == 403
    assert editor.post("/api/plugins/sample/actions/wave", json={}).status_code == 200
    assert editor.post("/api/plugins/sample/actions/reboot_all", json={}).status_code == 403


def test_cross_site_action_posts_are_refused(client, sample):
    turn_on(client)
    resp = client.post("/api/plugins/sample/actions/wave", json={}, headers={"Origin": "https://evil.example.com"})
    assert resp.status_code == 403


# ── Widgets, endpoints, dashboard ────────────────────────────────────────────────────────

def test_widgets_are_checked_data(client, sample):
    turn_on(client)
    client.post("/api/plugins/sample/actions/wave", json={"times": 2})
    w = client.get("/api/plugins/sample/widgets/count").get_json()
    assert (w["type"], w["value"], w["label"]) == ("stat", 2, "Waves")
    assert w["link"] == ""   # only links on this site
    resp = client.get("/api/plugins/sample/widgets/broken")
    assert resp.status_code == 502 and "can't draw" in resp.get_json()["error"]


def test_widgets_and_endpoints_are_never_public(anon_client, client, sample):
    turn_on(client)
    assert anon_client.get("/api/plugins/sample/widgets/count").status_code == 401
    assert anon_client.get("/api/plugins/sample/endpoints/info").status_code == 401
    assert anon_client.get("/api/dashboard").status_code == 401
    assert anon_client.get("/dashboard").status_code == 302


def test_endpoints_return_json(client, sample):
    turn_on(client)
    body = client.get("/api/plugins/sample/endpoints/info?seat=A1").get_json()
    assert body == {"token_set": False, "args": {"seat": "A1"}}


def test_dashboard_lists_what_the_role_may_see(client, app_module, sample):
    turn_on(client)
    tiles = client.get("/api/dashboard").get_json()["tiles"]
    assert {t["id"] for t in tiles} >= {"count", "secret_stats"}
    app_module.app.extensions["auth"].users.add("vi", TEST_PASSWORD, role="viewer")
    viewer = app_module.app.test_client()
    viewer.post("/login", data={"username": "vi", "password": TEST_PASSWORD})
    ids = {t["id"] for t in viewer.get("/api/dashboard").get_json()["tiles"] if t["plugin"] == "sample"}
    assert ids == {"count", "broken"}
    assert viewer.get("/api/plugins/sample/widgets/secret_stats").status_code == 403
    assert b"Dashboard" in viewer.get("/dashboard").data


def test_widget_shapes():
    item = {"id": "w", "label": "W"}
    ok = check_widget({"type": "status", "items": [{"label": "DNS", "state": "up"}]}, item)
    assert ok["items"][0]["state"] == "up"
    for bad in ({"type": "html", "html": "<b>"}, {"type": "status", "items": [{"state": "on fire"}]},
                {"type": "sparkline", "points": ["1"]}, {"type": "table", "columns": []}, "nope"):
        with pytest.raises(WidgetError):
            check_widget(bad, item)


# ── Hooks ────────────────────────────────────────────────────────────────────────────────

def test_hooks_run_on_audited_changes(client, registry, sample, monkeypatch):
    turn_on(client)
    ran = []

    class Inline:   # run the hook in this thread, so the test doesn't race it
        def __init__(self, target, args, **kwargs):
            self.target, self.args = target, args

        def start(self):
            ran.append(self.args[2])
            self.target(*self.args)

    monkeypatch.setattr("floorbit.plugins.threading.Thread", Inline)
    client.post("/api/switches", json={"name": "sw-demo-01", "x": 1, "y": 1})
    assert ran == ["change"]
    last = registry.state_of("sample")["last_event"]
    assert (last["action"], last["target"]) == ("Added switch", "sw-demo-01")


# ── Built-in: HTTP check ─────────────────────────────────────────────────────────────────

class FakeResponse:
    def __init__(self, status):
        self.status_code = status


def test_http_check(client, monkeypatch):
    import requests
    calls = []

    def fake_request(self, method, url, **kw):
        calls.append((url, kw["timeout"], kw["allow_redirects"], self.verify))
        if "down" in url:
            raise requests.exceptions.ConnectionError("refused")
        return FakeResponse(200)

    monkeypatch.setattr(requests.Session, "request", fake_request)
    client.put("/api/settings", json={"plugin.http-check.targets": ["Cache=https://cache.example.com/health",
                                                                    "https://down.example.com"]})
    turn_on(client, "http-check")
    resp = client.post("/api/plugins/http-check/actions/check", json={})
    assert resp.get_json()["message"] == "1 of 2 up: down.example.com down"
    assert calls[0] == ("https://cache.example.com/health", 5, False, True)
    w = client.get("/api/plugins/http-check/widgets/services").get_json()
    assert [(i["label"], i["state"]) for i in w["items"]] == [("Cache", "up"), ("down.example.com", "down")]

    client.put("/api/settings", json={"plugin.http-check.targets": ["file:///etc/passwd"]})
    assert "is not an http" in client.post("/api/plugins/http-check/actions/check", json={}).get_json()["error"]
