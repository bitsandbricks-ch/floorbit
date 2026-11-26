"""Which source decides a discovery area per kind of device, and source conflicts (issue #965)."""
import pytest
from test_plugin_discovery import add, fwthing  # noqa: F401  # the fixture: a plugin with three areas

from floorbit import discovery_sources, inventory, inventory_discovery
from floorbit.blueprints.inventory import data_lock
from floorbit.store import load_data, save_data


@pytest.fixture
def telemetry(monkeypatch):
    """A monitoring source that reads the built-in areas, as telemetry does."""
    monkeypatch.setattr(discovery_sources, '_monitoring', lambda: ('telemetry', 'Built-in telemetry'))


def read_by_telemetry(dev_id, **fields):
    with data_lock:
        data = load_data()
        data.setdefault('inventory_readings', {}).setdefault(dev_id, {})['telemetry'] = \
            {'fields': fields, 'descr': '', 'at': '2026-11-25T18:00:00Z'}
        save_data(data)


def test_the_monitoring_source_decides_by_default_and_an_admin_picks_another(client, fwthing, telemetry):  # noqa: F811
    rows = {r['area']: r for r in client.get('/api/inventory/discovery/types/firewall').get_json()['rows']}
    assert [s['id'] for s in rows['identity']['sources']] == ['monitoring', 'fwthing']
    assert rows['identity']['deciding'] == 'monitoring' and rows['identity']['why'] == 'default'
    assert rows['gateways']['deciding'] == 'fwthing' and rows['gateways']['why'] == 'only'
    assert rows['gateways']['goes_to'] == 'auto.gateways.*' and rows['routes']['goes_to'] == 'discovered.routes'
    assert 'poe' not in rows                    # a firewall has no PoE budget to read
    r = client.put('/api/inventory/discovery/deciding',
                   json={'role': 'firewall', 'area': 'routes', 'source': 'fwthing'})
    routes = next(x for x in r.get_json()['rows'] if x['area'] == 'routes')
    assert routes['deciding'] == 'fwthing' and routes['why'] == 'admin' and routes['action'] == 'fwthing.routes'
    assert client.put('/api/inventory/discovery/deciding',
                      json={'role': 'firewall', 'area': 'routes', 'source': 'nobody'}).status_code == 400
    assert client.put('/api/inventory/discovery/deciding',
                      json={'role': 'firewall', 'area': 'routes', 'source': None}).status_code == 200
    assert discovery_sources.deciding(load_data(), 'firewall', 'routes')[0] == 'monitoring'


def test_only_admins_pick():
    # auth/roles.py: picking is a setting; taking a value is an editor's, like a drift row.
    from auth.roles import needed_for
    assert needed_for('/api/inventory/discovery/deciding', 'PUT') == 'settings.manage'
    assert needed_for('/api/inventory/d1/conflicts/take', 'POST') == 'floorplan.edit'


def test_a_conflict_shows_both_sources_and_the_deciding_one_fills(client, fwthing, telemetry):  # noqa: F811
    part, _calls = fwthing
    fw = add(client, name='fw-01', role='firewall', platform='OPNsense')
    read_by_telemetry(fw, os='OPNsense 24.7.9', model='DEC850')
    part.answers = {'identity': {'software': 'OPNsense 24.7.10', 'model': 'DEC850', 'serial': 'SN0001'}}
    client.post('/api/inventory/discovery/run', json={'actions': ['fwthing.identity']})
    dev = client.get(f'/api/inventory/{fw}').get_json()
    # The plugin doesn't decide: it fills only what telemetry didn't read (the serial).
    assert dev['serial'] == 'SN0001' and dev['os'] != 'OPNsense 24.7.10'
    [conflict] = dev['conflicts']
    assert conflict['field'] == 'os' and conflict['deciding'] == {'source': 'monitoring', 'name': 'Built-in telemetry',
                                                                  'value': 'OPNsense 24.7.9'}
    assert conflict['other']['source'] == 'fwthing' and conflict['other']['value'] == 'OPNsense 24.7.10'
    rows = {r['area']: r for r in client.get('/api/inventory/discovery/types/firewall').get_json()['rows']}
    assert rows['identity']['conflicts'] == 1
    # Take the plugin's value: like a hand edit.
    r = client.post(f'/api/inventory/{fw}/conflicts/take', json={'field': 'os', 'source': 'fwthing'})
    assert r.status_code == 200 and r.get_json()['os'] == 'OPNsense 24.7.10'
    same = client.post(f'/api/inventory/{fw}/conflicts/take', json={'field': 'model', 'source': 'fwthing'})
    assert same.status_code == 404


def test_the_deciding_plugin_takes_over_what_telemetry_filled(client, fwthing, telemetry):  # noqa: F811
    part, _calls = fwthing
    fw = add(client, name='fw-01', role='firewall')
    read_by_telemetry(fw, os='OPNsense 24.7.9')
    with data_lock:
        data = load_data()
        dev = inventory.find(data, fw)
        inventory_discovery.fill(dev, {'os': 'OPNsense 24.7.9'})        # what telemetry's run put there
        save_data(data)
    client.put('/api/inventory/discovery/deciding', json={'role': 'firewall', 'area': 'identity', 'source': 'fwthing'})
    part.answers = {'identity': {'software': 'OPNsense 24.7.10'}}
    client.post('/api/inventory/discovery/run', json={'actions': ['fwthing.identity']})
    dev = client.get(f'/api/inventory/{fw}').get_json()
    assert dev['os'] == 'OPNsense 24.7.10'
    assert dev['conflicts'][0]['deciding']['source'] == 'fwthing'


def test_a_deciding_plugin_s_routes_come_first(client, fwthing, telemetry):  # noqa: F811
    part, _calls = fwthing
    fw = add(client, name='fw-01', role='firewall', platform='OPNsense')
    with data_lock:
        data = load_data()
        data['inventory_discovered'] = {fw: {'routes': [{'network': '10.0.0.0/8', 'next_hop': '', 'interface': '',
                                                         'proto': 'static'}], 'at': 'x'}}
        save_data(data)
    part.answers = {'routes': {'routes': [{'network': '0.0.0.0/0', 'next_hop': '198.51.100.1'}]}}
    client.post('/api/inventory/discovery/run', json={'actions': ['fwthing.routes']})
    assert inventory_discovery.discovered_of(load_data(), fw)['routes'][0]['network'] == '10.0.0.0/8'
    client.put('/api/inventory/discovery/deciding', json={'role': 'firewall', 'area': 'routes', 'source': 'fwthing'})
    assert inventory_discovery.discovered_of(load_data(), fw)['routes'][0]['network'] == '0.0.0.0/0'


def test_unknown_kinds_are_refused(client):
    assert client.get('/api/inventory/discovery/types/toaster').status_code == 404
    assert client.put('/api/inventory/discovery/deciding', json={'role': 'toaster', 'area': 'routes',
                                                                 'source': None}).status_code == 400
