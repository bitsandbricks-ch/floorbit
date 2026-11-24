"""Plan presets (floorbit/plan_presets.py): several items kept together, placed again."""

ZONE = {'kind': 'mark', 'body': {'kind': 'zone', 'x': 10, 'y': 10, 'w': 20, 'h': 15, 'label': 'Admin', 'id': 'm1',
                                 'hall_id': 'main', 'locked': True}}
BLOCK = {'kind': 'block', 'body': {'name': 'A', 'x': 15, 'y': 15, 'naming': 'block',
                                   'rows': [{'seats': 4}, {'seats': 6, 'shape': 'arc', 'bend': 40, 'gap': 1}]}}


def test_a_zone_with_its_block_is_kept_as_one_preset(client):
    made = client.post('/api/plan-presets', json={'name': 'Admin zone', 'items': [ZONE, BLOCK]})
    assert made.status_code == 201, made.get_json()
    preset = made.get_json()
    assert preset['counts'] == {'mark': 1, 'block': 1}
    # What ties an item to one plan stays behind.
    assert not {'id', 'hall_id', 'locked'} & set(preset['items'][0]['body'])
    listed = client.get('/api/plan-presets').get_json()['presets']
    assert [p['name'] for p in listed] == ['Admin zone'] and listed[0]['items'][1]['body']['rows'][1]['shape'] == 'arc'
    # Placing posts each item again, like a paste.
    block = client.post('/api/seat-blocks', json={**listed[0]['items'][1]['body'], 'x': 60, 'y': 60})
    assert block.status_code == 201, block.get_json()


def test_presets_are_checked(client):
    def save(**body):
        return client.post('/api/plan-presets', json={'name': 'X', 'items': [ZONE], **body})
    assert save(name='').status_code == 400
    assert save(items=[]).status_code == 400
    assert save(items=[{'kind': 'switch', 'body': {'name': 'sw1'}}]).status_code == 400
    assert save(items=[{'kind': 'cable', 'body': {}}]).status_code == 400
    assert save().status_code == 201
    dup = save(name='x')
    assert dup.status_code == 400 and 'exists' in dup.get_json()['error']


def test_a_preset_is_deleted(client):
    preset = client.post('/api/plan-presets', json={'name': 'Gone', 'items': [BLOCK]}).get_json()
    assert client.delete(f"/api/plan-presets/{preset['id']}").status_code == 200
    assert client.get('/api/plan-presets').get_json()['presets'] == []
    assert client.delete(f"/api/plan-presets/{preset['id']}").status_code == 404
