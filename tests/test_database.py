"""Where documents live (issue #464): SQLite or Postgres, and the one-time import of the old files."""
import json
import os
import threading
import time

import pytest

from floorbit import database, store


@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA_FILE", str(tmp_path / "data.json"))
    monkeypatch.setenv(database.ENV, f"sqlite:///{tmp_path / 'floorbit.db'}")
    yield tmp_path
    database.backend().close()


def test_sqlite_in_the_state_folder_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv(database.ENV, raising=False)
    monkeypatch.setattr(store, "DATA_FILE", str(tmp_path / "data.json"))
    where = f"sqlite (sqlite:///{tmp_path / database.DEFAULT_FILE})"
    assert database.status() == {"kind": "sqlite", "where": where, "ok": True}
    store.write_json(str(tmp_path / "data.json"), {"a": 1})
    assert store.read_json(str(tmp_path / "data.json")) == {"a": 1}
    assert (tmp_path / database.DEFAULT_FILE).exists() and not (tmp_path / "data.json").exists()


def test_a_file_is_imported_once_and_then_left_alone(sqlite_db):
    path = sqlite_db / "data.json"
    path.write_text(json.dumps({"floor": "from the file"}))
    assert store.read_json(str(path), {}) == {"floor": "from the file"}
    store.write_json(str(path), {"floor": "from the database"})
    # The file is no longer read or written: the database has the document now.
    assert json.loads(path.read_text()) == {"floor": "from the file"}
    path.write_text(json.dumps({"floor": "changed by hand"}))
    assert store.read_json(str(path), {}) == {"floor": "from the database"}


def test_missing_documents_give_the_default(sqlite_db):
    assert store.read_json(str(sqlite_db / "nothing.json"), {"empty": True}) == {"empty": True}
    assert store.stamp(str(sqlite_db / "nothing.json")) is None


def test_stamp_changes_on_every_write(sqlite_db):
    path = str(sqlite_db / "data.json")
    store.write_json(path, {"n": 1})
    first = store.stamp(path)
    store.write_json(path, {"n": 2})
    assert store.stamp(path) != first


def test_keys_are_paths_under_the_state_folder(sqlite_db):
    assert database.key_for(str(sqlite_db / "templates" / "abc.json")) == "templates/abc.json"
    outside = os.path.abspath("/elsewhere/x.json")
    assert database.key_for(outside) == outside.replace(os.sep, "/")


def test_list_and_delete_cover_files_and_rows(sqlite_db):
    folder = sqlite_db / "templates"
    folder.mkdir()
    (folder / "old.json").write_text("{}")            # still only a file
    store.write_json(str(folder / "new.json"), {})     # only a row
    store.write_json(str(sqlite_db / "templates_like.json"), {})  # a similar name, not in the folder
    assert sorted(store.list_json(str(folder))) == ["new.json", "old.json"]
    assert store.delete_json(str(folder / "new.json"))
    assert store.delete_json(str(folder / "old.json"))
    assert store.list_json(str(folder)) == []


def test_like_wildcards_in_names_are_literal(sqlite_db):
    db = database.backend()
    db.put("a_b/x.json", "{}")
    db.put("axb/y.json", "{}")
    assert db.keys("a_b/") == ["a_b/x.json"]


def test_migrations_run_once(sqlite_db):
    db = database.backend()
    db.conn()
    assert database.migrate(db, db.conn()) == []
    rows = db.run("SELECT version FROM floorbit_schema", fetch=True)
    assert [r[0] for r in rows] == list(range(1, len(database.MIGRATIONS) + 1))


def test_two_threads_write_without_locking_errors(sqlite_db):
    path = str(sqlite_db / "busy.json")
    errors = []

    def write(n):
        try:
            for i in range(25):
                store.write_json(path, {"thread": n, "i": i})
        except database.DatabaseError as exc:  # "database is locked" is what this guards against
            errors.append(exc)

    threads = [threading.Thread(target=write, args=(n,)) for n in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    assert store.read_json(path, {})["i"] == 24


def test_bad_urls_are_refused_without_the_password():
    with pytest.raises(database.DatabaseError) as err:
        database.Sql("mysql://floorbit:hunter2@db.example.com/floorbit", "/tmp")
    assert "hunter2" not in str(err.value)
    assert database._redact("postgresql://floorbit:hunter2@db.example.com/floorbit") == \
        "postgresql://floorbit:***@db.example.com/floorbit"


def test_an_unreachable_database_is_reported_not_raised(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "DATA_FILE", str(tmp_path / "data.json"))
    # A folder where the database file should be: SQLite cannot open it.
    (tmp_path / "db").mkdir()
    monkeypatch.setenv(database.ENV, f"sqlite:///{tmp_path / 'db'}")
    status = database.status()
    assert status["kind"] == "sqlite" and status["ok"] is False and "error" in status


def test_start_waits_for_the_database_then_goes_on_without_it(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "DATA_FILE", str(tmp_path / "data.json"))
    (tmp_path / "db").mkdir()
    monkeypatch.setenv(database.ENV, f"sqlite:///{tmp_path / 'db'}")
    out = database.wait_until_ready(0)
    assert out["ok"] is False and "since" in out


def test_opening_while_another_connection_writes_waits_instead_of_failing(tmp_path):
    """Switching to WAL needs the file to itself, and SQLite says "locked" at once instead of
    waiting: a second worker opening during a write must try again, not fail (CI saw this)."""
    import sqlite3
    path = tmp_path / "fresh.db"
    writer = sqlite3.connect(path, isolation_level=None)
    writer.execute("CREATE TABLE t (x)")
    writer.execute("BEGIN IMMEDIATE")                 # mid-write, still in the default journal mode
    writer.execute("INSERT INTO t VALUES (1)")
    opened, failed = [], []

    def open_it():
        try:
            opened.append(database.Sql(f"sqlite:///{path}", str(tmp_path))._connect())
        except Exception as exc:  # noqa: BLE001
            failed.append(exc)

    t = threading.Thread(target=open_it)
    t.start()
    time.sleep(0.3)
    writer.execute("COMMIT")
    t.join(10)
    assert not failed and opened
    assert opened[0].execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    opened[0].close()
    writer.close()


def test_many_threads_share_a_few_connections(sqlite_db, monkeypatch):
    """One connection per thread used up a shared Postgres: the pool keeps the count fixed."""
    monkeypatch.setenv(database.POOL_ENV, "3")
    monkeypatch.setenv(database.ENV, f"sqlite:///{sqlite_db / 'pooled.db'}")
    db = database.backend()
    opened = []
    real_connect = db._connect

    def counting_connect():
        c = real_connect()
        opened.append(c)
        return c

    monkeypatch.setattr(db, "_connect", counting_connect)
    errors = []

    def work(n):
        try:
            for i in range(10):
                db.put(f"t{n}.json", json.dumps({"i": i}))
                db.get(f"t{n}.json")
        except database.DatabaseError as exc:
            errors.append(exc)

    threads = [threading.Thread(target=work, args=(n,)) for n in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert 1 <= len(opened) <= 3
    assert db.get("t7.json") == {"i": 9}


def test_a_connection_that_failed_is_not_handed_out_again(sqlite_db):
    # A pool of its own: a thread left over from an earlier test can borrow from the shared one
    # and put a second connection back while this test counts them.
    url = os.environ[database.ENV]
    db = database.Sql(url, database.state_root())
    db.run("SELECT 1")
    (used,) = db._idle
    with pytest.raises(database.DatabaseError):
        db.run("SELECT * FROM no_such_table")
    assert used not in db._idle            # it may be mid-transaction or broken: closed instead
    db.run("SELECT 1")                      # and the next caller just opens a fresh one
    assert len(db._idle) == 1 and db._idle[0] is not used
    db.close()


def test_a_save_that_meets_another_pods_write_merges_again(sqlite_db, monkeypatch):
    # Another pod saves between our read of the row and our write: the conditional write misses,
    # we merge with its version and both additions stay (two pods used to lose a third of them).
    path = str(sqlite_db / "data.json")
    store.write_json(path, {"teams": {}})
    mine = store.read_json(path)
    db = database.backend()
    key = database.key_for(path)
    real = db.get_versioned
    calls = []

    def other_pod_writes_first(k):
        found = real(k)
        if not calls:
            db.put(key, json.dumps({"teams": {"theirs": {"id": "theirs"}}}))
        calls.append(k)
        return found

    monkeypatch.setattr(db, "get_versioned", other_pod_writes_first)
    mine["teams"]["mine"] = {"id": "mine"}
    store.write_json(path, mine)
    assert len(calls) == 2
    assert set(store.read_json(path)["teams"]) == {"theirs", "mine"}


def test_a_save_that_never_gets_through_is_refused_not_lost(sqlite_db, monkeypatch):
    path = str(sqlite_db / "data.json")
    store.write_json(path, {"n": 0})
    mine = store.read_json(path)
    db = database.backend()
    monkeypatch.setattr(db, "put_if", lambda *a: False)
    mine["n"] = 1
    with pytest.raises(database.DatabaseError):
        store.write_json(path, mine)


def test_put_if_only_writes_the_version_it_read(sqlite_db):
    db = database.backend()
    assert db.put_if("doc", "1", None) is True
    assert db.put_if("doc", "2", None) is False          # already there
    text, version = db.get_versioned("doc")
    assert text == "1"
    assert db.put_if("doc", "2", version) is True
    assert db.put_if("doc", "3", version) is False       # someone (we) wrote since
    assert db.get_versioned("doc")[0] == "2"
