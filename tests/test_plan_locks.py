"""Locked items on the floor plan (floorbit/plan_locks.py)."""


def test_items_lock_and_unlock_per_hall(client):
    hall = client.get('/api/plan-locks').get_json()['hall_id']
    wall = {'kind': 'mark', 'id': 'w1'}
    res = client.put('/api/plan-locks', json={'hall_id': hall, 'items': [wall, wall, {'kind': 'block', 'id': 'b1'}],
                                              'locked': True})
    assert res.status_code == 200, res.get_json()
    assert res.get_json()['locks'] == [wall, {'kind': 'block', 'id': 'b1'}]
    assert client.get(f'/api/plan-locks?hall={hall}').get_json()['locks'] == [wall, {'kind': 'block', 'id': 'b1'}]
    out = client.put('/api/plan-locks', json={'hall_id': hall, 'items': [wall], 'locked': False}).get_json()
    assert out['locks'] == [{'kind': 'block', 'id': 'b1'}]


def test_bad_locks_are_refused(client):
    for body in ({'items': [], 'locked': True}, {'items': [{'kind': 'cable', 'id': 'x'}], 'locked': True},
                 {'items': [{'kind': 'mark', 'id': ''}], 'locked': True}, {'items': [{'kind': 'mark', 'id': 'x'}]},
                 {'hall_id': 'nope', 'items': [{'kind': 'mark', 'id': 'x'}], 'locked': True}):
        assert client.put('/api/plan-locks', json=body).status_code == 400, body
