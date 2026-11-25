"""Dashboards as files for another Floorbit, and the ones plugins ship (#938)."""
import json

import pytest
from test_plugin_panels import turn_on
from test_plugins import write_plugin

from floorbit.plugins import _load, validate

BOARD = {"name": "Power desk", "fit": True, "range": "6h", "sections": [{"panels": [
    {"x": 0, "y": 0, "w": 12, "h": 6,
     "node": {"pane": {"kind": "tile", "tile": "floorbit/w/switches", "type": "stat"}}},
    {"x": 12, "y": 0, "w": 12, "h": 6, "node": {"pane": {"kind": "tile", "tile": "shelly/w/power", "title": "Load"}}},
    {"x": 0, "y": 6, "w": 24, "h": 6, "node": {"pane": {"kind": "text", "text": "Doors open at 18:00", "size": "m",
                                                        "align": "center"}}},
]}]}


def test_export_then_import_makes_a_new_dashboard(client):
    assert client.put("/api/dashboards/power-desk", json={**BOARD, "public": True}).status_code == 200
    r = client.get("/api/dashboards/power-desk/export")
    assert r.status_code == 200
    disposition = r.headers["Content-Disposition"]
    assert "attachment" in disposition and "power-desk.dashboard.json" in disposition
    file = json.loads(r.data)
    assert file["floorbit_dashboard"] == 1 and file["plugins"] == ["shelly"]
    # The layout only: no id, who saved it, when, or whether it is public here.
    assert not {"id", "by", "updated_at", "public"} & set(file)
    r = client.post("/api/dashboards/import", json=file)
    assert r.status_code == 201, r.get_json()
    body = r.get_json()
    made = body["layout"]
    assert made["id"] == "power-desk-2" and made["name"] == "Power desk" and made["public"] is False
    assert made["range"] == "6h" and made["sections"] == client.get("/api/dashboards/power-desk").get_json()["sections"]
    assert body["missing"] == ["shelly"]   # the screen says which plugin each of its panes needs


def test_a_saved_widget_goes_into_the_file_as_its_own_tile(client):
    w = client.post("/api/widgets", json={"name": "Switches up", "pane": {"kind": "tile", "tile": "floorbit/w/switches",
                                                                         "type": "gauge"}}).get_json()
    board = {"name": "With widget", "sections": [{"panels": [
        {"x": 0, "y": 0, "w": 8, "h": 4, "node": {"pane": {"kind": "widget", "widget": w["id"]}}}]}]}
    assert client.put("/api/dashboards/with-widget", json=board).status_code == 200
    file = client.get("/api/dashboards/with-widget/export").get_json()
    pane = file["sections"][0]["panels"][0]["node"]["pane"]
    assert pane == {"kind": "tile", "tile": "floorbit/w/switches", "type": "gauge", "title": "Switches up"}
    assert "plugins" not in file


@pytest.mark.parametrize("body", [None, {"name": "x"}, {"floorbit_dashboard": 2, **BOARD},
                                  {"floorbit_dashboard": 1, "name": "No sections"}])
def test_only_a_dashboard_file_imports(client, body):
    r = client.post("/api/dashboards/import", json=body)
    assert r.status_code == 400 and "not a Floorbit dashboard file" in r.get_json()["error"]


def test_a_broken_file_is_refused_like_a_broken_dashboard(client):
    bad = {"floorbit_dashboard": 1, **BOARD, "sections": [{"panels": [
        {"x": 0, "y": 0, "w": 30, "h": 6, "node": {"pane": {"kind": "empty"}}}]}]}
    assert client.post("/api/dashboards/import", json=bad).status_code == 400


def test_who_may_export_and_import(client, kiosk_client, anon_client):
    client.put("/api/dashboards/power-desk", json=BOARD)
    file = client.get("/api/dashboards/power-desk/export").get_json()
    assert kiosk_client.post("/api/dashboards/import", json=file).status_code == 403
    assert anon_client.post("/api/dashboards/import", json=file).status_code == 401
    assert anon_client.get("/api/dashboards/power-desk/export").status_code == 401
    assert client.get("/api/dashboards/nope/export").status_code == 404


YAML = """
id: power-box
name: Power box
version: "1.0"
uses: [widgets]
widgets:
  - {id: load, label: Load}
  - {id: circuits, label: Circuits}
dashboards:
  - id: power
    label: Power
    fit: true
    panels:
      - {widget: load, x: 0, y: 0, w: 8, h: 4, type: gauge}
      - {widget: circuits, x: 8, y: 0, w: 16, h: 4, title: Circuits}
"""

PY = """
from floorbit.plugins.base import Plugin as Base

class Plugin(Base):
    def widget_load(self):
        return {'type': 'stat', 'value': 3}

    def widget_circuits(self):
        return {'type': 'list', 'items': []}
"""


@pytest.fixture
def power_box(tmp_path, app_module):
    registry = app_module.app.extensions["floorbit_plugins"]
    spec = _load(write_plugin(tmp_path, "power-box", YAML, PY), "development", registry.version)
    assert spec.error == ""
    registry.specs[spec.id] = spec
    yield spec
    registry.specs.pop(spec.id, None)


def test_a_plugin_that_is_on_lists_its_dashboards(client, power_box):
    ids = lambda: [x["id"] for x in client.get("/api/dashboards").get_json()["layouts"]]   # noqa: E731
    assert "power-box-power" not in ids()   # off
    turn_on(client, "power-box")
    board = next(x for x in client.get("/api/dashboards").get_json()["layouts"] if x["id"] == "power-box-power")
    assert board["builtin"] is True and board["plugin"] == "power-box"
    assert board["name"] == "Power" and board["fit"] is True
    panes = [p["node"]["pane"] for p in board["sections"][0]["panels"]]
    assert panes == [{"kind": "tile", "tile": "power-box/w/load", "type": "gauge"},
                     {"kind": "tile", "tile": "power-box/w/circuits", "title": "Circuits"}]
    # Saved under its id, it is the crew's own version; deleting that brings the plugin's back.
    assert client.put("/api/dashboards/power-box-power", json={**BOARD, "name": "Our power"}).status_code == 200
    mine = next(x for x in client.get("/api/dashboards").get_json()["layouts"] if x["id"] == "power-box-power")
    assert mine["name"] == "Our power" and mine["changed"] is True
    client.delete("/api/dashboards/power-box-power")
    layouts = client.get("/api/dashboards").get_json()["layouts"]
    assert next(x for x in layouts if x["id"] == "power-box-power")["plugin"]


BASE = {"id": "demo-x", "name": "X", "version": "1.0.0", "uses": ["widgets"], "widgets": [{"id": "load"}]}
PANEL = {"widget": "load", "x": 0, "y": 0, "w": 8, "h": 4}


@pytest.mark.parametrize("boards, error", [
    ("power", "a list of up to 5"),
    ([{"id": f"d{n}", "panels": [PANEL]} for n in range(6)], "a list of up to 5"),
    ([{"id": "Bad id", "panels": [PANEL]}], "bad id"),
    ([{"id": "x", "panels": [PANEL]}, {"id": "x", "panels": [PANEL]}], "duplicate"),
    ([{"id": "x", "panels": [PANEL], "script": "alert(1)"}], "unknown key(s) script"),
    ([{"id": "x", "panels": []}], "panels lists the widgets"),
    ([{"id": "x", "panels": [{**PANEL, "widget": "nope"}]}], "only ids from the plugin's own widgets"),
    ([{"id": "x", "panels": [{**PANEL, "html": "<b>"}]}], "unknown key(s) html"),
    ([{"id": "x", "panels": [{**PANEL, "w": 40}]}], "dashboards.x:"),
    ([{"id": "x", "panels": [PANEL, PANEL]}], "overlap"),
    ([{"id": "x", "fit": "yes", "panels": [PANEL]}], "fit is true"),
])
def test_bad_plugin_dashboards_are_refused(boards, error):
    assert error in validate({**BASE, "dashboards": boards})


def test_plugin_dashboards_need_widgets_under_uses():
    assert "not under uses" in validate({**BASE, "uses": ["actions"], "widgets": [],
                                         "dashboards": [{"id": "x", "panels": [PANEL]}]})
