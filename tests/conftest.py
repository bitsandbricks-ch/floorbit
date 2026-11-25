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
# Same for the check-in verifier: caught between a test's teardown steps it learned a seat's port
# into seat_ports.json in the checkout (and a run once committed that file).
os.environ.setdefault("CHECKIN_FILE", os.path.join(tempfile.mkdtemp(prefix="floorbit-checkins-"), "checkins.json"))

# Names a failing test before its report is built, and keeps that report quick (issue #1464).
pytest_plugins = ["tests.failure_report"]


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
    """The whole suite runs on SQLite by default, as Floorbit does: a fresh floorbit.db next to each
    test's data.json. FLOORBIT_TEST_DATABASE=postgres runs it on FLOORBIT_TEST_POSTGRES_URL, emptied
    per test (CI does both)."""
    kind = os.environ.get("FLOORBIT_TEST_DATABASE", "")
    if kind == "postgres":
        monkeypatch.setenv("FLOORBIT_DATABASE_URL", os.environ["FLOORBIT_TEST_POSTGRES_URL"])
        from floorbit import database
        db = database.Sql(os.environ["FLOORBIT_TEST_POSTGRES_URL"], str(tmp_path))
        db.run("DELETE FROM floorbit_documents")
        db.run("DELETE FROM floorbit_log")
        db.close()
    else:
        monkeypatch.delenv("FLOORBIT_DATABASE_URL", raising=False)     # the default: SQLite in the state folder
    yield


@pytest.fixture(autouse=True)
def fresh_monitoring_state(tmp_path, monkeypatch):
    """No last good monitoring data or outage carried over from another test (docs/offline.md)."""
    monkeypatch.setenv("MONITORING_CACHE_FILE", str(tmp_path / "monitoring-cache.json"))
    from floorbit import sources
    from floorbit.sources import lastgood
    lastgood.clear()
    sources.mark_ok(None)
    from integrations import seat_sources  # its merged mapping is kept 30 s: one test's seats aren't the next's
    seat_sources.invalidate()
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
    from floorbit.dhcp_leases import leases  # leases learned from syslog lines, in memory without Valkey
    leases.reset()


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
    # The power watch files an incident when a circuit turns red; under the demo's readings a round
    # landing mid-test added one to a test that counts the incidents. Tests that want readings
    # call the watch themselves.
    power = app.app.extensions["floorbit_power"]
    power.stop()
    monkeypatch.setattr(power, "start", lambda: None)
    from integrations.monitor import StatusMonitor
    StatusMonitor.latest.update(polled=None, at=None, devices=None)   # one that ran between tests
    app.app.config["TESTING"] = True
    yield app
    # Its thread outlives the test and polls for real once the patch above is undone; an agent
    # coming back in a later test wakes every monitor (sources.status_wake), so stop this one.
    monitor.stop()
    # The collector reads data.json and writes it back (its ingest token). Under Postgres every
    # test's data.json is one row, so a round that read this test's accounts and wrote after the
    # next test emptied the table brought them back ("User tester already exists", #1141).
    from floorbit import telemetry
    if telemetry._runner is not None:
        telemetry._runner.stop(wait=10)
        telemetry._runner = None


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
    import requests

    from floorbit.builtin_plugins.librenms import breaker, client
    from integrations.monitor import StatusMonitor
    breaker.reset()
    client.reset_caches()
    # Through requests.get, so a test's fake LibreNMS (monkeypatched requests.get) answers.
    breaker._send = lambda url, **kw: requests.get(url, **kw)
    StatusMonitor.latest.update(polled=None, at=None, devices=None)
    yield
    breaker.reset()
    client.reset_caches()


@pytest.fixture(autouse=True)
def _no_agent_releases_from_github(monkeypatch):
    """The app's hourly look at the agent's GitHub releases (floorbit/agent_updates.py) never runs
    in tests: tests/test_agent_updates.py hands refresh() a fake instead."""
    from floorbit import agent_updates
    monkeypatch.setattr(agent_updates, "_loop", lambda: None)


@pytest.fixture(autouse=True)
def _no_wrong_pins_yet(monkeypatch):
    """Wrong check-in PINs count per PC for ten minutes; one test's guesses don't lock the next."""
    from integrations import checkin
    monkeypatch.setattr(checkin, "_wrong_pins", {})


@pytest.fixture
def built(tmp_path, monkeypatch):
    """The React app counts as built, so its pages answer 200 (without a build they answer 503)."""
    from tests.test_spa import _manifest
    _manifest(tmp_path, monkeypatch, {"index.html": {"file": "assets/index.js"}})


@pytest.fixture
def lan_here(monkeypatch):
    """Run the LAN plugins in this process, as the local agent does in the hall: for tests of the
    plugins themselves (LibreNMS, NetBox, SSH, ...). This process then counts as the agent (it has
    an agent key); the Floorbit server never reaches the LAN itself (floorbit/agent_link.py, lan_here)."""
    monkeypatch.setenv("FLOORBIT_AGENT_KEY", "fba_0123abcd_example-key-for-tests-only")


FRONT_DOOR_KEY = "fba_0f0f0f0f_example-front-door-key-for-tests"


@pytest.fixture
def front_door(monkeypatch):
    """Attendees reach Floorbit through the local agent's front door, as in the hall: a request a
    test makes with ``environ_base={"REMOTE_ADDR": ip}`` arrives with the agent's key and the
    address the agent saw, which is the only address check-in takes (integrations/checkin.py,
    attendee_ip). Requests without it come from outside. The key check itself is tested in
    tests/test_front_door.py; here the agent's key is simply accepted."""
    from flask.testing import FlaskClient

    from floorbit import agent_link
    real_door = agent_link.front_door
    monkeypatch.setattr(agent_link, "front_door",
                        lambda key, now=None: "front-door" if key == FRONT_DOOR_KEY else real_door(key, now))
    real_open = FlaskClient.open

    def through_the_door(self, *args, **kwargs):
        ip = (kwargs.get("environ_base") or {}).get("REMOTE_ADDR")
        if ip:
            headers = dict(kwargs.pop("headers", None) or {})
            headers.setdefault("Floorbit-Front-Door", FRONT_DOOR_KEY)
            headers.setdefault("Floorbit-Client-IP", ip)
            kwargs["headers"] = headers
        return real_open(self, *args, **kwargs)
    monkeypatch.setattr(FlaskClient, "open", through_the_door)
    return FRONT_DOOR_KEY


# ── agents sign their requests (floorbit/agent_identity.py) ────────────────────────────────────

from tests.agent_keys import AGENT_KEYS, UNSIGNED, agent_csr, agent_signature  # noqa: E402


@pytest.fixture(autouse=True)
def _agents_sign(monkeypatch):
    """A request a test makes with an agent's key (``Floorbit-Agent-Key`` or the front door's) is
    signed with that agent's test key, enrolled the first time, as the real agent does. Tests of
    the signature itself send ``Floorbit-Test-Unsigned`` or their own ``Floorbit-Agent-Signature``."""
    from flask.testing import EnvironBuilder, FlaskClient

    from floorbit import agent_identity, agent_link
    AGENT_KEYS.clear()
    agent_identity._seen.clear()
    real_open = FlaskClient.open

    def signing_open(self, *args, **kwargs):
        if args and not isinstance(args[0], str):
            return real_open(self, *args, **kwargs)
        headers = dict(kwargs.get("headers") or {})
        key = headers.get("Floorbit-Agent-Key") or headers.get("Floorbit-Front-Door")
        m = agent_link.KEY_RE.match(str(key or "").strip())
        if not m or UNSIGNED in headers or agent_identity.SIGNATURE_HEADER in headers:
            headers.pop(UNSIGNED, None)
            if "headers" in kwargs:
                kwargs["headers"] = headers
            return real_open(self, *args, **kwargs)
        agent_id = m.group(1)
        path = args[0] if args else kwargs.get("path", "/")
        if path != agent_identity.OPEN_PATHS[1]:
            with self.application.app_context():
                pinned = agent_identity.pinned(agent_id)
            if pinned is None:
                real_open(self, agent_identity.OPEN_PATHS[1], method="POST",
                          json={"csr": agent_csr(agent_id)},
                          headers={"Floorbit-Agent-Key": key, "Floorbit-Agent-Protocol": "2"})
        builder = EnvironBuilder(self.application, *args, **{k: v for k, v in kwargs.items()
                                                             if k not in ("buffered", "follow_redirects")})
        try:
            req = builder.get_request()
            query = req.query_string.decode("latin-1")
            target = req.path + (f"?{query}" if query else "")
            body = req.get_data()
        finally:
            builder.close()
        headers[agent_identity.SIGNATURE_HEADER] = agent_signature(agent_id, req.method, target, body)
        kwargs["headers"] = headers
        return real_open(self, *args, **kwargs)
    monkeypatch.setattr(FlaskClient, "open", signing_open)


@pytest.fixture(autouse=True)
def _agent_lease_fresh(monkeypatch):
    """No lease holder remembered from another test, and Floorbit started long ago, so nothing
    waits for a holder after a restart (floorbit/agent_ha.py, tests/test_agent_ha_lease.py)."""
    from floorbit import agent_ha
    kept = {}
    monkeypatch.setattr(agent_ha, "_remembered", kept.get)
    monkeypatch.setattr(agent_ha, "_remember", kept.__setitem__)
    monkeypatch.setattr(agent_ha, "_started", -10 * agent_ha.STARTUP_GRACE)
    monkeypatch.setattr(agent_ha, "_back", set())
