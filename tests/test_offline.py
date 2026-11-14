"""Offline mode: the last good monitoring data while the source is down, and one alert per outage."""
import pytest

from floorbit.plugins.base import PluginError
from floorbit.sources import lastgood
from integrations import events
from integrations.discord import DiscordNotifier
from integrations.monitor import StatusMonitor


@pytest.fixture
def nms(app_module, monkeypatch):
    """The LibreNMS plugin, set up, answering from ``state`` until ``state['down']`` is set."""
    from floorbit import runtime
    from floorbit.builtin_plugins.librenms import client as nms_client
    monkeypatch.setattr(runtime.rt, 'librenms_enabled', True)
    monkeypatch.setenv('STATUS_MONITOR_CONFIRM', '1')
    state = {'down': False, 'status': 1}

    def devices():
        if state['down']:
            raise ConnectionError('no route to host')
        return [{'display': 'sw-a-01', 'hostname': 'sw-a-01.example.com', 'status': state['status']}]

    def details(hostname):
        if state['down']:
            return {'status': 'unknown', 'hostname': hostname}   # how the client reports a dead NMS
        return {'status': 'online', 'hostname': hostname, 'cpu_load': 12}
    monkeypatch.setattr(nms_client, 'list_devices', devices)
    monkeypatch.setattr(nms_client, 'fetch_librenms_details', details)
    return state


def test_last_good_survives_a_restart_without_redis(tmp_path):
    lastgood._last_write = 0
    lastgood.put('k', {'a': 1})
    lastgood._loaded, lastgood._memory = False, {}     # a new process
    at, value = lastgood.get('k')
    assert value == {'a': 1} and at > 0
    assert (tmp_path / 'monitoring-cache.json').is_file()


def test_pages_get_the_last_good_answer_marked_stale(client, nms):
    monitor = StatusMonitor(lambda: [{'id': '1', 'name': 'sw-a-01'}])
    monitor.poll_once()
    assert client.get('/api/switches/sw-a-01/status').get_json()['status'] == 'online'

    nms['down'] = True
    with pytest.raises(PluginError):
        monitor.poll_once()
    body = client.get('/api/switches/sw-a-01/status').get_json()
    assert body['status'] == 'online' and body['stale'] is True and body['cpu_load'] == 12
    assert body['as_of'] <= body['offline_since']
    health = client.get('/api/monitoring/health').get_json()
    assert health['ok'] is False and health['name'] == 'librenms' and health['offline_since']
    # Viewers see the plugin's short message, never the raw exception (it can name hosts).
    assert 'ConnectionError' in health['error'] and 'no route' not in health['error']

    nms['down'] = False
    monitor.poll_once()
    assert 'stale' not in client.get('/api/switches/sw-a-01/status').get_json()


def test_one_message_per_outage_and_no_flood_after_it(app_module, nms):
    got = []
    events.subscribe('*', lambda ev: got.append(ev['type']))
    monitor = StatusMonitor(lambda: [{'id': '1', 'name': 'sw-a-01'}])
    monitor.poll_once()                       # baseline
    nms['down'] = True
    for _ in range(3):
        with pytest.raises(PluginError):
            monitor.poll_once()
    assert got.count('monitoring.offline') == 1 and 'switch.status' not in got

    # Back, with the switch down meanwhile: a fresh baseline, no alert for what changed while blind.
    nms['down'], nms['status'] = False, 0
    assert monitor.poll_once() == []
    assert got.count('monitoring.online') == 1 and 'switch.status' not in got
    # Changes after that are announced as usual.
    nms['status'] = 1
    assert monitor.poll_once()[0]['status'] == 'online'


def test_discord_says_it_once_without_pinging_anyone(monkeypatch):
    n = DiscordNotifier()
    down = n.build_source_message('monitoring.offline', {'source': 'LibreNMS'})
    assert 'LibreNMS is unreachable' in down['embeds'][0]['title'] and down['allowed_mentions'] == {'parse': []}
    back = n.build_source_message('monitoring.online', {'source': 'LibreNMS', 'down_for': 125})
    assert 'back' in back['embeds'][0]['title'] and '2' in back['embeds'][0]['description']
