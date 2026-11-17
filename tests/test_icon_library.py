"""The shared icon library: uploads are rebuilt from an allowlist, recoloured, admin-only."""
import pytest

from floorbit import icon_library

GOOD = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24">'
        '<title>Rack</title><path d="M4 4h16v16H4z" fill="#ff0000" stroke="blue"/>'
        '<circle cx="12" cy="12" r="3" fill="none"/></svg>')


def test_a_clean_icon_keeps_its_shapes_and_takes_the_item_colour():
    out = icon_library.sanitize(GOOD)
    assert 'd="M4 4h16v16H4z"' in out and 'viewBox="0 0 24 24"' in out
    assert '#ff0000' not in out and 'blue' not in out
    assert out.count('currentColor') >= 2 and 'fill="none"' in out


@pytest.mark.parametrize('bad', [
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1"><script>alert(1)</script><path d="M0 0h1v1z"/></svg>',
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1" onload="alert(1)">'
    '<path d="M0 0h1v1z" onclick="x()"/></svg>',
    '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 1 1">'
    '<a xlink:href="javascript:alert(1)"><path d="M0 0h1v1z"/></a><use xlink:href="https://example.com/x.svg#a"/>'
    '<image href="https://example.com/a.png"/><path d="M0 0h1v1z"/></svg>',
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1"><foreignObject><div xmlns="http://www.w3.org/1999/xhtml">'
    '<iframe src="https://example.com"/></div></foreignObject><style>@import url(https://example.com/x.css)</style>'
    '<path d="M0 0h1v1z" style="fill:url(https://example.com/x)" fill="url(https://example.com/#a)"/></svg>',
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1"><path d="M0 0h1v1z" clip-path="url(https://example.com/#c)"/>'
    '<animate attributeName="href" to="javascript:alert(1)"/><set attributeName="onload" to="x"/></svg>',
])
def test_nothing_that_runs_or_loads_survives(bad):
    out = icon_library.sanitize(bad).lower()
    for word in ('script', 'onload', 'onclick', 'javascript', 'href', 'example.com', 'foreignobject', 'iframe',
                 'style', 'image', '<use', '<a', 'animate', '<set', 'import'):
        assert word not in out, word
    assert '<path' in out


@pytest.mark.parametrize('bad, message', [
    ('<?xml version="1.0"?><!DOCTYPE svg [<!ENTITY x SYSTEM "file:///etc/passwd">]><svg>&x;</svg>', 'DOCTYPE'),
    ('<html><body/></html>', 'not a valid SVG'),
    ('not xml', 'not a valid SVG'),
    ('<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0h1v1z"/></svg>', 'viewBox'),
    ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1"><script/></svg>', 'nothing to draw'),
    ('<svg>' + ' ' * (icon_library.MAX_BYTES + 1) + '</svg>', 'at most'),
])
def test_bad_files_are_refused(bad, message):
    with pytest.raises(icon_library.IconError, match=message):
        icon_library.sanitize(bad)


def test_admins_upload_everyone_sees_and_removing_resets_devices(app_module, client):
    r = client.post('/api/icons', json={'name': 'Rack', 'svg': GOOD})
    assert r.status_code == 201, r.get_json()
    icon = r.get_json()
    assert client.post('/api/icons', json={'name': 'Again', 'svg': GOOD}).status_code == 200   # same file, one icon
    assert client.post('/api/icons', json={'name': 'X', 'svg': '<svg/>'}).status_code == 400
    assert [i['name'] for i in client.get('/api/icons').get_json()['icons']] == ['Rack']

    served = client.get(icon['url'])
    assert served.status_code == 200 and served.mimetype == 'image/svg+xml'
    assert 'sandbox' in served.headers['Content-Security-Policy']
    assert client.get('/api/icons/custom-000000000000.svg').status_code == 404

    dev = client.post('/api/inventory', json={'name': 'sw-01', 'role': 'switch', 'icon': icon['id']}).get_json()
    assert dev['icon'] == icon['id']
    assert client.post('/api/inventory', json={'name': 'sw-02', 'icon': 'custom-nope'}).status_code == 400
    assert client.patch(f"/api/icons/{icon['id']}", json={'name': 'Server rack'}).get_json()['name'] == 'Server rack'
    assert client.delete(f"/api/icons/{icon['id']}").get_json()['was_used'] == 1
    assert client.get(f"/api/inventory/{dev['id']}").get_json()['icon'] == ''


def test_only_admins_change_the_library(app_module, client):
    from tests.test_rbac import sign_in_as
    tech = sign_in_as(app_module, 'te7', 'tech')
    assert tech.get('/api/icons').status_code == 200
    assert tech.post('/api/icons', json={'name': 'Rack', 'svg': GOOD}).status_code == 403
