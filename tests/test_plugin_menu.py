"""Plugin entries in the floor plan's right-click menu (issue #54)."""
import pytest
from conftest import TEST_PASSWORD

from floorbit.plugins import _load, validate
from tests.test_plugins import turn_on, write_plugin

MENU_YAML = """
id: tickets
name: Ticket shop
version: "1.0"
floorbit: ">=0.1,<2"
uses: [actions, context_menu]
actions:
  - {id: lookup, label: Look up ticket, role: editor, params: [{key: seat, type: string}]}
  - {id: kick, label: Kick, role: admin, danger: true, params: [{key: seat, type: string}, {key: switch, type: string}]}
context_menu:
  - {action: lookup, targets: seat}
  - {action: kick, targets: [seat, switch], label: Remove from the hall}
"""

MENU_PY = """
from floorbit.plugins.base import Plugin as Base

class Plugin(Base):
    def run_lookup(self, params):
        return {'message': f"Seat {params['seat']}: ticket ok"}

    def run_kick(self, params):
        return {'message': 'Removed'}
"""


@pytest.fixture
def tickets(tmp_path, app_module):
    registry = app_module.app.extensions["floorbit_plugins"]
    spec = _load(write_plugin(tmp_path, "tickets", MENU_YAML, MENU_PY), "development", registry.version)
    assert spec.error == ""
    registry.specs[spec.id] = spec
    yield spec
    registry.specs.pop(spec.id, None)


@pytest.mark.parametrize("menu, error", [
    ([{"action": "nope", "targets": "seat"}], "unknown action"),
    ([{"action": "x", "targets": "hall"}], "targets must be"),
    ([{"action": "x", "targets": "switch"}], "needs a switch parameter"),
    ([{"action": "x", "targets": "seat", "label": ""}], "label is 1 to 60"),
])
def test_bad_menu_entries_are_refused(menu, error):
    manifest = {"id": "ok-plugin", "uses": ["actions", "context_menu"],
                "actions": [{"id": "x", "params": [{"key": "seat", "type": "string"}]}], "context_menu": menu}
    assert error in validate(manifest)
    assert '"context_menu" is not under uses' in validate({**manifest, "uses": ["actions"]})


def test_the_menu_lists_what_the_account_may_run(client, app_module, tickets):
    assert client.get("/api/plugins/menu").get_json()["entries"] == []   # switched off
    turn_on(client, "tickets")
    entries = client.get("/api/plugins/menu").get_json()["entries"]
    assert [(e["label"], e["targets"], e["danger"]) for e in entries] == [
        ("Look up ticket", ["seat"], False), ("Remove from the hall", ["seat", "switch"], True)]
    assert entries[0]["url"] == "/api/plugins/tickets/actions/lookup"
    assert client.post(entries[0]["url"], json={"seat": "A-1"}).get_json()["message"] == "Seat A-1: ticket ok"

    app_module.app.extensions["auth"].users.add("ed", TEST_PASSWORD, role="editor")
    editor = app_module.app.test_client()
    editor.post("/login", data={"username": "ed", "password": TEST_PASSWORD})
    assert [e["label"] for e in editor.get("/api/plugins/menu").get_json()["entries"]] == ["Look up ticket"]
    anon = app_module.app.test_client()
    assert anon.get("/api/plugins/menu").get_json()["entries"] == []
