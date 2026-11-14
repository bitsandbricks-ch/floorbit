"""Event timeline replay (issue #21)."""
import time

import pytest

from integrations import history


@pytest.fixture
def hall(client, app_module, monkeypatch, tmp_path):
    monkeypatch.setenv("CHECKIN_HISTORY_FILE", str(tmp_path / "checkins-history.jsonl"))
    client.post("/api/seat-blocks", json={"name": "D", "x": 40, "y": 50, "cols": 4, "rows": 1})
    stats = app_module.app.extensions["floorbit_stats"]
    stats.reset()
    return stats


def _read(stats, up, now):
    dev = {"id": "s1", "name": "sw-d-01"}
    ports = [(dev, {"name": f"Gi1/0/{n}", "state": "up" if f"D-{n}" in up else "down",
                    "download_bps": 1e6, "upload_bps": 1e5}, f"D-{n}") for n in range(1, 5)]
    stats.record(ports, ["sw-d-01"], now=now)


def test_seat_changes_are_recorded_on_change_only(hall):
    t0 = 1_000_000
    _read(hall, {"D-1"}, t0)
    _read(hall, {"D-1"}, t0 + 120)
    _read(hall, {"D-1", "D-2"}, t0 + 240)
    _read(hall, {"D-2"}, t0 + 360)
    tl = hall.timeline()
    assert tl["seat_events"] == [[t0, "D-1", 1], [t0 + 240, "D-2", 1], [t0 + 360, "D-1", 0]]
    assert tl["seat_base"] == {"t": t0, "online": []}
    assert [s["online"] for s in tl["samples"]] == [1, 1, 2, 1]


def test_old_changes_fold_into_the_start(hall):
    t0 = 1_000_000
    _read(hall, {"D-1"}, t0)
    _read(hall, {"D-1", "D-3"}, t0 + 3600)
    _read(hall, {"D-1", "D-3"}, t0 + 25 * 3600)   # a day later: the first change is out of the window
    tl = hall.timeline()
    assert tl["seat_base"] == {"t": t0, "online": ["D-1"]}
    assert tl["seat_events"] == [[t0 + 3600, "D-3", 1]]


def test_replay_api(client, hall):
    now = time.time()
    _read(hall, {"D-1", "D-2"}, now - 600)
    _read(hall, {"D-2"}, now - 300)
    row = {"seat": "D-3", "username": "player-three", "ip": "198.51.100.3", "mac": "02:00:00:00:00:03"}
    history.record("checkin", row, ts=now - 500)
    history.record("moved", {"seat": "D-3", "username": "player-three"}, ts=now - 100, to_seat="D-4")
    client.post("/api/incidents", json={"seat": "D-2", "title": "Port flapping"})
    data = client.get("/api/replay").get_json()
    assert [c["seat"] for b in data["drawing"]["shapes"] for c in b["cells"]] == ["D-1", "D-2", "D-3", "D-4"]
    assert data["seat_events"] == [[now - 600, "D-1", 1], [now - 600, "D-2", 1], [now - 300, "D-1", 0]]
    assert data["checkins"] == [[now - 500, "D-3", 1], [now - 100, "D-3", 0]]
    assert data["incidents"][0]["seat"] == "D-2" and data["incidents"][0]["end"] is None
    assert data["start"] == now - 600 and data["end"] >= now - 100
    body = client.get("/api/replay").get_data(as_text=True)
    for secret in ("player-three", "198.51.100.3", "02:00:00:00:00:03"):
        assert secret not in body


def test_replay_needs_floor_plan_access(anon_client, app_module, monkeypatch):
    monkeypatch.setattr(app_module.app.extensions["auth"], "public_read", False)
    assert anon_client.get("/api/replay").status_code in (302, 401)


def test_demo_day_fills_up(app_module):
    from floorbit.blueprints.demo import demo_history, demo_seat_history
    samples = demo_history(now=2_000_000)
    events, start = demo_seat_history(samples)
    assert samples[0]["online"] == 0 and samples[-1]["online"] > 60 and start == samples[0]["t"]
    online = set()
    for _t, seat, on in events:
        (online.add if on else online.discard)(seat)
    assert len(online) == samples[-1]["online"]
