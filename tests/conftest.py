"""Fixtures: the Flask test client with a throwaway data file and a fake Redis.

Nothing here talks to NetBox, LibreNMS or a real Redis.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

TEST_USER = "tester"
TEST_PASSWORD = "correct-horse-battery"


class FakeRedis:
    """Just enough of redis.Redis for the app's cache helpers."""

    def __init__(self, *args, **kwargs):
        self.store = {}

    def ping(self):
        return True

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, *args, **kwargs):
        self.store[key] = value
        return True

    def setex(self, key, ttl, value):
        self.store[key] = value
        return True

    def delete(self, *keys):
        return sum(1 for key in keys if self.store.pop(key, None) is not None)

    def keys(self, pattern="*"):
        prefix = pattern.rstrip("*")
        return [key for key in self.store if key.startswith(prefix)]

    def scan_iter(self, match="*", **kwargs):
        return iter(self.keys(match))

    def ttl(self, key):
        return 300 if key in self.store else -2

    def dbsize(self):
        return len(self.store)

    def info(self, *args, **kwargs):
        return {}


@pytest.fixture(autouse=True)
def fresh_monitoring_state(tmp_path, monkeypatch):
    """No last good monitoring data or outage carried over from another test (docs/offline.md)."""
    monkeypatch.setenv("MONITORING_CACHE_FILE", str(tmp_path / "monitoring-cache.json"))
    from floorbit import sources
    from floorbit.sources import lastgood
    lastgood.clear()
    sources.mark_ok(None)
    yield
    lastgood.clear()
    sources.mark_ok(None)


@pytest.fixture
def app_module(tmp_path, monkeypatch):
    for name in ("NETBOX_URL", "NETBOX_TOKEN", "LIBRENMS_URL", "LIBRENMS_TOKEN", "AUDIT_FILE", "PLUGINS_FILE",
                 "FLOORBIT_DEV_PLUGINS"):
        monkeypatch.delenv(name, raising=False)
    # Set before the first import, so the app never writes a generated key to ./data.json.
    monkeypatch.setenv("SECRET_KEY", "test-secret-key")

    import redis

    # Without this, every request retries a real Redis five times with a 2 s sleep.
    monkeypatch.setattr(redis, "Redis", FakeRedis)

    import app
    from floorbit import cache, runtime, store

    data_file = str(tmp_path / "data.json")
    monkeypatch.setattr(store, "DATA_FILE", data_file)
    # An installed Floorbit: the first-run setup (tests/test_setup.py) is over.
    store.write_json(data_file, {"setup": {"done": True, "steps": {}}})
    # The settings store was built at import time with the real data.json: point it at the temp file.
    settings = app.app.extensions["floorbit_settings"]
    monkeypatch.setattr(settings, "data_file", data_file)
    settings.reload()
    runtime.apply(settings)
    monkeypatch.setattr(cache, "redis_client", None)
    monkeypatch.setattr(runtime.rt, "netbox_enabled", False)
    monkeypatch.setattr(runtime.rt, "librenms_enabled", False)
    auth = app.app.extensions["auth"]
    # Accounts share the throwaway data file with the floor plan.
    monkeypatch.setattr(auth.users, "path", data_file)
    monkeypatch.setattr(auth, "enabled", True)
    monkeypatch.setattr(auth, "public_read", True)
    monkeypatch.setattr(auth, "_failures", {})
    app.app.config["TESTING"] = True
    return app


@pytest.fixture
def anon_client(app_module):
    """Nobody signed in."""
    return app_module.app.test_client()


@pytest.fixture
def client(app_module):
    """Signed in as TEST_USER, an admin, so tests can change anything."""
    app_module.app.extensions["auth"].users.add(TEST_USER, TEST_PASSWORD, role="admin")
    test_client = app_module.app.test_client()
    resp = test_client.post("/login", data={"username": TEST_USER, "password": TEST_PASSWORD})
    assert resp.status_code == 302, resp.data
    return test_client
