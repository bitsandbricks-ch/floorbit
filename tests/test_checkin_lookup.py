"""A check-in's PC looked up on the switches (issue #947, floorbit/checkin_lookup.py and
floorbit/telemetry/lookup.py). RFC 5737 addresses, example MACs, no real switch."""
import time

import pytest

from floorbit import checkin_lookup, segments, sources
from floorbit.telemetry import lookup, snmpget
from floorbit.telemetry.state import State
from integrations import checkin, events

MAC = '02:00:00:00:00:31'
MAC_OID = '2.0.0.0.0.49'


@pytest.fixture(autouse=True)
def fresh():
    checkin_lookup.reset()
    yield
    checkin_lookup.reset()


# ── on the agent: the GETs and the uplinks ────────────────────────────────────────────────────

def fake_get(answers, asked):
    def get(target, oids, vlan=None, timeout=None):
        asked.append((target['name'], oids[0], vlan))
        return {oids[0]: answers.get((target['name'], oids[0]))}
    return get


def test_the_agent_finds_the_mac_on_the_core_then_skips_uplinks():
    st = State()
    tags = 'device=access-a1,address=192.0.2.11,driver=snmp'
    st.apply_text(f'fb_ifmac,{tags},index=10149 ifName="Gi1/0/49"\n'
                  f'fb_ifmac,{tags},index=10107 ifName="Gi1/0/7"\n'
                  f'fb_ifvlan,{tags},index=10149 vlanTrunkPortDynamicStatus=1i\n')
    answers = {('core-01', f'{snmpget.ARP_MAC}.110.192.0.2.23'): bytes.fromhex('020000000031').hex(),
               # dist-01 learned it on its uplink to the access switch; access-a1 on the seat's port
               ('access-a1', f'{snmpget.FDB_PORT}.{MAC_OID}'): 7,
               ('access-a1', f'{snmpget.BASE_PORT_IFINDEX}.7'): 10107,
               ('access-b1', f'{snmpget.FDB_PORT}.{MAC_OID}'): 49,
               ('access-b1', f'{snmpget.BASE_PORT_IFINDEX}.49'): 10149}
    st.apply_text('fb_ifvlan,device=access-b1,address=192.0.2.12,driver=snmp,index=10149 '
                  'vlanTrunkPortDynamicStatus=1i\n')
    targets = [{'name': n, 'address': '192.0.2.1', 'community': 'example-community'}
               for n in ('core-01', 'access-a1', 'access-b1')]
    asked = []
    said = []
    out = lookup.find({'ip': '192.0.2.23', 'vlan': 110, 'if_index': 110, 'core': 'core-01',
                       'switches': ['access-b1', 'access-a1', 'not-mine']},
                      targets, st, get=fake_get(answers, asked), log=said.append)
    assert out['mac'] == MAC
    assert out['switch'] == 'access-a1' and out['if_index'] == 10107 and out['port'] == 'Gi1/0/7'
    assert out['skipped'] == [{'switch': 'access-b1', 'if_index': 10149}]          # its trunk: an uplink
    assert out['asked'] == ['access-b1', 'access-a1']                              # not another agent's
    assert all(vlan in (None, 110) for _n, _o, vlan in asked)                     # the VLAN's own bridge
    assert 'lookup 192.0.2.23 in VLAN 110: access-a1 Gi1/0/7' in said[0]
    assert 'example-community' not in said[0]


def test_a_known_mac_skips_the_core_and_a_dead_switch_is_not_the_end():
    def get(target, oids, vlan=None, timeout=None):
        if target['name'] == 'dead':
            raise snmpget.SnmpError('dead: timeout')
        return {oids[0]: 3 if oids[0].startswith(snmpget.FDB_PORT) else 10103}
    targets = [{'name': 'dead', 'address': '192.0.2.9'}, {'name': 'live', 'address': '192.0.2.10'}]
    out = lookup.find({'ip': '192.0.2.23', 'vlan': 110, 'mac': '0200.0000.0031', 'switches': ['dead', 'live']},
                      targets, None, get=get)
    assert out['mac'] == MAC and out['switch'] == 'live' and out['if_index'] == 10103
    assert out['errors'] == [{'switch': 'dead', 'error': 'dead: timeout'}]


# ── on the hosted side: segment, window, order, sharing ───────────────────────────────────────

def _segment(client, on=True, **extra):
    seg = client.post('/api/settings/segments', json={'vlan': 110, 'network': '192.0.2.0/24'}).get_json()['segment']
    from floorbit.store import load_data, save_data
    data = load_data()
    for s in data['segments']:
        s.update({'lookups': on, 'device': 'core-01', 'if_index': 110, **extra})
    save_data(data)
    return seg


def test_no_lookup_outside_a_segment_with_lookups_on(client):
    asked = []
    assert checkin_lookup.lookup('192.0.2.23', ask=asked.append) == {'state': 'todo', 'todo': 'no_segment'}
    _segment(client, on=False)
    off = checkin_lookup.lookup('192.0.2.23', ask=asked.append)
    assert off == {'state': 'todo', 'todo': 'segment_off', 'vlan': 110}
    assert asked == []


def test_only_inside_the_window_unless_the_crew_asks(client):
    _segment(client)
    asked = []

    def ask(req):
        asked.append(req)
        return {'mac': MAC, 'switch': 'access-a1', 'port': 'Gi1/0/7', 'asked': ['access-a1'], 'took_ms': 30}
    assert checkin_lookup.lookup('192.0.2.23', ask=ask)['state'] == 'closed' and asked == []
    found = checkin_lookup.lookup('192.0.2.23', seat='A-1', crew=True, ask=ask)
    assert found['state'] == 'found' and found['switch'] == 'access-a1' and found['port'] == 'Gi1/0/7'
    assert asked[0]['core'] == 'core-01' and asked[0]['if_index'] == 110 and asked[0]['vlan'] == 110
    # The IP and MAC history knows it at once.
    from floorbit import endpoints
    assert any(r['port'] == 'Gi1/0/7' for r in endpoints.history().search('192.0.2.23'))


@pytest.fixture
def checkin_on(monkeypatch, tmp_path):
    monkeypatch.setenv('CHECKIN_ENABLED', 'true')
    monkeypatch.setenv('CHECKIN_FILE', str(tmp_path / 'checkins.json'))


def test_the_window_opens_at_doors_by_hand_and_stays_open_after_checkins(client, checkin_on):
    from floorbit.store import load_data, save_data
    now = time.time()
    assert not checkin_lookup.window(now)['open']
    data = load_data()
    data['schedule'] = {'event': {'start': now - 3600, 'end': now + 86400}, 'items': []}
    save_data(data)
    w = checkin_lookup.window(now)
    assert w['open'] and w['why'] == 'doors' and w['until'] == now - 3600 + 6 * 3600
    assert not checkin_lookup.window(now + 6 * 3600)['open']
    data['schedule'] = {}
    save_data(data)
    hand = client.post('/api/checkins/lookup-window', json={'hours': 2})
    assert hand.status_code == 200 and hand.get_json()['open'] and hand.get_json()['why'] == 'by_hand'
    later = now + 2 * 3600 - 60
    checkin_lookup.touch(later)                                   # a check-in near the end
    w = checkin_lookup.window(later + 20 * 60)
    assert w['open'] and w['why'] == 'activity'
    assert not checkin_lookup.window(later + 31 * 60)['open']
    assert client.delete('/api/checkins/lookup-window').get_json()['open'] is False
    assert client.post('/api/checkins/lookup-window', json={'hours': 'x'}).status_code == 400


def test_kiosk_cannot_open_the_window(kiosk_client, checkin_on):
    assert kiosk_client.post('/api/checkins/lookup-window', json={}).status_code == 403


def test_the_same_pc_asked_twice_shares_one_lookup(client):
    _segment(client)
    checkin_lookup.open_window('crew')
    asked = []

    def ask(req):
        asked.append(req)
        return {'mac': MAC, 'switch': None, 'asked': ['access-a1']}
    assert checkin_lookup.lookup('192.0.2.23', ask=ask)['state'] == 'not_found'
    assert checkin_lookup.lookup('192.0.2.23', ask=ask)['state'] == 'not_found'
    assert len(asked) == 1
    checkin_lookup.lookup('192.0.2.23', crew=True, ask=ask)     # the walk always asks afresh
    assert len(asked) == 2


def test_the_seats_row_comes_first_then_its_block_then_the_vlan(client, monkeypatch):
    client.post('/api/seat-blocks', json={'name': 'A', 'x': 10, 'y': 10, 'cols': 2, 'rows': 2})
    monkeypatch.setattr(checkin, 'learned_ports', lambda: {
        'A-1': {'switch': 'access-row'}, 'A-3': {'switch': 'access-block'}})
    from floorbit.telemetry import targets
    monkeypatch.setattr(targets, 'listing', lambda data=None: [
        {'name': 'access-block', 'kind': 'switch', 'drivers': ['snmp'], 'vlans': [110]},
        {'name': 'access-other', 'kind': 'switch', 'drivers': ['snmp'], 'vlans': [110]},
        {'name': 'access-elsewhere', 'kind': 'switch', 'drivers': ['snmp'], 'vlans': [120]},
        {'name': 'fw-01', 'kind': 'firewall', 'drivers': ['snmp'], 'vlans': []}])
    from floorbit.seat_names import block_rows
    from floorbit.store import load_data
    rows = [[s.upper() for s in r] for r in block_rows(load_data()['seat_blocks'][0])]
    assert 'A-1' in rows[0] and 'A-3' not in rows[0]
    seat = next(s for s in rows[0] if s != 'A-1')                # A-1's row-mate
    order = checkin_lookup.candidates(seat, 110)
    assert order == ['access-row', 'access-block', 'access-other']


def test_a_pending_checkin_is_verified_by_the_switches(client, tmp_path, monkeypatch, front_door):
    monkeypatch.setenv('CHECKIN_ENABLED', 'true')
    monkeypatch.setenv('CHECKIN_FILE', str(tmp_path / 'checkins.json'))
    monkeypatch.setattr(checkin, 'lookup_mac', lambda ip: None)
    monkeypatch.setattr(checkin, 'port_of', lambda ip: None)         # the tables don't know it yet
    monkeypatch.setattr(checkin, '_monitoring', sources.NoMonitoring)
    monkeypatch.setattr(events, 'publish', lambda kind, data=None, origin=None: None)
    client.post('/api/seat-blocks', json={'name': 'A', 'x': 10, 'y': 10, 'cols': 4, 'rows': 1})
    _segment(client)
    monkeypatch.setattr(checkin_lookup, '_ask_agents', lambda req: {
        'mac': MAC, 'switch': 'access-a1', 'port': 'Gi1/0/7', 'asked': ['access-a1']})
    client.post('/api/checkin', json={'seat': 'A-1', 'username': 'pixel'}, environ_base={'REMOTE_ADDR': '192.0.2.23'})
    checkin.verify_pending()
    row = checkin.load_all()['A-1']
    assert row['wired'] == 'pending'                                 # the window is closed: not asked
    assert row['lookup'] == {'state': 'closed', 'vlan': 110}
    assert client.get('/api/checkins/overview').get_json()['rows'][0]['lookup']['state'] == 'closed'
    checkin_lookup.open_window('crew')
    checkin.verify_pending()
    row = checkin.load_all()['A-1']
    assert row['wired'] == 'verified' and row['port_seen'] == {'switch': 'access-a1', 'port': 'Gi1/0/7'}
    assert row['mac'] == MAC


def test_tables_every_15_minutes_once_a_segment_has_lookups(client):
    from floorbit.telemetry import polling
    registry = client.application.extensions['floorbit_plugins']
    assert polling.tables_minutes(registry) == 1
    _segment(client)
    assert segments.lookups_on() and polling.tables_minutes(registry) == 15
