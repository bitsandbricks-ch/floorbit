"""A plugin's own German: locales/de-CH.json in its folder (docs/plugin-spec.md, Texts and German)."""
import json

import pytest
from test_plugins import turn_on, write_plugin

from floorbit.plugins import _load

YAML = """
id: hallgreet
name: Hall greeter
version: "1.0"
description: Greets the hall.
uses: [settings, actions, widgets]
settings:
  - {key: greeting, label: Greeting, help: What it says, type: string, default: hi}
actions:
  - {id: wave, label: Wave, role: editor, dashboard: true, params: [{key: times, type: int, default: 1}]}
  - {id: grumble, label: Grumble, role: editor}
widgets:
  - {id: count, label: Waves today}
"""

PY = """
from floorbit.plugins.base import Plugin as Base, PluginError

class Plugin(Base):
    def run_wave(self, params):
        return {'message': f"Waved {params['times']} times"}

    def run_grumble(self, params):
        raise PluginError('Not in the mood')

    def widget_count(self):
        return {'type': 'status', 'items': [{'label': 'Front door', 'state': 'up', 'detail': 'Up'}],
                'sub': 'since the doors opened'}
"""

GERMAN = {"Hall greeter": "Hallengrüsser", "Greets the hall.": "Grüsst die Halle.", "Greeting": "Gruss",
          "What it says": "Was er sagt", "Wave": "Winken", "Waves today": "Winker heute",
          "Waved {} times": "{} Mal gewunken", "Not in the mood": "Keine Lust", "Front door": "Haupteingang",
          "since the doors opened": "seit Türöffnung", "Strasse": "Strasse"}
DE = {"Accept-Language": "de-CH"}


@pytest.fixture
def greeter(tmp_path, app_module, client):
    registry = app_module.app.extensions["floorbit_plugins"]
    folder = write_plugin(tmp_path, "hallgreet", YAML, PY)
    (folder / "locales").mkdir()
    (folder / "locales" / "de-CH.json").write_text(json.dumps(GERMAN), encoding="utf-8")
    spec = _load(folder, "development", registry.version)
    assert spec.error == ""
    registry.specs[spec.id] = spec
    registry._register_settings()
    turn_on(client, "hallgreet")
    yield registry
    registry.specs.pop(spec.id, None)


def test_its_tiles_messages_and_errors_read_german(client, greeter):
    tile = client.get("/api/plugins/hallgreet/widgets/count", headers=DE).get_json()
    assert (tile["label"], tile["sub"]) == ("Winker heute", "seit Türöffnung")
    assert tile["items"][0]["label"] == "Haupteingang"
    done = client.post("/api/plugins/hallgreet/actions/wave", json={"times": 3}, headers=DE).get_json()
    assert done["message"] == "3 Mal gewunken"
    refused = client.post("/api/plugins/hallgreet/actions/grumble", json={}, headers=DE).get_json()
    assert refused["error"] == "Keine Lust"
    english = client.post("/api/plugins/hallgreet/actions/wave", json={"times": 3}).get_json()
    assert english["message"] == "Waved 3 times"


def test_its_name_settings_and_dashboard_read_german(client, greeter):
    listed = {p["id"]: p for p in client.get("/api/settings/plugins", headers=DE).get_json()["plugins"]}
    assert (listed["hallgreet"]["name"], listed["hallgreet"]["description"]) == ("Hallengrüsser", "Grüsst die Halle.")
    assert listed["hallgreet"]["actions"][0]["label"] == "Winken"
    settings = client.get("/api/settings", headers=DE).get_json()
    field = next(f for f in settings["fields"] if f["key"] == "plugin.hallgreet.greeting")
    assert (field["label"], field["help"]) == ("Gruss", "Was er sagt")
    section = next(s for s in settings["sections"] if s["id"] == "plugin-hallgreet")
    assert section["title"] == "Plugin: Hallengrüsser"
    tiles = client.get("/api/dashboard", headers=DE).get_json()["tiles"]
    mine = [t for t in tiles if t["plugin"] == "hallgreet"]
    assert {t["label"] for t in mine} == {"Winker heute", "Winken"}
    assert all(t["plugin_name"] == "Hallengrüsser" for t in mine)


def test_standard_german_is_made_from_the_swiss(client, greeter):
    assert greeter.text(greeter.specs["hallgreet"], "Greeting", "de") == "Gruß"


@pytest.mark.parametrize("content, error", [
    ("not json", "locales/de-CH.json"),
    (json.dumps(["a"]), "an object of up to"),
    (json.dumps({"Waved {} times": "Gewunken"}), "different number of {}"),
    (json.dumps({"a": 1}), "an object of up to"),
])
def test_a_bad_german_file_is_refused(tmp_path, content, error):
    folder = write_plugin(tmp_path, "hallgreet", YAML, PY)
    (folder / "locales").mkdir()
    (folder / "locales" / "de-CH.json").write_text(content, encoding="utf-8")
    assert error in _load(folder, "development", "1.0").error
