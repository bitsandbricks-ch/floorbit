"""Reading an unchanged document again costs no query (issue #1289, docs/database.md)."""
import time

import pytest

from floorbit import database, store


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA_FILE", str(tmp_path / "data.json"))
    monkeypatch.setenv(database.ENV, f"sqlite:///{tmp_path / 'floorbit.db'}")
    b = database.backend()
    yield b
    b.close()


def _counting(db, monkeypatch):
    asked = []
    run = db.run

    def counted(sql, args=(), fetch=False):
        asked.append(sql.split()[1])
        return run(sql, args, fetch)
    monkeypatch.setattr(db, "run", counted)
    return asked


def test_an_unchanged_document_is_read_from_the_copy(db, tmp_path, monkeypatch):
    path = str(tmp_path / "data.json")
    store.write_json(path, {"halls": ["main"]})
    asked = _counting(db, monkeypatch)
    for _ in range(5):
        assert store.read_json(path) == {"halls": ["main"]}
    assert asked == []


def test_each_read_still_gets_its_own_copy(db, tmp_path):
    path = str(tmp_path / "data.json")
    store.write_json(path, {"halls": ["main"]})
    store.read_json(path)["halls"].append("changed in place")
    assert store.read_json(path) == {"halls": ["main"]}


def test_a_save_here_shows_at_once(db, tmp_path):
    path = str(tmp_path / "data.json")
    store.write_json(path, {"v": 1})
    assert store.read_json(path) == {"v": 1}
    store.write_json(path, {"v": 2})
    assert store.read_json(path) == {"v": 2}


def test_another_replicas_save_shows_within_the_recheck(db, tmp_path, monkeypatch):
    path = str(tmp_path / "data.json")
    store.write_json(path, {"v": 1})
    assert store.read_json(path) == {"v": 1}
    other = database.Sql(db.url, db.root)            # another pod on the same database
    other.put(database.key_for(path, db.root), '{"v": 2}')
    monkeypatch.setattr(database, "STAMP_RECHECK", 0.01)
    time.sleep(0.02)
    assert store.read_json(path) == {"v": 2}


def test_a_missing_document_is_not_asked_for_again_and_again(db, tmp_path, monkeypatch):
    path = str(tmp_path / "plugins.json")
    assert store.read_json(path, {}) == {}
    asked = _counting(db, monkeypatch)
    for _ in range(5):
        assert store.read_json(path, {}) == {}
    assert asked == []
    store.write_json(path, {"demo": {"enabled": True}})
    assert store.read_json(path, {}) == {"demo": {"enabled": True}}
