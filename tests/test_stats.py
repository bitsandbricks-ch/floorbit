"""The stats dashboard (issue #24): bandwidth, peaks, uplinks, online seats and top talkers."""
import json

import pytest
from test_attention import Monitoring, port

from floorbit import cache, sources, stats
from integrations import seat_sources

M = 1_000_000


def seat_port(name, seat, down, up=0, state="up"):
    return {**port(name, state=state, description=f"Seat {seat}"), "download_bps": down * M, "upload_bps": up * M}


@pytest.fixture
def hall(client, app_module, monkeypatch):
    mon = Monitoring()
    monkeypatch.setattr(sources, "monitoring", lambda: mon)
    monkeypatch.setenv("SEAT_SOURCES", "manual")
    seat_sources.invalidate()
    client.post("/api/seat-blocks", json={"name": "A", "x": 10, "y": 10, "cols": 4, "rows": 1})
    sw = client.post("/api/switches", json={"name": "sw-a-01", "x": 10, "y": 5}).get_json()
    client.post("/api/switches", json={"name": "dist-01", "x": 50, "y": 5})
    app = app_module.app
    app.extensions["floorbit_attention"].reset()
    app.extensions["floorbit_stats"].reset()
    return {"mon": mon, "switch": sw, "app": app}


def poll(hall, now):
    with hall["app"].app_context():
        hall["app"].extensions["floorbit_attention"].poll_once(now=now)


def read(client, screen=False):
    return client.get("/api/stats" + ("?screen=1" if screen else "")).get_json()


def busy(mon, a1=300, a2=50):
    mon.set("sw-a-01",
            seat_port("Gi1/0/1", "A-1", a1, 20), seat_port("Gi1/0/2", "A-2", a2, 5),
            seat_port("Gi1/0/3", "A-3", 0, state="down"),
            {**port("Te1/1/1", description="Uplink to dist-01"), "download_bps": 25 * M, "upload_bps": 375 * M,
             "speed_bps": 10_000 * M, "utilization": 0.0375})


def test_one_read_gives_bandwidth_seats_ports_uplinks_and_talkers(client, hall):
    busy(hall["mon"])
    poll(hall, 1000)
    body = read(client)
    now = body["now"]
    assert (now["down"], now["up"]) == (350 * M, 25 * M)   # the uplink isn't counted twice
    assert now["online"] == 2 and (now["ports_up"], now["ports_down"]) == (3, 1)
    [uplink] = body["uplinks"]
    assert uplink["switch"] == "sw-a-01" and uplink["port"] == "Te1/1/1" and uplink["utilization"] == 0.0375
    assert [t["seat"] for t in body["top"]] == ["A-1", "A-2"] and body["top"][0]["bps"] == 320 * M
    assert body["peak"] == {"bps": 375 * M, "at": 1000}


def test_a_port_naming_another_switch_is_an_uplink(client, hall):
    hall["mon"].set("sw-a-01", {**port("Gi1/0/48", description="to dist-01"), "download_bps": M, "upload_bps": M})
    poll(hall, 1000)
    assert [u["port"] for u in read(client)["uplinks"]] == ["Gi1/0/48"]


def test_hour_day_and_event_peak(client, hall):
    mon = hall["mon"]
    busy(mon, a1=900)
    poll(hall, 1000)                    # busiest, but more than an hour before the last read
    busy(mon, a1=100)
    poll(hall, 1000 + 2 * 3600)
    busy(mon, a1=200)
    poll(hall, 1000 + 2 * 3600 + 120)
    body = client.get("/api/stats").get_json()
    snap = hall["app"].extensions["floorbit_stats"].snapshot(now=1000 + 2 * 3600 + 120)
    assert snap["hour"]["peak_bps"] == 275 * M and snap["hour"]["samples"] == 2
    assert snap["day"]["peak_bps"] == 975 * M and snap["day"]["samples"] == 3
    assert body["peak"]["bps"] == 975 * M
    assert [s["t"] for s in body["series"]] == [1000, 1000 + 7200, 1000 + 7320]


def test_samples_older_than_a_day_drop_out(hall):
    busy(hall["mon"])
    poll(hall, 1000)
    poll(hall, 1000 + 24 * 3600 + 1)
    assert len(hall["app"].extensions["floorbit_stats"].samples) == 1


def test_nicks_only_for_seats_view_and_never_on_a_screen(client, anon_client, hall):
    client.put("/api/seat-map/A-1", json={"ip": "198.51.100.7", "nick": "player-one"})
    seat_sources.invalidate()
    busy(hall["mon"])
    poll(hall, 1000)
    assert read(client)["top"][0]["nick"] == "player-one"
    assert "nick" not in read(client, screen=True)["top"][0]
    assert "nick" not in read(anon_client)["top"][0]   # public read, no seats.view
    assert "player-one" not in json.dumps(hall["app"].extensions["floorbit_stats"].snapshot())


def test_reset_the_peak(client, anon_client, hall):
    mon = hall["mon"]
    busy(mon, a1=900)
    poll(hall, 1000)
    busy(mon, a1=100)
    poll(hall, 1120)
    assert anon_client.post("/api/stats/peak/reset").status_code in (401, 403)
    body = client.post("/api/stats/peak/reset").get_json()
    assert body["peak"] == {"bps": 175 * M, "at": 1120}


def test_kept_in_redis_across_a_restart(hall, monkeypatch):
    from conftest import FakeRedis
    fake = FakeRedis()
    monkeypatch.setattr(cache, "redis_client", fake)
    busy(hall["mon"])
    poll(hall, 1000)
    again = stats.Stats()
    assert [s["t"] for s in again.snapshot(now=1100)["series"]] == [1000]
    assert again.snapshot(now=1100)["peak"]["bps"] == 375 * M


def test_nothing_yet(client, hall):
    body = read(client)
    assert body["now"] is None and body["series"] == [] and body["monitoring"] is True


def test_demo_history_backfills_only_an_empty_day():
    from floorbit.blueprints.demo import demo_history
    s = stats.Stats()
    day = demo_history(now=100_000)
    s.backfill(day)
    assert len(s.samples) == 720 and s.peak["bps"] == max(d["down"] + d["up"] for d in day)
    s.backfill(demo_history(now=200_000))
    assert len(s.samples) == 720


def test_the_screen_version_gets_the_kiosk_look(client):
    from test_theme import html_tag
    assert 'data-preset="kiosk"' in html_tag(client.get("/stats?screen=1"))
    assert 'data-preset="floorbit"' in html_tag(client.get("/stats"))
