"""Swapping a dead switch for a spare (issue #1060): the switch keeps its name and IP, takes the
spare's hardware, and the dead box goes on the shelf as failed."""
import pytest

from floorbit import inventory, switch_swap
from floorbit.store import load_data, save_data
from floorbit.switch_swap import SwapError


def _hall():
    data = {}
    sw = inventory.create(data, {'name': 'sw-a1', 'model': 'C2960X', 'serial': 'OLD1', 'mgmt_ip': '192.0.2.11'})
    same = inventory.create(data, {'name': 'spare-1', 'model': 'C2960X', 'serial': 'NEW1', 'status': 'inventory'})
    other = inventory.create(data, {'name': 'spare-0', 'model': 'C3850', 'serial': 'NEW0', 'status': 'inventory'})
    inventory.create(data, {'name': 'sw-a2', 'model': 'C2960X', 'serial': 'X2', 'status': 'active'})
    inventory.create(data, {'name': 'fw-1', 'role': 'firewall', 'serial': 'F1', 'status': 'inventory'})
    return data, sw, same, other


def test_the_plan_lists_spares_of_the_same_kind_same_model_first():
    data, sw, _, _ = _hall()
    mapping = {'A-2': {'switch': 'SW-A1', 'port': 'Gi1/0/10'}, 'A-1': {'switch': 'sw-a1', 'port': 'Gi1/0/2'},
               'B-1': {'switch': 'sw-b1', 'port': 'Gi1/0/1'}}
    p = switch_swap.plan(data, sw['id'], {'status': 'down', 'since': 5}, mapping=mapping)
    assert [s['name'] for s in p['spares']] == ['spare-1', 'spare-0']   # no active switch, no firewall
    assert p['spares'][0]['same_model'] and not p['spares'][1]['same_model']
    assert p['switch']['status'] == 'down' and p['switch']['mgmt_ip'] == '192.0.2.11'
    assert p['seat_ports'] == [{'port': 'Gi1/0/2', 'seat': 'A-1'}, {'port': 'Gi1/0/10', 'seat': 'A-2'}]
    assert p['config'] is None and p['config_readable'] is False   # no configs.read, no config link
    with pytest.raises(SwapError) as err:
        switch_swap.plan(data, 'nope')
    assert err.value.status == 404


def test_a_swap_with_a_spare_trades_the_hardware_and_keeps_the_dead_box():
    data, sw, same, _ = _hall()
    entry = switch_swap.swap(data, sw['id'], {'spare_id': same['id']}, 'Mike', now=1_700_000_000)
    assert (sw['name'], sw['mgmt_ip'], sw['serial'], sw['model']) == ('sw-a1', '192.0.2.11', 'NEW1', 'C2960X')
    assert (same['serial'], same['status']) == ('OLD1', 'failed')
    assert same['notes'].startswith('Pulled from sw-a1 on ')
    assert entry['old_serial'] == 'OLD1' and entry['new_serial'] == 'NEW1' and entry['spare_id'] == same['id']
    assert sw['swaps'] == [entry]
    # The used spare is off the shelf now: a second swap with it is refused.
    with pytest.raises(SwapError, match='not on the shelf'):
        switch_swap.swap(data, sw['id'], {'spare_id': same['id']}, 'Mike')


def test_a_swap_with_a_typed_serial_and_the_mistakes_it_refuses():
    data, sw, _, _ = _hall()
    with pytest.raises(SwapError, match='serial number'):
        switch_swap.swap(data, sw['id'], {}, 'Mike')
    with pytest.raises(SwapError, match='already has'):
        switch_swap.swap(data, sw['id'], {'serial': 'OLD1'}, 'Mike')
    with pytest.raises(SwapError, match='not on the shelf'):
        switch_swap.swap(data, sw['id'], {'spare_id': sw['id']}, 'Mike')
    entry = switch_swap.swap(data, sw['id'], {'serial': ' FOC123 ', 'model': 'C2960X-48'}, 'Mike')
    assert (sw['serial'], sw['model']) == ('FOC123', 'C2960X-48') and entry['spare_id'] is None
    assert switch_swap.plan(data, sw['id'])['swaps'][0]['new_serial'] == 'FOC123'


def test_swaps_survive_a_save_and_are_capped():
    data, sw, _, _ = _hall()
    for n in range(switch_swap.MAX_SWAPS + 3):
        switch_swap.swap(data, sw['id'], {'serial': f'S{n}'}, 'Mike', now=n)
    restored = inventory.normalize(sw)
    assert len(restored['swaps']) == switch_swap.MAX_SWAPS and restored['swaps'][-1]['new_serial'] == 'S22'


def test_the_api_swaps_audits_and_notes_the_open_incident(client):
    data = load_data()
    data['inventory'] = []
    sw = inventory.create(data, {'name': 'sw-a1', 'model': 'C2960X', 'serial': 'OLD1'})
    spare = inventory.create(data, {'name': 'spare-1', 'model': 'C2960X', 'serial': 'NEW1', 'status': 'inventory'})
    save_data(data)
    made = client.post('/api/incidents', json={'title': 'sw-a1 is down', 'switch_id': sw['id']}).get_json()
    plan = client.get(f"/api/switch-swap/{sw['id']}").get_json()
    assert plan['incident']['id'] == made['id'] and plan['config_readable'] is True
    assert client.post(f"/api/switch-swap/{sw['id']}", json={}).status_code == 400
    resp = client.post(f"/api/switch-swap/{sw['id']}", json={'spare_id': spare['id']})
    assert resp.status_code == 200, resp.data
    body = resp.get_json()
    assert body['swap']['new_serial'] == 'NEW1' and body['switch']['serial'] == 'NEW1' and body['spares'] == []
    [incident] = client.get('/api/incidents').get_json()['incidents']
    assert any('OLD1 out, NEW1 in' in n['text'] for n in incident['notes'])
    entries = client.get('/api/settings/audit').get_json()['entries']
    assert any(e['action'] == 'Swapped switch hardware' for e in entries)
    assert client.get('/api/switch-swap/nope').status_code == 404
    assert client.get(f"/switch-swap/{sw['id']}").status_code in (200, 503)


def test_a_viewer_can_look_but_not_swap(kiosk_client, client):
    data = load_data()
    sw = inventory.create(data, {'name': 'sw-a1', 'serial': 'OLD1'})
    save_data(data)
    assert kiosk_client.get(f"/api/switch-swap/{sw['id']}").status_code == 200
    assert kiosk_client.post(f"/api/switch-swap/{sw['id']}", json={'serial': 'N'}).status_code == 403
