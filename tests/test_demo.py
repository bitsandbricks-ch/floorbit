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
    # The ten firewalls and the LAN cache stand in the rack behind the core, not on the floor.
    placed = [s for s in switches if not s['name'].startswith(('fw-', 'lancache'))]
    assert len(placed) == 26 and all(s['x'] is not None for s in placed)
    assert len(demo.get('/api/firewalls').get_json()['ranges']) == 10
    lines = demo.get('/api/services').get_json()['uplinks']
    assert [(u['name'], u['device'], u['port'], u['probe_host']) for u in lines] == [
        ('ISP A', 'core-01', 'Ethernet1/47', '203.0.113.1'), ('ISP B', 'core-01', 'Ethernet1/48', '203.0.113.2')]
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


def test_the_side_hall_seats_have_no_patched_port(demo):
    """Nobody wrote the side hall's patching down: until check-ins teach its ports, a seat has only its IP."""
    seats = {r['seat']: r for r in demo.get('/api/seat-map').get_json()['seats']}
    assert not seats['E-2'].get('switch') and seats['E-2'].get('ip')
    assert seats['A-2']['switch'] == 'sw-a-01' and seats['A-2']['port'] == 'Gi1/0/2'


def test_the_demo_servers_answer_for_themselves(demo, monkeypatch):
    """DNS, internet lines and game servers are answered by the demo: nothing is sent out."""
    from floorbit import game_query, probes
    for name in ('dns', 'tcp'):
        monkeypatch.setattr(probes, name, lambda *a, **k: pytest.fail('the demo sent a probe out'))
    for name in ('query', 'rcon'):
        monkeypatch.setattr(game_query, name, lambda *a, **k: pytest.fail('the demo asked a game server'))
    demo.post('/api/demo/layout')
    from floorbit import game_servers, services
    services.poller.poll_once()
    body = demo.get('/api/services').get_json()
    assert [(r['name'], r['address'], r['status']) for r in body['resolvers']] == [
        ('LAN cache DNS', '198.51.100.53', 'up'), ('Provider DNS', '203.0.113.53', 'up')]
    assert len(body['sites']) == 9 and all(s['latency_ms'] for s in body['sites'])   # answered by the demo too
    assert all(u['latency_ms'] is not None and u['status'] in ('up', 'warn') for u in body['uplinks'])
    game_servers.poller.poll_once()
    servers = demo.get('/api/game-servers').get_json()['servers']
    assert [s['name'] for s in servers] == ['CS2 #1', 'CS2 #2', 'Minecraft', 'Trackmania']
    assert [s['rcon'] for s in servers] == [True, True, True, False]
    cs = servers[0]
    assert cs['status'] == 'up' and cs['info']['map'] == 'de_mirage' and 0 < cs['info']['players'] <= 10
    answer = demo.post(f"/api/game-servers/rcon/{cs['id']}", json={'command': 'status'}).get_json()
    assert 'de_mirage' in answer['answer'] and 'player-' in answer['answer']
    asked = demo.post(f"/api/game-servers/rcon/{cs['id']}", json={'command': 'changelevel de_nuke'})
    assert asked.status_code == 409                                 # still asks to confirm
    mc = servers[2]
    listed = demo.post(f"/api/game-servers/rcon/{mc['id']}", json={'command': 'list'}).get_json()['answer']
    assert listed.startswith('There are ') and 'max of 40' in listed


def test_the_stand_in_lets_other_hosts_through_and_stops_with_the_demo(demo, registry):
    from floorbit import probes
    demo.post('/api/demo/layout')
    assert probes.stood_in('dns_probe', ('198.51.100.53', 'example.com'))['rcode'] == 'NOERROR'
    assert probes.stood_in('dns_probe', ('192.0.2.200', 'example.com')) is None     # not a demo server
    demo.put('/api/settings/plugins/demo', json={'enabled': False})
    assert probes.stood_in('dns_probe', ('198.51.100.53', 'example.com')) is None


def test_the_event_so_far_fills_the_crew_pages(demo, app_module):
    """Incidents, check-ins, status page, dashboards and schedule, so no crew page starts empty."""
    demo.post('/api/demo/layout')
    board = demo.get('/api/incidents').get_json()['incidents']
    assert len(board) == 6 and {i['status'] for i in board} == {'open', 'assigned', 'fixed'}
    assert any(i.get('switch_name') == 'sw-c-02' for i in board)
    users = app_module.app.extensions['auth'].users
    assert all(users.get(name) is not None for name in ('alex', 'sam', 'robin'))
    checkins = demo.get('/api/checkins').get_json()
    rows = checkins['checkins'] if isinstance(checkins, dict) else checkins
    assert len(rows) > 50 and all(r['username'].startswith('player-') for r in rows)
    seats = {r['seat']: r for r in demo.get('/api/seat-map').get_json()['seats']}
    assert seats['E-2']['switch'] == 'sw-e-01'      # the side hall learned its ports from check-ins
    assert not seats['E-7'].get('switch')
    history = demo.get('/api/checkins/history').get_json()
    assert history['total'] > 50 and 'moved' in repr(history['rows'])
    items = demo.get('/api/schedule').get_json()['items']
    assert len(items) == 8 and items[-1]['title'] == 'Doors close'
    # A second layout run never adds them twice.
    demo.post('/api/demo/layout')
    assert len(demo.get('/api/incidents').get_json()['incidents']) == 6


def test_the_demo_speaks_swiss_german_when_asked(monkeypatch):
    from floorbit.builtin_plugins.demo import texts
    monkeypatch.setenv('FLOORBIT_DEMO_LANGUAGE', 'de-CH')
    assert texts.text()['main_hall'] == 'Haupthalle'
    monkeypatch.delenv('FLOORBIT_DEMO_LANGUAGE')
    assert texts.text()['main_hall'] == 'Main hall'
    english, german = texts.TEXTS['en'], texts.TEXTS['de']
    assert english.keys() == german.keys() and 'ß' not in repr(german)
    for key in ('incidents', 'schedule', 'status_updates'):
        assert len(english[key]) == len(german[key]), key


def test_telemetry_hears_the_demo_devices(demo, registry, tmp_path, monkeypatch):
    """Settings > Telemetry lists the demo's devices, and what Telegraf would send for them fills the
    picture: ports with rates, MAC tables on the access switches, ARP on the core, the firewalls."""
    from floorbit.builtin_plugins.demo import telemetry as demo_telemetry
    from floorbit.plugins import Context
    from floorbit.telemetry import clients, state, storage
    monkeypatch.setenv("FLOORBIT_TELEGRAF_CONF", str(tmp_path / "telegraf" / "telegraf.conf"))
    state.state.reset()
    storage.reset()
    from floorbit import endpoints
    endpoints.reset()
    try:
        demo.post('/api/demo/layout')
        body = demo.get('/api/settings/telemetry').get_json()
        kinds = {t['name']: (t['platform'], t['drivers']) for t in body['targets']}
        assert kinds['core-01'] == ('nxos', ['snmp', 'traps', 'gnmi']) and kinds['sw-a-01'][0] == 'ios'
        assert kinds['fw-01'] == ('opnsense', ['push']) and len(kinds) == 26      # 16 switches, 10 firewalls
        assert not any(set(d) & {'nxapi', 'restconf', 'opnsense'} for _p, d in kinds.values())   # nothing polled
        context = Context(registry.specs['demo'], registry)
        import time
        now = time.time()
        demo_telemetry.feed(context, now=now - 30)
        taken = demo_telemetry.feed(context, now=now)
        assert taken['bad'] == 0 and taken['taken'] == taken['points']
        core = state.state.device('core-01')
        assert core.online() and core.arp and core.lldp
        access = state.state.device('sw-a-01')
        seat = next(i for i in access.interfaces.values() if i.name == 'Gi1/0/1')
        assert seat.oper == 'up' and seat.speed == 1e9 and seat.in_bps is not None
        assert state.state.device('fw-01').gateways and not state.state.device('fw-03').seen   # fw-03 is down
        seen = {(s['device'], s['port']) for s in clients.sightings(state.state)}
        assert ('sw-a-01', 'Gi1/0/1') in seen and not any(p == 'Te1/0/1' for _d, p in seen)   # never the uplink
        from floorbit import endpoints
        found = endpoints.history().search('192.0.2.1')
        assert any(r['device'] == 'sw-a-01' and r['port'] == 'Gi1/0/1' for r in found)
    finally:
        state.state.reset()
        storage.reset()
        endpoints.reset()
