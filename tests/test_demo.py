"""Demo mode: the built-in demo plugin and the demo hall on an empty floor plan."""
import ipaddress

import pytest

from floorbit import sources

DOC_NETS = [ipaddress.ip_network(n) for n in ('192.0.2.0/24', '198.51.100.0/24', '203.0.113.0/24')]


@pytest.fixture
def registry(app_module):
    return app_module.app.extensions['floorbit_plugins']


@pytest.fixture
def demo(client, registry):
    client.put('/api/settings/plugins/demo', json={'enabled': True})
    assert registry.demo_on()
    return client


def test_off_until_turned_on_or_forced_by_the_env(registry, monkeypatch):
    spec = registry.specs['demo']
    assert spec.error == '' and not registry.enabled(spec)
    monkeypatch.setenv('FLOORBIT_DEMO', '1')
    assert registry.enabled(spec) and registry.demo_on()


def test_demo_replaces_the_live_source(demo, monkeypatch):
    from floorbit import runtime
    monkeypatch.setattr(runtime.rt, 'librenms_enabled', True)
    assert sources.monitoring().name == 'demo'
    body = demo.get('/api/config').get_json()
    assert body['demo'] is True and body['monitoring_source'] == 'demo' and body['librenms_enabled'] is True


def test_lay_out_the_hall_once_on_an_empty_plan(demo):
    first = demo.post('/api/demo/layout').get_json()
    assert first == {'placed': 15, 'blocks': 4}
    switches = demo.get('/api/switches').get_json()
    assert len(switches) == 15 and all(s['x'] is not None for s in switches)
    assert [b['name'] for b in demo.get('/api/seat-blocks').get_json()] == ['A', 'B', 'C', 'D']
    # Never moves anything that is already on the plan.
    assert demo.post('/api/demo/layout').get_json()['skipped'] == 'the floor plan is not empty'


def test_layout_needs_the_plugin_and_an_admin(client, app_module, anon_client):
    assert client.post('/api/demo/layout').status_code == 409
    assert anon_client.post('/api/demo/layout').status_code in (401, 403)


def test_live_data_looks_real_and_uses_documentation_addresses(demo):
    seats = [r for r in demo.get('/api/seat-map').get_json()['seats'] if r['from'].get('ip') == 'demo']
    assert len(seats) > 50
    for row in seats:
        assert any(ipaddress.ip_address(row['ip']) in net for net in DOC_NETS)
        assert row['mac'].startswith('02:') and row['nick'].startswith('player-')
    ip = seats[0]['ip']
    found = demo.get(f'/api/resolve/{ip}').get_json()
    assert found['device_name'].startswith('sw-') and found['port'].startswith('Gi1/0/')
    assert found['stats']['state'] in ('up', 'down') and found['stats']['speed_bps'] == 1e9
    assert demo.get('/api/switches/core-01/status').get_json()['status'] == 'online'


def test_one_switch_flaps(app_module, registry):
    mod = registry.specs['demo'].module
    assert mod._down(mod.FLAPPING, now=0) and not mod._down(mod.FLAPPING, now=60)
    assert not mod._down('sw-a-01', now=0)


def test_every_page_says_demo_data_while_it_is_on(client, anon_client):
    assert b'demo.css' not in anon_client.get('/login').data
    client.put('/api/settings/plugins/demo', json={'enabled': True})
    assert b'demo.css' in anon_client.get('/login').data
    assert b'demo.css' in client.get('/inventory').data
