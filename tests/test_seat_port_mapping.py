"""The seat mapping is keyed by switch port; the IP and MAC are read off the port (Mike, 2026-11-16)."""
import pytest

from floorbit import seatmap
from floorbit.seatmap import MappingError


@pytest.fixture
def seats_file(tmp_path, monkeypatch):
    from integrations import seat_sources
    f = tmp_path / 'seats.json'
    f.write_text('{"seats": {"A-1": {"username": "from-file", "ip_address": "192.0.2.1"}}}')
    monkeypatch.setenv('SEAT_SOURCE_JSON_PATH', str(f))
    monkeypatch.setenv('SEAT_SOURCES', 'json')
    seat_sources.invalidate()
    yield f
    seat_sources.invalidate()


@pytest.fixture
def finder(app_module):
    f = app_module.app.extensions['floorbit_port_clients']
    yield f
    f.reset()


class FakeMonitor:
    def __init__(self, seen):
        self.seen = seen      # {ip: (mac, switch, port)}

    def enabled(self):
        return True

    def ip_for_mac(self, mac):
        return next((ip for ip, (m, _s, _p) in self.seen.items() if m == mac), None)

    def mac_for_ip(self, ip):
        return (self.seen.get(ip) or (None,))[0]

    def resolve_ip(self, ip, search_device=None):
        hit = self.seen.get(ip)
        return {'device_name': hit[1], 'port': hit[2]} if hit else {}


def _rows(client):
    return {r['seat']: r for r in client.get('/api/seat-map').get_json()['seats']}


def test_a_port_needs_its_switch_and_one_port_is_one_seat():
    data = {}
    for body in ({'port': 'Gi1/0/3'}, {'switch': 'sw-a-01'}):
        with pytest.raises(MappingError):
            seatmap.put(data, 'A-3', body)
    seatmap.put(data, 'A-3', {'switch': 'sw-a-01', 'port': 'Gi1/0/3'})
    with pytest.raises(MappingError, match='already seat A-3'):
        seatmap.put(data, 'A-4', {'switch': 'SW-A-01', 'port': 'gi1/0/3'})
    assert seatmap.put(data, 'A-3', {'switch': 'sw-a-01', 'port': 'Gi1/0/3', 'nick': 'p1'})['port'] == 'Gi1/0/3'


def test_the_port_comes_from_a_cable_and_a_hand_entry_overrides_it(client, seats_file):
    client.post('/api/cables', json={'switch': 'sw-a-01', 'port': 'Gi1/0/5', 'seat': 'A-5'})
    a5 = _rows(client)['A-5']
    assert (a5['switch'], a5['port'], a5['port_origin']) == ('sw-a-01', 'Gi1/0/5', 'cable')
    assert client.put('/api/seat-map/A-5', json={'switch': 'sw-a-01', 'port': 'Gi1/0/6'}).status_code == 200
    a5 = _rows(client)['A-5']
    assert (a5['port'], a5['port_origin'], a5['from']['port']) == ('Gi1/0/6', 'manual', 'manual')


def test_ip_and_mac_are_read_off_the_port_before_a_file(client, seats_file, finder):
    finder.seat_macs = {'A-1': {'mac_address': '02:00:00:00:00:01', 'ip_address': '192.0.2.101'}}
    a1 = _rows(client)['A-1']
    assert (a1['ip'], a1['mac'], a1['nick']) == ('192.0.2.101', '02:00:00:00:00:01', 'from-file')
    assert a1['from'] == {'ip': 'network', 'mac': 'network', 'nick': 'json'}


def test_a_port_with_two_machines_names_no_mac(app_module):
    from floorbit import port_clients

    class Monitor(FakeMonitor):
        def port_clients(self, switch):
            return [{'port': 'Gi1/0/1', 'mac': '02:00:00:00:00:01'}, {'port': 'Gi1/0/1', 'mac': '02:00:00:00:00:02'},
                    {'port': 'Gi1/0/2', 'mac': '02:00:00:00:00:03'}]

        def arp(self, net):
            return []

    data = {'cables': [{'id': 'c1', 'label': 'C-1', 'switch': 'sw-a-01', 'port': 'Gi1/0/1', 'seat': 'A-1'},
                       {'id': 'c2', 'label': 'C-2', 'switch': 'sw-a-01', 'port': 'Gi1/0/2', 'seat': 'A-2'}]}
    result = port_clients.find(Monitor({}), data, {})
    assert result['seat_macs'] == {'A-2': {'mac_address': '02:00:00:00:00:03', 'ip_address': ''}}


def test_find_a_port_by_mac(client, seats_file, monkeypatch):
    from floorbit.blueprints import seat_map
    monitor = FakeMonitor({'192.0.2.9': ('02:00:00:00:00:09', 'sw-b-01', 'Gi1/0/9')})
    monkeypatch.setattr(seat_map.sources, 'monitoring', lambda: monitor)
    body = client.post('/api/seat-map/find-port', json={'mac': '0200.0000.0009', 'seat': 'B-9'}).get_json()
    assert body == {'switch': 'sw-b-01', 'port': 'Gi1/0/9', 'ip': '192.0.2.9', 'mac': '02:00:00:00:00:09',
                    'held_by': None}
    client.put('/api/seat-map/B-8', json={'switch': 'sw-b-01', 'port': 'Gi1/0/9'})
    again = client.post('/api/seat-map/find-port', json={'ip': '192.0.2.9', 'seat': 'B-9'}).get_json()
    assert again['held_by'] == 'B-8'
    assert client.post('/api/seat-map/find-port', json={'mac': '02:00:00:00:00:77'}).status_code == 404
    assert client.post('/api/seat-map/find-port', json={}).status_code == 400


def test_old_ip_entries_get_their_port(client, seats_file, monkeypatch):
    from floorbit.blueprints import seat_map
    monitor = FakeMonitor({'192.0.2.11': ('02:00:00:00:00:11', 'sw-a-01', 'Gi1/0/11'),
                           '192.0.2.12': ('02:00:00:00:00:12', 'sw-a-01', 'Gi1/0/12')})
    monkeypatch.setattr(seat_map.sources, 'monitoring', lambda: monitor)
    client.put('/api/seat-map/A-11', json={'ip': '192.0.2.11', 'nick': 'p11'})
    client.put('/api/seat-map/A-12', json={'mac': '02:00:00:00:00:12'})
    client.put('/api/seat-map/A-13', json={'ip': '192.0.2.13'})
    client.put('/api/seat-map/A-14', json={'switch': 'sw-a-01', 'port': 'Gi1/0/12'})
    dry = client.post('/api/seat-map/resolve-ports', json={'dry_run': True}).get_json()
    assert set(dry['found']) == {'A-11', 'A-12'} and dry['missed'] == ['A-13']
    assert _rows(client)['A-11']['port'] == ''
    done = client.post('/api/seat-map/resolve-ports', json={}).get_json()
    assert done['found'] == {'A-11': {'switch': 'sw-a-01', 'port': 'Gi1/0/11'}}
    assert done['taken'] == [{'seat': 'A-12', 'held_by': 'A-14', 'switch': 'sw-a-01', 'port': 'Gi1/0/12'}]
    a11 = _rows(client)['A-11']
    assert (a11['port'], a11['nick'], a11['ip']) == ('Gi1/0/11', 'p11', '192.0.2.11')


def test_csv_carries_the_port_and_refuses_a_port_twice(client, seats_file):
    ok = client.post('/api/seat-map/import', json={'csv': 'seat,switch,port\nA-1,sw-a-01,Gi1/0/1\n'})
    assert ok.status_code == 200
    assert b'A-1,sw-a-01,Gi1/0/1' in client.get('/api/seat-map.csv').data
    csv = 'seat,switch,port\nA-2,sw-a-01,Gi1/0/2\nA-3,sw-a-01,gi1/0/2\n'
    twice = client.post('/api/seat-map/import', json={'csv': csv})
    assert twice.status_code == 400 and 'already seat A-2' in twice.get_json()['problems'][0]
    held = client.post('/api/seat-map/import', json={'csv': 'seat,switch,port\nA-4,sw-a-01,Gi1/0/1\n'})
    assert held.status_code == 400 and 'already seat A-1' in held.get_json()['problems'][0]
    assert client.post('/api/seat-map/import', json={'csv': 'seat,switch,port\nA-4,sw-a-01,Gi1/0/1\n',
                                                     'replace': True}).status_code == 200


def test_port_actions_use_the_mapped_port(client, seats_file):
    from floorbit import ports
    client.put('/api/seat-map/A-7', json={'switch': 'sw-a-01', 'port': 'Gi1/0/7'})
    assert ports.resolve_seat('A-7') == ('sw-a-01', 'Gi1/0/7')


def test_port_actions_find_a_seat_known_only_by_its_mac(client, seats_file, monkeypatch):
    from floorbit import ports, sources

    class Monitor:
        def ip_for_mac(self, mac):
            return '192.0.2.8' if mac == '02:00:00:00:00:08' else None

        def resolve_ip(self, ip):
            return {'device_name': 'sw-a-01', 'port': 'Gi1/0/8'} if ip == '192.0.2.8' else None
    monkeypatch.setattr(sources, 'monitoring', lambda: Monitor())
    client.put('/api/seat-map/A-8', json={'mac': '02:00:00:00:00:08'})
    assert ports.resolve_seat('A-8') == ('sw-a-01', 'Gi1/0/8')


def test_the_port_list_says_which_seat_holds_a_mapped_port(client, seats_file, monkeypatch):
    from floorbit import sources

    class Monitor:
        def device_ports(self, switch):
            return [{'name': 'Gi1/0/1'}, {'name': 'Gi1/0/2'}]

    monkeypatch.setattr(sources, 'monitoring', lambda: Monitor())
    client.put('/api/seat-map/A-2', json={'switch': 'sw-a-01', 'port': 'Gi1/0/2'})
    rows = client.get('/api/options/ports?switch=sw-a-01').get_json()['options']
    assert [(o['value'], o['used']) for o in rows] == [('Gi1/0/1', None), ('Gi1/0/2', 'A-2')]
