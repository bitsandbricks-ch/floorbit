"""Docker Compose install (issue #12): the pieces the image and compose file rely on."""
import importlib
import subprocess
import sys

from integrations import seat_sources


def test_healthz_answers_without_signing_in(app_module):
    anon = app_module.app.test_client()
    resp = anon.get("/healthz")
    assert resp.status_code == 200 and resp.get_json() == {"ok": True}
    assert anon.get("/api/settings").status_code in (302, 401, 403)


def test_data_file_comes_from_the_environment(tmp_path):
    # A fresh interpreter, so the module-level default is read again.
    target = tmp_path / "state" / "data.json"
    out = subprocess.run([sys.executable, "-c", "from floorbit import store; print(store.DATA_FILE)"],
                         env={"FLOORBIT_DATA_FILE": str(target), "PATH": ""}, capture_output=True,
                         text=True, check=True, cwd=importlib.import_module("floorbit").__path__[0] + "/..")
    assert out.stdout.strip() == str(target)


def test_a_missing_seats_file_is_no_error(tmp_path, monkeypatch):
    monkeypatch.setenv("SEAT_SOURCE_JSON_PATH", str(tmp_path / "seats.json"))
    monkeypatch.setenv("SEAT_SOURCES", "json")
    seat_sources.invalidate()
    assert seat_sources.load(max_age=0) == {}
    assert seat_sources.info()["errors"] == {}


def test_files_the_app_cannot_write_are_named(tmp_path, monkeypatch):
    from floorbit import store
    (tmp_path / "data.json").write_text("{}")
    (tmp_path / "audit.jsonl").write_text("")
    assert store.unwritable(str(tmp_path / "data.json")) == []
    # Tests may run as root, where every file is writable, so stand in for a root-owned copy.
    real = store.os.access
    monkeypatch.setattr(store.os, "access", lambda p, mode: not p.endswith("data.json") and real(p, mode))
    assert store.unwritable(str(tmp_path / "data.json")) == [str(tmp_path / "data.json")]
    assert store.unwritable(str(tmp_path / "missing" / "data.json")) == []
