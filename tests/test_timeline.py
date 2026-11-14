"""Event changelog (issue #100): audit log, outages, incidents, alerts and deploys in one timeline."""
import time

import pytest

from floorbit import timeline
from integrations import events
from tests.test_rbac import sign_in_as


@pytest.fixture(autouse=True)
def journal(tmp_path, monkeypatch):
    """A journal of its own, and on the bus: other tests reset the subscribers."""
    monkeypatch.setenv('TIMELINE_FILE', str(tmp_path / 'timeline.jsonl'))
    events.subscribe_once('*', timeline.on_event)


def kinds_of(client, query=''):
    return [(e['kind'], e['title']) for e in client.get(f'/api/timeline{query}').get_json()['entries']]


def test_one_timeline(client, app_module):
    client.post('/api/seat-blocks', json={'name': 'A', 'x': 10, 'y': 10, 'cols': 2, 'rows': 2})
    stats = app_module.app.extensions['floorbit_stats']
    stats.new_event()   # other tests leave switch outages behind
    now = time.time()
    stats.record_switch({'id': 's1', 'name': 'sw-a-01', 'status': 'offline', 'since': now - 300})
    stats.record_switch({'id': 's1', 'name': 'sw-a-01', 'status': 'online', 'since': now - 60})
    i = client.post('/api/incidents', json={'seat': 'A-1', 'title': 'Cable cut'}).get_json()
    client.patch(f"/api/incidents/{i['id']}", json={'status': 'fixed'})
    events.publish('forecast.alert', {'t': now, 'bps': 9e8, 'pct': 91.4, 'capacity_bps': 1e9})
    events.publish('security.finding', {'id': 'f1', 'kind': 'rogue_dhcp', 'severity': 'down', 'switch': 'sw-a-01',
                                        'port': 'Gi1/0/3', 'seat': 'A-3', 'mac': '02:00:00:00:00:09'})
    events.publish('seat.something.else', {})

    body = client.get('/api/timeline').get_json()
    got = {(e['kind'], e['title']) for e in body['entries']}
    assert {('change', 'Added seat block'), ('change', 'Filed incident'), ('change', 'Changed incident (status)'),
            ('sign-in', 'Signed in')} <= got
    assert ('outage', 'Switch went offline') in got and ('outage', 'Switch back online after 4 min') in got
    assert ('incident', 'Incident opened: Cable cut') in got and ('incident', 'Incident fixed: Cable cut') in got
    assert ('alert', 'Bandwidth forecast: 91% of the line expected') in got
    assert ('alert', 'Security: rogue dhcp (seat A-3)') in got
    assert '02:00:00:00:00:09' not in str(body)   # webhook words only: no MACs
    ts = [e['t'] for e in body['entries']]
    assert ts == sorted(ts, reverse=True)
    assert body['counts']['outage'] == 2 and body['counts']['incident'] == 2

    assert {k for k, _ in kinds_of(client, '?kinds=outage,alert')} == {'outage', 'alert'}
    assert kinds_of(client, '?q=cable cut&kinds=incident') == [('incident', 'Incident fixed: Cable cut'),
                                                               ('incident', 'Incident opened: Cable cut')]
    older = client.get(f'/api/timeline?before={now - 120}').get_json()['entries']
    assert [e['title'] for e in older if e['kind'] == 'outage'] == ['Switch went offline']

    csv = client.get('/api/timeline.csv?kinds=outage').data.decode().splitlines()
    assert csv[0] == 'time,kind,title,target,who' and len(csv) == 3 and 'sw-a-01' in csv[1]
    whole = client.get('/api/timeline?format=json')
    assert 'attachment' in whole.headers['Content-Disposition'] and whole.get_json()['entries']


def test_version_change_is_a_deploy(app_module, client):
    timeline.record_start('1.0.0')
    entry = timeline.record_start('1.1.0')
    assert entry['title'] == 'Floorbit updated from 1.0.0 to 1.1.0'
    assert timeline.record_start('1.1.0')['title'] == 'Floorbit started (version 1.1.0)'
    deploys = client.get('/api/timeline?kinds=deploy').get_json()['entries']
    assert deploys[1]['title'] == 'Floorbit updated from 1.0.0 to 1.1.0' and deploys[1]['version'] == '1.1.0'


def test_journal_is_trimmed(app_module, monkeypatch):
    monkeypatch.setattr(timeline, 'MAX_BYTES', 2000)
    for n in range(100):
        timeline.write('alert', f'alert {n}')
    rows = timeline._journal()
    assert len(rows) < 100 and rows[-1]['title'] == 'alert 99'


def test_needs_audit_read(app_module, client):
    tech = sign_in_as(app_module, 'te1', 'tech')
    assert tech.get('/api/timeline').status_code == 403
    assert tech.get('/api/timeline.csv').status_code == 403
