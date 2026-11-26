"""Check-in and the inventory's IP ranges (issues #1613, #1623): a range counts as the event network,
public or not, and its "Check-in allowed" switch (on by default) refuses ranges no seat PC is on.
Documentation and made-up addresses only."""
import pytest

from integrations import checkin, events

ENTRIES = '/api/inventory/entries/prefix'


@pytest.fixture
def hall(client, front_door, tmp_path, monkeypatch):
    monkeypatch.setenv('CHECKIN_ENABLED', 'true')
    monkeypatch.setenv('CHECKIN_VALIDATE_SEATS', 'false')
    monkeypatch.setenv('CHECKIN_FILE', str(tmp_path / 'checkins.json'))
    monkeypatch.setattr(events, 'publish', lambda kind, data=None, origin=None: None)
    return client


def check_in(client, ip):
    return client.post('/api/checkin', json={'seat': 'D-3', 'username': 'pixel'}, environ_base={'REMOTE_ADDR': ip})


def test_a_public_range_in_the_inventory_counts_as_the_event_network(hall):
    public = '5.6.7.8'
    assert check_in(hall, public).status_code == 403
    # With or without a VLAN, written as a network or from-to.
    assert hall.post(ENTRIES, json={'name': 'Players', 'fields': {'prefix': '5.6.7.0-5.6.7.200'}}).status_code == 201
    assert check_in(hall, public).status_code == 200
    assert checkin.refusal('5.6.7.201') == 'public'


def test_a_range_with_check_in_switched_off_is_refused(hall):
    """Mike, 2026-11-26: a "Check-in allowed" switch per IP range, on by default. Off for the
    Wi-Fi: a phone there is not the seat's PC and would only make a false check-in."""
    assert hall.post(ENTRIES, json={'name': 'Seats', 'fields': {'prefix': '10.10.0.0/16'}}).status_code == 201
    wifi = hall.post(ENTRIES, json={'name': 'Wi-Fi', 'fields': {'prefix': '10.10.200.0/24', 'checkin': 'no'}})
    assert wifi.status_code == 201
    assert checkin.refusal('10.10.1.5') is None              # on by default
    r = check_in(hall, '10.10.200.9')                       # the narrowest range wins
    assert r.status_code == 403 and 'not over Wi-Fi' in r.get_json()['error']
    info = hall.get('/api/checkin/info', environ_base={'REMOTE_ADDR': '10.10.200.9'}).get_json()
    assert info['refused'] == 'range'
    assert check_in(hall, '10.10.1.5').status_code == 200
    # Switched back on, the Wi-Fi may check in again.
    assert hall.patch(f"{ENTRIES}/{wifi.get_json()['id']}", json={'fields': {'checkin': 'yes'}}).status_code == 200
    assert checkin.refusal('10.10.200.9') is None


def test_the_switch_is_on_for_new_ranges(hall):
    types = hall.get('/api/inventory/types').get_json()
    prefix = next(t for t in (types.get('types') or types) if t['id'] == 'prefix')
    field = next(f for f in prefix['fields'] if f['key'] == 'checkin')
    assert field['kind'] == 'bool' and field['default'] == 'yes'
