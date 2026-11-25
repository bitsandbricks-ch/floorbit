"""The event report's numbers as Overview tiles (floorbit/dashboard_report.py, #898)."""
from floorbit import dashboard_report, dashboards

REPORT = {
    'seats': 112, 'online_max': 96, 'checked_in_max': 85, 'bytes_moved': 4_000_000_000,
    'peak': {'bps': 2_500_000_000, 'at': 0},
    'incidents': {'total': 7, 'fixed': 5, 'open': 2, 'median_fix_s': 600},
    'outages': [{'switch': 'sw-a-01', 'times': 2, 'down_s': 300, 'longest_s': 240, 'still_down': False},
                {'switch': 'sw-b-02', 'times': 1, 'down_s': 90, 'longest_s': 90, 'still_down': True}],
    'problem_ports': [{'switch': 'sw-a-01', 'port': 'Gi1/0/3', 'seat': 'A-3', 'count': 6},
                      {'switch': 'sw-b-02', 'port': 'Gi1/0/9', 'seat': None, 'count': 3}],
}


def test_the_numbers_read_like_the_report():
    w = lambda tile, lang='en': dashboard_report.widget(tile, lang, REPORT)  # noqa: E731
    assert w('event_online')['value'] == 96 and w('event_online')['sub'] == 'of 112 seats'
    assert w('event_checked_in')['value'] == 85 and w('event_checked_in')['link'] == '/checkins'
    assert w('event_moved')['value'] == 4_000_000_000 and w('event_moved')['unit'] == 'B'
    incidents = w('event_incidents')
    assert incidents['value'] == 7 and incidents['tone'] == 'warn'
    assert incidents['sub'] == '5 fixed · 2 open · half fixed within 10 min'
    outages = w('event_outages', 'de')
    assert outages['value'] == 3 and outages['tone'] == 'err'
    assert outages['sub'] == 'an 2 Switches · längster 4 Min. · 1 noch aus'
    ports = w('event_problem_ports')['items']
    assert [p['label'] for p in ports] == ['sw-a-01 Gi1/0/3', 'sw-b-02 Gi1/0/9']
    assert ports[0]['number'] == 1 and ports[0]['sub'] == 'A-3' and 'sub' not in ports[1]


def test_an_empty_event_says_so():
    empty = {'seats': 10, 'incidents': {}, 'outages': [], 'problem_ports': []}
    assert dashboard_report.widget('event_incidents', 'en', empty)['value'] == 0
    assert dashboard_report.widget('event_outages', 'en', empty)['sub'] == 'No switch went down'
    assert dashboard_report.widget('event_problem_ports', 'en', empty)['items'] == []


def test_the_tiles_are_listed_and_answer(client):
    tiles = {t['id']: t for t in client.get('/api/dashboard').get_json()['tiles'] if t['plugin'] == 'floorbit'}
    assert tiles['event_incidents']['label'] == 'Incidents this event'
    for tile in dashboard_report.TILES:
        body = client.get(f'/api/dashboard/floorbit/{tile}').get_json()
        assert body['type'] in ('stat', 'list'), tile


def test_the_tiles_stay_crew_only():
    assert not any(t.endswith(tuple(dashboard_report.TILES)) for t in dashboards.PUBLIC_TILES)


def test_the_overview_has_a_section_for_the_event():
    sections = dashboards.BUILTIN['overview']['sections']
    event = next(s for s in sections if s.get('title') == 'During the event')
    tiles = {p['node']['pane']['tile'] for p in event['panels']}
    assert {f'floorbit/w/{t}' for t in dashboard_report.TILES} <= tiles
