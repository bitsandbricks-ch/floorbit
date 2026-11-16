"""Append-only logs in files or in the database (issue #464)."""
import json

import pytest

from floorbit import audit, database, journal, store


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA_FILE", str(tmp_path / "data.json"))
    return tmp_path


@pytest.fixture(params=["files", "sqlite"])
def kind(request, state, monkeypatch):
    if request.param == "sqlite":
        monkeypatch.setenv("FLOORBIT_DATABASE_URL", f"sqlite:///{state / 'floorbit.db'}")
    else:
        monkeypatch.delenv("FLOORBIT_DATABASE_URL", raising=False)
    return request.param


def test_append_read_trim_and_remove(kind, state):
    path = str(state / "log.jsonl")
    assert journal.lines(path) == [] and journal.size(path) == 0
    for i in range(10):
        journal.append(path, json.dumps({"i": i}))
    assert [json.loads(x)["i"] for x in journal.lines(path)] == list(range(10))
    assert journal.size(path) >= 10 * len('{"i": 0}')
    journal.keep_newest_half_over(path, 10_000)              # small enough: kept whole
    assert len(journal.lines(path)) == 10
    journal.keep_newest_half_over(path, 20)
    assert [json.loads(x)["i"] for x in journal.lines(path)] == [5, 6, 7, 8, 9]
    journal.replace(path, ["a", "b"])
    assert journal.lines(path) == ["a", "b"]
    journal.remove(path)
    assert journal.lines(path) == []
    journal.remove(path)                                      # removing nothing is fine


def test_a_database_imports_the_old_file_once(state, monkeypatch):
    path = state / "audit.jsonl"
    path.write_text('{"n": 1}\n{"n": 2}\n\n', encoding="utf-8")
    monkeypatch.setenv("FLOORBIT_DATABASE_URL", f"sqlite:///{state / 'floorbit.db'}")
    assert journal.lines(str(path)) == ['{"n": 1}', '{"n": 2}']
    journal.append(str(path), '{"n": 3}')
    path.write_text('{"n": 99}\n', encoding="utf-8")         # the file is a backup now, not read again
    db = database.backend()
    db.__dict__.pop("journal_checked")                        # as a restarted process would
    assert journal.lines(str(path)) == ['{"n": 1}', '{"n": 2}', '{"n": 3}']
    assert db.get("journal-imported/audit.jsonl") == {"imported": True}
    assert db.log_lines("audit.jsonl") == journal.lines(str(path))


def test_the_audit_log_lives_in_the_database_when_there_is_one(state, monkeypatch):
    monkeypatch.setenv("FLOORBIT_DATABASE_URL", f"sqlite:///{state / 'floorbit.db'}")
    monkeypatch.setenv("AUDIT_FILE", str(state / "audit.jsonl"))
    audit.record("settings", "change", "admin", "theme")
    assert not (state / "audit.jsonl").exists()
    [entry], total = audit.read()
    assert (entry["area"], entry["target"]) == ("settings", "theme")
