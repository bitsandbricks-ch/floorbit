"""Agents > Telemetry collector shows when each device's last syslog line came (issue #904)."""
import time

from floorbit import syslog


def test_the_receiver_remembers_when_a_device_last_sent(tmp_path, monkeypatch):
    monkeypatch.setenv('SYSLOG_ALLOW', '192.0.2.0/24')
    r = syslog.SyslogReceiver(path=str(tmp_path / 'syslog'))
    r._allow_cache = (time.monotonic() + 3600, [syslog.ipaddress.ip_network('192.0.2.0/24')],
                      {'198.51.100.5': 'SW-A-01'})
    r.receive(b'<14>first', '198.51.100.5', now=1000.0)
    r.receive(b'<14>later', '198.51.100.5', now=2000.0)
    # A line an agent kept while the uplink was down says nothing about now.
    r.receive(b'<14>old', '198.51.100.5', now=3000.0, late=True)
    assert r.heard == {'sw-a-01': 2000.0}
    # Capped: a flood of made-up host names can't grow it.
    monkeypatch.setattr(syslog, 'HEARD_MAX', 1)
    r.receive(b'<14>Nov 14 10:00:01 made-up-1 x', '192.0.2.9', now=4000.0)
    assert set(r.heard) == {'sw-a-01'}


def test_the_overview_carries_the_last_syslog_line_per_device(client, monkeypatch):
    from floorbit.blueprints import telemetry as view
    listed = [{'name': 'sw-a-01'}, {'name': 'sw-b-01'}]
    receiver = client.application.extensions['floorbit_syslog']
    monkeypatch.setattr(receiver, 'heard', {'sw-a-01': 1_800_000_000.0, 'other': 1.0})
    with client.application.app_context():
        assert view._syslog_heard(listed) == {'sw-a-01': 1_800_000_000.0}
    assert 'syslog' in client.get('/api/telemetry/overview').get_json()
