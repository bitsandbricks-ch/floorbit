"""Each settings section and each plugin has its own address, all served by the React app."""


def test_section_and_plugin_pages_open(client):
    for path in ('/settings', '/settings/netbox', '/settings/attention', '/settings/plugins',
                 '/settings/plugins/http-check'):
        assert client.get(path).status_code == 200, path


def test_the_other_settings_pages_keep_their_own_routes(client):
    # /settings/<section> must not swallow them: each renders under its own title.
    assert b'<title>ApiTokens' in client.get('/settings/api').data
    assert b'<title>Settings' in client.get('/settings/netbox').data


def test_they_need_settings_manage(app_module):
    anonymous = app_module.app.test_client()
    for path in ('/settings/netbox', '/settings/plugins/http-check'):
        assert anonymous.get(path).status_code in (302, 401, 403), path
