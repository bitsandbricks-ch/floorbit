"""Every seat lookup uses the editor's naming rules (floorbit/seat_names.py). A block named by rows
(A-1, A-2, ..., B-1) used to be unknown to the incident board, so "Flag for a tech" refused every
seat. Made-up nicks, RFC 5737 addresses."""
import pytest

from floorbit import incidents
from floorbit.store import load_data
from integrations import checkin, events


@pytest.fixture
def rows_block(client, tmp_path, monkeypatch):
    monkeypatch.setenv("CHECKIN_ENABLED", "true")
    monkeypatch.setenv("CHECKIN_FILE", str(tmp_path / "checkins.json"))
    monkeypatch.setattr(events, "publish", lambda kind, data=None, origin=None: None)
    r = client.post("/api/seat-blocks", json={"name": "", "x": 10, "y": 10, "cols": 4, "rows": 2, "naming": "rows"})
    assert r.status_code in (200, 201), r.get_json()
    return client


def test_rows_named_seats_are_seats(rows_block):
    assert {"A-1", "A-4", "B-1", "B-4"} <= incidents.seat_numbers()
    assert "A-8" not in incidents.seat_numbers()       # "block" numbering would have made A-1..A-8


def test_flag_for_a_tech_takes_a_rows_named_seat(rows_block):
    r = rows_block.post("/api/incidents", json={"seat": "B-2", "title": "Tech visit", "note": ""})
    assert r.status_code in (200, 201), r.get_json()
    assert rows_block.post("/api/incidents", json={"seat": "C-1", "title": "Tech visit"}).status_code == 400


def test_seat_panel_and_check_in_know_the_same_seats(rows_block):
    assert rows_block.get("/api/plan/seats/B-3").status_code == 200
    r = rows_block.post("/api/checkin", json={"seat": "B-3", "username": "pixel"},
                        environ_base={"REMOTE_ADDR": "192.0.2.40"})
    assert r.status_code == 200, r.get_json()
    assert "B-3" in checkin.known_seats(load_data)
