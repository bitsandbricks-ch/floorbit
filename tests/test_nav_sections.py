"""Sidebar sections admins make themselves (floorbit/nav_sections.py)."""
from floorbit import nav_sections


def _put(client, sections):
    return client.put('/api/settings/sidebar', json={'sections': sections})


def test_save_and_show_in_the_page_list(client):
    r = _put(client, [{'name': 'Main hall', 'icon': 'star', 'links': [
        {'kind': 'dashboard', 'ref': 'kiosk'},
        {'kind': 'page', 'ref': 'problems'},
        {'kind': 'url', 'href': 'https://example.com/grafana', 'label': 'Grafana'},
        {'kind': 'url', 'href': '/plan?seat=A-1', 'label': 'Seat A-1'},
    ]}])
    assert r.status_code == 200, r.get_json()
    saved = r.get_json()['sections']
    assert saved[0]['id'] == 'main-hall' and saved[0]['icon'] == 'star'
    assert client.get('/api/settings/sidebar').get_json()['sections'] == saved

    custom = client.get('/api/pages').get_json()['custom']
    links = custom[0]['links']
    assert [x['href'] for x in links] == ['/dashboards/kiosk', '/problems', 'https://example.com/grafana',
                                          '/plan?seat=A-1']
    assert links[0]['label'] == 'Kiosk'
    assert links[1] == {'kind': 'page', 'href': '/problems', 'page': 'problems', 'label': 'Problems', 'own': False}
    assert links[2]['external'] is True and links[3]['external'] is False


def test_bad_links_are_refused(client):
    for link in ({'kind': 'url', 'href': 'javascript:alert(1)', 'label': 'x'},
                 {'kind': 'url', 'href': '//evil.example.com', 'label': 'x'},
                 {'kind': 'url', 'href': 'https://example.com'},          # no name
                 {'kind': 'page', 'ref': 'nope'},
                 {'kind': 'dashboard', 'ref': 'Bad Id'},
                 {'kind': 'file', 'ref': 'x'}):
        assert _put(client, [{'name': 'A', 'links': [link]}]).status_code == 400, link
    assert _put(client, [{'name': ' ', 'links': []}]).status_code == 400
    too_many = [{'name': f's{n}', 'links': []} for n in range(nav_sections.MAX_SECTIONS + 1)]
    assert _put(client, too_many).status_code == 400
    assert client.put('/api/settings/sidebar', json=[]).status_code == 400


def test_unknown_icon_and_clashing_ids(client):
    saved = _put(client, [{'name': 'Hall', 'icon': '<svg>'}, {'name': 'Hall', 'id': 'hall'}]).get_json()['sections']
    assert saved[0]['icon'] == 'folder'
    assert [s['id'] for s in saved] == ['hall', 'hall-2']


def test_each_person_sees_only_what_they_may_open(app_module):
    with app_module.app.app_context():
        nav_sections.save({'sections': [
            {'name': 'Admin bits', 'links': [{'kind': 'page', 'ref': 'settings'},
                                             {'kind': 'dashboard', 'ref': 'gone'}]},
            {'name': 'Wall', 'links': [{'kind': 'dashboard', 'ref': 'kiosk', 'label': 'Big screen'}]},
        ]}, 'test')
        # Someone without Settings and without dashboards: nothing left, so no section.
        assert nav_sections.for_pages([{'href': '/problems', 'id': 'problems', 'label': 'Problems'}]) == []
        seen = nav_sections.for_pages([{'href': '/dashboards', 'id': 'dashboards', 'label': 'Dashboards'}])
        assert [s['name'] for s in seen] == ['Wall']
        assert seen[0]['links'] == [{'kind': 'dashboard', 'href': '/dashboards/kiosk', 'label': 'Big screen'}]


def test_options_for_the_editor(client):
    assert {'value': 'kiosk', 'label': 'Kiosk'} in client.get('/api/options/dashboards').get_json()['options']
    pages = client.get('/api/options/pages').get_json()['options']
    assert {'value': 'problems', 'label': 'Problems', 'hint': '/problems'} in pages


def test_only_admins_change_them(kiosk_client):
    assert kiosk_client.put('/api/settings/sidebar', json={'sections': []}).status_code == 403
    assert kiosk_client.get('/api/settings/sidebar').status_code == 403
