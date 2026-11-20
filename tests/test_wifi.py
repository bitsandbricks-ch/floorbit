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


def test_no_wifi_plugin(lan_here, client):
    body = client.get('/api/wifi').get_json()
    assert body['aps'] == [] and body['sources'] == [] and body['clients'] == 0


def test_demo_aps_on_the_plan(demo):
    demo.post('/api/demo/layout')
    body = demo.get('/api/wifi').get_json()
    names = [a['name'] for a in body['aps']]
    assert 'ap-stage' in names and len(names) == 10
    here = [a for a in body['aps'] if a['name'] != 'ap-10']      # ap-10 is in the side hall
    assert all(a['on_plan'] and a['px'] is not None for a in here)
    assert 'ap-stage' in body['busy']
    assert body['overlaps'] == [{'band': '5', 'channel': 44, 'aps': ['ap-02', 'ap-03']}]
    assert body['clients'] == sum(a['clients'] for a in body['aps'])
    assert set(body['bands']) == {'2.4', '5'} and body['drawing']['shapes']
    x, y, w, h = (float(v) for v in body['drawing']['box'].split())
    assert all(x <= a['px'] <= x + w and y <= a['py'] <= y + h for a in here)
    assert demo.get('/api/wifi?hall=nope').status_code == 404


def test_unplaced_aps_are_listed_not_drawn(demo):
    body = demo.get('/api/wifi').get_json()
    assert len(body['aps']) == 10 and not any(a['on_plan'] for a in body['aps'])
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



def test_turning_a_plugin_off_shows_at_once(demo):
    """#1056: the crew turns a plugin on or off and looks at the page right after."""
    assert len(demo.get('/api/wifi').get_json()['aps']) == 10
    demo.put('/api/settings/plugins/demo', json={'enabled': False})
    assert demo.get('/api/wifi').get_json()['aps'] == []
    demo.put('/api/settings/plugins/demo', json={'enabled': True})
    assert len(demo.get('/api/wifi').get_json()['aps']) == 10


def test_saving_settings_drops_the_cached_view(demo):
    demo.get('/api/wifi')
    assert wifi._cache['value'] is not None
    assert demo.put('/api/settings', json={'cache.ttl_arp': 61}).status_code == 200
    assert wifi._cache['value'] is None
