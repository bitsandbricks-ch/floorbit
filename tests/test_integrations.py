import json
import os
import sys
import threading

import pytest
from flask import Flask, jsonify, request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from integrations import checkin, config, events, init_integrations, seat_sources  # noqa: E402
from integrations.discord import DiscordNotifier  # noqa: E402
from integrations.monitor import StatusMonitor  # noqa: E402

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
