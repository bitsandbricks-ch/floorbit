"""Seat mapping: hand entries that win over every other source, CSV in and out, plugin feeds,
and who may see it."""
import pytest
from conftest import TEST_PASSWORD

from floorbit import seatmap
from floorbit.seatmap import MappingError


def test_values_are_checked_and_normalised():
    assert seatmap.clean_mac('AA-BB-CC-DD-EE-FF') == 'aa:bb:cc:dd:ee:ff'
    assert seatmap.clean_mac('aabb.ccdd.eeff') == 'aa:bb:cc:dd:ee:ff'
    assert seatmap.clean_ip(' 2001:DB8::1 ') == '2001:db8::1'
    for bad in (lambda: seatmap.clean_mac('aa:bb'), lambda: seatmap.clean_ip('300.1.1.1'),
                lambda: seatmap.clean_seat('A-1; DROP'), lambda: seatmap.clean_entry({'nick': 'a\nb'})):
        with pytest.raises(MappingError):
            bad()


def test_an_entry_with_nothing_left_is_removed():
    data = {}
    assert seatmap.put(data, 'A-1', {'ip': '192.0.2.1', 'nick': 'player1'}, user='ed')['updated_by'] == 'ed'
    assert seatmap.put(data, 'A-1', {'ip': '', 'nick': ''}) is None
    assert seatmap.entries(data) == {}


def test_csv_round_trip_escapes_formulas():
    data = {}
    seatmap.put(data, 'A-2', {'nick': '=HYPERLINK("x")', 'mac': 'aabbccddeeff'})
    seatmap.put(data, 'A-10', {'ip': '192.0.2.10'})
    text = seatmap.to_csv(data)
    assert text.splitlines()[0] == 'seat,ip,mac,nick,note'
    assert [line.split(',')[0] for line in text.splitlines()[1:]] == ['A-2', 'A-10']   # natural order
    assert "'=HYPERLINK" in text
    rows, errors = seatmap.parse_csv(text)
    assert errors == [] and rows['A-2']['username'] == '=HYPERLINK("x")'


def test_csv_import_checks_every_row_first():
    _rows, errors = seatmap.parse_csv('seat,ip,mac\nA-1,192.0.2.1,\nA-2,nope,\nA-1,192.0.2.3,\n,,\n')
    assert errors == ['line 3: "nope" is not an IP address', 'line 4: seat A-1 is in the file twice']
    with pytest.raises(MappingError, match='Unknown column'):
        seatmap.parse_csv('seat,password\nA-1,x\n')
    with pytest.raises(MappingError, match='name the columns'):
        seatmap.parse_csv('A-1,192.0.2.1\n')


# ── API ──────────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def seats_file(tmp_path, monkeypatch):
    from integrations import seat_sources
    f = tmp_path / 'seats.json'
    f.write_text('{"seats": {"A-1": {"username": "from-file", "ip_address": "192.0.2.1"},'
                 ' "A-2": {"username": "other", "ip_address": "192.0.2.2"}}}')
    monkeypatch.setenv('SEAT_SOURCE_JSON_PATH', str(f))
    monkeypatch.setenv('SEAT_SOURCES', 'json')
    seat_sources.invalidate()
    yield f
    seat_sources.invalidate()


def test_hand_entries_win_field_by_field(client, seats_file):
    resp = client.put('/api/seat-map/A-1', json={'ip': '192.0.2.99', 'mac': 'AA-BB-CC-DD-EE-01'})
    assert resp.status_code == 200 and resp.get_json()['entry']['mac'] == 'aa:bb:cc:dd:ee:01'
    rows = {r['seat']: r for r in client.get('/api/seat-map').get_json()['seats']}
    a1 = rows['A-1']
    assert (a1['ip'], a1['mac'], a1['nick']) == ('192.0.2.99', 'aa:bb:cc:dd:ee:01', 'from-file')
    assert a1['from'] == {'ip': 'manual', 'mac': 'manual', 'nick': 'json'}
    assert rows['A-2']['manual'] is None
    # The floor plan's merged mapping has it too, without who typed it in.
    info = client.get('/api/seats/info').get_json()['seats']['A-1']
    assert info['ip_address'] == '192.0.2.99' and 'updated_by' not in info
    assert client.delete('/api/seat-map/A-1').status_code == 200
    rows = {r['seat']: r for r in client.get('/api/seat-map').get_json()['seats']}
    assert rows['A-1']['ip'] == '192.0.2.1'
    assert client.delete('/api/seat-map/A-1').status_code == 404


def test_bad_input_is_refused(client, seats_file):
    assert client.put('/api/seat-map/A-1', json={'mac': 'zz'}).status_code == 400
    assert client.put('/api/seat-map/A%201%3B', json={'ip': '192.0.2.1'}).status_code == 400


def test_import_dry_run_then_replace(client, seats_file):
    client.put('/api/seat-map/Z-9', json={'nick': 'old'})
    csv = 'seat,ip,nick\nA-1,192.0.2.50,imported\nB-1,192.0.2.51,\n'
    dry = client.post('/api/seat-map/import', json={'csv': csv, 'replace': True, 'dry_run': True}).get_json()
    assert dry == {'dry_run': True, 'added': 2, 'updated': 0, 'removed': 1}
    assert {r['seat'] for r in client.get('/api/seat-map').get_json()['seats'] if r['manual']} == {'Z-9'}
    done = client.post('/api/seat-map/import', json={'csv': csv, 'replace': True}).get_json()
    assert done == {'added': 2, 'updated': 0, 'removed': 1}
    manual = {r['seat'] for r in client.get('/api/seat-map').get_json()['seats'] if r['manual']}
    assert manual == {'A-1', 'B-1'}
    bad = client.post('/api/seat-map/import', json={'csv': 'seat,ip\nA-1,nope\n'})
    assert bad.status_code == 400 and bad.get_json()['problems'] == ['line 2: "nope" is not an IP address']
    export = client.get('/api/seat-map.csv')
    assert export.mimetype == 'text/csv' and b'A-1,192.0.2.50' in export.data


def test_changes_are_audited_without_values(client, app_module, seats_file):
    from floorbit import audit
    client.put('/api/seat-map/A-1', json={'nick': 'secret-nick', 'ip': '192.0.2.7'})
    entry = audit.read(limit=1)[0][0]
    assert entry['area'] == 'seat mapping' and entry['target'] == 'A-1'
    assert entry['fields'] == ['ip', 'nick'] and 'secret-nick' not in str(entry)


def test_only_editors_see_it_never_the_public(app_module, anon_client, seats_file):
    users = app_module.app.extensions['auth'].users
    users.add('vi', TEST_PASSWORD, role='viewer')
    viewer = app_module.app.test_client()
    viewer.post('/login', data={'username': 'vi', 'password': TEST_PASSWORD})
    for c, code in ((anon_client, 401), (viewer, 403)):
        assert c.get('/api/seat-map').status_code == code
        assert c.get('/api/seat-map.csv').status_code == code
        assert c.get('/seat-mapping').status_code in (302, 403)


def test_a_plugin_feeds_the_mapping_after_hand_entries(client, app_module, seats_file, tmp_path, monkeypatch):
    from floorbit.plugins import _load
    registry = app_module.app.extensions['floorbit_plugins']
    folder = tmp_path / 'p' / 'dhcp-feed'
    folder.mkdir(parents=True)
    (folder / 'plugin.yaml').write_text('id: dhcp-feed\nname: DHCP feed\nuses: [mapping]\n')
    (folder / 'plugin.py').write_text(
        'from floorbit.plugins.base import Plugin as B\n'
        'class Plugin(B):\n'
        '    def seat_mapping(self):\n'
        "        return {'A-2': {'mac': 'aa:bb:cc:00:00:02', 'ip': '192.0.2.200'}, 'bad seat!': {'ip': '1'},\n"
        "                'C-1': {'mac': 'not-a-mac'}}\n")
    spec = _load(folder, 'development', registry.version)
    assert spec.error == ''
    registry.specs[spec.id] = spec
    try:
        client.put('/api/settings/plugins/dhcp-feed', json={'enabled': True})
        client.put('/api/seat-map/A-2', json={'ip': '192.0.2.22'})
        body = client.get('/api/seat-map').get_json()
        assert body['sources'][:2] == ['manual', 'dhcp-feed'] and body['labels']['dhcp-feed'] == 'DHCP feed'
        a2 = {r['seat']: r for r in body['seats']}['A-2']
        assert (a2['ip'], a2['mac']) == ('192.0.2.22', 'aa:bb:cc:00:00:02')
        assert a2['from'] == {'ip': 'manual', 'mac': 'dhcp-feed', 'nick': 'json'}
        assert 'C-1' not in {r['seat'] for r in body['seats']}
    finally:
        registry.specs.pop(spec.id, None)


def test_mapping_method_needs_the_area(tmp_path):
    from floorbit.plugins import _load
    folder = tmp_path / 'p' / 'sneaky'
    folder.mkdir(parents=True)
    (folder / 'plugin.yaml').write_text('id: sneaky\nuses: [http]\n')
    (folder / 'plugin.py').write_text(
        'from floorbit.plugins.base import Plugin as B\n'
        'class Plugin(B):\n    def seat_mapping(self):\n        return {}\n')
    assert 'needs "mapping"' in _load(folder, 'development', '1.0').error
