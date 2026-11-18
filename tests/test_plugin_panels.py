"""Plugin panels: a plugin's box in the side panel of a seat, a switch or an inventory device."""
import pytest
from test_plugins import turn_on, write_plugin

from floorbit.plugins import _load, validate

YAML = """
id: panelthing
name: Panel thing
icon: chart
version: "1.0"
uses: [panels]
panels:
  - {id: load, for: seat, label: Seat load}
  - {id: uplink, for: switch, label: Uplink, refresh: 5}
  - {id: secret, for: seat, permission: settings.manage}
  - {id: slow, for: device}
  - {id: bad, for: device}
"""

PY = """
import time
from floorbit.plugins.base import Plugin as Base

class Plugin(Base):
    def panel_load(self, target):
        return {'type': 'stat', 'value': len(target['id']), 'sub': target['kind'] + ' ' + target['id']}

    def panel_uplink(self, target):
        return {'type': 'stat', 'value': 1}

    def panel_secret(self, target):
        return {'type': 'stat', 'value': 42}

    def panel_slow(self, target):
        time.sleep(5)

    def panel_bad(self, target):
        return {'type': 'html', 'value': '<script>alert(1)</script>'}
"""

BASE = {'id': 'demo-x', 'name': 'X', 'version': '1.0.0', 'uses': ['panels']}


@pytest.fixture
def thing(tmp_path, app_module):
    registry = app_module.app.extensions["floorbit_plugins"]
    spec = _load(write_plugin(tmp_path, "panelthing", YAML, PY), "development", registry.version)
    assert spec.error == ""
    registry.specs[spec.id] = spec
    yield spec
    registry.specs.pop(spec.id, None)


@pytest.mark.parametrize("panels, error", [
    ([{"id": "x", "for": "hall"}], "for must be one of seat, switch, device"),
    ([{"id": "x"}], "for must be one of"),
    ([{"id": "x", "for": "seat"}, {"id": "x", "for": "seat"}], "duplicate"),
    ([{"id": "x", "for": "seat", "permission": "nope"}], "unknown permission"),
    ([{"id": "x", "for": "seat", "permision": "settings.manage"}], "unknown key(s) permision"),
])
def test_bad_panels_are_refused(panels, error):
    assert error in validate({**BASE, "panels": panels})


def test_panels_need_the_area():
    assert 'not under uses' in validate({**BASE, "uses": ["settings"], "panels": [{"id": "x", "for": "seat"}]})


def test_a_panel_method_without_a_manifest_entry_is_refused(tmp_path, app_module):
    registry = app_module.app.extensions["floorbit_plugins"]
    code = PY + "\n    def panel_hidden(self, target):\n        return {}\n"
    spec = _load(write_plugin(tmp_path, "panelthing", YAML, code), "development", registry.version)
    assert "panel_hidden has no matching entry" in spec.error


def test_the_list_says_which_panels_go_where(client, thing):
    assert client.get("/api/plugins/panels?on=seat").get_json()["panels"] == []   # off: none
    turn_on(client, "panelthing")
    seat = client.get("/api/plugins/panels?on=seat").get_json()["panels"]
    assert [p["id"] for p in seat] == ["load", "secret"]
    assert seat[0]["icon"] == "chart" and seat[0]["label"] == "Seat load" and seat[0]["refresh"] == 60
    assert [p["id"] for p in client.get("/api/plugins/panels?on=switch").get_json()["panels"]] == ["uplink"]
    assert client.get("/api/plugins/panels?on=switch").get_json()["panels"][0]["refresh"] == 10   # at least 10 s
    assert client.get("/api/plugins/panels?on=hall").status_code == 400


def test_a_panel_gets_its_target(client, thing):
    turn_on(client, "panelthing")
    body = client.get("/api/plugins/panelthing/panels/load?target=A-12").get_json()
    assert (body["type"], body["value"], body["sub"], body["label"]) == ("stat", 4, "seat A-12", "Seat load")


@pytest.mark.parametrize("target", ["", "x" * 129, "A-1\n", "A\x00"])
def test_a_bad_target_is_refused(client, thing, target):
    turn_on(client, "panelthing")
    assert client.get("/api/plugins/panelthing/panels/load", query_string={"target": target}).status_code == 400


def test_a_broken_or_slow_panel_is_an_error_not_a_hang(client, thing, monkeypatch):
    monkeypatch.setattr("floorbit.plugins.REQUEST_BUDGET", 0.3)
    turn_on(client, "panelthing")
    bad = client.get("/api/plugins/panelthing/panels/bad?target=sw-1")
    assert bad.status_code == 502 and "can't draw" in bad.get_json()["error"]
    slow = client.get("/api/plugins/panelthing/panels/slow?target=sw-1")
    assert slow.status_code == 502 and "did not answer" in slow.get_json()["error"]


def test_unknown_panels_are_404(client, thing):
    turn_on(client, "panelthing")
    assert client.get("/api/plugins/panelthing/panels/nope?target=A-1").status_code == 404
    assert client.get("/api/plugins/nothing/panels/load?target=A-1").status_code == 404


def test_a_panel_asks_for_the_permission_it_names(client, thing, kiosk_client, anon_client):
    turn_on(client, "panelthing")
    # A kiosk only sees the plan: a panel that asks for more is neither listed nor served.
    assert [p["id"] for p in kiosk_client.get("/api/plugins/panels?on=seat").get_json()["panels"]] == ["load"]
    assert kiosk_client.get("/api/plugins/panelthing/panels/secret?target=A-1").status_code == 403
    assert kiosk_client.get("/api/plugins/panelthing/panels/load?target=A-1").status_code == 200
    assert anon_client.get("/api/plugins/panels?on=seat").status_code == 401
    assert anon_client.get("/api/plugins/panelthing/panels/load?target=A-1").status_code == 401
