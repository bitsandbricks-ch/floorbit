"""Plugin layers: a layer on the floor plan that colours seats, with its own legend."""
import pytest
from test_plugin_panels import turn_on
from test_plugins import write_plugin

from floorbit.plugins import WidgetError, _load, check_layer, validate

YAML = """
id: layerthing
name: Layer thing
version: "1.0"
uses: [layers]
layers:
  - {id: load, label: Seat load, refresh: 5}
  - {id: secret, permission: settings.manage}
  - {id: slow}
  - {id: bad}
"""

PY = """
import time
from floorbit.plugins.base import Plugin as Base

class Plugin(Base):
    def layer_load(self):
        return {'seats': {'A-1': {'tone': 'ok', 'label': 'Up'}, 'A-2': {'tone': 'err', 'label': 'Down'}},
                'legend': [{'tone': 'ok', 'label': 'Up'}, {'tone': 'err', 'label': 'Down'}]}

    def layer_secret(self):
        return {'seats': {}}

    def layer_slow(self):
        time.sleep(5)

    def layer_bad(self):
        return {'seats': {'A-1': {'tone': 'red; background:url(x)'}}}
"""

BASE = {'id': 'demo-x', 'name': 'X', 'version': '1.0.0', 'uses': ['layers']}


@pytest.fixture
def thing(tmp_path, app_module):
    registry = app_module.app.extensions["floorbit_plugins"]
    spec = _load(write_plugin(tmp_path, "layerthing", YAML, PY), "development", registry.version)
    assert spec.error == ""
    registry.specs[spec.id] = spec
    yield spec
    registry.specs.pop(spec.id, None)


@pytest.mark.parametrize("layers, error", [
    ([{"id": "x"}, {"id": "x"}], "duplicate"),
    ([{"id": "x", "permission": "nope"}], "unknown permission"),
    ([{"id": "x", "permision": "settings.manage"}], "unknown key(s) permision"),
    ([{"id": "Bad"}], "bad id"),
])
def test_bad_layers_are_refused(layers, error):
    assert error in validate({**BASE, "layers": layers})


def test_layers_need_the_area():
    assert "not under uses" in validate({**BASE, "uses": ["settings"], "layers": [{"id": "x"}]})


def test_a_layer_method_without_a_manifest_entry_is_refused(tmp_path, app_module):
    registry = app_module.app.extensions["floorbit_plugins"]
    code = PY + "\n    def layer_hidden(self):\n        return {}\n"
    spec = _load(write_plugin(tmp_path, "layerthing", YAML, code), "development", registry.version)
    assert "layer_hidden has no matching entry" in spec.error


@pytest.mark.parametrize("raw", [
    None, [], {"seats": []}, {"seats": {"A-1": {"tone": "pink"}}}, {"seats": {"A-1": "ok"}},
    {"seats": {"": {"tone": "ok"}}}, {"seats": {"x" * 129: {"tone": "ok"}}}, {"seats": {}, "legend": [{"tone": "x"}]},
])
def test_what_a_layer_returns_is_checked(raw):
    with pytest.raises(WidgetError):
        check_layer(raw)


def test_a_layer_is_cut_to_what_the_plan_draws():
    got = check_layer({"seats": {f"S-{i}": {"tone": "warn", "label": "x" * 100, "html": "<b>"} for i in range(6000)},
                       "legend": [{"tone": "info", "label": "a"}] * 20, "script": "alert(1)"})
    assert len(got["seats"]) == 5000 and got["seats"]["S-0"] == {"tone": "warn", "label": "x" * 60}
    assert len(got["legend"]) == 8 and set(got) == {"seats", "legend"}


def test_the_list_and_one_layer(client, thing):
    assert client.get("/api/plugins/layers").get_json()["layers"] == []      # off: none
    turn_on(client, "layerthing")
    listed = client.get("/api/plugins/layers").get_json()["layers"]
    assert [p["id"] for p in listed] == ["load", "secret", "slow", "bad"]
    assert listed[0]["label"] == "Seat load" and listed[0]["refresh"] == 10 and listed[0]["plugin"] == "layerthing"
    body = client.get("/api/plugins/layerthing/layers/load").get_json()
    assert body["seats"]["A-2"] == {"tone": "err", "label": "Down"}
    assert body["legend"][0] == {"tone": "ok", "label": "Up"}


def test_a_broken_or_slow_layer_is_an_error_not_a_hang(client, thing, monkeypatch):
    monkeypatch.setattr("floorbit.plugins.REQUEST_BUDGET", 0.3)
    turn_on(client, "layerthing")
    bad = client.get("/api/plugins/layerthing/layers/bad")
    assert bad.status_code == 502 and "can't draw" in bad.get_json()["error"]
    slow = client.get("/api/plugins/layerthing/layers/slow")
    assert slow.status_code == 502 and "did not answer" in slow.get_json()["error"]
    assert client.get("/api/plugins/layerthing/layers/nope").status_code == 404


def test_a_layer_asks_for_the_permission_it_names(client, thing, kiosk_client, anon_client):
    turn_on(client, "layerthing")
    assert "secret" not in [p["id"] for p in kiosk_client.get("/api/plugins/layers").get_json()["layers"]]
    assert kiosk_client.get("/api/plugins/layerthing/layers/secret").status_code == 403
    assert kiosk_client.get("/api/plugins/layerthing/layers/load").status_code == 200
    assert anon_client.get("/api/plugins/layers").status_code == 401
    assert anon_client.get("/api/plugins/layerthing/layers/load").status_code == 401
