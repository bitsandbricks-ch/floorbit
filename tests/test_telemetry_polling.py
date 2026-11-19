"""Who polls the switches: LibreNMS or Telemetry (issue #945, floorbit/telemetry/polling.py)."""
import pytest

from floorbit import sources
from floorbit.telemetry import polling, telegraf

SWITCH = {'name': 'access-01', 'address': '192.0.2.21', 'drivers': ['snmp', 'traps'], 'platform': 'ios',
          'kind': 'switch', 'community': 'example-community', 'fdb': 'cisco_vlans', 'vlans': [10]}


@pytest.fixture
def registry(app_module):
    return app_module.app.extensions['floorbit_plugins']


@pytest.fixture
def librenms_set_up(registry, monkeypatch):
    from floorbit import runtime
    monkeypatch.setattr(runtime.rt, 'librenms_enabled', True)
    monkeypatch.setenv('LIBRENMS_URL', 'https://librenms.example.com')
    monkeypatch.setenv('LIBRENMS_TOKEN', 'example-token')


def _set(client, **values):
    registry = client.application.extensions['floorbit_plugins']
    assert client.put('/api/settings/plugins/telemetry', json={'enabled': True}).status_code == 200
    registry.settings_store.update({f'plugin.telemetry.{k}': v for k, v in values.items()})


def test_with_librenms_on_telemetry_only_takes_traps_facts_and_streams(registry, librenms_set_up):
    plan = polling.plan(registry)
    assert plan['who'] == 'librenms' and plan['why'] == 'LibreNMS is on' and plan['tables_minutes'] == 0
    conf = '\n'.join(telegraf.snmp(polling.apply([SWITCH], plan)[0]))
    assert 'name = "fb_if"' not in conf and 'fb_system' not in conf        # no port polls
    assert 'fb_arp' not in conf and 'fb_fdb' not in conf                    # no table walks
    assert 'fb_facts' in conf                                               # discovery keeps the inventory filled
    full = telegraf.render(polling.apply([SWITCH], plan), 'http://127.0.0.1:1/write', 'x')
    assert '[[inputs.snmp_trap]]' in full                                   # traps still arrive here


def test_without_librenms_telemetry_polls_and_walks_the_tables(registry, monkeypatch):
    from floorbit import runtime
    monkeypatch.setattr(runtime.rt, 'librenms_enabled', False)
    plan = polling.plan(registry)
    assert plan == {'who': 'telemetry', 'why': 'LibreNMS is off', 'tables_minutes': 1}
    conf = '\n'.join(telegraf.snmp(polling.apply([SWITCH], plan)[0], tables_interval=polling.tables_interval(plan)))
    assert 'name = "fb_if"' in conf and 'fb_arp' in conf and 'example-community@10' in conf
    assert 'interval = "60s"' in conf


def test_the_setting_overrides_auto(client, registry, librenms_set_up, monkeypatch):
    from floorbit.telemetry import targets
    monkeypatch.setattr(targets, 'any_device', lambda *a: True)     # Telemetry has devices: it is set up
    _set(client, polling='telemetry', tables_minutes=15)
    plan = polling.plan(registry)
    assert plan == {'who': 'telemetry', 'why': 'set to Telemetry', 'tables_minutes': 15}
    assert polling.tables_interval(plan) == '15m'
    # Telemetry polls, so it answers before LibreNMS.
    assert registry.monitoring_source().id == 'telemetry'
    _set(client, polling='telemetry', tables_minutes=0)
    target = polling.apply([SWITCH], polling.plan(registry))[0]
    assert target['poll_ports'] is True and target['tables'] is False


def test_auto_keeps_librenms_first(client, registry, librenms_set_up):
    _set(client, polling='auto')
    assert registry.monitoring_source().id == 'librenms'


def test_an_ip_the_chosen_source_does_not_know_is_asked_of_the_other(registry, monkeypatch):
    class FakeRegistry:
        """Two monitoring plugins: the first knows only the MAC, the second the port."""
        def __init__(self):
            self.specs = {'librenms': type('S', (), {'id': 'librenms', 'name': 'LibreNMS'})(),
                          'telemetry': type('S', (), {'id': 'telemetry', 'name': 'Telemetry'})()}

        def monitoring_sources(self):
            return [self.specs['librenms'], self.specs['telemetry']]

        def call(self, spec, method, *args):
            if method == 'configured':
                return True
            if spec.id == 'librenms':
                return {'ip': args[0], 'mac': '02:00:00:00:00:31', 'port': None}
            return {'ip': args[0], 'mac': '02:00:00:00:00:31', 'hostname': 'access-01', 'port': 'Gi1/0/7'}

    fake = FakeRegistry()
    source = sources.PluginMonitoring(fake, fake.specs['librenms'])
    found = source.resolve_ip('192.0.2.31')
    assert found['port'] == 'Gi1/0/7' and found['answered_by'] == 'telemetry'


def test_the_agent_executor_helper_falls_back_too(registry, monkeypatch):
    calls = []

    def fake_call(spec, method, *args):
        calls.append((spec.id, method))
        if method == 'configured':
            return True
        return [] if spec.id == 'librenms' else [{'ipv4_address': '192.0.2.31', 'mac_address': '02:00:00:00:00:31'}]
    monkeypatch.setattr(registry, 'call', fake_call)
    monkeypatch.setattr(registry, 'monitoring_sources',
                        lambda: [registry.specs['librenms'], registry.specs['telemetry']])
    assert sources.call_monitoring(registry, 'arp', '192.0.2.31')[0]['mac_address'] == '02:00:00:00:00:31'
    assert ('telemetry', 'arp') in calls
