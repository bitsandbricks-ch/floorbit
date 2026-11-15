"""Full-event recording for the replay (issue #104)."""
import json
import os
from itertools import pairwise

from floorbit import recording
from floorbit.store import load_data

DAY = 24 * 3600


def _sample(t, online=2):
    return {'t': t, 'down': 2_000_000, 'up': 500_000, 'online': online}


def _halls(client):
    client.post("/api/seat-blocks", json={"name": "a", "x": 20, "y": 20, "cols": 2, "rows": 1})
    hall2 = client.post("/api/halls", json={"name": "Hall 2"}).get_json()
    client.post("/api/seat-blocks", json={"name": "B", "x": 60, "y": 60, "cols": 2, "rows": 1, "hall_id": hall2["id"]})
    return hall2["id"]


def test_a_frame_has_numbers_per_block_and_no_people(client):
    _halls(client)
    data = load_data()
    f = recording.frame(_sample(1000.04), {'A-1': 3000, 'B-2': 1000}, {'A-1', None}, data)
    assert f == {'t': 1000.0, 'down': 2_000_000, 'up': 500_000, 'online': 2, 'seats': ['A-1', 'B-2'],
                 'incidents': ['A-1'], 'blocks': {'A': [2, 1, 3000, 1], 'B': [2, 1, 1000, 0]}}


def test_capture_keeps_one_frame_per_step_and_survives_a_restart(client):
    _halls(client)
    data = load_data()
    t0 = 1_800_000_000
    assert recording.capture(_sample(t0), {}, set(), data) is not None
    assert recording.capture(_sample(t0 + 120), {}, set(), data) is None   # too soon
    assert recording.capture(_sample(t0 + 300), {}, set(), data) is not None
    recording._state['last'] = None   # as after a restart: it reads the last frame's time back
    assert recording.capture(_sample(t0 + 360), {}, set(), data) is None
    assert [f['t'] for f in recording.frames()] == [t0, t0 + 300]


def test_old_frames_are_thinned_out():
    now = 100 * DAY
    frames = [{'t': now - age} for age in range(0, 10 * DAY, 300)][::-1]
    kept = recording.thin(frames, now)
    def gaps(lo, hi):
        ts = [f['t'] for f in kept if lo <= now - f['t'] < hi]
        return {round(b - a) for a, b in pairwise(ts)}
    assert gaps(0, DAY - 600) == {300}
    assert gaps(DAY + 1800, 7 * DAY - 1800) == {1800}
    assert gaps(7 * DAY + 3600, 10 * DAY) == {3600}
    assert len(recording.thin([{'t': t * 3600.0} for t in range(6000)], 6000 * 3600)) == recording.MAX_FRAMES


def test_compacting_rewrites_the_file(client, monkeypatch):
    _halls(client)
    data = load_data()
    t0 = 1_800_000_000
    for i in range(12 * 4):   # two days of a frame every quarter hour, written straight to the file
        with open(recording.path(), 'a', encoding='utf-8') as f:
            f.write(json.dumps(recording.frame(_sample(t0 + i * 900), {}, set(), data)) + '\n')
    with open(recording.path(), 'a', encoding='utf-8') as f:
        f.write('{"t": 18000')   # cut short by a crash
    recording._compact(t0 + 2 * DAY + 3 * DAY)
    ts = [f['t'] for f in recording.frames()]
    assert len(ts) == 24 and all(b - a == 1800 for a, b in pairwise(ts))


def test_the_whole_event_api_is_per_hall_and_new_event_clears_it(client):
    hall2 = _halls(client)
    data = load_data()
    recording.capture(_sample(1_800_000_000), {'A-1': 1000, 'B-1': 2000}, {'B-1'}, data)
    main = client.get("/api/replay/event").get_json()
    assert main['step'] == 300 and main['start'] == main['end'] == 1_800_000_000
    assert main['frames'][0]['seats'] == ['A-1'] and main['frames'][0]['incidents'] == []
    assert main['frames'][0]['blocks'] == {'A': [2, 1, 1000, 0]}
    other = client.get(f"/api/replay/event?hall={hall2}").get_json()
    assert other['frames'][0]['seats'] == ['B-1'] and other['frames'][0]['incidents'] == ['B-1']
    download = client.get("/api/replay/event.json")
    assert 'attachment' in download.headers['Content-Disposition']
    assert download.get_json()['frames'][0]['seats'] == ['A-1', 'B-1']
    assert client.post("/api/report/new-event").status_code == 200
    assert not os.path.exists(recording.path())
    assert client.get("/api/replay/event").get_json()['frames'] == []


def test_the_port_watch_writes_frames(client, app_module):
    from floorbit.attention import _record_frame
    _halls(client)
    _record_frame(_sample(1_800_000_000), {'A-2': 500}, load_data())
    assert recording.frames()[0]['seats'] == ['A-2']
