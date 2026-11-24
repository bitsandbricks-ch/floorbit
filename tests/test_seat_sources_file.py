"""The seat file lives next to data.json, never in the repository or in demo mode (#871)."""
import json
import os

from floorbit import store
from integrations import seat_sources


def test_the_seat_file_defaults_to_the_state_folder(monkeypatch):
    monkeypatch.delenv("SEAT_SOURCE_JSON_PATH", raising=False)
    path = seat_sources.JsonFileSource().path()
    assert path == os.path.join(store.state_folder(), "seats.json")


def test_demo_mode_never_reads_the_file(tmp_path, monkeypatch):
    f = tmp_path / "seats.json"
    f.write_text(json.dumps({"seats": {"A-1": {"username": "player-01", "ip_address": "192.0.2.11"}}}))
    monkeypatch.setenv("SEAT_SOURCE_JSON_PATH", str(f))
    assert seat_sources.JsonFileSource().fetch() == {"A-1": {"username": "player-01", "ip_address": "192.0.2.11"}}
    monkeypatch.setenv("FLOORBIT_DEMO", "1")
    assert seat_sources.JsonFileSource().fetch() == {}


def test_the_example_holds_only_documentation_addresses():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "seats.example.json")) as f:
        seats = json.load(f)["seats"]
    assert all(e["ip_address"].startswith("192.0.2.") for e in seats.values())
