"""What a plugin does (#1435): the state on its card comes from what arrives, not only its switch."""
from floorbit import plugin_activity, sources


def _agent(name, connected=True, **report):
    return {'id': name, 'name': name, 'connected': connected, 'report': report}


def _state(pid, agents):
    registry = sources.registry
    return plugin_activity.one(registry, registry.specs[pid], agents)


def test_an_agent_plugin_receives_once_its_data_arrives(client):
    client.put('/api/settings/plugins/syslog-relay', json={'enabled': True})
    assert _state('syslog-relay', [])['state'] == 'no_agent'
    assert _state('syslog-relay', [_agent('a', connected=False, syslog_received=5)])['state'] == 'no_agent'
    assert _state('syslog-relay', [_agent('a')])['state'] == 'waiting'
    got = _state('syslog-relay', [_agent('a', syslog_received=12), _agent('b')])
    assert got == {'state': 'receiving', 'values': {'count': 2, 'total': 2}}
    failing = _agent('b', plugins={'syslog-relay': {'status': 'error', 'running': False}})
    assert _state('syslog-relay', [_agent('a', syslog_received=12), failing]) == {
        'state': 'failing', 'values': {'names': 'b'}}
    client.put('/api/settings/plugins/syslog-relay', json={'enabled': False})
    assert _state('syslog-relay', [_agent('a', syslog_received=12)])['state'] == 'off'


def test_a_part_the_agent_says_is_off_is_not_configured(client):
    client.put('/api/settings/plugins/netflow-relay', json={'enabled': True})
    off = _agent('a', plugins={'netflow-relay': {'status': 'off', 'running': False}})
    assert _state('netflow-relay', [off])['state'] == 'not_configured'


def test_a_hosted_plugin_without_its_settings_is_not_configured(client):
    client.put('/api/settings/plugins/netbox', json={'enabled': True})
    assert _state('netbox', [])['state'] == 'not_configured'
    client.put('/api/settings', json={'netbox.url': 'https://netbox.example.com', 'netbox.token': 'example-token'})
    assert _state('netbox', [])['state'] == 'on'


def test_the_list_carries_each_state(client):
    body = client.get('/api/settings/plugins').get_json()
    states = {p['id']: p['activity']['state'] for p in body['plugins']}
    assert states['http-check'] in ('off', 'on')
    assert body['missing'] == []      # no LAN cache data without the plugin here
    turned = client.put('/api/settings/plugins/http-check', json={'enabled': True}).get_json()
    assert {p['id']: p['activity']['state'] for p in turned['plugins']}['http-check'] == 'on'


def test_the_agent_ports_need_no_setting():
    # #1436: syslog and flows listen on the agent's fixed ports, like its other ones.
    store = sources.registry.settings_store
    assert store.get('plugin.syslog-relay.port') == 5514
    assert store.get('plugin.netflow-relay.port') == 2055
