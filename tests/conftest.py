"""Fixtures: the Flask test client with a throwaway data file and a fake Redis.

Nothing here talks to NetBox, LibreNMS or a real Redis.
"""

import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# The local agent lives in bitsandbricks-ch/floorbit-agent; the hosted side's end-to-end tests run
# it. CI checks out the commit in AGENT_REF; locally, a clone next to this one is used.
_HERE = Path(__file__).resolve().parent.parent
_AGENT_SRC = Path(os.environ.get("FLOORBIT_AGENT_SRC") or _HERE.parent / "floorbit-agent")
if (_AGENT_SRC / "floorbit_agent" / "__init__.py").is_file():
    sys.path.insert(1, str(_AGENT_SRC.resolve()))

# The collector's background thread can outlive the test that started it (and its monkeypatch), and
# then writes Telegraf's config into the checkout: give the whole run a folder of its own too.
_TELEGRAF_DIR = tempfile.mkdtemp(prefix="floorbit-telegraf-")
os.environ.setdefault("FLOORBIT_TELEGRAF_CONF", os.path.join(_TELEGRAF_DIR, "telegraf.conf"))


def login_page(client):
    """What the sign-in page (React, issue #46) shows: its options and the last error, once."""
    return client.get("/api/auth/login-options").get_json()


def login_error(client):
    return login_page(client)["error"] or ""


def stored(path):
    """A document as Floorbit keeps it (a file, or a row when the suite runs on a database), as text:
    for tests that check what is, or isn't, written down."""
    import json

    from floorbit import store
    return json.dumps(store.read_json(str(path), None))


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
def database_under_test(tmp_path, monkeypatch):
    """The whole suite runs on files by default. FLOORBIT_TEST_DATABASE=sqlite runs it on a fresh
    SQLite file per test, =postgres on FLOORBIT_TEST_POSTGRES_URL emptied per test (CI does both)."""
    kind = os.environ.get("FLOORBIT_TEST_DATABASE", "")
    if kind == "sqlite":
        monkeypatch.setenv("FLOORBIT_DATABASE_URL", f"sqlite:///{tmp_path / 'floorbit.db'}")
    elif kind == "postgres":
        monkeypatch.setenv("FLOORBIT_DATABASE_URL", os.environ["FLOORBIT_TEST_POSTGRES_URL"])
        from floorbit import database
        db = database.Sql(os.environ["FLOORBIT_TEST_POSTGRES_URL"], str(tmp_path))
        db.run("DELETE FROM floorbit_documents")
        db.run("DELETE FROM floorbit_log")
        db.close()
    else:
        monkeypatch.delenv("FLOORBIT_DATABASE_URL", raising=False)
    yield


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
    from floorbit import port_clients  # its last MAC table read feeds the seat mapping
    if port_clients._finder is not None:
        port_clients._finder.reset()
    from integrations import checkin  # the port lookup budget is per process
    checkin._bucket.update(tokens=None, at=None)
    checkin._warm.clear()
    checkin._port_cache.clear()


@pytest.fixture
def app_module(tmp_path, monkeypatch):
    for name in ("NETBOX_URL", "NETBOX_TOKEN", "LIBRENMS_URL", "LIBRENMS_TOKEN", "AUDIT_FILE", "PLUGINS_FILE",
                 "FLOORBIT_DEV_PLUGINS"):
        monkeypatch.delenv(name, raising=False)
    # Set before the first import, so the app never writes a generated key to ./data.json.
    monkeypatch.setenv("SECRET_KEY", "test-secret-key")

    import redis

    # No test talks to a real Redis.
    monkeypatch.setattr(redis, "Redis", FakeRedis)

    import app
    from floorbit import cache, runtime, store

    data_file = str(tmp_path / "data.json")
    # The demo seeds check-ins: keep them (and the learned ports and history beside them) out of the checkout.
    monkeypatch.setenv("CHECKIN_FILE", str(tmp_path / "checkins.json"))
    # Telegraf's config is written where the state lives (the checkout, in tests): keep it out.
    monkeypatch.setenv("FLOORBIT_TELEGRAF_CONF", str(tmp_path / "telegraf" / "telegraf.conf"))
    monkeypatch.setattr(store, "DATA_FILE", data_file)
    # An installed Floorbit: the first-run setup (tests/test_setup.py) is over.
    store.write_json(data_file, {"setup": {"done": True, "steps": {}}})
    # The settings store was built at import time with the real data.json: point it at the temp file.
    settings = app.app.extensions["floorbit_settings"]
    monkeypatch.setattr(settings, "data_file", data_file)
    settings.reload()
    runtime.apply(settings)
    monkeypatch.setattr(cache, "redis_client", None)
    monkeypatch.setattr(cache, "_next_try", 0.0)   # a Redis away in one test is not away in the next
    from floorbit import recording
    # The whole-event recording remembers its last frame: start each test without one.
    monkeypatch.setattr(recording, "_state", {"last": None, "compacted": 0.0})
    monkeypatch.setattr(runtime.rt, "netbox_enabled", False)
    monkeypatch.setattr(runtime.rt, "librenms_enabled", False)
    auth = app.app.extensions["auth"]
    # Accounts share the throwaway data file with the floor plan.
    monkeypatch.setattr(auth.users, "path", data_file)
    monkeypatch.setattr(auth, "enabled", True)
    monkeypatch.setattr(auth, "public_read", True)
    monkeypatch.setattr(auth, "_failures", {})
    # Lines a local agent relayed in an earlier test would show as relayed in the next one.
    receiver = app.app.extensions.get("floorbit_syslog")
    if receiver is not None:
        monkeypatch.setattr(receiver, "relayed", {})
    # The app's status monitor starts polling with the first request and goes on every minute: a
    # poll landing mid-test replaced the statuses or "last poll" a test had set up. Tests that
    # want a poll call one themselves.
    monitor = app.app.extensions["floorbit_integrations"]["monitor"]
    monkeypatch.setattr(monitor, "poll_once", lambda *a, **k: None)
    from integrations.monitor import StatusMonitor
    StatusMonitor.latest.update(polled=None, at=None, devices=None)   # one that ran between tests
    app.app.config["TESTING"] = True
    return app


@pytest.fixture
def anon_client(app_module):
    """Nobody signed in."""
    return app_module.app.test_client()


@pytest.fixture
def kiosk_client(app_module):
    """Signed in with a kiosk account: floorplan.view only, like a big screen."""
    app_module.app.extensions["auth"].users.add("screen-1", "kiosk-password-1", role="kiosk")
    c = app_module.app.test_client()
    c.post("/login", data={"username": "screen-1", "password": "kiosk-password-1"})
    return c


@pytest.fixture
def client(app_module):
    """Signed in as TEST_USER, an admin, so tests can change anything."""
    app_module.app.extensions["auth"].users.add(TEST_USER, TEST_PASSWORD, role="admin")
    test_client = app_module.app.test_client()
    resp = test_client.post("/login", data={"username": TEST_USER, "password": TEST_PASSWORD})
    assert resp.status_code == 302, resp.data
    return test_client


@pytest.fixture(autouse=True)
def _librenms_answers_again():
    """A LibreNMS that didn't answer in one test answers in the next (librenms/breaker.py), and no
    status monitor has polled yet."""
    from floorbit.builtin_plugins.librenms import breaker
    from integrations.monitor import StatusMonitor
    breaker.reset()
    StatusMonitor.latest.update(polled=None, at=None, devices=None)
    yield
    breaker.reset()


@pytest.fixture(autouse=True)
def _no_wrong_pins_yet(monkeypatch):
    """Wrong check-in PINs count per PC for ten minutes; one test's guesses don't lock the next."""
    from integrations import checkin
    monkeypatch.setattr(checkin, "_wrong_pins", {})
