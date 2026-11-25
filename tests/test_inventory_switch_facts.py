"""Seats, uplink load and PoE per switch in the inventory list, for Network > Switches (#902)."""
from types import SimpleNamespace

from floorbit import cables
from floorbit import inventory_columns as cols
from floorbit.store import load_data, save_data
from floorbit.syslog import canonical_port


def _device(client, name):
    return client.post('/api/inventory', json={'name': name, 'role': 'switch'}).get_json()['id']


def test_the_list_carries_seats_load_and_poe(client, monkeypatch):
    sid = _device(client, 'sw-a-01')
    monkeypatch.setattr(cols, 'uplinks', lambda data: {'sw-a-01': {
        'port': 'Te1/1/1', 'peer': 'dist-01', 'peer_port': 'Te1/0/4', 'speed_bps': 10e9, 'planned_gbps': 10,
        'state': 'up', 'issue': ''}})
    # Two seats from the mapping, one more from a port description; the same seat twice counts once.
    monkeypatch.setattr(cables, 'port_seats', lambda data: {('sw-a-01', 'Gi1/0/1'): 'A1', ('sw-a-01', 'Gi1/0/2'): 'A2'})
    watch = SimpleNamespace(port_seats={('sw-a-01', 'Gi1/0/2'): 'A2', ('sw-a-01', 'Gi1/0/3'): 'A3'},
                            port_reads={('sw-a-01', canonical_port('Te1/1/1')): {'state': 'up', 'utilization': 0.84},
                                        ('sw-a-01', canonical_port('Gi1/0/1')): {'state': 'up', 'utilization': None}})
    monkeypatch.setitem(client.application.extensions, 'floorbit_attention', watch)
    data = load_data()
    data['inventory_discovered'] = {sid: {'poe': {'budget_w': 740.0, 'used_w': 210.0}}}
    save_data(data)
    row = client.get('/api/inventory').get_json()['devices'][0]
    assert row['seats'] == 3
    assert row['uplink']['load'] == 0.84
    assert row['poe'] == {'budget_w': 740.0, 'used_w': 210.0}
    assert row['ports'] == {'up': 2, 'total': 2}


def test_a_switch_nothing_read_yet(client):
    _device(client, 'sw-b-01')
    row = client.get('/api/inventory').get_json()['devices'][0]
    assert row['seats'] == 0 and row['poe'] is None


def test_the_switches_page_is_listed(client, built):
    assert client.get('/switches').status_code == 200
    pages = client.get('/api/pages').get_json()
    ids = [p['id'] for p in (pages.get('pages') if isinstance(pages, dict) else pages)]
    assert 'switches' in ids
