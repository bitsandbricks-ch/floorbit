"""Plugins in Problems (issue #1065): turned on but not loading, failing for a while, withdrawn."""
import json

import pytest

from floorbit import marketplace
from floorbit.plugins import PluginError, bundles
from tests.test_marketplace import market  # noqa: F401  # the fixture


@pytest.fixture
def registry(app_module):
    return app_module.app.extensions['floorbit_plugins']


def plugin_problems(client, lang=None):
    body = client.get('/api/problems', headers={'Accept-Language': lang} if lang else {}).get_json()
    return {p['id']: p for p in body['problems'] if p['kind'] == 'plugin'}


def test_a_plugin_turned_on_that_does_not_load(client, registry, monkeypatch):
    assert client.put('/api/settings/plugins/demo', json={'enabled': True}).status_code == 200
    spec = registry.specs['demo']
    monkeypatch.setattr(spec, 'error', 'plugin.py: SyntaxError on line 3')
    found = plugin_problems(client)['plugin:load:demo']
    assert (found['level'], found['title'], found['where']) == ('down', f'{spec.name} does not load',
                                                                 'plugin.py: SyntaxError on line 3')
    assert found['link'] == '/settings/plugins/demo'
    assert plugin_problems(client, 'de-CH')['plugin:load:demo']['title'] == f'{spec.name} lädt nicht'
    client.put('/api/settings/plugins/demo', json={'enabled': False})
    assert plugin_problems(client) == {}      # off on purpose: not a problem


def test_a_plugin_whose_calls_keep_failing(client, registry, monkeypatch):
    assert client.put('/api/settings/plugins/demo', json={'enabled': True}).status_code == 200
    spec = registry.specs['demo']

    def broken(self):
        raise PluginError('the controller refused the login')
    # Every call fails, the seat mapping too (Problems reads the seat sources, which ask the plugin).
    for method in ('wifi_aps', 'seat_mapping'):
        monkeypatch.setattr(spec.plugin_class(), method, broken)
    with pytest.raises(PluginError):
        registry.call(spec, 'wifi_aps')
    assert plugin_problems(client) == {}      # one failure isn't a problem yet
    since, message = registry.failing()['demo']
    registry._failing[('demo', 'wifi_aps')] = (since - 301, message)
    found = plugin_problems(client)['plugin:failing:demo']
    assert found['level'] == 'warn' and found['where'] == 'the controller refused the login'
    monkeypatch.undo()
    registry.call(spec, 'wifi_aps')           # works again
    # Failing is kept per method, and the seat sources may also have caught seat_mapping failing
    # (in this test's Problems call or the background loop), so check only the method that recovered.
    assert ('demo', 'wifi_aps') not in registry._failing


def test_a_withdrawn_version_that_still_runs(client, market):  # noqa: F811
    market.publish('hallthing', '1.0.0')
    assert client.post('/api/settings/marketplace/hallthing', json={}).status_code == 200
    assert plugin_problems(client) == {}
    # 1.0.0 is withdrawn in a newer index, while this Floorbit still runs it.
    index = next(u for u in market.files if u.endswith('index.json'))
    doc = json.loads(market.files[index])
    doc['plugins'][0]['versions'][0]['withdrawn'] = 'Clears the cache on start'
    doc.pop('signature', None)
    market.files[index] = json.dumps(bundles.sign_index({**doc, 'generated': '2026-11-18'}, market.index_pem)).encode()
    marketplace._cache.clear()
    marketplace.fetch_index(marketplace.source(), force=True)   # what the background loop does
    found = plugin_problems(client)['plugin:withdrawn:hallthing:1.0.0']
    assert found['title'] == 'Hall thing 1.0.0 was withdrawn' and found['where'] == 'Clears the cache on start'
    assert found['link'] == '/settings/plugins?tab=updates'


def test_a_working_method_does_not_hide_another_that_keeps_failing(client, registry, monkeypatch):
    """#1225: the seat sources ask the seat mapping every 30 s; it working must not clear the Wi-Fi
    access points failing."""
    registry._failing.clear()     # the app's registry: other tests' failures stay in it
    assert client.put('/api/settings/plugins/demo', json={'enabled': True}).status_code == 200
    spec = registry.specs['demo']

    def broken(self):
        raise PluginError('the controller refused the login')
    monkeypatch.setattr(spec.plugin_class(), 'wifi_aps', broken)
    with pytest.raises(PluginError):
        registry.call(spec, 'wifi_aps')
    registry.call(spec, 'seat_mapping')        # another job of the same plugin works
    since, message = registry.failing()['demo']
    assert message == 'the controller refused the login'
    registry._failing[('demo', 'wifi_aps')] = (since - 301, message)
    assert plugin_problems(client)['plugin:failing:demo']['where'] == 'the controller refused the login'
    monkeypatch.undo()
    registry.call(spec, 'wifi_aps')
    assert 'demo' not in registry.failing()
