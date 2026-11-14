import json
import os
import sys
import threading

import pytest
from flask import Flask, jsonify

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from integrations import checkin, config, events, init_integrations, seat_sources
from integrations.discord import DiscordNotifier
from integrations.monitor import StatusMonitor

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
    events._subscribers.clear()


# ── config ───────────────────────────────────────────────────────────────────────────
def test_config_env_then_provider(monkeypatch):
    monkeypatch.setenv('DISCORD_COOLDOWN', '60')
    assert config.get_int('DISCORD_COOLDOWN', 300) == 60
    config.set_provider(lambda k: {'DISCORD_COOLDOWN': 10}.get(k))
    assert config.get_int('DISCORD_COOLDOWN', 300) == 10
    # unknown to the provider → env fallback
    monkeypatch.setenv('PUBLIC_URL', 'http://lan')
    assert config.get('PUBLIC_URL') == 'http://lan'


def test_describe_masks_secrets(monkeypatch):
    monkeypatch.setenv('DISCORD_WEBHOOK_URL', 'https://discord.com/api/webhooks/1/secret')
    item = next(i for i in config.describe() if i['key'] == 'DISCORD_WEBHOOK_URL')
    assert item['value'] == '••••' and 'secret' not in json.dumps(item['value'])


# ── monitor ──────────────────────────────────────────────────────────────────────────
def make_monitor(devices, switches, monkeypatch, confirm='1'):
    monkeypatch.setenv('LIBRENMS_URL', 'http://nms')
    monkeypatch.setenv('LIBRENMS_TOKEN', 't')
    monkeypatch.setenv('STATUS_MONITOR_CONFIRM', confirm)
    m = StatusMonitor(lambda: switches)
    m.fetch_devices = lambda: devices
    return m


def test_monitor_baseline_then_change(monkeypatch):
    devices = [{'display': 'sw-a1', 'hostname': 'sw-a1.lan', 'status': 1}]
    m = make_monitor(devices, [{'id': '1', 'name': 'SW-A1'}], monkeypatch)
    got = []
    events.subscribe('switch.status', got.append)
    assert m.poll_once() == []            # baseline, no alert
    devices[0]['status'] = 0
    changes = m.poll_once()
    assert changes[0]['status'] == 'offline' and changes[0]['previous'] == 'online'
    assert got and got[0]['data']['id'] == '1'
    assert m.snapshot() == {'1': 'offline'}


def test_monitor_confirm_ignores_flap(monkeypatch):
    devices = [{'display': 'sw-a1', 'status': 1}]
    m = make_monitor(devices, [{'id': '1', 'name': 'sw-a1'}], monkeypatch, confirm='2')
    m.poll_once()
    devices[0]['status'] = 0
    assert m.poll_once() == []            # seen once
    devices[0]['status'] = 1
    assert m.poll_once() == []            # back, flap ignored
    devices[0]['status'] = 0
    m.poll_once()
    assert m.poll_once()[0]['status'] == 'offline'


def test_monitor_short_name_match():
    devices = [{'display': 'other', 'hostname': 'sw-b2.core.lan', 'status': 1}]
    assert StatusMonitor.match('SW-B2', devices) is devices[0]
    assert StatusMonitor.match('nope', devices) is None


# ── discord ──────────────────────────────────────────────────────────────────────────
def change(sid, status, previous):
    return {'id': sid, 'name': f'sw-{sid}', 'status': status, 'previous': previous, 'down_for': 125}


def test_discord_batches_and_mentions(monkeypatch):
    monkeypatch.setenv('DISCORD_MENTION', '@here')
    d = DiscordNotifier()
    p = d.build_status_message([change('1', 'offline', 'online'), change('2', 'offline', 'online')])
    assert len(p['embeds']) == 2
    assert p['content'].startswith('@here') and '2 switches went offline' in p['content']


def test_discord_cooldown_and_recovery(monkeypatch):
    d = DiscordNotifier()
    assert d.build_status_message([change('1', 'offline', 'online')], now=1000)
    assert d.build_status_message([change('1', 'offline', 'online')], now=1100) is None  # cooldown
    rec = d.build_status_message([change('1', 'online', 'offline')], now=1150)
    assert 'back online' in rec['embeds'][0]['title']
    assert rec['embeds'][0]['fields'][1]['value'] == '2m 5s'
    monkeypatch.setenv('DISCORD_NOTIFY_RECOVERY', 'false')
    assert d.build_status_message([change('2', 'online', 'offline')], now=2000) is None
    # unknown → online is a new match, not a recovery
    monkeypatch.setenv('DISCORD_NOTIFY_RECOVERY', 'true')
    assert d.build_status_message([change('3', 'online', 'unknown')], now=2000) is None


def test_discord_send_retries_429(monkeypatch):
    monkeypatch.setenv('DISCORD_WEBHOOK_URL', 'http://hook')
    calls = []

    class R:
        def __init__(self, code):
            self.status_code, self.text = code, ''

        def json(self):
            return {'retry_after': 0}

    def fake_post(url, json, timeout):
        calls.append(json)
        return R(429 if len(calls) == 1 else 204)

    monkeypatch.setattr('integrations.discord.requests.post', fake_post)
    assert DiscordNotifier().send({'content': 'x'}) is True
    assert len(calls) == 2


# ── seat sources ─────────────────────────────────────────────────────────────────────
def test_seat_sources_merge(tmp_path, monkeypatch):
    f = tmp_path / 'seats.json'
    f.write_text(json.dumps({'_metadata': {}, 'seats': {
        'A-1': {'username': 'alice', 'ip_address': '10.0.0.1'},
        'A-2': {'username': 'bob', 'ip_address': ''},
    }}))
    monkeypatch.setenv('SEAT_SOURCE_JSON_PATH', str(f))

    @seat_sources.register
    class Fake(seat_sources.SeatSource):
        name = 'fake'

        def fetch(self):
            return {'A-2': {'ip': '10.0.0.2'}, 'B-1': {'user': 'carol', 'ip': '10.0.0.9'}}

    monkeypatch.setenv('SEAT_SOURCES', 'fake,json,missing')
    seats = seat_sources.load(max_age=0)
    assert seats['A-1']['ip_address'] == '10.0.0.1'
    assert seats['A-2'] == {'ip': '10.0.0.2', 'ip_address': '10.0.0.2', 'username': 'bob',
                            'sources': ['fake', 'json']}
    assert seats['B-1']['username'] == 'carol'
    assert seat_sources.info()['errors'] == {'missing': 'unknown source'}


# ── HTTP wiring ──────────────────────────────────────────────────────────────────────────
@pytest.fixture
def app():
    data = {'switches': [{'id': 's1', 'name': 'sw-a1', 'placed': True, 'x': 5, 'y': 5}],
            'cached_devices': [{'id': '9', 'name': 'nb-1'}], 'positions': {'9': {'x': 1, 'y': 1}},
            'seat_blocks': [{'name': 'd', 'cols': 4, 'rows': 6}]}
    a = Flask(__name__, template_folder=os.path.join(ROOT, 'templates'))

    @a.route('/api/switches/<sid>', methods=['PUT'])
    def put(sid):
        return jsonify({'id': sid})

    a.ext = init_integrations(a, load_data=lambda: data, start_background=False)
    return a


def test_integrations_endpoint(app):
    body = app.test_client().get('/api/integrations').get_json()
    assert set(body) >= {'live', 'monitor', 'discord', 'seat_sources', 'settings'}
    assert body['discord']['configured'] is False


def test_placed_switches_includes_netbox(app):
    names = [s['name'] for s in app.ext['monitor']._list_switches()]
    assert names == ['sw-a1', 'nb-1']


def test_write_publishes_data_changed(app):
    got = []
    events.subscribe('data.changed', got.append)
    app.test_client().put('/api/switches/s1', json={}, headers={'X-Client-Id': 'abc'})
    assert got[0]['data']['resource'] == 'switches' and got[0]['origin'] == 'abc'


def test_sse_stream_delivers_events(app):
    gen = events.stream({'statuses': {}})
    assert next(gen).startswith('retry')
    assert 'event: hello' in next(gen)
    threading.Timer(0.05, lambda: events.publish('switch.status', {'id': 's1', 'status': 'offline'})).start()
    msg = next(gen)
    assert 'event: switch.status' in msg and '"offline"' in msg
    gen.close()
    assert events.client_count() == 0


def test_discord_test_endpoint_needs_webhook(app):
    r = app.test_client().post('/api/integrations/discord/test')
    assert r.status_code == 400


# ── check-in ─────────────────────────────────────────────────────────────────────────
@pytest.fixture
def checkin_env(tmp_path, monkeypatch):
    monkeypatch.setenv('CHECKIN_ENABLED', 'true')
    monkeypatch.setenv('CHECKIN_FILE', str(tmp_path / 'checkins.json'))
    arp = {'10.0.2.144': 'AA-BB-CC-00-11-22'}
    monkeypatch.setattr(checkin, 'lookup_mac', lambda ip: checkin.normalise_mac(arp.get(ip)))
    monkeypatch.setattr(checkin, 'lookup_ip', lambda mac: next(
        (ip for ip, m in arp.items() if checkin.normalise_mac(m) == mac), None))
    return arp


def post_checkin(client, seat, user, ip):
    return client.post('/api/checkin', json={'seat': seat, 'username': user},
                       environ_base={'REMOTE_ADDR': ip})


def test_checkin_disabled_by_default(app):
    assert app.test_client().get('/checkin').status_code == 404
    assert post_checkin(app.test_client(), 'D-1', 'x', '10.0.0.1').status_code == 404


def test_checkin_records_ip_and_mac(app, checkin_env, monkeypatch):
    c = app.test_client()
    assert b'Seat check-in' in c.get('/checkin').data
    r = post_checkin(c, 'd-22', 'Reykime', '10.0.2.144').get_json()
    assert r == {'ok': True, 'seat': 'D-22', 'username': 'Reykime', 'ip': '10.0.2.144', 'mac_found': True}
    row = c.get('/api/checkins').get_json()['checkins'][0]
    assert row['mac'] == 'aa:bb:cc:00:11:22'
    me = c.get('/api/checkin/me', environ_base={'REMOTE_ADDR': '10.0.2.144'}).get_json()
    assert me['checkin']['seat'] == 'D-22'
    # feeds the seat sources
    monkeypatch.setenv('SEAT_SOURCES', 'checkin')
    seats = seat_sources.load(max_age=0)
    assert seats['D-22']['mac_address'] == 'aa:bb:cc:00:11:22'


def test_checkin_validation(app, checkin_env, monkeypatch):
    c = app.test_client()
    assert 'not on the floor plan' in post_checkin(c, 'Z-99', 'x', '10.0.0.5').get_json()['error']
    assert post_checkin(c, 'D-1', '', '10.0.0.5').status_code == 400
    monkeypatch.setenv('CHECKIN_ALLOWED_NETWORKS', '10.0.0.0/16')
    assert post_checkin(c, 'D-1', 'x', '192.168.1.5').status_code == 403
    assert post_checkin(c, 'D-1', 'x', '10.0.9.5').status_code == 200


def test_checkin_moves_machine_between_seats(app, checkin_env):
    c = app.test_client()
    post_checkin(c, 'D-1', 'bob', '10.0.0.7')
    post_checkin(c, 'D-2', 'bob', '10.0.0.7')
    assert list(checkin.load_all()) == ['D-2']


def test_checkin_follows_dhcp_change(app, checkin_env):
    c = app.test_client()
    post_checkin(c, 'D-22', 'Reykime', '10.0.2.144')
    checkin_env.clear()
    checkin_env['10.0.2.200'] = 'aa:bb:cc:00:11:22'   # new lease, same MAC
    assert checkin.refresh_once() == ['D-22']
    row = checkin.load_all()['D-22']
    assert row['ip'] == '10.0.2.200' and row['ip_changed']


def test_checkin_admin_token(app, checkin_env, monkeypatch):
    monkeypatch.setenv('CHECKIN_ADMIN_TOKEN', 's3cret')
    c = app.test_client()
    assert c.get('/api/checkins').status_code == 401
    assert c.get('/api/checkins', headers={'X-Admin-Token': 's3cret'}).status_code == 200


def test_trust_proxy(app, checkin_env, monkeypatch):
    c = app.test_client()
    hdr = {'X-Forwarded-For': '10.0.3.3, 172.16.0.1'}
    r = c.post('/api/checkin', json={'seat': 'D-3', 'username': 'a'}, headers=hdr,
               environ_base={'REMOTE_ADDR': '172.16.0.1'}).get_json()
    assert r['ip'] == '172.16.0.1'
    monkeypatch.setenv('CHECKIN_TRUST_PROXY', 'true')
    r = c.post('/api/checkin', json={'seat': 'D-3', 'username': 'a'}, headers=hdr,
               environ_base={'REMOTE_ADDR': '172.16.0.1'}).get_json()
    assert r['ip'] == '10.0.3.3'


# ── settings store bridge ──────────────────────────────────────────────────────────────────
def test_settings_bridge(monkeypatch, tmp_path):
    import types

    from integrations import settings_bridge

    mod = types.ModuleType('fake_settings_store')
    mod.SECTIONS = [{'id': 'librenms', 'title': 'LibreNMS', 'description': ''}]
    mod.FIELDS = [dict(key='librenms.url', section='librenms', label='URL', type='url',
                       env='LIBRENMS_URL', default='')]
    mod.FIELDS_BY_KEY = {f['key']: f for f in mod.FIELDS}

    class Store:
        __module__ = 'fake_settings_store'

        def __init__(self):
            self.saved = {'librenms.url': 'http://saved-nms',
                          'integrations.seat_sources': ['checkin', 'json'],
                          'integrations.discord_cooldown': 42}

        def reload(self):
            pass

        def reload_if_changed(self):
            return False

        def source(self, key):
            return 'saved' if key in self.saved else 'default'

        def get(self, key):
            return self.saved.get(key, mod.FIELDS_BY_KEY[key]['default'])

    monkeypatch.setitem(sys.modules, 'fake_settings_store', mod)
    monkeypatch.setenv('LIBRENMS_URL', 'http://env-nms')
    monkeypatch.setenv('DISCORD_USERNAME', 'from-env')
    assert settings_bridge.connect(Store()) is True

    keys = {f['key']: f for f in mod.FIELDS}
    assert keys['integrations.discord_webhook_url']['type'] == 'secret'
    assert keys['integrations.seat_sources']['type'] == 'list'
    assert keys['integrations.status_monitor_interval']['min'] == 10
    assert {s['id'] for s in mod.SECTIONS} >= {'discord', 'checkin', 'monitor'}

    assert config.get('LIBRENMS_URL') == 'http://saved-nms'      # store's own field
    assert seat_sources.active_names() == ['checkin', 'json']       # list → csv
    assert config.get_int('DISCORD_COOLDOWN', 300) == 42
    assert config.get('DISCORD_USERNAME') == 'from-env'             # not saved → env
    assert config.get('DISCORD_MENTION', 'dflt') == 'dflt'          # → default
