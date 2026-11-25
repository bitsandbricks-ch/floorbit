"""Walkways on the floor plan (floorbit/plan_marks.py, #1564): drawn like a wall, with a width in seats."""
import pytest


def test_a_walkway_has_a_width_and_reaches_the_plan(client):
    client.post('/api/seat-blocks', json={'name': 'A', 'cols': 4, 'rows': 1, 'x': 50, 'y': 50})
    res = client.post('/api/plan-marks', json={'kind': 'walkway', 'x': 10, 'y': 40, 'x2': 90, 'y2': 40})
    assert res.status_code == 201, res.get_json()
    mark = res.get_json()
    assert mark['width'] == 2 and 'style' not in mark and mark['layer'] == 'overview'
    wider = client.put(f"/api/plan-marks/{mark['id']}", json={'width': 3.5}).get_json()
    assert wider['width'] == 3.5
    drawn = next(m for m in client.get('/api/plan').get_json()['drawing']['marks'] if m['kind'] == 'walkway')
    assert drawn['width'] == 3.5 and drawn['x2'] > drawn['x']


@pytest.mark.parametrize('bad', [
    {'kind': 'walkway', 'x': 1, 'y': 1, 'x2': 1, 'y2': 1},
    {'kind': 'walkway', 'x': 1, 'y': 1, 'x2': 9, 'y2': 1, 'width': 0},
    {'kind': 'walkway', 'x': 1, 'y': 1, 'x2': 9, 'y2': 1, 'width': 21},
    {'kind': 'walkway', 'x': 1, 'y': 1, 'x2': 9, 'y2': 1, 'width': 'nan'},
])
def test_bad_walkways_are_refused(client, bad):
    assert client.post('/api/plan-marks', json=bad).status_code == 400
