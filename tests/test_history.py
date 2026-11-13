import csv
import io
import json
import os
import sys
import time

import pytest
from flask import Flask

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from integrations import (  # noqa: E402
    checkin,
    config,
    events,
    history,
    init_integrations,
    seat_sources,
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for item in config.SCHEMA:
        monkeypatch.delenv(item['key'], raising=False)
    for key in ('LIBRENMS_URL', 'LIBRENMS_TOKEN'):
        monkeypatch.delenv(key, raising=False)
    config.set_provider(None)
    events._subscribers.clear()
    seat_sources.invalidate()
    yield
    config.set_provider(None)


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv('CHECKIN_ENABLED', 'true')
    monkeypatch.setenv('CHECKIN_FILE', str(tmp_path / 'checkins.json'))
    arp = {'10.0.2.144': 'AA-BB-CC-00-11-22', '10.0.2.150': 'aa:bb:cc:00:11:33'}
    monkeypatch.setattr(checkin, 'lookup_mac', lambda ip: checkin.normalise_mac(arp.get(ip)))
    monkeypatch.setattr(checkin, 'lookup_ip', lambda mac: next(
        (ip for ip, m in arp.items() if checkin.normalise_mac(m) == mac), None))
    return arp


@pytest.fixture
def client():
    data = {'seat_blocks': [{'name': 'd', 'cols': 4, 'rows': 6}]}
    a = Flask(__name__, template_folder=os.path.join(ROOT, 'templates'))
    init_integrations(a, load_data=lambda: data, start_background=False)
    return a.test_client()


def post(client, seat, user, ip):
    r = client.post('/api/checkin', json={'seat': seat, 'username': user}, environ_base={'REMOTE_ADDR': ip})
    assert r.status_code == 200, r.get_json()


def test_history_file_defaults_next_to_checkins(env, tmp_path, monkeypatch):
    assert history.path() == str(tmp_path / 'checkins-history.jsonl')
    monkeypatch.setenv('CHECKIN_HISTORY_FILE', str(tmp_path / 'log' / 'h.jsonl'))
    assert history.path().endswith('h.jsonl')


def test_every_change_is_logged(env, client):
    post(client, 'D-22', 'Reykime', '10.0.2.144')
    post(client, 'D-23', 'Reykime', '10.0.2.144')     # same machine moves seat
    env.clear()
    env['10.0.2.200'] = 'aa:bb:cc:00:11:22'           # new DHCP lease
    checkin.refresh_once()
    checkin.remove('D-23')
    kinds = [(e['event'], e['seat']) for e in history.read_all()]
    assert kinds == [('checkin', 'D-22'), ('moved', 'D-22'), ('checkin', 'D-23'),
                     ('ip_changed', 'D-23'), ('removed', 'D-23')]
    moved, changed = history.read_all()[1], history.read_all()[3]
    assert moved['to_seat'] == 'D-23' and moved['mac'] == 'aa:bb:cc:00:11:22'
    assert changed['ip'] == '10.0.2.200' and changed['previous_ip'] == '10.0.2.144'


def test_history_can_be_turned_off(env, client, monkeypatch):
    monkeypatch.setenv('CHECKIN_HISTORY_ENABLED', 'false')
    post(client, 'D-1', 'a', '10.0.0.1')
    assert history.read_all() == [] and checkin.load_all()


def test_broken_history_never_blocks_checkin(env, client, monkeypatch, tmp_path):
    (tmp_path / 'dir').mkdir()
    monkeypatch.setenv('CHECKIN_HISTORY_FILE', str(tmp_path / 'dir'))   # a directory: open() fails
    post(client, 'D-1', 'a', '10.0.0.1')
    assert 'D-1' in checkin.load_all()


def test_reader_skips_torn_last_line(env, tmp_path):
    history.record('checkin', {'seat': 'D-1', 'username': 'a', 'ip': '10.0.0.1'}, ts=1)
    with open(history.path(), 'a') as f:
        f.write('{"ts": 2, "event": "chec')
    assert len(history.read_all()) == 1


def ev(ts, kind, seat, user='alice', ip='10.0.0.1', mac='aa:aa:aa:aa:aa:01', **kw):
    return dict(ts=ts, event=kind, seat=seat, username=user, ip=ip, mac=mac, **kw)


def test_sessions_fold():
    log = [
        ev(100, 'checkin', 'D-1'),
        ev(150, 'checkin', 'D-1'),                              # same person again: same session
        ev(200, 'ip_changed', 'D-1', ip='10.0.0.9', previous_ip='10.0.0.1'),
        ev(300, 'checkin', 'D-1', user='bob', ip='10.0.0.5', mac=None),   # bob takes the seat
        ev(400, 'moved', 'D-1', user='bob', ip='10.0.0.5', mac=None, to_seat='D-2'),
        ev(400, 'checkin', 'D-2', user='bob', ip='10.0.0.5', mac=None),
    ]
    s = history.sessions(log)
    assert [(x['seat'], x['username'], x['start'], x['end'], x['end_reason']) for x in s] == [
        ('D-1', 'alice', 100, 300, 'replaced'), ('D-1', 'bob', 300, 400, 'moved'),
        ('D-2', 'bob', 400, None, None)]
    assert s[0]['ips'] == ['10.0.0.1', '10.0.0.9']


def test_filters():
    rows = [ev(100, 'checkin', 'D-1'), ev(200, 'checkin', 'D-2', user='Bob', ip='10.0.3.4',
                                          mac='aa:aa:aa:aa:aa:02')]
    pick = lambda **a: [r['seat'] for r in rows if history.make_filter(a)(r)]  # noqa: E731
    assert pick(seat='d-2') == ['D-2']
    assert pick(user='bo') == ['D-2']
    assert pick(ip='10.0.3.') == ['D-2']
    assert pick(mac='AA-AA-AA-AA-AA-02') == ['D-2']
    assert pick(since='150') == ['D-2'] and pick(until='150') == ['D-1']
    # sessions overlap the window, not just start inside it
    sess = {'seat': 'D-1', 'username': 'a', 'mac': None, 'ips': ['10.0.0.1'], 'start': 100, 'end': None}
    assert history.make_filter({'since': '5000'})(sess)
    day = time.mktime((2026, 11, 14, 0, 0, 0, 0, 0, -1))
    assert history.parse_time('2026-11-14') == day
    assert history.parse_time('2026-11-14', end_of_day=True) > day + 86000
    assert history.parse_time('2026-11-14T20:30') == day + 20.5 * 3600
    with pytest.raises(ValueError):
        history.parse_time('saturday')


def test_csv_is_safe_for_spreadsheets():
    rows = [ev(100, 'checkin', 'D-1', user='=HYPERLINK("http://x")'), ev(200, 'checkin', 'D-2', user='Jörg')]
    text = history.to_csv(rows, 'events')
    assert text.startswith('﻿')
    parsed = list(csv.DictReader(io.StringIO(text.lstrip('﻿'))))
    assert parsed[0]['username'] == '\'=HYPERLINK("http://x")'
    assert parsed[1]['username'] == 'Jörg' and parsed[1]['timestamp'] == '200'
    assert list(parsed[0]) == list(history.EVENT_COLUMNS)


def test_history_api_and_csv(env, client):
    post(client, 'D-22', 'Reykime', '10.0.2.144')
    post(client, 'D-23', 'carol', '10.0.2.150')
    body = client.get('/api/checkins/history').get_json()
    assert body['view'] == 'sessions' and body['total'] == 2
    assert body['rows'][0]['seat'] == 'D-23' and body['rows'][0]['end'] is None
    body = client.get('/api/checkins/history?view=events&user=reyk').get_json()
    assert [r['seat'] for r in body['rows']] == ['D-22'] and body['rows'][0]['time_local']

    r = client.get('/api/checkins/history.csv?view=sessions&seat=D-22')
    assert r.mimetype == 'text/csv'
    assert 'attachment; filename="lal-checkins-sessions-' in r.headers['Content-Disposition']
    rows = list(csv.DictReader(io.StringIO(r.data.decode('utf-8-sig'))))
    assert len(rows) == 1 and rows[0]['mac'] == 'aa:bb:cc:00:11:22' and rows[0]['left'] == ''

    assert client.get('/api/checkins/history?view=nope').status_code == 400
    assert client.get('/api/checkins/history?since=saturday').status_code == 400
    assert b'Check-in history' in client.get('/checkins/history').data


def test_history_stays_readable_when_checkin_closes(env, client, monkeypatch):
    post(client, 'D-1', 'a', '10.0.0.1')
    monkeypatch.setenv('CHECKIN_ENABLED', 'false')
    assert client.get('/api/checkins/history').get_json()['total'] == 1


def test_history_needs_admin_token(env, client, monkeypatch):
    monkeypatch.setenv('CHECKIN_ADMIN_TOKEN', 's3cret')
    assert client.get('/api/checkins/history').status_code == 401
    assert client.get('/api/checkins/history.csv').status_code == 401
    assert client.get('/api/checkins/history', headers={'X-Admin-Token': 's3cret'}).status_code == 200


def test_history_settings_in_schema():
    keys = {i['key'] for i in config.describe()}
    assert {'CHECKIN_HISTORY_ENABLED', 'CHECKIN_HISTORY_FILE'} <= keys
    assert json.dumps(config.describe())
