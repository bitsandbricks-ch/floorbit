"""Operational settings that used to be env-only are on the settings page (issue: env settings in the
UI): a value saved there wins over the env var, the env var stays the fallback, and leaving the field
empty again goes back to it."""
import pytest

from integrations import config, settings_bridge

MOVED = ('ATTENTION_INTERVAL', 'SYSLOG_ALLOW', 'SYSLOG_RETENTION_HOURS', 'DNS_MIN_SEATS', 'FORECAST_CAPACITY_MBPS',
         'CONFIG_KEEP', 'TERMINAL_IDLE_MINUTES', 'CHECKIN_PIN_TRIES', 'SEAT_FINDER', 'SEAT_FINDER_NICKS')
BOOTSTRAP = ('SECRET_KEY', 'REDIS_URL', 'DATABASE_URL', 'FLOORBIT_DATA_FILE', 'SYSLOG_PORT', 'PROBE_NETS')


def test_the_moved_settings_are_on_the_page_and_bootstrap_ones_are_not(client):
    values = client.get("/api/settings").get_json()["values"]
    for env in MOVED:
        assert 'integrations.' + env.lower() in values, env
    keys = {item['key'] for item in config.SCHEMA}
    assert not keys & set(BOOTSTRAP)


@pytest.fixture
def connected(app_module, monkeypatch):
    # Other tests clear the provider (the app is imported once), so connect this app's store again.
    settings_bridge.connect(app_module.app.extensions['floorbit_settings'])
    yield
    config.set_provider(None)


def test_saved_wins_over_env_and_clearing_goes_back(client, connected, monkeypatch):
    monkeypatch.setenv("DNS_MIN_SEATS", "7")
    assert config.get_int('DNS_MIN_SEATS', 5) == 7
    assert client.put("/api/settings", json={"integrations.dns_min_seats": 12}).status_code == 200
    assert config.get_int('DNS_MIN_SEATS', 5) == 12
    assert client.put("/api/settings", json={"integrations.dns_min_seats": None}).status_code == 200
    assert config.get_int('DNS_MIN_SEATS', 5) == 7


def test_limits_hold(client):
    assert client.put("/api/settings", json={"integrations.dns_min_seats": 4}).status_code == 400
    assert client.put("/api/settings", json={"integrations.attention_interval": 5}).status_code == 400


def test_a_list_saves_as_the_comma_separated_value(client, connected):
    assert client.put("/api/settings", json={"integrations.syslog_allow": ["192.0.2.0/24", "198.51.100.7"]}
                      ).status_code == 200
    assert config.get('SYSLOG_ALLOW') == '192.0.2.0/24,198.51.100.7'
