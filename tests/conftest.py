"""Fixtures: the Flask test client with a throwaway data file and a fake Redis.

Nothing here talks to NetBox, LibreNMS or a real Redis.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


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


@pytest.fixture
def app_module(tmp_path, monkeypatch):
    for name in ("NETBOX_URL", "NETBOX_TOKEN", "LIBRENMS_URL", "LIBRENMS_TOKEN"):
        monkeypatch.delenv(name, raising=False)

    import redis

    # Without this, every request retries a real Redis five times with a 2 s sleep.
    monkeypatch.setattr(redis, "Redis", FakeRedis)

    import app

    monkeypatch.setattr(app, "DATA_FILE", str(tmp_path / "data.json"))
    monkeypatch.setattr(app, "redis_client", None)
    monkeypatch.setattr(app, "NETBOX_ENABLED", False)
    monkeypatch.setattr(app, "LIBRENMS_ENABLED", False)
    app.app.config["TESTING"] = True
    return app


@pytest.fixture
def client(app_module):
    return app_module.app.test_client()
