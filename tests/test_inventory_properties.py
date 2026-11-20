"""A device's properties in three levels (issue #965): system.* with who set each value and what each
source read, auto.* from discovery, and the custom properties people set, inherited."""
from test_inventory_discovery import IOS, Telemetry, add

from floorbit import sources


def test_a_device_shows_its_properties_with_each_sources_reading(client):
    sw = add(client, name='sw-a-01', serial='S-BY-HAND', mgmt_ip='192.0.2.10')
    group = client.post('/api/inventory/groups', json={'name': 'Hall A', 'properties': {'rack': 'B3'}})
    assert group.status_code == 201, group.data
    body = {'group_id': group.get_json()['id'], 'properties': {'owner': 'core-team'}}
    r = client.patch(f"/api/inventory/{sw['id']}", json=body)
    assert r.status_code == 200, r.data
    rows = [{'hostname': 'sw-a-01', 'sysName': 'sw-a-01.example.org', 'ip': '192.0.2.10', 'status': 1,
             'source': 'telemetry',
             'facts': {'descr': IOS, 'model': 'WS-C2960X-48FPD-L', 'serial': 'FOC0000X0AA',
                       'poe': {'budget_w': 740, 'used_w': 61.5}, 'vlans': {'10': 'seats', '20': 'crew'}}}]
    before = sources.use(Telemetry(rows, {'sw-a-01': [{'name': 'Gi1/0/1', 'speed_bps': 1e9, 'state': 'up'}]}))
    try:
        assert client.post('/api/inventory/sync').status_code == 200
        view = client.get(f"/api/inventory/{sw['id']}").get_json()['property_view']
    finally:
        sources.use(before)
    system, auto, custom = view['system'], view['auto'], view['custom']
    # A hand value wins, and the device's own reading stands next to it.
    assert system['system.serial'] == {'value': 'S-BY-HAND', 'set_by': 'hand', 'sources': {'telemetry': 'FOC0000X0AA'}}
    assert system['system.model'] == {'value': 'WS-C2960X-48FPD-L', 'set_by': 'discovery',
                                      'sources': {'telemetry': 'WS-C2960X-48FPD-L'}}
    assert system['system.name']['sources'] == {'telemetry': 'sw-a-01.example.org'}
    assert system['system.mgmt_ip']['sources'] == {'telemetry': '192.0.2.10'}
    assert 'system.notes' not in system
    assert auto['auto.poe.budget_w']['value'] == 740 and auto['auto.vlans.count']['value'] == 2
    descr = auto['auto.snmp.sysdescr']
    assert (descr['value'], descr['source'], bool(descr['seen'])) == (IOS, 'telemetry', True)
    assert auto['auto.interfaces.count']['value'] == 1
    assert custom['owner']['value'] == 'core-team' and custom['owner']['from']['type'] == 'device'
    assert custom['rack'] == {'value': 'B3', 'from': {'type': 'group', 'id': group.get_json()['id'], 'name': 'Hall A'}}


def test_a_device_never_discovered_has_no_readings(client):
    sw = add(client, name='sw-z-01', model='WS-C2960X')
    view = client.get(f"/api/inventory/{sw['id']}").get_json()['property_view']
    assert view['system']['system.model'] == {'value': 'WS-C2960X', 'set_by': 'hand', 'sources': {}}
    assert view['auto'] == {}


def test_custom_names_cannot_take_floorbits_own_levels(client):
    sw = add(client, name='sw-y-01')
    for key in ('system.serial', 'auto.poe.budget_w'):
        r = client.patch(f"/api/inventory/{sw['id']}", json={'properties': {key: 'x'}})
        assert r.status_code == 400 and 'Floorbit' in r.get_json()['error']
    assert client.patch(f"/api/inventory/{sw['id']}", json={'properties': {'systems.note': 'x'}}).status_code == 200
