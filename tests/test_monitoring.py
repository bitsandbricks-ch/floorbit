"""LibreNMS as the built-in monitoring plugin, and the core asking ``sources.monitoring()``."""
import pytest

from floorbit import sources
from integrations import checkin
from integrations.monitor import StatusMonitor


@pytest.fixture
def registry(app_module):
    return app_module.app.extensions['floorbit_plugins']


@pytest.fixture
def librenms(registry, monkeypatch):
    """The LibreNMS plugin, set up, with its API client answering from ``fake`` instead of the network."""
    from floorbit import runtime
    from floorbit.builtin_plugins.librenms import client as nms
    monkeypatch.setattr(runtime.rt, 'librenms_enabled', True)
    fake = {'devices': [{'display': 'sw-a-01', 'hostname': 'sw-a-01.example.com', 'status': 1}],
            'arp': [{'ipv4_address': '192.0.2.11', 'mac_address': '02-00-00-00-00-11'}]}
    monkeypatch.setattr(nms, 'list_devices', lambda: fake['devices'])
    monkeypatch.setattr(nms, 'arp_entries', lambda query: [
        e for e in fake['arp'] if query in (e['ipv4_address'], sources.normalise_mac(e['mac_address']))])
    return fake


def test_librenms_ships_on_and_is_the_monitoring_source(registry, app_module):
    spec = registry.specs['librenms']
    assert spec.error == '' and registry.enabled(spec)
    assert sources.monitoring().name == 'librenms'
    # Not set up yet (no URL or token): the floor plan shows everything as unknown.
    assert sources.monitoring().enabled() is False


def test_turning_the_plugin_off_turns_monitoring_off(client, registry, librenms):
    assert client.get('/api/config').get_json()['librenms_enabled'] is True
    client.put('/api/settings/plugins/librenms', json={'enabled': False})
    assert isinstance(sources.monitoring(), sources.NoMonitoring)
    body = client.get('/api/config').get_json()
    assert body['librenms_enabled'] is False and body['monitoring_source'] is None
    assert client.get('/api/switches/x/status').get_json()['status'] == 'unknown'


def test_status_monitor_reads_devices_through_the_plugin(app_module, librenms, monkeypatch):
    monkeypatch.setenv('STATUS_MONITOR_CONFIRM', '1')
    m = StatusMonitor(lambda: [{'id': '1', 'name': 'sw-a-01'}])
    assert m.enabled()
    m.poll_once()
    librenms['devices'][0]['status'] = 0
    assert m.poll_once()[0]['status'] == 'offline'


def test_check_in_looks_up_arp_through_the_plugin(app_module, librenms):
    assert checkin.lookup_mac('192.0.2.11') == '02:00:00:00:00:11'
    assert checkin.lookup_ip('02:00:00:00:00:11') == '192.0.2.11'
    assert checkin.lookup_mac('192.0.2.99') is None


def test_a_failing_plugin_reads_as_unknown_and_is_logged(registry, librenms, monkeypatch):
    from floorbit.builtin_plugins.librenms import client as nms

    def boom(*a):
        raise ConnectionError('no route to host')
    monkeypatch.setattr(nms, 'arp_entries', boom)
    monkeypatch.setattr(nms, 'fetch_librenms_details', boom)
    assert checkin.lookup_mac('192.0.2.11') is None
    assert sources.monitoring().device_details('sw-a-01')['status'] == 'unknown'
    assert any(e['line'].startswith('arp failed: ConnectionError') for e in registry.logs.get('librenms'))


def test_use_swaps_the_source_and_none_goes_back(app_module):
    class Fake(sources.NoMonitoring):
        name = 'fake'

        def enabled(self):
            return True
    previous = sources.use(Fake())
    try:
        assert sources.monitoring().name == 'fake'
    finally:
        sources.use(previous)
    assert sources.monitoring().name == 'librenms'


def test_monitoring_methods_need_the_area(tmp_path):
    from floorbit.plugins import _load
    folder = tmp_path / 'p' / 'nms'
    folder.mkdir(parents=True)
    (folder / 'plugin.yaml').write_text('id: nms\nuses: [http]\n')
    (folder / 'plugin.py').write_text('from floorbit.plugins.base import Plugin as P\n'
                                      'class Plugin(P):\n    def resolve_ip(self, ip, d=None):\n        return None\n')
    assert 'needs "monitoring"' in _load(folder, 'development', '1.0').error
    (folder / 'plugin.yaml').write_text('id: nms\nuses: [monitoring]\n')
    assert 'Plugin has no' in _load(folder, 'development', '1.0').error
