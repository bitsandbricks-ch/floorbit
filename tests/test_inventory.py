"""The inventory: hand edits, plugin syncs that never undo them, the move from the old layout,
the NetBox plugin and the API."""
import pytest
from conftest import TEST_PASSWORD

from floorbit import inventory
from floorbit.inventory import InventoryError

# ── Rules (no Flask) ────────────────────────────────────────────────────────────────────


def feed(*items):
    cleaned, skipped = inventory.clean_feed(list(items))
    assert skipped == 0
    return cleaned


def test_old_layout_moves_over_once_keeping_ids_and_positions():
    data = {'switches': [{'id': 'm1', 'name': 'sw-hand-01', 'x': 1, 'y': 2, 'placed': True}],
            'cached_devices': [{'id': '7', 'name': 'sw-nb-07', 'netbox_status': 'active'},
                               {'id': '8', 'name': 'sw-nb-08'}],
            'positions': {'7': {'x': 30, 'y': 40}}}
    assert inventory.migrate(data) is True
    assert not {'switches', 'cached_devices', 'positions'} & set(data)
    by_id = {d['id']: d for d in data['inventory']}
    assert by_id['m1']['origin'] == 'manual' and (by_id['m1']['x'], by_id['m1']['y']) == (1, 2)
    assert by_id['7']['refs'] == {'netbox': '7'} and by_id['7']['status'] == 'active'
    assert (by_id['7']['x'], by_id['7']['y']) == (30, 40)
    assert by_id['8']['x'] is None
    assert inventory.migrate(data) is False


def test_sync_adds_updates_and_flags_gone_but_never_deletes():
    data = {}
    r = inventory.sync(data, 'nb', feed({'id': '1', 'name': 'sw-01', 'model': 'X1'}, {'id': '2', 'name': 'sw-02'}))
    assert (r['added'], r['updated'], r['unchanged']) == (2, 0, 0)
    r = inventory.sync(data, 'nb', feed({'id': '1', 'name': 'sw-01', 'model': 'X2'}))
    assert (r['updated'], r['gone']) == (1, 1)
    devs = {d['name']: d for d in inventory.devices(data)}
    assert devs['sw-01']['model'] == 'X2'
    assert devs['sw-02']['gone'] == ['nb']   # still there
    r = inventory.sync(data, 'nb', feed({'id': '1', 'name': 'sw-01', 'model': 'X2'}, {'id': '2', 'name': 'sw-02'}))
    assert (r['back'], r['unchanged']) == (1, 2) and devs['sw-02']['gone'] == []
    assert len(inventory.sync_log(data)) == 3


def test_a_hand_edit_locks_the_field_until_unlocked():
    data = {}
    inventory.sync(data, 'nb', feed({'id': '1', 'name': 'sw-01', 'hall': 'Hall 1'}))
    dev = inventory.devices(data)[0]
    inventory.update(data, dev['id'], {'hall': 'Hall 2'})
    assert dev['locked'] == ['hall']
    r = inventory.sync(data, 'nb', feed({'id': '1', 'name': 'sw-01', 'hall': 'Hall 3'}))
    assert dev['hall'] == 'Hall 2' and r['locked'] == 1
    assert dev['fed']['nb']['hall'] == 'Hall 3'   # what NetBox says is kept for the page
    _, changed = inventory.update(data, dev['id'], {'unlock': ['hall']})
    assert dev['hall'] == 'Hall 3' and dev['locked'] == [] and changed == ['unlock:hall']


def test_editing_a_field_no_plugin_sends_does_not_lock_it():
    data = {}
    inventory.sync(data, 'nb', feed({'id': '1', 'name': 'sw-01'}))
    dev = inventory.devices(data)[0]
    inventory.update(data, dev['id'], {'notes': 'by the stage'})
    assert dev['locked'] == []


def test_a_plugin_joins_a_hand_made_device_by_name_and_keeps_what_differs():
    data = {}
    made = inventory.create(data, {'name': 'SW-Core', 'model': 'Hand model', 'x': 5, 'y': 6})
    r = inventory.sync(data, 'nb', feed({'id': '9', 'name': 'sw-core', 'model': 'NB model', 'serial': 'S1'}))
    assert r['joined'] == 1 and r['added'] == 0
    assert made['refs'] == {'nb': '9'} and made['origin'] == 'manual'
    assert made['model'] == 'Hand model' and made['serial'] == 'S1'
    assert sorted(made['locked']) == ['model', 'name']
    assert (made['x'], made['y']) == (5, 6)


def test_deleting_a_fed_device_hides_it_and_a_sync_keeps_it_hidden():
    data = {}
    inventory.sync(data, 'nb', feed({'id': '1', 'name': 'sw-01'}))
    dev = inventory.devices(data)[0]
    assert inventory.delete(data, dev['id']) == 'hidden'
    inventory.sync(data, 'nb', feed({'id': '1', 'name': 'sw-01'}))
    assert inventory.devices(data) == [] and len(inventory.devices(data, include_hidden=True)) == 1
    hand = inventory.create(data, {'name': 'sw-hand'})
    assert inventory.delete(data, hand['id']) == 'deleted'
    assert all(d['id'] != hand['id'] for d in inventory.devices(data, include_hidden=True))


def test_two_plugins_feed_one_device_without_fighting_over_ids():
    data = {}
    inventory.sync(data, 'nb', feed({'id': '1', 'name': 'sw-01', 'model': 'A'}))
    r = inventory.sync(data, 'other', feed({'id': '1', 'name': 'sw-01', 'serial': 'S'}))
    assert r['joined'] == 1
    [dev] = inventory.devices(data)
    assert dev['refs'] == {'nb': '1', 'other': '1'} and dev['model'] == 'A' and dev['serial'] == 'S'


def test_feed_entries_are_checked():
    cleaned, skipped = inventory.clean_feed([
        {'id': '1', 'name': 'ok', 'mgmt_ip': '192.0.2.10', 'role': 'Switch'},
        {'name': 'no id'},
        {'id': '1', 'name': 'duplicate id'},
        {'id': '3', 'name': 'bad ip', 'mgmt_ip': 'not-an-ip'},
        {'id': '4', 'name': 'two\nlines'},
        {'id': '5', 'name': 'bad role', 'role': 'toaster'},
        'not a dict',
    ])
    assert [c['name'] for c in cleaned] == ['ok'] and cleaned[0]['role'] == 'switch'
    assert skipped == 6
    with pytest.raises(InventoryError):
        inventory.clean_feed({'not': 'a list'})


def test_hand_input_is_checked():
    data = {}
    with pytest.raises(InventoryError):
        inventory.create(data, {'name': ''})
    with pytest.raises(InventoryError):
        inventory.create(data, {'name': 'x', 'mgmt_ip': '999.1.1.1'})
    dev = inventory.create(data, {'name': 'x', 'mgmt_ip': ' 2001:db8::1 '})
    assert dev['mgmt_ip'] == '2001:db8::1'


# ── NetBox plugin ────────────────────────────────────────────────────────────────────────

class FakeResponse:
    def __init__(self, payload, status=200):
        self._payload, self.status_code = payload, status

    def json(self):
        return self._payload


class FakeHttp:
    def __init__(self, pages):
        self.base = 'https://netbox.example.com'
        self.pages, self.calls = pages, []

    def get(self, path, **kw):
        self.calls.append((path, kw.get('params')))
        return self.pages[path]


def netbox_plugin(registry, http):
    from floorbit.plugins.base import Context
    spec = registry.specs['netbox']
    plugin = spec.plugin_class()(Context(spec, registry))
    plugin._client = lambda: http
    return plugin


NB_DEVICE = {'id': 12, 'name': 'sw-a-01', 'role': {'slug': 'access-switch'}, 'device_type': {'model': 'C9200'},
             'serial': 'FOC123', 'primary_ip': {'address': '192.0.2.5/24'}, 'site': {'name': 'Hall A'},
             'status': {'value': 'active'}}


def test_netbox_device_mapping_works_for_netbox_3_and_4():
    from floorbit.builtin_plugins.netbox.plugin import device
    assert device(NB_DEVICE) == {'id': '12', 'name': 'sw-a-01', 'role': 'switch', 'model': 'C9200',
                                 'serial': 'FOC123', 'mgmt_ip': '192.0.2.5', 'hall': 'Hall A', 'status': 'active'}
    old = {'id': 3, 'name': 'ap-1', 'device_role': {'slug': 'wifi-ap'}, 'location': {'name': 'Stage'}}
    assert device(old)['role'] == 'access-point' and device(old)['hall'] == 'Stage'
    assert device({'id': 4, 'name': 'x', 'role': {'slug': 'core'}})['role'] == 'other'


def test_netbox_follows_pages_on_the_same_host_only(app_module):
    registry = app_module.app.extensions['floorbit_plugins']
    http = FakeHttp({
        '/api/dcim/devices/': FakeResponse({'results': [NB_DEVICE, {'id': 13, 'name': None}],
                                            'next': 'https://netbox.example.com/api/dcim/devices/?offset=500'}),
        'https://netbox.example.com/api/dcim/devices/?offset=500': FakeResponse({'results': [], 'next': None}),
    })
    assert [d['name'] for d in netbox_plugin(registry, http).inventory()] == ['sw-a-01']
    assert http.calls[1][1] is None   # "next" carries its own query
    from floorbit.plugins import PluginError
    evil = FakeHttp({'/api/dcim/devices/': FakeResponse({'results': [], 'next': 'https://elsewhere.example.net/x'})})
    with pytest.raises(PluginError, match='another host'):
        netbox_plugin(registry, evil).inventory()


def test_netbox_ships_on_and_reads_the_old_settings(app_module, client):
    registry = app_module.app.extensions['floorbit_plugins']
    spec = registry.specs['netbox']
    assert spec.error == '' and registry.enabled(spec)
    client.put('/api/settings', json={'netbox.url': 'https://netbox.example.com',
                                      'netbox.device_roles': ['access-switch']})
    s = registry.settings_of(spec)
    assert s['url'] == 'https://netbox.example.com' and s['device_roles'] == ['access-switch']
    listed = {p['id']: p for p in client.get('/api/settings/plugins').get_json()['plugins']}
    assert listed['netbox']['settings_section'] == 'netbox' and listed['netbox']['default_enabled'] is True
    # Turned off by an admin: stays off.
    client.put('/api/settings/plugins/netbox', json={'enabled': False})
    assert not registry.enabled(spec)


def test_only_builtin_plugins_may_be_on_by_default(tmp_path, app_module):
    from floorbit.plugins import _load
    folder = tmp_path / 'p' / 'sneaky'
    folder.mkdir(parents=True)
    (folder / 'plugin.yaml').write_text('id: sneaky\nuses: [http]\ndefault_enabled: true\ncore_settings: auth\n')
    spec = _load(folder, 'development', '1.0')
    assert 'only for plugins that ship with Floorbit' in spec.error


# ── API ──────────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def fake_netbox(app_module, monkeypatch):
    """The NetBox plugin, answering with whatever the test puts in ``devices``."""
    registry = app_module.app.extensions['floorbit_plugins']
    devices = [dict(NB_DEVICE)]
    from floorbit.builtin_plugins.netbox.plugin import device
    # The class the registry loaded (plugin.py is imported under its own module name).
    cls = registry.specs['netbox'].plugin_class()
    monkeypatch.setattr(cls, 'inventory', lambda self: [device(d) for d in devices])
    return devices


def test_sync_endpoint_and_switch_api_share_one_inventory(client, fake_netbox):
    assert client.post('/api/inventory/sync').status_code == 200
    body = client.get('/api/inventory').get_json()
    [dev] = body['devices']
    assert dev['name'] == 'sw-a-01' and dev['sources'] == ['netbox'] and dev['placed'] is False
    assert body['sources'][0]['id'] == 'netbox' and body['sources'][0]['last_sync']['added'] == 1
    # The floor plan sees it as an unplaced NetBox switch, and placing it keeps it fed.
    [sw] = client.get('/api/switches').get_json()
    assert sw['source'] == 'netbox' and sw['netbox_status'] == 'active' and not sw['placed']
    assert client.put(f"/api/switches/{sw['id']}", json={'x': 10, 'y': 20}).get_json()['placed'] is True
    # Renaming it on the floor plan locks the name against NetBox.
    client.put(f"/api/switches/{sw['id']}", json={'name': 'Stage switch'})
    fake_netbox[0]['name'] = 'sw-a-01-renamed'
    client.post('/api/switches/sync')
    dev = client.get('/api/inventory').get_json()['devices'][0]
    assert dev['name'] == 'Stage switch' and dev['locked'] == ['name']
    assert dev['fed']['netbox']['name'] == 'sw-a-01-renamed'
    # Removing it from the floor plan only unplaces it.
    client.delete(f"/api/switches/{sw['id']}")
    assert client.get('/api/inventory').get_json()['devices'][0]['placed'] is False


def test_api_edits_unlock_and_hide(client, fake_netbox):
    client.post('/api/inventory/sync')
    dev = client.get('/api/inventory').get_json()['devices'][0]
    resp = client.patch(f"/api/inventory/{dev['id']}", json={'model': 'Custom', 'notes': 'rack 3'})
    assert resp.get_json()['locked'] == ['model'] and sorted(resp.get_json()['changed']) == ['model', 'notes']
    resp = client.patch(f"/api/inventory/{dev['id']}", json={'unlock': ['model']})
    assert resp.get_json()['model'] == 'C9200'
    assert client.patch(f"/api/inventory/{dev['id']}", json={'mgmt_ip': 'nope'}).status_code == 400
    assert client.delete(f"/api/inventory/{dev['id']}").get_json() == {'result': 'hidden'}
    assert client.get('/api/inventory').get_json()['devices'] == []
    assert len(client.get('/api/inventory?hidden=1').get_json()['devices']) == 1
    assert client.patch('/api/inventory/nope', json={}).status_code == 404


def test_a_failing_source_is_logged_not_fatal(client, app_module, monkeypatch):
    # NetBox is on by default but has no URL in tests: its sync fails with a clear message.
    resp = client.post('/api/inventory/sync').get_json()
    assert 'Set the NetBox URL' in resp['reports'][0]['error']
    assert 'Set the NetBox URL' in client.get('/api/inventory/log').get_json()['log'][0]['error']
    assert client.post('/api/switches/sync').status_code == 502


def test_who_may_do_what(app_module, anon_client, client, fake_netbox):
    users = app_module.app.extensions['auth'].users
    users.add('vi', TEST_PASSWORD, role='viewer')
    viewer = app_module.app.test_client()
    viewer.post('/login', data={'username': 'vi', 'password': TEST_PASSWORD})
    assert viewer.get('/api/inventory').status_code == 200
    assert viewer.post('/api/inventory', json={'name': 'x'}).status_code == 403
    assert viewer.post('/api/inventory/sync').status_code == 403
    assert viewer.get('/api/inventory/log').status_code == 403
    assert client.post('/api/inventory', json={'name': 'sw-new', 'role': 'switch'}).status_code == 201
    assert anon_client.post('/api/inventory', json={'name': 'x'}).status_code == 401


def test_old_backups_still_restore(client):
    old = {'format': 'floorbit-backup', 'version': 1, 'settings': {},
           'layout': {'switches': [{'id': 'm1', 'name': 'sw-old', 'x': 1, 'y': 1}],
                      'cached_devices': [{'id': '5', 'name': 'sw-nb'}], 'positions': {}, 'seat_blocks': []}}
    resp = client.post('/api/settings/backup', json=old)
    assert resp.status_code == 200, resp.get_json()
    names = sorted(d['name'] for d in client.get('/api/inventory').get_json()['devices'])
    assert names == ['sw-nb', 'sw-old']
    new = client.get('/api/settings/backup').get_json()
    assert 'inventory' in new['layout'] and 'switches' not in new['layout']
    assert client.post('/api/settings/backup', json=new).status_code == 200
    assert sorted(d['name'] for d in client.get('/api/inventory').get_json()['devices']) == ['sw-nb', 'sw-old']
