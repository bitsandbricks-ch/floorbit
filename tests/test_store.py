"""data.json is written in place (bind mount), so readers must never see half a file."""
import json
import threading
import time

import pytest

from floorbit import database, store


def test_readers_never_see_half_a_file(tmp_path):
    path = str(tmp_path / "data.json")
    big = {"seat_blocks": [{"id": str(i), "name": "A" * 50} for i in range(2000)]}
    store.write_json(path, big)
    stop, errors = threading.Event(), []

    def writer():
        while not stop.is_set():
            store.write_json(path, big)

    def reader():
        for _ in range(200):
            try:
                assert len(store.read_json(path)["seat_blocks"]) == 2000
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

    threads = [threading.Thread(target=writer)] + [threading.Thread(target=reader) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads[1:]:
        t.join()
    stop.set()
    threads[0].join()
    assert errors == []


def test_a_half_file_from_another_process_is_read_again(tmp_path):
    path = tmp_path / "data.json"
    path.write_text('{"seat_blocks": [')            # another worker is in the middle of a write
    threading.Timer(0.05, lambda: path.write_text(json.dumps({"seat_blocks": []}))).start()
    assert store.read_json(str(path)) == {"seat_blocks": []}


def test_missing_and_broken_files(tmp_path):
    assert store.read_json(str(tmp_path / "nope.json"), {"a": 1}) == {"a": 1}
    broken = tmp_path / "broken.json"
    broken.write_text("not json")
    started = time.time()
    with pytest.raises(json.JSONDecodeError):
        store.read_json(str(broken))
    assert time.time() - started < 1


def test_a_value_that_cannot_be_saved_leaves_the_file_alone(tmp_path):
    path = str(tmp_path / "data.json")
    store.write_json(path, {"ok": True})
    with pytest.raises(TypeError):
        store.write_json(path, {"bad": object()})
    assert store.read_json(path) == {"ok": True}


@pytest.fixture
def files(monkeypatch):
    """The copy beside the file is for the files backend; a database writes in one go anyway."""
    monkeypatch.delenv(database.ENV, raising=False)


@pytest.mark.usefixtures("files")
def test_a_write_cut_short_is_read_from_the_last_complete_copy(tmp_path, capsys):
    path = tmp_path / "data.json"
    store.write_json(str(path), {"seat_blocks": [{"id": "a"}]})
    # The disk filled up (or the pod died) halfway through the write in place.
    raw = path.read_text()
    path.write_text(raw[: len(raw) // 2])
    assert store.read_json(str(path)) == {"seat_blocks": [{"id": "a"}]}
    assert "last complete copy" in capsys.readouterr().out
    # The next save mends the file itself.
    store.write_json(str(path), {"seat_blocks": []})
    assert json.loads(path.read_text()) == {"seat_blocks": []}


@pytest.mark.usefixtures("files")
def test_when_the_copy_cannot_be_written_the_file_is_left_alone(tmp_path, monkeypatch):
    path = tmp_path / "data.json"
    store.write_json(str(path), {"ok": True})
    real_open = open

    def full_disk(name, mode="r", *a, **kw):
        if str(name).endswith(store.NEXT) and "w" in mode:
            raise OSError(28, "No space left on device")
        return real_open(name, mode, *a, **kw)

    monkeypatch.setattr("builtins.open", full_disk)
    with pytest.raises(OSError):
        store.write_json(str(path), {"ok": False})
    monkeypatch.undo()
    assert json.loads(path.read_text()) == {"ok": True}


@pytest.mark.usefixtures("files")
def test_a_broken_file_and_copy_still_say_so(tmp_path):
    path = tmp_path / "data.json"
    path.write_text("not json")
    (tmp_path / ("data.json" + store.NEXT)).write_text("not json either")
    with pytest.raises(json.JSONDecodeError):
        store.read_json(str(path))


@pytest.mark.usefixtures("files")
def test_deleting_a_document_takes_its_copy_too(tmp_path):
    path = tmp_path / "template.json"
    store.write_json(str(path), {"a": 1})
    assert (tmp_path / ("template.json" + store.NEXT)).exists()
    assert store.delete_json(str(path))
    assert list(tmp_path.iterdir()) == []
    assert store.list_json(str(tmp_path)) == []


@pytest.mark.usefixtures("files")
def test_the_app_keeps_answering_on_a_half_written_data_file(app_module, tmp_path):
    # Before, a cut-short data.json crashed every start: a restart loop with no way in.
    client = app_module.app.test_client()
    data = store.load_data()
    data["seat_blocks"] = [{"id": "kept"}]
    store.save_data(data)
    with open(store.DATA_FILE) as f:
        raw = f.read()
    with open(store.DATA_FILE, "w") as f:
        f.write(raw[: len(raw) // 3])
    assert store.load_data()["seat_blocks"] == [{"id": "kept"}]
    assert client.get("/api/version").status_code < 500


# ── Two savers at once (each loads the whole document and saves it whole) ──────────────────────

def test_a_save_keeps_what_another_saved_meanwhile(tmp_path):
    path = str(tmp_path / "data.json")
    store.write_json(path, {"incidents": [{"id": "i1", "status": "open"}], "game_servers": []})
    background = store.read_json(path)            # a monitor tick loads the document ...
    request = store.read_json(path)
    request["incidents"][0]["status"] = "fixed"   # ... a crew member marks the incident fixed ...
    store.write_json(path, request)
    background["game_servers"] = [{"id": "g1"}]   # ... and the tick saves its own part
    store.write_json(path, background)
    found = store.read_json(path)
    assert found["incidents"][0]["status"] == "fixed" and found["game_servers"] == [{"id": "g1"}]


def test_the_same_part_saved_twice_keeps_the_last(tmp_path):
    path = str(tmp_path / "data.json")
    store.write_json(path, {"notes": ["a"]})
    first, second = store.read_json(path), store.read_json(path)
    first["notes"] = ["first"]
    second["notes"] = ["second"]
    store.write_json(path, first)
    store.write_json(path, second)
    assert store.read_json(path)["notes"] == ["second"]


def test_a_removed_part_stays_removed_and_new_parts_stay(tmp_path):
    path = str(tmp_path / "data.json")
    store.write_json(path, {"old": 1, "kept": 2})
    remover, adder = store.read_json(path), store.read_json(path)
    del remover["old"]
    store.write_json(path, remover)
    adder["new"] = 3
    store.write_json(path, adder)
    assert store.read_json(path) == {"kept": 2, "new": 3}


def test_saving_the_same_copy_again_still_keeps_the_others(tmp_path):
    path = str(tmp_path / "data.json")
    store.write_json(path, {"a": 0, "b": 0})
    mine, theirs = store.read_json(path), store.read_json(path)
    theirs["b"] = 1
    store.write_json(path, theirs)
    mine["a"] = 1
    store.write_json(path, mine)
    mine["a"] = 2                                 # the same copy, saved again later
    store.write_json(path, mine)
    assert store.read_json(path) == {"a": 2, "b": 1}


def test_a_new_document_is_written_as_given(tmp_path):
    path = str(tmp_path / "data.json")
    store.write_json(path, {"a": 1})
    store.write_json(path, {"b": 2})              # not read from the store: replaces it whole, as before
    assert store.read_json(path) == {"b": 2}


def test_a_document_that_is_not_an_object_counts_as_empty(tmp_path, monkeypatch):
    # data.json edited by hand into a list: Floorbit started into a crash on every request.
    path = str(tmp_path / "data.json")
    store.write_json(path, [1, 2])
    assert store.read_json(path, {}) == {}
    assert store.read_json(path) == [1, 2]          # a caller that takes anything still gets it
    monkeypatch.setattr(store, "DATA_FILE", path)
    assert store.load_data()["seat_blocks"] == []


def test_the_app_starts_on_a_data_file_that_is_a_list(app_module):
    store.write_json(store.DATA_FILE, ["not", "an", "object"])
    app_module.app.extensions["floorbit_settings"].reload()
    client = app_module.app.test_client()
    assert client.get("/api/version").status_code < 500
    assert client.get("/api/seat-blocks").status_code < 500


def test_data_of_dropped_features_goes_with_the_next_write(client):
    from floorbit import store
    data = store.load_data()
    data["planner"] = {"settings": {"model": "example"}}
    store.save_data(data)
    assert "planner" not in store.load_data()
