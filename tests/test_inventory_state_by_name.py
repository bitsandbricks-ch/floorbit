"""The inventory list's state for devices the status monitor doesn't track (issue #1425):
firewalls and servers are looked up by name in the monitor's last poll, as the Firewalls page does."""
import time

from floorbit import seat_view
from integrations.monitor import StatusMonitor


def _poll(devices):
    now = time.time()
    StatusMonitor.latest.update(polled=now, at=now, devices=devices)


def test_a_firewall_and_a_server_get_their_state_from_the_monitor_poll(client, monkeypatch):
    monkeypatch.setattr(seat_view, 'monitor_statuses', lambda: {})
    for name, role in (('fw-01', 'firewall'), ('fw-03', 'firewall'), ('cache-01', 'server'), ('nas-01', 'server')):
        client.post('/api/inventory', json={'name': name, 'role': role})
    _poll([{'display': 'fw-01', 'status': 1}, {'display': 'fw-03', 'status': 0},
           {'hostname': 'cache-01.example.com', 'status': 1}])
    rows = {d['name']: d['state'] for d in client.get('/api/inventory').get_json()['devices']}
    assert rows == {'fw-01': 'online', 'fw-03': 'offline', 'cache-01': 'online', 'nas-01': 'unknown'}


def test_a_tracked_switch_keeps_the_monitor_state_and_a_failed_poll_says_nothing(client, monkeypatch):
    dev = client.post('/api/inventory', json={'name': 'sw-a-01', 'role': 'switch'}).get_json()
    fw = client.post('/api/inventory', json={'name': 'fw-01', 'role': 'firewall'}).get_json()
    monkeypatch.setattr(seat_view, 'monitor_statuses', lambda: {dev['id']: {'status': 'offline'}})
    _poll([{'display': 'sw-a-01', 'status': 1}, {'display': 'fw-01', 'status': 1}])
    rows = {d['id']: d['state'] for d in client.get('/api/inventory').get_json()['devices']}
    # The monitor's confirmed state wins over one raw read.
    assert rows == {dev['id']: 'offline', fw['id']: 'online'}
    StatusMonitor.latest['polled'] = time.time() + 1   # the last poll failed
    rows = {d['id']: d['state'] for d in client.get('/api/inventory').get_json()['devices']}
    assert rows[fw['id']] is None
