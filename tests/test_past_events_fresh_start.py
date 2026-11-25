"""Closing an event starts the next with an empty replay and no seat notes (#1430)."""
from floorbit import recording, seat_notes
from floorbit.store import load_data


def test_closing_the_event_empties_the_replay_and_the_seat_notes(client):
    client.post("/api/seat-blocks", json={"name": "A", "x": 20, "y": 20, "cols": 2, "rows": 1})
    recording.capture({'t': 1_800_000_000, 'down': 1, 'up': 1, 'online': 1}, {'A-1': 10}, set(), load_data())
    assert client.put("/api/plan/seats/A-1/note", json={"text": "Cable taped down"}).status_code == 200
    assert recording.frames() and seat_notes.get("A-1")

    closed = client.post("/api/past-events/close", json={"confirm": "close"})
    assert closed.status_code == 200, closed.get_json()
    assert recording.frames() == []
    assert seat_notes.get("A-1") is None
    assert client.get("/api/replay/event").get_json()["frames"] == []
