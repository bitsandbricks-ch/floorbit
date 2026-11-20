"""Wi-Fi access points in Problems (issue #1064): down, busy for a while, and co-channel overlaps."""
import types

import pytest

from floorbit import wifi


@pytest.fixture(autouse=True)
def fresh():
    wifi.reset()
    yield
    wifi.reset()


def radio(band, channel, utilization, clients):
    return {'band': band, 'channel': channel, 'width': 20, 'utilization': utilization, 'clients': clients}


APS = [
    {'name': 'ap-stage', 'model': 'C9136I-E', 'status': 'down', 'clients': 0, 'radios': [], 'controller': 'wlc-01'},
    {'name': 'ap-hall-01', 'model': 'C9120AXI-E', 'status': 'up', 'clients': 12,
     'radios': [radio('5', 36, 82, 12)], 'source': 'Telemetry'},
    {'name': 'ap-crew', 'model': 'C9120AXI-E', 'status': 'up', 'clients': 3, 'radios': [radio('5', 44, 10, 3)]},
]


@pytest.fixture
def aps(client, monkeypatch):
    # Any Wi-Fi plugin on is enough; what it says is replaced by APS.
    assert client.put('/api/settings/plugins/demo', json={'enabled': True}).status_code == 200
    monkeypatch.setattr(wifi, 'ask', lambda registry: ([dict(a) for a in APS], []))
    clock = [1_800_000_000.0]
    # wifi's own clock only: the session must not expire with it.
    monkeypatch.setattr(wifi, 'time', types.SimpleNamespace(time=lambda: clock[0]))
    return clock


def wifi_problems(client):
    body = client.get('/api/problems').get_json()
    return {p['id']: p for p in body['problems'] if p['kind'] == 'wifi'}, body


def test_a_down_ap_is_a_problem_at_once_a_busy_one_after_a_while(client, aps):
    found, body = wifi_problems(client)
    assert list(found) == ['wifi:down:ap-stage']
    down = found['wifi:down:ap-stage']
    assert (down['level'], down['title'], down['where']) == ('down', 'ap-stage is down', 'wlc-01')
    assert down['since'] == aps[0] and down['link'] == wifi.LINK and down['mute_id'] == 'wifi:ap-stage'
    assert body['counts']['down'] >= 1

    aps[0] += wifi.BUSY_FOR + 1
    found, _ = wifi_problems(client)
    busy = found['wifi:busy:ap-hall-01']
    assert busy['level'] == 'warn' and busy['title'] == 'ap-hall-01 is busy: 82 % channel use, 12 clients'
    assert found['wifi:down:ap-stage']['since'] == aps[0] - wifi.BUSY_FOR - 1   # still since it went down
    assert 'wifi:busy:ap-crew' not in found


def test_an_ap_that_calms_down_starts_again(client, aps, monkeypatch):
    wifi_problems(client)
    calm = [dict(a, radios=[radio('5', 36, 20, 12)]) if a['name'] == 'ap-hall-01' else dict(a) for a in APS]
    monkeypatch.setattr(wifi, 'ask', lambda registry: (calm, []))
    aps[0] += 120
    wifi_problems(client)
    monkeypatch.setattr(wifi, 'ask', lambda registry: ([dict(a) for a in APS], []))
    aps[0] += wifi.BUSY_FOR - 60
    assert 'wifi:busy:ap-hall-01' not in wifi_problems(client)[0]   # its clock started again


def test_mute_an_access_point(client, aps):
    res = client.post('/api/alerts/mutes', json={'ap': 'AP-STAGE', 'minutes': 30, 'reason': 'Unplugged on purpose'})
    assert res.status_code == 201 and res.get_json()['switch_id'] == 'wifi:ap-stage'
    found, body = wifi_problems(client)
    assert found['wifi:down:ap-stage']['muted']['reason'] == 'Unplugged on purpose'
    assert body['counts']['muted'] >= 1
    assert {'switch_id': 'wifi:ap-stage', 'kind': 'wifi'}.items() <= body['mutes'][0].items()
    assert client.post('/api/alerts/mutes', json={'ap': 'ap-gone', 'minutes': 30}).status_code == 400
    assert client.delete('/api/alerts/mutes/wifi:ap-stage').status_code == 200
    de = client.post('/api/alerts/mutes', json={'ap': 'ap-gone', 'minutes': 30}, headers={'Accept-Language': 'de-CH'})
    assert de.get_json()['error'] == 'Diesen Access Point gibt es nicht.'


def test_in_german(client, aps):
    body = client.get('/api/problems', headers={'Accept-Language': 'de-CH'}).get_json()
    assert next(p for p in body['problems'] if p['kind'] == 'wifi')['title'] == 'ap-stage ist ausgefallen'


def test_nothing_when_wifi_is_off_or_has_no_source(client, aps, monkeypatch):
    assert client.put('/api/settings/features', json={'wifi': False}).status_code == 200
    assert wifi_problems(client)[0] == {}
    assert client.put('/api/settings/features', json={'wifi': True}).status_code == 200
    monkeypatch.setattr(wifi, 'agent_active', lambda: False)   # no agent either
    for pid in ('demo', 'telemetry'):   # every plugin that feeds the Wi-Fi view
        assert client.put(f'/api/settings/plugins/{pid}', json={'enabled': False}).status_code == 200
    assert wifi_problems(client)[0] == {}


def test_two_aps_near_each_other_on_one_channel(monkeypatch):
    view = {'aps': [dict(a, placed=True) for a in APS], 'down': [], 'busy': [],
            'overlaps': [{'band': '5', 'channel': 36, 'aps': ['ap-crew', 'ap-hall-01']}]}
    monkeypatch.setattr(wifi, 'overview', lambda registry, data: view)
    [overlap] = wifi.problems(None, {}, {}, now=1.0)
    assert overlap['level'] == 'warn'
    assert overlap['title'] == 'ap-crew and ap-hall-01 share channel 36 (5 GHz) close together'
