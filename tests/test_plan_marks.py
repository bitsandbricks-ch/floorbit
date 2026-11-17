"""Text, walls, zones and icons on the floor plan (floorbit/plan_marks.py), and the example hall."""
import pytest

from floorbit import plan_marks
from floorbit.store import load_data


def test_marks_are_added_changed_and_removed(client):
    text = client.post("/api/plan-marks", json={"kind": "text", "x": 50, "y": 8, "text": " Main hall ", "size": "l"})
    assert text.status_code == 201
    mark = text.get_json()
    assert mark["text"] == "Main hall" and mark["rotation"] == 0 and mark["hall_id"]
    moved = client.put(f"/api/plan-marks/{mark['id']}", json={"x": 40, "rotation": 90}).get_json()
    assert (moved["x"], moved["rotation"], moved["text"]) == (40, 90, "Main hall")
    body = client.get("/api/plan-marks").get_json()
    assert [m["id"] for m in body["marks"]] == [mark["id"]] and "exit" in body["icons"]
    assert client.delete(f"/api/plan-marks/{mark['id']}").status_code == 200
    assert client.delete(f"/api/plan-marks/{mark['id']}").status_code == 404


@pytest.mark.parametrize("bad", [
    {"kind": "sofa", "x": 1, "y": 1},
    {"kind": "text", "x": 1, "y": 1, "text": ""},
    {"kind": "text", "x": 20000, "y": 1, "text": "Too far"},
    {"kind": "text", "x": "nan", "y": 1, "text": "Not a number"},
    {"kind": "icon", "x": 1, "y": 1, "icon": "unicorn"},
    {"kind": "icon", "x": 1, "y": 1},
    {"kind": "wall", "x": 1, "y": 1, "x2": 1, "y2": 1},
    {"kind": "zone", "x": 1, "y": 1, "w": 0, "h": 5},
    {"kind": "text", "x": 1, "y": 1, "text": "Tilted", "rotation": 45},
    {"kind": "icon", "x": 1, "y": 1, "icon": "wc", "scale": 20},
    {"kind": "icon", "x": 1, "y": 1, "icon": "wc", "scale": "big"},
])
def test_bad_marks_are_refused(client, bad):
    assert client.post("/api/plan-marks", json=bad).status_code == 400


def test_labels_and_icons_keep_a_scale(client):
    icon = client.post("/api/plan-marks", json={"kind": "icon", "x": 5, "y": 5, "icon": "wc"}).get_json()
    assert "scale" not in icon
    grown = client.put(f"/api/plan-marks/{icon['id']}", json={"scale": 1.666}).get_json()
    assert grown["scale"] == 1.67
    moved = client.put(f"/api/plan-marks/{icon['id']}", json={"x": 9}).get_json()
    assert moved["scale"] == 1.67
    back = client.put(f"/api/plan-marks/{icon['id']}", json={"scale": 1}).get_json()
    assert "scale" not in back


def test_only_editors_draw(app_module, client):
    from tests.test_rbac import sign_in_as
    viewer = sign_in_as(app_module, "vi9", "viewer")
    assert viewer.get("/api/plan-marks").status_code == 200
    assert viewer.post("/api/plan-marks", json={"kind": "icon", "x": 5, "y": 5, "icon": "wc"}).status_code == 403


def test_marks_go_with_backups_and_templates(client):
    client.post("/api/plan-marks", json={"kind": "wall", "x": 4, "y": 4, "x2": 96, "y2": 4, "style": "dashed"})
    backup = client.get("/api/settings/backup").get_json()
    assert backup["layout"]["plan_marks"][0]["style"] == "dashed"
    from floorbit import layout_templates
    layout = layout_templates.snapshot(load_data())
    cleaned, dropped = layout_templates.clean_layout(layout)
    assert cleaned["plan_marks"][0]["kind"] == "wall" and "plan_marks" not in dropped


def test_the_example_hall_carries_on_the_rows(client):
    client.post("/api/seat-blocks", json={"name": "", "cols": 2, "rows": 2, "x": 10, "y": 10, "naming": "rows"})
    resp = client.post("/api/halls/example")
    assert resp.status_code == 201
    hall = resp.get_json()
    data = load_data()
    blocks = [b for b in data["seat_blocks"] if b.get("hall_id") == hall["id"]]
    assert blocks[0]["row_start"] == "C" and blocks[-1]["rotation"] == 90
    assert len(plan_marks.all_marks(data, hall["id"])) > 10
    # Drawn on the Seats view with its walls and icons.
    from floorbit.blueprints.screen import plan
    drawing, _ = plan(data, hall_id=hall["id"])
    kinds = {m["kind"] for m in drawing["marks"]}
    assert kinds == {"text", "icon", "wall", "zone"} and "exit" in drawing["icons"]
    assert client.post("/api/halls/example").get_json()["name"] == "Example hall 2"


def test_marks_go_with_their_hall(client):
    hall = client.post("/api/halls", json={"name": "Side hall"}).get_json()
    made = client.post("/api/plan-marks", json={"kind": "text", "text": "Bar", "x": 10, "y": 10, "hall_id": hall["id"]})
    assert made.status_code == 201 and len(plan_marks.all_marks(load_data(), hall["id"])) == 1
    assert client.delete(f"/api/halls/{hall['id']}").status_code == 200
    assert plan_marks.all_marks(load_data()) == []


def test_marks_sit_on_layers_and_crew_layers_stay_off_attendee_pages(client):
    from floorbit.blueprints.screen import plan
    client.post("/api/seat-blocks", json={"name": "A", "cols": 2, "rows": 1, "x": 50, "y": 50})
    base = {"kind": "icon", "x": 20, "y": 20}
    assert client.post("/api/plan-marks", json={**base, "icon": "extinguisher", "layer": "safety"}).status_code == 201
    assert client.post("/api/plan-marks", json={**base, "icon": "server", "layer": "services"}).status_code == 201
    assert client.post("/api/plan-marks", json={**base, "icon": "wc"}).get_json()["layer"] == "overview"
    assert client.post("/api/plan-marks", json={**base, "icon": "wc", "layer": "attic"}).status_code == 400
    crew, _ = plan(load_data())
    public, _ = plan(load_data(), public=True)
    assert {m["layer"] for m in crew["marks"]} == {"overview", "safety", "services"}
    assert {m["layer"] for m in public["marks"]} == {"overview", "safety"} and "server" not in public["icons"]


def test_a_wall_bends_round_corners(client):
    # Mike: walls with bends, like cables. The bends travel with the wall into the plan.
    client.post('/api/seat-blocks', json={'name': 'A', 'cols': 4, 'rows': 1, 'x': 50, 'y': 50})
    body = {'kind': 'wall', 'x': 10, 'y': 10, 'x2': 30, 'y2': 30, 'points': [[30, 10], [30, 10]]}
    res = client.post('/api/plan-marks', json=body)
    assert res.status_code == 201, res.get_json()
    mark = res.get_json()
    assert mark['points'] == [[30, 10]]      # the same bend twice is one
    wall = next(m for m in client.get('/api/plan').get_json()['drawing']['marks'] if m['kind'] == 'wall')
    assert wall['points'] == [[480, 100]] and wall['x2'] == 480
    # A wall back to where it started is fine when it bends on the way.
    loop = {**body, 'x2': 10, 'y2': 10, 'points': [[30, 10], [30, 30]]}
    assert client.post('/api/plan-marks', json=loop).status_code == 201
    for bad in ([[1]], 'x', [[1, 2]] * 51, [['a', 1]]):
        assert client.post('/api/plan-marks', json={**body, 'points': bad}).status_code == 400, bad
    # Straight again: no points kept.
    res = client.put(f"/api/plan-marks/{mark['id']}", json={'points': []})
    assert 'points' not in res.get_json()
