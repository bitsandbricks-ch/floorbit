"""data.json is written in place (bind mount), so readers must never see half a file."""
import json
import threading
import time

import pytest

from floorbit import store


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
