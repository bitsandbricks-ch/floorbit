"""Settings > Floor plan: what new seat blocks in the editor start with (floorbit/settings.py)."""


def test_the_editor_gets_the_floor_plan_defaults(client):
    assert client.get("/api/config").get_json()["floorplan_defaults"] == {
        "naming": "rows", "row_labels": "start", "reverse_numbers": False, "block_gap": 3}
    res = client.put("/api/settings", json={"floorplan.naming": "block", "floorplan.row_labels": "both",
                                           "floorplan.reverse_numbers": True, "floorplan.block_gap": 5})
    assert res.status_code == 200, res.get_json()
    assert client.get("/api/config").get_json()["floorplan_defaults"] == {
        "naming": "block", "row_labels": "both", "reverse_numbers": True, "block_gap": 5}


def test_a_default_outside_the_choices_is_refused(client):
    assert client.put("/api/settings", json={"floorplan.row_labels": "middle"}).status_code == 400
