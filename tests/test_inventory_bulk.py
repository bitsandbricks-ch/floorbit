"""Acting on several inventory devices at once (issue #980)."""
from floorbit import audit, inventory, inventory_scope


def _devices(client, *names):
    return [client.post('/api/inventory', json={'name': n, 'role': 'switch'}).get_json()['id'] for n in names]


def _rows(client):
    return {d['name']: d for d in client.get('/api/inventory?hidden=1').get_json()['devices']}


def test_tags_go_on_and_off_together_and_each_change_is_audited(client):
    a, b = _devices(client, 'sw-a-01', 'sw-a-02')
    tag = client.post('/api/inventory/tags', json={'name': 'Stage'}).get_json()['id']
    client.patch(f'/api/inventory/{a}', json={'tags': [tag]})
    resp = client.post('/api/inventory/bulk', json={'ids': [a, b], 'action': 'tag-add', 'tag': tag})
    # The one that had it already is left alone.
    assert resp.status_code == 200 and resp.get_json() == {'changed': [b], 'unchanged': 1}
    assert [r['tags'] for r in _rows(client).values()] == [[tag], [tag]]
    entries = [e for e in audit.read(20)[0] if e['action'] == 'Changed device' and e.get('fields') == ['tags']]
    assert entries[0]['target'] == 'sw-a-02'
    client.post('/api/inventory/bulk', json={'ids': [a, b], 'action': 'tag-remove', 'tag': tag})
    assert [r['tags'] for r in _rows(client).values()] == [[], []]


def test_move_to_a_group_and_out_again(client):
    a, b = _devices(client, 'sw-a-01', 'sw-a-02')
    group = client.post('/api/inventory/groups', json={'name': 'Hall B'}).get_json()['id']
    client.post('/api/inventory/bulk', json={'ids': [a, b], 'action': 'group', 'group_id': group})
    assert {r['group_id'] for r in _rows(client).values()} == {group}
    client.post('/api/inventory/bulk', json={'ids': [a, b], 'action': 'group', 'group_id': None})
    assert {r['group_id'] for r in _rows(client).values()} == {None}


def test_hide_and_show(client):
    a, b = _devices(client, 'sw-a-01', 'sw-a-02')
    client.post('/api/inventory/bulk', json={'ids': [a, b], 'action': 'hide'})
    assert client.get('/api/inventory').get_json()['devices'] == []
    client.post('/api/inventory/bulk', json={'ids': [a], 'action': 'show'})
    assert [d['name'] for d in client.get('/api/inventory').get_json()['devices']] == ['sw-a-01']


def test_bad_requests_change_nothing(client):
    a, = _devices(client, 'sw-a-01')
    assert client.post('/api/inventory/bulk', json={'ids': [a], 'action': 'delete'}).status_code == 400
    for body in ({'ids': [], 'action': 'hide'}, {'ids': [a], 'action': 'tag-add', 'tag': 'nope'},
                 {'ids': [a], 'action': 'group', 'group_id': 'nope'}):
        assert client.post('/api/inventory/bulk', json=body).status_code == 400
    resp = client.post('/api/inventory/bulk', json={'ids': [a, 'gone'], 'action': 'hide'})
    assert resp.status_code == 404 and resp.get_json()['missing'] == ['gone']
    assert not _rows(client)['sw-a-01']['hidden']


def test_viewers_cannot(client, kiosk_client):
    a, = _devices(client, 'sw-a-01')
    assert kiosk_client.post('/api/inventory/bulk', json={'ids': [a], 'action': 'hide'}).status_code in (401, 403)


def test_a_device_the_change_cannot_take_stops_it_all(client, monkeypatch):
    """The inventory's own message comes back, and no device is changed."""
    a, b = _devices(client, 'sw-a-01', 'sw-a-02')
    tag = client.post('/api/inventory/tags', json={'name': 'Stage'}).get_json()['id']
    update = inventory.update

    def refuse_second(data, device_id, patch):
        if device_id == b:
            raise inventory_scope.ScopeError('At most 20 tags.')
        return update(data, device_id, patch)

    monkeypatch.setattr(inventory, 'update', refuse_second)
    resp = client.post('/api/inventory/bulk', json={'ids': [a, b], 'action': 'tag-add', 'tag': tag})
    assert resp.status_code == 400 and resp.get_json() == {'error': 'At most 20 tags.'}
    assert [r['tags'] for r in _rows(client).values()] == [[], []]


def test_bad_device_input_answers_with_the_inventory_message(client):
    resp = client.post('/api/inventory', json={'name': '', 'role': 'switch'})
    assert resp.status_code == 400 and resp.get_json() == {'error': 'A device needs a name'}
    a, = _devices(client, 'sw-a-01')
    resp = client.patch(f'/api/inventory/{a}', json={'mgmt_ip': 'not-an-ip'})
    assert resp.status_code == 400 and 'is not an IP address' in resp.get_json()['error']
