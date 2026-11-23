"""Which seats each switch serves (issue #948, floorbit/switch_areas.py)."""
from floorbit import checkin_lookup, switch_areas
from floorbit.store import load_data, save_data

BLOCK = {'id': 'b1', 'name': 'A', 'x': 50, 'y': 50, 'cols': 4, 'rows': 2, 'rotation': 0,
         'row_gaps': [{'after': 1, 'size': 2}]}         # an aisle between the two rows


def _hall(switches, cables=()):
    data = load_data()
    data['seat_blocks'] = [dict(BLOCK)]
    data['inventory'] = [{'id': f'id-{n}', 'name': n, 'role': 'switch', **pos} for n, pos in switches.items()]
    data['cables'] = [{'id': f'c{i}', 'switch': sw, 'port': f'Gi1/0/{i}', 'seat': seat}
                      for i, (sw, seat) in enumerate(cables, 1)]
    save_data(data)
    return data


def _by_name(client):
    return {s['name']: s for s in client.get('/api/switch-areas').get_json()['switches']}


def test_a_switch_in_the_aisle_serves_the_block_and_one_outside_is_a_todo(client):
    # The aisle is the middle of the block: x 50 %, y 50 %. 30 % to the right is outside.
    _hall({'sw-in': {'x': 50, 'y': 50}, 'sw-out': {'x': 80, 'y': 50}, 'sw-nowhere': {}})
    found = _by_name(client)
    assert found['sw-in']['how'] == 'plan' and found['sw-in']['serves']['blocks'] == ['b1']
    assert found['sw-out']['todo'] and found['sw-nowhere']['todo']
    seats = switch_areas.seat_names.hall_rows(load_data())[0]['seats']
    assert checkin_lookup._switches_of(seats, load_data()) == ['sw-in']


def test_learned_seats_suggest_their_row_and_a_pin_wins(client):
    data = _hall({'sw-1': {}}, cables=[('sw-1', s) for s in ('A-1', 'A-2', 'A-3', 'A-4', 'A-5')])
    rows = switch_areas.seat_names.hall_rows(data)
    sw = _by_name(client)['sw-1']
    assert sw['how'] == 'learned' and len(sw['learned']) == 5
    full = next(r for r in rows if set(r['seats']) <= {'A-1', 'A-2', 'A-3', 'A-4', 'A-5'})
    assert [r['id'] for r in sw['suggest']] == [full['id']]
    r = client.put('/api/switch-areas/sw-1', json={'rows': [full['id']]})
    assert r.status_code == 200
    sw = _by_name(client)['sw-1']
    assert sw['how'] == 'manual' and sw['serves']['rows'] == [full['id']] and sw['suggest'] == []
    # The fifth seat is in the other row: shown, never dropped or moved silently.
    other = next(s for s in ('A-1', 'A-2', 'A-3', 'A-4', 'A-5') if s not in full['seats'])
    assert sw['drift'] == [{'kind': 'learned_outside_pin', 'seats': [other]}]
    assert client.put('/api/switch-areas/sw-1', json={}).get_json() == {
        'blocks': [], 'rows': [], 'seats': [], 'exclude': False}
    assert _by_name(client)['sw-1']['how'] == 'learned'


def test_learned_seats_in_another_block_than_drawn_are_drift(client):
    _hall({'sw-in': {'x': 50, 'y': 50}}, cables=[('sw-in', 'B-1')])
    data = load_data()
    data['seat_blocks'].append({**BLOCK, 'id': 'b2', 'name': 'B', 'x': 10, 'y': 10})
    save_data(data)
    sw = _by_name(client)['sw-in']
    assert sw['drift'] == [{'kind': 'learned_outside_plan', 'seats': ['B-1']}]


def test_bad_pins_are_refused(client, kiosk_client):
    _hall({'sw-1': {}})
    assert client.put('/api/switch-areas/nope', json={'rows': []}).status_code == 400
    assert client.put('/api/switch-areas/sw-1', json={'rows': ['b9:1']}).status_code == 400
    assert client.put('/api/switch-areas/sw-1', json={'seats': 'A-1'}).status_code == 400
    assert client.put('/api/switch-areas/sw-1', json={'seats': ['a-1'], 'exclude': True}).get_json()['seats'] == ['A-1']
    assert kiosk_client.put('/api/switch-areas/sw-1', json={}).status_code == 403
