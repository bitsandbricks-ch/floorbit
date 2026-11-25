"""Devices that send but aren't in the inventory (issue #1443)."""
import time

import pytest

from floorbit import syslog, unknown_senders
from floorbit.flows import store as flow_store
from floorbit.telemetry.lineproto import Point
from floorbit.telemetry.state import State

NOW = time.time()


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    unknown_senders.syslog.clear()
    monkeypatch.setattr(flow_store, 'latest', lambda: None)
    monkeypatch.setattr(unknown_senders, '_telemetry', lambda: [])
    yield
    unknown_senders.syslog.clear()


@pytest.fixture
def receiver(tmp_path, monkeypatch):
    monkeypatch.setenv('SYSLOG_ALLOW', '192.0.2.0/24')
    r = syslog.SyslogReceiver(path=str(tmp_path / 'syslog'))
    r._allow_cache = (time.monotonic() + 3600, [syslog.ipaddress.ip_network('192.0.2.0/24')],
                      {'192.0.2.5': 'sw-a-01'})
    return r


def test_syslog_from_outside_the_allow_list_is_still_dropped_but_listed(receiver):
    assert receiver.receive(b'<14>Nov 14 10:00:00 sw-x-09 %LINK-3-UPDOWN: up', '203.0.113.7', now=NOW,
                            agent='Hall agent') is None
    receiver.receive(b'<14>Nov 14 10:00:01 sw-x-09 again', '203.0.113.7', now=NOW + 1)
    # Allowed, but no device has the address: kept and listed too.
    assert receiver.receive(b'<14>hello', '192.0.2.9', now=NOW)
    # A device's own lines are not.
    receiver.receive(b'<14>from the switch', '192.0.2.5', now=NOW)
    rows = {r['address']: r for r in unknown_senders.syslog.rows(NOW + 2)}
    assert set(rows) == {'203.0.113.7', '192.0.2.9'}
    assert rows['203.0.113.7']['count'] == 2 and rows['203.0.113.7']['name'] == 'sw-x-09'
    assert rows['203.0.113.7']['agents'] == ['Hall agent']


def test_the_list_caps_and_forgets_after_a_day():
    seen = unknown_senders.Seen(most=2)
    seen.note('syslog', '192.0.2.1', now=NOW - 10)
    seen.note('syslog', '192.0.2.2', now=NOW - 5)
    seen.note('syslog', '192.0.2.3', now=NOW)           # the quietest goes
    assert sorted(r['address'] for r in seen.rows(NOW)) == ['192.0.2.2', '192.0.2.3']
    assert seen.rows(NOW + unknown_senders.WINDOW + 1) == []


def test_traps_and_streams_from_an_unknown_address_are_noted():
    state = State()
    state.know([{'name': 'sw-a-01', 'address': '192.0.2.5'}])
    state.apply([Point('snmp_trap', {'source': '192.0.2.5'}, {'oid': 'x'}),
                 Point('snmp_trap', {'source': '203.0.113.8', 'sysName': 'sw-new'}, {'oid': 'x'}),
                 Point('gnmi_ifcounters', {'source': '203.0.113.9'}, {'in': 1})], now=NOW)
    rows = {r['address']: r for r in state.senders.rows(NOW)}
    assert set(rows) == {'203.0.113.8', '203.0.113.9'}
    assert (rows['203.0.113.8']['kind'], rows['203.0.113.8']['name']) == ('trap', 'sw-new')
    assert rows['203.0.113.9']['kind'] == 'stream'


def test_collect_merges_kinds_and_leaves_out_inventory_devices(monkeypatch):
    unknown_senders.syslog.note('syslog', '203.0.113.7', name='sw-x-09', agent='A', now=NOW - 60)
    unknown_senders.syslog.note('syslog', '192.0.2.5', now=NOW)
    monkeypatch.setattr(flow_store, 'latest', lambda: {'agent': 'B', 'exporters': [
        {'address': '203.0.113.7', 'flows': 40, 'last': NOW}, {'address': '192.0.2.5', 'flows': 1, 'last': NOW}]})
    monkeypatch.setattr(unknown_senders, '_telemetry', lambda: [
        {'kind': 'trap', 'address': '203.0.113.8', 'name': '', 'count': 3, 'first': NOW - 30, 'last': NOW - 30,
         'agents': ['A']}])
    data = {'inventory': [{'id': 'd1', 'name': 'sw-a-01', 'mgmt_ip': '192.0.2.5', 'hidden': True}],
            'unknown_senders_ignored': ['203.0.113.8']}
    rows = unknown_senders.collect(data, now=NOW)
    assert [r['address'] for r in rows] == ['203.0.113.7', '203.0.113.8']
    assert rows[0]['kinds'] == {'syslog': 1, 'flow': 40} and rows[0]['agents'] == ['A', 'B']
    assert rows[0]['name'] == 'sw-x-09' and not rows[0]['ignored'] and rows[1]['ignored']


def test_api_lists_ignores_and_raises_one_problem(client):
    unknown_senders.syslog.note('syslog', '203.0.113.7', name='sw-x-09', agent='A')
    rows = client.get('/api/inventory/unknown-senders').get_json()['senders']
    assert [r['address'] for r in rows] == ['203.0.113.7']
    look = [p for p in client.get('/api/problems').get_json()['attention'] if p['kind'] == 'unknown-senders']
    assert look and look[0]['link'] == '/inventory?view=unknown'
    assert client.post('/api/inventory/unknown-senders/ignore', json={'address': '203.0.113.7'}).status_code == 200
    assert client.get('/api/inventory/unknown-senders').get_json()['senders'][0]['ignored']
    assert not [p for p in client.get('/api/problems').get_json()['attention'] if p['kind'] == 'unknown-senders']
    # Adding it to the inventory takes it off the list.
    client.post('/api/inventory', json={'name': 'sw-x-09', 'role': 'switch', 'mgmt_ip': '203.0.113.7'})
    assert client.get('/api/inventory/unknown-senders').get_json()['senders'] == []


def test_viewers_cannot_ignore(client, kiosk_client):
    assert kiosk_client.post('/api/inventory/unknown-senders/ignore',
                             json={'address': '203.0.113.7'}).status_code in (401, 403)
