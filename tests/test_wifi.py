"""Wi-Fi view (issue #98): AP load and client counts per radio, on the floor plan."""
import pytest

from floorbit import wifi
from tests.test_rbac import sign_in_as


@pytest.fixture(autouse=True)
def fresh():
    wifi.reset()
    yield
    wifi.reset()


@pytest.fixture
def registry(app_module):
    return app_module.app.extensions['floorbit_plugins']


@pytest.fixture
def demo(client, registry):
    client.put('/api/settings/plugins/demo', json={'enabled': True})
    return client


def test_clean_ap_keeps_counts_only():
    raw = {'name': ' ap-1 ', 'model': 'U6', 'status': 'up', 'clients': None,
           'stations': [{'hostname': 'player-pc', 'mac': '02:00:00:00:00:01'}],
           'radios': [{'band': 'na', 'channel': '36', 'width': '80', 'utilization': 140, 'clients': 12,
                       'mac': '02:00:00:00:00:02'},
                      {'band': 'ng', 'channel': 6, 'width': 20, 'utilization': 31.6, 'clients': 3},
                      {'band': '60', 'channel': 1}]}
    ap = wifi.clean_ap(raw)
    assert ap == {'name': 'ap-1', 'model': 'U6', 'status': 'up', 'clients': 15, 'radios': [
        {'band': '2.4', 'channel': 6, 'width': 20, 'utilization': 32, 'clients': 3},
        {'band': '5', 'channel': 36, 'width': 80, 'utilization': None, 'clients': 12}]}
    assert 'mac' not in str(ap) and 'player' not in str(ap)
    assert wifi.clean_ap({'name': ''}) is None and wifi.clean_ap('x') is None
    assert wifi.clean_ap({'name': 'a', 'status': 'offline'})['status'] == 'down'


def test_no_wifi_plugin(client):
    body = client.get('/api/wifi').get_json()
    assert body['aps'] == [] and body['sources'] == [] and body['clients'] == 0


def test_demo_aps_on_the_plan(demo):
    demo.post('/api/demo/layout')
    body = demo.get('/api/wifi').get_json()
    names = [a['name'] for a in body['aps']]
    assert 'ap-stage' in names and len(names) == 9
    assert all(a['on_plan'] and a['px'] is not None for a in body['aps'])
    assert 'ap-stage' in body['busy']
    assert body['overlaps'] == [{'band': '5', 'channel': 44, 'aps': ['ap-02', 'ap-03']}]
    assert body['clients'] == sum(a['clients'] for a in body['aps'])
    assert set(body['bands']) == {'2.4', '5'} and body['drawing']['shapes']
    x, y, w, h = (float(v) for v in body['drawing']['box'].split())
    assert all(x <= a['px'] <= x + w and y <= a['py'] <= y + h for a in body['aps'])
    assert demo.get('/api/wifi?hall=nope').status_code == 404


def test_unplaced_aps_are_listed_not_drawn(demo):
    body = demo.get('/api/wifi').get_json()
    assert len(body['aps']) == 9 and not any(a['on_plan'] for a in body['aps'])
    assert body['overlaps'] == []


def test_plugin_failure_is_shown(demo, registry, monkeypatch):
    from floorbit.plugins import PluginError

    def broken(self):
        raise PluginError('controller down')
    monkeypatch.setattr(registry.specs['demo'].plugin_class(), 'wifi_aps', broken)
    body = demo.get('/api/wifi').get_json()
    assert body['aps'] == [] and body['errors'] == ['Demo data: controller down']


def test_viewers_see_the_counts(app_module, demo):
    viewer = sign_in_as(app_module, 'vi1', 'viewer')
    assert viewer.get('/api/wifi').status_code == 200
    assert viewer.get('/wifi').status_code == 200


def test_unifi_wifi_aps(registry):
    from floorbit.plugins.base import Context
    spec = registry.specs['unifi']
    plugin = spec.plugin_class()(Context(spec, registry))
    plugin._get = lambda what: [
        {'type': 'usw', 'name': 'sw-1'},
        {'type': 'uap', 'name': 'ap-hall-01', 'model': 'U6PRO', 'state': 1, 'num_sta': 21,
         'radio_table': [{'radio': 'ng', 'ht': '20'}, {'radio': 'na', 'ht': '80'}],
         'radio_table_stats': [{'radio': 'ng', 'channel': 1, 'cu_total': 55, 'num_sta': 5},
                               {'radio': 'na', 'channel': 44, 'cu_total': 20, 'num_sta': 16}]},
        {'type': 'uap', 'name': 'ap-hall-02', 'state': 0}]
    aps = [wifi.clean_ap(a) for a in plugin.wifi_aps()]
    assert [a['name'] for a in aps] == ['ap-hall-01', 'ap-hall-02']
    assert aps[0]['radios'][1] == {'band': '5', 'channel': 44, 'width': 80, 'utilization': 20, 'clients': 16}
    assert aps[0]['clients'] == 21 and aps[1]['status'] == 'down'
