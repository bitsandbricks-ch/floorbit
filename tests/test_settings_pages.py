"""Each settings section and each plugin has its own address, all served by the React app."""


def test_section_and_plugin_pages_open(client):
    for path in ('/settings', '/settings/netbox', '/settings/attention', '/settings/plugins',
                 '/settings/plugins/http-check'):
        assert client.get(path).status_code in (200, 503), path   # 503: no frontend build (CI)


def test_the_other_settings_pages_keep_their_own_routes(client):
    # /settings/<section> must not swallow them: each renders under its own title.
    assert b'<title>ApiTokens' in client.get('/settings/api').data
    assert b'<title>Settings' in client.get('/settings/netbox').data


def test_they_need_settings_manage(app_module):
    anonymous = app_module.app.test_client()
    for path in ('/settings/netbox', '/settings/plugins/http-check'):
        assert anonymous.get(path).status_code in (302, 401, 403), path


def test_a_trailing_slash_opens_settings_too(client):
    assert b'<title>Settings' in client.get('/settings/').data


def test_server_internals_are_marked_advanced(client):
    # #991: file paths, rates and caches fold under Advanced; what crews change stays in view.
    fields = {f['key']: f for f in client.get('/api/settings').get_json()['fields']}
    assert fields['integrations.checkin_file'].get('advanced') is True
    assert fields['cache.ttl_arp'].get('advanced') is True
    assert not fields['integrations.checkin_enabled'].get('advanced')
