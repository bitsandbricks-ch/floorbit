"""Floorbit installs as an app on a phone: the manifest and service worker (blueprints/app_install.py)."""


def test_the_manifest_names_the_app_and_its_icons_without_signing_in(anon_client):
    res = anon_client.get('/manifest.webmanifest')
    assert res.status_code == 200
    assert res.mimetype == 'application/manifest+json'
    m = res.get_json()
    assert m['name'] == 'Floorbit' and m['display'] == 'standalone' and m['start_url'] == '/'
    assert {i['sizes'] for i in m['icons']} == {'192x192', '512x512'}
    assert any(i.get('purpose') == 'maskable' for i in m['icons'])
    for icon in m['icons']:
        assert anon_client.get(icon['src']).status_code == 200


def test_the_service_worker_comes_from_the_root_and_is_asked_for_again(anon_client):
    res = anon_client.get('/sw.js')
    assert res.status_code == 200
    assert res.mimetype == 'text/javascript'
    assert res.headers['Cache-Control'] == 'no-cache'
    assert b"addEventListener('fetch'" in res.data


def test_every_page_links_the_manifest(client):
    assert b'rel="manifest" href="/manifest.webmanifest"' in client.get('/plan').data
