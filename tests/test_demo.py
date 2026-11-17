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
    assert first == {'placed': 26, 'blocks': 5}   # 16 switches and 10 access points
    switches = demo.get('/api/switches').get_json()
    # The ten firewalls stand behind the core, not on the floor.
    placed = [s for s in switches if not s['name'].startswith('fw-')]
    assert len(placed) == 26 and all(s['x'] is not None for s in placed)
    assert len(demo.get('/api/firewalls').get_json()['ranges']) == 10
    lines = demo.get('/api/services').get_json()['uplinks']
    assert [(u['name'], u['device'], u['port'], u['probe_host']) for u in lines] == [
        ('ISP A', 'core-01', 'Ethernet1/47', ''), ('ISP B', 'core-01', 'Ethernet1/48', '')]     # no probes sent out
    assert [b['name'] for b in demo.get('/api/seat-blocks').get_json()] == ['A', 'B', 'C', 'D', 'E']
    assert [h['name'] for h in demo.get('/api/halls').get_json()['halls']] == ['Main hall', 'Side hall']
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
    status = demo.get('/api/switches/core-01/status').get_json()
    assert status['status'] == 'online' and status['ip']


def test_a_signed_out_kiosk_gets_the_status_without_the_management_ip(demo, anon_client):
    body = anon_client.get('/api/switches/core-01/status').get_json()
    assert body['status'] == 'online' and 'ip' not in body


def test_one_switch_flaps(app_module, registry):
    mod = registry.specs['demo'].module
    assert mod._down(mod.FLAPPING, now=0) and not mod._down(mod.FLAPPING, now=60)
    assert not mod._down('sw-a-01', now=0)


def test_every_page_says_demo_data_while_it_is_on(client, anon_client):
    assert b'demo.css' not in anon_client.get('/login').data
    client.put('/api/settings/plugins/demo', json={'enabled': True})
    assert b'demo.css' in anon_client.get('/login').data
    assert b'demo.css' in client.get('/inventory').data


def test_demo_devices_do_not_sit_on_each_other():
    """Every demo device gets its own spot on its hall's plan, so no two names print over each other."""
    from floorbit.builtin_plugins.demo.plugin import LAYOUT
    for devices in [LAYOUT['devices'], *(h['devices'] for h in LAYOUT['halls'])]:
        spots = list(devices.items())
        for i, (a, (ax, ay)) in enumerate(spots):
            for b, (bx, by) in spots[i + 1:]:
                assert abs(ax - bx) >= 5 or abs(ay - by) >= 5, (a, b)


def test_switches_list_every_port_of_their_model(demo):
    """A real hardware mix: Nexus core, Catalyst 4500-X distribution, 2960-X access, with all their ports."""
    from floorbit import inventory
    from floorbit.store import load_data
    demo.post('/api/demo/layout')
    models = {d['name']: d['model'] for d in inventory.devices(load_data())}
    assert 'Nexus' in models['core-01'] and '4500-X' in models['dist-01'] and '2960-X' in models['sw-a-01']
    source = sources.monitoring()
    access = source.device_ports('sw-a-01')
    assert [p['name'] for p in access][:2] == ['Gi1/0/1', 'Gi1/0/2'] and len(access) == 50
    uplink = next(p for p in access if p['name'] == 'Te1/0/1')
    assert uplink['state'] == 'up' and uplink['speed_bps'] == 10e9 and 'dist-01' in uplink['description']
    assert next(p for p in access if p['name'] == 'Gi1/0/30')['state'] == 'down'     # nothing plugged in
    assert len(source.device_ports('core-01')) == 54 and len(source.device_ports('dist-02')) == 16
    assert source.device_ports('fw-01') == []


def test_the_plan_has_typed_uplinks_a_patch_panel_bends_areas_marks_and_groups(demo):
    demo.post('/api/demo/layout')
    links = demo.get('/api/links').get_json()['links']
    assert {(link['type'], link['speed']) for link in links} == {('fiber-sm', 10), ('fiber-mm', 10), ('dac', 10)}
    slow = next(p for p in sources.monitoring().device_ports('sw-c-02') if p['name'] == 'Te1/0/1')
    assert slow['speed_bps'] == 1e9                                   # planned 10G, came up at 1G
    plan = demo.get('/api/cable-plan').get_json()
    assert plan['panels'] == [{'name': 'PP-A', 'x': 10, 'y': 34, 'ports': 24}]
    lan = [c for c in plan['cables'] if c['kind'] == 'lan']
    assert sum(c['via'] == 'PP-A' for c in lan) == 24                    # block A runs through its panel
    assert sum(c['manual'] for c in lan) == 2                             # two routed by hand
    assert {c['media'] for c in plan['cables']} >= {'copper', 'fiber', 'power'}
    cables = demo.get('/api/cables').get_json()['cables']
    assert len(cables) == 96 and not any(c['seat'].startswith('E-') for c in cables)
    areas = demo.get('/api/port-areas').get_json()['areas']
    assert [(a['switch'], a['label']) for a in areas] == [('sw-e-01', 'E-1..E-8'), ('sw-e-01', 'E-9..E-16')]
    marks = demo.get('/api/plan-marks').get_json()['marks']
    assert {m['layer'] for m in marks} >= {'overview', 'safety', 'network', 'electrical'}
    groups = demo.get('/api/plan-groups').get_json()['groups']
    assert [g['name'] for g in groups] == ['Block A', 'Block B', 'Block C', 'Block D']
    assert {'kind': 'panel', 'id': 'PP-A'} in groups[0]['members']


def test_the_side_hall_seats_have_no_known_port_yet(demo):
    seats = {r['seat']: r for r in demo.get('/api/seat-map').get_json()['seats']}
    assert not seats['E-2'].get('switch') and seats['E-2'].get('ip')
    assert seats['A-2']['switch'] == 'sw-a-01' and seats['A-2']['port'] == 'Gi1/0/2'
