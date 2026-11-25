"""Saves that meet another process's save wait a random, growing while before merging again."""
import pytest

from floorbit import database, store


@pytest.fixture
def doc(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA_FILE", str(tmp_path / "data.json"))
    monkeypatch.setenv(database.ENV, f"sqlite:///{tmp_path / 'floorbit.db'}")
    path = str(tmp_path / "data.json")
    store.write_json(path, {"n": 0})
    yield path
    database.backend().close()


def test_a_save_that_met_another_waits_before_trying_again(doc, monkeypatch):
    db = database.backend()
    real, tries, waits = db.put_if, [], []
    monkeypatch.setattr(store.time, "sleep", waits.append)
    monkeypatch.setattr(db, "put_if", lambda *a: tries.append(1) or (len(tries) > 3 and real(*a)))
    mine = store.read_json(doc)
    mine["n"] = 1
    store.write_json(doc, mine)
    assert store.read_json(doc)["n"] == 1
    assert len(waits) == 3
    assert all(0 <= w <= 0.2 for w in waits)


def test_the_waits_stay_short_when_it_never_gets_through(doc, monkeypatch):
    db = database.backend()
    waits = []
    monkeypatch.setattr(store.time, "sleep", waits.append)
    monkeypatch.setattr(store.random, "uniform", lambda lo, hi: hi)   # the longest wait each time
    monkeypatch.setattr(db, "put_if", lambda *a: False)
    mine = store.read_json(doc)
    mine["n"] = 1
    with pytest.raises(database.DatabaseError):
        store.write_json(doc, mine)
    assert len(waits) == store.WRITE_TRIES
    assert sum(waits) < 2
