"""Inventory > Discovery: devices and links LLDP/CDP found that the inventory lacks (#891, #968)."""
from floorbit import links


def _topology(monkeypatch, neighbours, suggestions=()):
    monkeypatch.setattr(links, 'topology', lambda now=None, suggest=True: {
        'nodes': [{'name': n} for n in neighbours], 'suggestions': list(suggestions)})
    monkeypatch.setattr(links.reader, 'cached_neighbours', lambda switch: neighbours.get(switch, []))


def test_lists_unknown_neighbours_and_unplanned_links(client, monkeypatch):
    client.post('/api/inventory', json={'name': 'dist-02', 'role': 'switch'})
    client.post('/api/inventory', json={'name': 'sw-b-01', 'role': 'switch', 'mgmt_ip': '192.0.2.21'})
    _topology(monkeypatch, {
        'dist-02': [{'port': 'Te1/1/4', 'remote': 'sw-c-02.example.com', 'remote_port': 'Te1/1/1', 'protocol': 'lldp'},
                    {'port': 'Te1/1/1', 'remote': 'sw-b-01', 'remote_port': 'Te1/1/1', 'protocol': 'lldp'}],
        'sw-b-01': [{'port': 'Gi1/0/48', 'remote': 'ap-h2-07', 'remote_port': 'eth0', 'protocol': 'cdp'},
                    {'port': 'Gi1/0/47', 'remote': '192.0.2.21', 'remote_port': 'x', 'protocol': 'cdp'}],
    }, [{'a': 'dist-02', 'a_port': 'Te1/1/1', 'b': 'sw-b-01', 'b_port': 'Te1/1/1', 'protocol': 'lldp', 'speed': 10}])
    body = client.get('/api/inventory/found').get_json()
    # A known device, by name or by address, isn't "found".
    assert [d['name'] for d in body['devices']] == ['ap-h2-07', 'sw-c-02.example.com']
    assert body['devices'][1]['seen_by'] == [{'switch': 'dist-02', 'port': 'Te1/1/4', 'remote_port': 'Te1/1/1'}]
    assert body['links'][0]['key'] == 'dist-02|te1/1/1 -- sw-b-01|te1/1/1'


def test_ignoring_hides_a_row_and_can_be_taken_back(client, monkeypatch):
    _topology(monkeypatch, {'dist-02': [{'port': 'Te1/1/4', 'remote': 'sw-c-02', 'remote_port': 'Te1/1/1'}]},
              [{'a': 'a', 'a_port': '1', 'b': 'b', 'b_port': '2', 'protocol': 'lldp', 'speed': None}])
    assert client.post('/api/inventory/found/ignore', json={'kind': 'device', 'key': 'SW-C-02'}).status_code == 200
    assert client.post('/api/inventory/found/ignore', json={'kind': 'link', 'key': 'a|1 -- b|2'}).status_code == 200
    body = client.get('/api/inventory/found').get_json()
    assert body['devices'] == [] and body['links'] == []
    assert body['ignored'] == {'devices': 1, 'links': 1}
    client.post('/api/inventory/found/ignore', json={'kind': 'device', 'key': 'sw-c-02', 'ignored': False})
    assert [d['name'] for d in client.get('/api/inventory/found').get_json()['devices']] == ['sw-c-02']


def test_bad_ignore_and_viewers(client, kiosk_client):
    assert client.post('/api/inventory/found/ignore', json={'kind': 'seat', 'key': 'x'}).status_code == 400
    assert client.post('/api/inventory/found/ignore', json={'kind': 'link'}).status_code == 400
    assert kiosk_client.post('/api/inventory/found/ignore', json={'kind': 'link', 'key': 'x'}).status_code in (401, 403)
