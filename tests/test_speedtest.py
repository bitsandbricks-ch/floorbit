"""Speedtest at the seat (issue #99): from the signed help link, numbers only, on the seat's report."""
import pytest

from floorbit import incidents, speedtest
from floorbit.blueprints import incidents as incidents_bp
from tests.test_incidents import api_url, sign_in_as

RESULT = {"down_mbps": 912.44, "up_mbps": 455, "ping_ms": 1.234, "jitter_ms": 0.2}


@pytest.fixture
def floor(client):
    """Block A with seats A-1..A-4."""
    client.post("/api/seat-blocks", json={"name": "A", "x": 10, "y": 10, "cols": 2, "rows": 2})


@pytest.fixture(autouse=True)
def fresh():
    speedtest.reset()
    incidents_bp._reports.clear()
    yield
    speedtest.reset()


def speed_url(app_module, seat, what, extra=""):
    with app_module.app.test_request_context():
        return f"/help/{seat}/speed/{what}?k={incidents.signature(seat)}{extra}"


def test_streams_need_the_signed_link(anon_client, app_module, floor):
    assert anon_client.get("/help/A-1/speed/ping").status_code == 404
    assert anon_client.get("/help/A-1/speed/ping?k=0000").status_code == 404
    assert anon_client.get(speed_url(app_module, "Z-9", "ping")).status_code == 404
    ping = anon_client.get(speed_url(app_module, "A-1", "ping"))
    assert ping.status_code == 200 and "no-store" in ping.headers["Cache-Control"]


def limit(monkeypatch, **changes):
    monkeypatch.setattr(speedtest, "limits", lambda: {**speedtest.DEFAULTS, **changes})


def test_download_and_upload(anon_client, app_module, floor):
    down = anon_client.get(speed_url(app_module, "A-1", "down", "&bytes=300000"))
    assert down.status_code == 200 and len(down.data) == 300000
    assert down.headers["Content-Length"] == "300000"
    capped = anon_client.get(speed_url(app_module, "A-2", "down", "&bytes=99999999999"), buffered=False)
    # At most half of what a test may move (250 MB by default) and no more than one request's top.
    assert int(capped.headers["Content-Length"]) == min(speedtest.MAX_DOWN, 125 * speedtest.MB)
    capped.close()
    assert anon_client.get(speed_url(app_module, "A-1", "down", "&bytes=lots")).status_code == 400
    up = anon_client.post(speed_url(app_module, "A-1", "up"), data=b"x" * 200000,
                          content_type="application/octet-stream")
    assert up.get_json() == {"bytes": 200000}
    assert speedtest._running[0] == 0   # every stream gave its slot back


def test_busy_and_budget(anon_client, app_module, floor, monkeypatch):
    limit(monkeypatch, max_running=0)
    r = anon_client.get(speed_url(app_module, "A-1", "down", "&bytes=1000"))
    assert r.status_code == 503 and "Other seats" in r.get_json()["error"]
    # One client IP may move a few tests' worth in ten minutes, over all seats.
    limit(monkeypatch, test_mb=20, seat_minutes=0)
    big = 10 * speedtest.MB
    for _ in range(8):
        assert anon_client.get(speed_url(app_module, "A-1", "down", f"&bytes={big}")).status_code == 200
    r = anon_client.get(speed_url(app_module, "A-1", "down", f"&bytes={big}"))
    assert r.status_code == 429 and "from here" in r.get_json()["error"]


def test_one_test_per_seat_in_a_while(anon_client, app_module, floor, monkeypatch):
    limit(monkeypatch, test_mb=20, seat_minutes=10)
    big = 10 * speedtest.MB
    assert anon_client.get(speed_url(app_module, "A-1", "down", f"&bytes={big}")).status_code == 200
    assert anon_client.get(speed_url(app_module, "A-1", "down", f"&bytes={big}")).status_code == 200
    again = anon_client.get(speed_url(app_module, "A-1", "down", f"&bytes={big}"))
    assert again.status_code == 429 and again.get_json()["error"] == \
        "This seat was tested a moment ago. Try again in 10 minutes."
    assert anon_client.get(speed_url(app_module, "A-2", "down", f"&bytes={big}")).status_code == 200
    # 0 minutes: no limit per seat.
    limit(monkeypatch, test_mb=20, seat_minutes=0)
    assert anon_client.get(speed_url(app_module, "A-1", "down", f"&bytes={big}")).status_code == 200


def test_speed_tests_can_be_switched_off(anon_client, client, app_module, floor):
    assert anon_client.get(api_url(app_module, "A-1")).get_json()["speedtest"] == {"test_mb": 250}
    client.put("/api/settings", json={"speedtest.enabled": False})
    assert anon_client.get(speed_url(app_module, "A-1", "ping")).status_code == 404
    assert anon_client.get(speed_url(app_module, "A-1", "down", "&bytes=1000")).status_code == 404
    assert anon_client.get(api_url(app_module, "A-1")).get_json()["speedtest"] is None


def test_the_limits_are_settings(client, app_module, floor):
    client.put("/api/settings", json={"speedtest.max_running": 2, "speedtest.test_mb": 100,
                                      "speedtest.seat_minutes": 0, "speedtest.max_mbps": 300})
    with app_module.app.app_context():
        assert speedtest.limits() == {"on": True, "max_running": 2, "test_mb": 100, "seat_minutes": 0, "max_mbps": 300}


def test_a_stream_is_held_to_the_speed_cap(monkeypatch):
    slept = []
    monkeypatch.setattr(speedtest.time, "sleep", slept.append)
    stream = speedtest.download(4 * speedtest.MB, mbps=8)   # 1 MB/s
    with speedtest._lock:
        speedtest._running[0] += 1
    assert sum(len(piece) for piece in stream) == 4 * speedtest.MB
    assert 3.5 < max(slept) < 4.5 and speedtest._running[0] == 0   # mocked sleep: the last wait is the total
    slept.clear()
    assert sum(len(piece) for piece in speedtest.download(speedtest.MB)) == speedtest.MB and not slept


def test_result_goes_with_the_report(anon_client, client, app_module, floor):
    saved = anon_client.post(speed_url(app_module, "A-1", "result"), json=RESULT).get_json()
    assert (saved["down_mbps"], saved["up_mbps"], saved["ping_ms"]) == (912.4, 455.0, 1.2)
    assert set(saved) == {"down_mbps", "up_mbps", "ping_ms", "jitter_ms", "at"}   # nothing personal
    anon_client.post(api_url(app_module, "A-1"), json={"problem": "slow"})
    [incident] = client.get("/api/incidents").get_json()["incidents"]
    assert incident["speedtest"]["down_mbps"] == 912.4
    # A test after the report lands on the open incident too.
    anon_client.post(speed_url(app_module, "A-1", "result"), json={**RESULT, "down_mbps": 3})
    [incident] = client.get("/api/incidents").get_json()["incidents"]
    assert incident["speedtest"]["down_mbps"] == 3.0
    seats = client.get("/api/speedtests?seat=a-1").get_json()["seats"]
    assert [r["down_mbps"] for r in seats["A-1"]] == [3.0, 912.4]


def test_result_is_checked_and_limited(anon_client, app_module, floor):
    url = speed_url(app_module, "A-2", "result")
    assert anon_client.post(url, json={"down_mbps": -1}).status_code == 400
    assert anon_client.post(url, json={"down_mbps": "fast"}).status_code == 400
    assert anon_client.post(url, json={}).status_code == 400
    for _ in range(7):   # 10 tries per IP in all, the refused ones too
        assert anon_client.post(url, json=RESULT).status_code == 200
    assert anon_client.post(url, json=RESULT).status_code == 429
    assert len(speedtest.results("A-2")) == speedtest.KEEP


def test_budget_is_per_client_behind_a_trusted_proxy(anon_client, app_module, floor, monkeypatch):
    monkeypatch.setenv("CHECKIN_TRUST_PROXY", "true")
    limit(monkeypatch, test_mb=20, seat_minutes=0)
    url = speed_url(app_module, "A-1", "down", f"&bytes={10 * speedtest.MB}")
    first, other = {"X-Forwarded-For": "192.0.2.30"}, {"X-Forwarded-For": "192.0.2.31"}
    for _ in range(8):
        assert anon_client.get(url, headers=first).status_code == 200
    assert anon_client.get(url, headers=first).status_code == 429
    assert anon_client.get(url, headers=other).status_code == 200


def test_results_are_for_the_crew(app_module, floor):
    viewer = sign_in_as(app_module, "vi1", "viewer")
    assert viewer.get("/api/speedtests").status_code == 403
    assert viewer.get("/api/speedtests/summary").status_code == 403
    assert viewer.get("/speedtests").status_code in (302, 403)
    tech = sign_in_as(app_module, "te1", "tech")
    assert tech.get("/api/speedtests/summary").status_code == 200


def _result(down, at, up=None, ping=1.0):
    return {"down_mbps": down, "up_mbps": up if up is not None else down, "ping_ms": ping, "jitter_ms": 0.2, "at": at}


def test_summary_per_switch():
    now = 1_800_000_000
    data = {speedtest.KEY: {
        "A-1": [_result(940, now - 60), _result(10, now - 7200)],   # only the latest counts
        "A-2": [_result(920, now - 120)],
        "B-1": [_result(90, now - 60, ping=6)],
        "B-2": [_result(110, now - 300)],
        "C-1": [_result(5, now - 13 * 3600)],                        # too old
        "D-1": [_result(900, now - 60)],                              # no known switch
    }}
    sw = {"A": [{"id": "s1", "name": "sw-a-01"}], "B": [{"id": "s2", "name": "sw-b-01"}]}
    out = speedtest.summary(lambda seat: sw.get(seat[0], []), data, now)
    assert out["hall"] == {"tests": 5, "down_mbps": 900.0, "up_mbps": 900.0, "ping_ms": 1.0}
    first, second = out["switches"]
    assert (first["name"], first["slow"], first["tests"], first["down_mbps"]) == ("sw-b-01", True, 2, 100.0)
    assert [s["seat"] for s in first["seats"]] == ["B-1", "B-2"] and first["ping_ms"] == 3.5
    assert (second["name"], second["slow"], second["down_mbps"]) == ("sw-a-01", False, 930.0)
    assert [r["seat"] for r in out["unknown"]] == ["D-1"]
    assert set(first["seats"][0]) == {"seat", "down_mbps", "up_mbps", "ping_ms", "at"}


def test_one_slow_seat_does_not_mark_its_switch():
    now = 1_800_000_000
    data = {speedtest.KEY: {"A-1": [_result(900, now)], "A-2": [_result(910, now)], "B-1": [_result(20, now)]}}
    out = speedtest.summary(lambda seat: [{"id": seat[0], "name": f"sw-{seat[0].lower()}"}], data, now)
    assert not any(s["slow"] for s in out["switches"])


def test_summary_endpoint(client, floor):
    body = client.get("/api/speedtests/summary").get_json()
    assert body["hours"] == 12 and body["hall"]["tests"] == 0 and body["switches"] == []
    assert client.get("/speedtests").status_code in (200, 503)   # 503: no frontend build (CI)


def test_streams_that_never_start_free_their_slot(anon_client, app_module, floor):
    """A HEAD, or a download closed before its first chunk, must not hold a stream slot for good:
    six of them used to lock the speed test for every seat until a restart."""
    for _ in range(speedtest.DEFAULTS["max_running"] + 2):
        head = anon_client.head(speed_url(app_module, "A-1", "down", "&bytes=1000"))
        assert head.status_code == 200
        assert head.headers["Content-Length"] == "1000"
    assert speedtest._running[0] == 0
    for _ in range(speedtest.DEFAULTS["max_running"] + 2):
        unread = anon_client.get(speed_url(app_module, "A-1", "down", "&bytes=1000"), buffered=False)
        assert unread.status_code == 200
        unread.close()
    assert speedtest._running[0] == 0
    stream = speedtest.download(10)
    stream.close()
    stream.close()
    assert speedtest._running[0] == 0
