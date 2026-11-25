"""The inventory list's Uplink, Last 24 h and Agent columns (issue #981)."""
from floorbit import inventory_columns as cols
from floorbit import links

NOW = 1_800_000_000.0
HOUR = 3600


def test_last_day_counts_seconds_down_per_hour():
    events = [(NOW - 3 * HOUR, 1, 'sw-a-01', 'offline'), (NOW - 3 * HOUR + 600, 1, 'sw-a-01', 'online'),
              (NOW - 30 * 60, 2, 'SW-B-01', 'offline')]
    out = cols.last_day(events, {'sw-a-01': 'online', 'sw-b-01': 'offline', 'sw-c-01': 'online'}, now=NOW)
    assert len(out['sw-a-01']) == 24
    assert sum(out['sw-a-01']) == 600 and out['sw-a-01'][21] == 600
    # Still down now: the last half hour counts, names are matched in lower case.
    assert out['sw-b-01'][-1] == 1800 and sum(out['sw-b-01']) == 1800
    # No change in the window: the device was in its current state all day.
    assert out['sw-c-01'] == [0] * 24


def test_a_device_down_all_day_and_one_the_monitor_never_saw():
    out = cols.last_day([], {'sw-a-01': 'offline', 'fw-01': None}, now=NOW)
    assert out['sw-a-01'] == [3600] * 24
    assert 'fw-01' not in out


def test_uplinks_point_towards_the_core(monkeypatch):
    def link(a, b, speed, speed_bps=None, state='up'):
        return {'a': a, 'b': b, 'a_port': f'{a}-p', 'b_port': f'{b}-p', 'speed': speed, 'speed_bps': speed_bps,
                'state': state, 'issue': ''}
    topo = {'nodes': [{'name': 'core-01', 'role': 'router'}, {'name': 'dist-01', 'role': 'switch'},
                      {'name': 'sw-a-01', 'role': 'switch'}],
            'links': [link('core-01', 'dist-01', 40, 40e9), link('sw-a-01', 'dist-01', 10, 1e9),
                      link('sw-a-01', 'dist-01', 1, 1e9, state='down')],
            'uplinks': []}
    monkeypatch.setattr(links, 'topology', lambda now=None, suggest=False: topo)
    out = cols.uplinks({})
    assert 'core-01' not in out
    assert out['dist-01']['peer'] == 'core-01' and out['dist-01']['port'] == 'dist-01-p'
    # Two links up: the faster planned one is the uplink, running at 1G of 10G.
    assert out['sw-a-01'] == {'port': 'sw-a-01-p', 'peer': 'dist-01', 'peer_port': 'dist-01-p', 'speed_bps': 1e9,
                              'planned_gbps': 10, 'state': 'up', 'issue': ''}


def test_the_list_call_carries_the_columns(client):
    client.post('/api/inventory', json={'name': 'sw-a-01', 'role': 'switch'})
    row = client.get('/api/inventory').get_json()['devices'][0]
    assert {'uplink', 'last_day', 'agent'} <= set(row)
    assert row['agent'] == ''


def test_a_broken_column_leaves_the_list_working(client, monkeypatch):
    client.post('/api/inventory', json={'name': 'sw-a-01', 'role': 'switch'})
    monkeypatch.setattr(cols, 'uplinks', lambda data: 1 / 0)
    resp = client.get('/api/inventory')
    assert resp.status_code == 200 and resp.get_json()['devices'][0]['uplink'] is None
