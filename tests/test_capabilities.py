"""Capabilities (#989): one switch turns its settings, features and plugins on together."""
from tests.test_rbac import sign_in_as


def _cap(client, cap_id):
    return next(c for c in client.get('/api/settings/capabilities').get_json()['capabilities'] if c['id'] == cap_id)


def test_one_switch_turns_every_part_on_and_off(client):
    assert _cap(client, 'captive_note')['state'] == 'off'
    body = client.put('/api/settings/capabilities/captive_note', json={'on': True}).get_json()
    cap = next(c for c in body['capabilities'] if c['id'] == 'captive_note')
    assert cap['state'] == 'on'
    assert all(p['on'] for p in cap['parts'])
    assert {p['id'] for p in cap['parts']} == {'integrations.captive_enabled', 'captive-note'}
    assert client.get('/api/settings').get_json()['values']['integrations.captive_enabled']['value'] is True
    plugins = {p['id']: p for p in client.get('/api/settings/plugins').get_json()['plugins']}
    assert plugins['captive-note']['enabled'] is True
    entries = client.get('/api/settings/audit').get_json()['entries']
    assert entries[0]['action'] == 'Turned a capability on'
    assert entries[0]['target'].startswith('captive_note: ')

    client.put('/api/settings/capabilities/captive_note', json={'on': False})
    assert _cap(client, 'captive_note')['state'] == 'off'


def test_part_of_it_on_is_partly(client):
    client.put('/api/settings/features', json={'traffic': True})
    client.put('/api/settings/plugins/netflow-relay', json={'enabled': False})
    assert _cap(client, 'traffic')['state'] == 'partly'


def test_it_says_what_it_still_needs(client):
    cap = _cap(client, 'captive_note')
    needs = {n['id']: n for n in cap['needs']}
    assert needs['agent']['ok'] is False and needs['agent']['href'] == '/settings/agents'   # no agent enrolled
    assert needs['dhcp114']['ok'] is None          # set in the event's DHCP, outside Floorbit
    assert 'cap.checkin' in needs
    logs = {n['id']: n for n in _cap(client, 'logs')['needs']}
    assert logs['port.syslog-relay']['ok'] is False
    client.put('/api/settings', json={'plugin.syslog-relay.port': 514})
    logs = {n['id']: n for n in _cap(client, 'logs')['needs']}
    assert logs['port.syslog-relay']['ok'] is True


def test_bad_switches(client):
    assert client.put('/api/settings/capabilities/nope', json={'on': True}).status_code == 404
    assert client.put('/api/settings/capabilities/logs', json={'on': 'yes'}).status_code == 400


def test_only_admins_switch_capabilities(app_module):
    viewer = sign_in_as(app_module, 'watcher', 'viewer')
    assert viewer.get('/api/settings/capabilities').status_code == 403
    assert viewer.put('/api/settings/capabilities/logs', json={'on': False}).status_code == 403
