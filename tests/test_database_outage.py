"""The database goes away while Floorbit runs, or isn't there when it starts (docs/database.md):
pages keep working on the last copies read, saving answers 503 in the reader's language, /healthz
stays up and says so, and everything comes back by itself."""
import sqlite3
import time

import pytest

from floorbit import database, store


def cut(db):
    """Pull the plug: every new connection is refused and the pool's open ones are dropped."""
    def refuse():
        raise sqlite3.OperationalError("unable to open database file")
    db._connect = refuse
    db.close()


def restore(db, now=True):
    del db._connect
    if now and db.down:
        db.down["next_try"] = 0        # don't wait for the next try in a test


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA_FILE", str(tmp_path / "data.json"))
    monkeypatch.setenv(database.ENV, f"sqlite:///{tmp_path / 'floorbit.db'}")
    b = database.backend()
    yield b
    if "_connect" in vars(b):
        del b._connect
    b.down = None
    b.close()


def test_reads_keep_the_last_copy_and_saving_is_refused(db, tmp_path):
    path = str(tmp_path / "data.json")
    store.write_json(path, {"halls": ["main"]})
    assert store.read_json(path) == {"halls": ["main"]}
    before = store.stamp(path)
    templates = str(tmp_path / "templates")
    store.write_json(f"{templates}/a.json", {"name": "a"})
    assert store.list_json(templates) == ["a.json"]

    cut(db)
    got = store.read_json(path)
    assert got == {"halls": ["main"]}
    got["halls"].append("changed by the caller")      # each read is its own copy
    assert store.read_json(path) == {"halls": ["main"]}
    assert store.stamp(path) == before                  # caches see no change
    assert store.list_json(templates) == ["a.json"]
    with pytest.raises(database.DatabaseUnavailable):
        store.write_json(path, {"halls": []})
    with pytest.raises(database.DatabaseUnavailable):
        store.read_json(str(tmp_path / "never-read.json"))   # no copy: never "empty" instead
    status = database.status()
    assert status["ok"] is False and status["since"] <= time.time() and "retry_in" in status
    assert database.available() is False

    restore(db)
    assert database.status()["ok"] is True and db.down is None
    store.write_json(path, {"halls": ["main", "annex"]})
    assert store.read_json(path) == {"halls": ["main", "annex"]}


def test_while_it_is_away_only_one_try_per_wait_and_the_waits_grow(db, tmp_path, monkeypatch):
    store.write_json(str(tmp_path / "data.json"), {"a": 1})
    tries = []

    def refuse():
        tries.append(time.monotonic())
        raise sqlite3.OperationalError("unable to open database file")
    db._connect = refuse
    db.close()
    for _ in range(20):                       # a burst of requests: one try, the rest give up at once
        assert store.read_json(str(tmp_path / "data.json")) == {"a": 1}
    assert len(tries) == 1 and db.down["wait"] == database.RETRY_FIRST
    waits = []
    for _ in range(8):
        db.down["next_try"] = 0
        database.status()
        waits.append(db.down["wait"])
    assert waits[:3] == [2.0, 4.0, 8.0] and waits[-1] == database.RETRY_MAX


def test_a_dropped_connection_is_reopened_without_counting_as_down(db, tmp_path):
    path = str(tmp_path / "data.json")
    store.write_json(path, {"a": 1})
    class Gone:                               # a server restart under an open connection
        def cursor(self):
            return self

        def execute(self, *args):
            raise sqlite3.OperationalError("server closed the connection unexpectedly")

        def close(self):
            pass
    db.close()
    db._idle.append(Gone())
    assert store.read_json(path) == {"a": 1} and db.down is None


def test_the_watch_notices_it_coming_back(db, tmp_path, monkeypatch):
    monkeypatch.setattr(database, "RETRY_FIRST", 0.05)
    monkeypatch.setattr(database, "PROBE_EVERY", 0.05)
    monkeypatch.setattr(database, "_watch_started", False)
    store.write_json(str(tmp_path / "data.json"), {"a": 1})
    cut(db)
    database.watch()
    deadline = time.time() + 5
    while db.down is None and time.time() < deadline:
        time.sleep(0.02)
    assert db.down is not None                # noticed without a request
    restore(db, now=False)
    while db.down is not None and time.time() < deadline:
        time.sleep(0.02)
    assert db.down is None                    # and back, also without one


def test_a_connection_borrowed_across_a_close_is_not_handed_out_again(db, tmp_path):
    # Another thread (the watch, a collector) may hold one while the plug is pulled.
    store.write_json(str(tmp_path / "data.json"), {"a": 1})
    with db.connection() as held:
        db.close()
    assert held not in db._idle and db._idle == []


def test_counters_wait_for_their_counts_instead_of_overwriting_them(db, tmp_path):
    from floorbit.dns import DnsStats
    path = str(tmp_path / "dns.json")
    store.write_json(path, {"version": 1, "hours": {"3600": {"lookups": 7, "blocked": 1, "sites": {}}}})
    db._docs.clear()                          # as after a restart: nothing read yet
    cut(db)
    stats = DnsStats(path=path)
    assert stats.ready() is False and stats.hours == {}
    stats._save()                             # nothing written over the stored hours
    stats.poll_once(now=7200)
    assert stats.last_error and stats.hours == {}
    restore(db)
    assert stats.ready() is True and stats.hours[3600]["lookups"] == 7


# ── the app ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def app_db(tmp_path, monkeypatch, client):
    """The test app, signed in, keeping its documents in SQLite."""
    monkeypatch.setenv(database.ENV, f"sqlite:///{tmp_path / 'app.db'}")
    b = database.backend()
    from tests.conftest import TEST_PASSWORD, TEST_USER
    store.write_json(store.DATA_FILE, {"setup": {"done": True, "steps": {}}})
    import app
    app.app.extensions["auth"].users.add(TEST_USER, TEST_PASSWORD, role="admin")
    assert client.post("/login", data={"username": TEST_USER, "password": TEST_PASSWORD}).status_code == 302
    yield client, b
    if "_connect" in vars(b):
        del b._connect
    b.down = None
    b.close()


def test_the_app_keeps_serving_and_refuses_saves_clearly(app_db, anon_client):
    client, db = app_db
    mark = {"kind": "text", "x": 10, "y": 10, "text": "Stage"}
    assert client.post("/api/plan-marks", json=mark).status_code == 201
    assert client.get("/api/plan-marks").status_code == 200        # read once: there is a copy
    assert client.get("/api/halls").status_code == 200

    cut(db)
    health = anon_client.get("/healthz")
    assert health.status_code == 200 and health.get_json()["database"] == "down"
    assert anon_client.get("/healthz?strict=1").status_code == 503
    marks = client.get("/api/plan-marks")
    assert marks.status_code == 200 and [m["text"] for m in marks.get_json()["marks"]] == ["Stage"]
    assert client.get("/api/halls").status_code == 200

    saved = client.post("/api/plan-marks", json=mark, headers={"Accept-Language": "de-CH"})
    assert saved.status_code == 503 and saved.headers["Retry-After"] == "10"
    assert saved.get_json()["code"] == "database_unavailable"
    assert saved.get_json()["error"].startswith("Die Datenbank antwortet gerade nicht")

    restore(db)
    assert anon_client.get("/healthz").get_json() == {"ok": True, "database": "up"}
    assert client.post("/api/plan-marks", json=mark).status_code == 201
    assert len(client.get("/api/plan-marks").get_json()["marks"]) == 2


def test_another_program_holding_the_file_is_busy_not_down(app_db, anon_client, tmp_path):
    """A backup tool or a ``sqlite3`` shell with the file open for writing: that save gets a 503 to
    retry, not an HTML 500, and Floorbit doesn't think the database is gone."""
    client, db = app_db
    mark = {"kind": "text", "x": 10, "y": 10, "text": "Stage"}
    assert client.post("/api/plan-marks", json=mark).status_code == 201
    db.busy_wait = 0.2
    db.close()                              # the pool's connections were opened with the long wait
    other = sqlite3.connect(tmp_path / "app.db", isolation_level=None)
    other.execute("BEGIN EXCLUSIVE")
    try:
        saved = client.post("/api/plan-marks", json=mark, headers={"Accept-Language": "de-CH"})
        assert saved.status_code == 503 and saved.headers["Retry-After"] == "2"
        assert saved.get_json()["code"] == "database_busy"
        assert saved.get_json()["error"].startswith("Die Datenbank ist gerade mit einem anderen Programm")
        assert db.down is None and anon_client.get("/healthz").get_json()["database"] == "up"
    finally:
        other.execute("ROLLBACK")
        other.close()
    assert client.post("/api/plan-marks", json=mark).status_code == 201


def test_a_page_without_any_copy_says_so_instead_of_an_error(app_module):
    from floorbit.blueprints.health import database_unavailable
    app = app_module.app
    with app.test_request_context("/status", headers={"Accept-Language": "de-CH", "Accept": "text/html"}):
        page = database_unavailable(database.DatabaseUnavailable("gone"))
    assert page.status_code == 503 and page.headers["Retry-After"] == "10"
    text = page.get_data(as_text=True)
    assert "Datenbank nicht erreichbar" in text and 'http-equiv="refresh"' in text
    with app.test_request_context("/api/halls"):
        answer = database_unavailable(database.DatabaseUnavailable("gone"))
    assert answer.status_code == 503 and answer.get_json()["code"] == "database_unavailable"


class _PgConn:
    """Enough of a psycopg connection: ``closed`` turns true when the pool closes it after a failed
    statement, ``broken`` only when the server went away."""
    def __init__(self, error, broken=False):
        self.error, self.broken, self.closed = error, broken, False

    def cursor(self):
        return self

    def execute(self, *args):
        raise self.error

    def close(self):
        self.closed = True


def _pg_error(name, text):
    kind = type(name, (Exception,), {"__module__": "psycopg"})
    return kind(text)


def test_a_mistake_in_a_statement_is_no_outage(db, tmp_path):
    """On Postgres a refused statement (a NUL byte, a duplicate key) used to count as the database
    being down: saving was off for everyone for the next seconds, again on every such statement."""
    store.write_json(str(tmp_path / "data.json"), {"a": 1})
    db.close()
    db._idle.append(_PgConn(_pg_error("DataError", "PostgreSQL text fields cannot contain NUL (0x00) bytes")))
    with pytest.raises(database.DatabaseError) as err:
        db.run("SELECT 1")
    assert not isinstance(err.value, database.DatabaseUnavailable)
    assert db.down is None and database.available() is True


def test_a_connection_the_server_dropped_is_still_reopened(db, tmp_path):
    path = str(tmp_path / "data.json")
    store.write_json(path, {"a": 1})
    db.close()
    db._idle.append(_PgConn(_pg_error("AdminShutdown", "terminating connection"), broken=True))
    assert store.read_json(path) == {"a": 1} and db.down is None
