"""Compare views (issue #90): today against yesterday, this event against the last, cut to the same length."""
import time

import pytest

from floorbit import compare, event_archive

G = 1_000_000_000


@pytest.fixture
def midnight():
    lt = time.localtime(time.time())
    return int(time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1)))


def hour(t, avg, online, peak=None):
    return {"t": t, "avg_bps": avg, "peak_bps": peak or avg * 2, "online_max": online}


def test_today_is_compared_with_yesterday_until_the_same_time(midnight):
    yesterday = midnight - 86400
    hours = [hour(yesterday + k * 3600, 1 * G, 50) for k in range(24)]
    hours[20] = hour(yesterday + 20 * 3600, 5 * G, 90)            # yesterday evening: not yet today
    hours += [hour(midnight + k * 3600, 2 * G, 60) for k in range(10)]
    events = [[yesterday + 3600, "s1", "sw-a-01", "offline"], [yesterday + 22 * 3600, "s1", "sw-a-01", "offline"],
              [midnight + 600, "s2", "sw-b-01", "offline"]]
    items = [{"created_at": yesterday + 100}, {"created_at": midnight + 100}, {"created_at": midnight + 200}]
    now = midnight + 10 * 3600 - 60                                # 09:59
    out = compare.day({"hours": hours, "switch_events": events}, items, now=now)
    assert out["now"]["avg_bps"] == 2 * G and out["now"]["online_max"] == 60 and out["now"]["hours"] == 10
    assert out["then"]["avg_bps"] == 1 * G and out["then"]["online_max"] == 50   # 20:00 is later in the day
    assert out["then"]["peak_bps"] == 2 * G
    assert (out["now"]["incidents"], out["then"]["incidents"]) == (2, 1)
    assert (out["now"]["outages"], out["then"]["outages"]) == (1, 1)
    assert out["series"][20] == {"hour": 20, "now_avg_bps": None, "then_avg_bps": 5 * G, "now_online": None,
                                 "then_online": 90}
    assert out["has_then"] is True


def test_this_event_against_the_last_ones_first_hours(monkeypatch):
    t0, t1 = 1_700_000_000, 1_790_000_000
    last = {"id": "20231114-abcd1234", "name": "Example LAN 2025", "start": t0, "figures": {"incidents": 9},
            "report": {"start": t0, "hours": [hour(t0 + k * 3600, (k + 1) * G, 10 * k) for k in range(30)],
                       "incidents": {"items": [{"start": t0 + 100}, {"start": t0 + 5 * 3600},
                                               {"start": t0 + 20 * 3600}]}}}
    monkeypatch.setattr(event_archive, "archived", lambda: [{"id": last["id"]}])
    monkeypatch.setattr(event_archive, "get", lambda _id: last)
    current = {"start": t1, "hours": [hour(t1 + k * 3600, 3 * G, 70) for k in range(6)],
               "incidents": {"total": 4}, "outages": [{"times": 2}, {"times": 1}]}
    out = compare.event(current, now=t1 + 6 * 3600)
    assert out["name"] == "Example LAN 2025" and out["elapsed_s"] == 6 * 3600
    assert out["now"]["avg_bps"] == 3 * G and out["now"]["incidents"] == 4 and out["now"]["outages"] == 3
    # The last event's first 6 hours: 1..6 Gbps, so 3.5 on average, and two incidents by then.
    assert out["then"]["avg_bps"] == 3.5 * G and out["then"]["hours"] == 6 and out["then"]["incidents"] == 2
    assert out["then_total"] == {"incidents": 9}
    assert len(out["series"]) == 30 and out["series"][7] == {"hour": 7, "now_avg_bps": None, "then_avg_bps": 8 * G,
                                                              "now_online": None, "then_online": 70}


def test_no_archived_event_means_no_event_comparison(monkeypatch):
    monkeypatch.setattr(event_archive, "archived", lambda: [])
    assert compare.event({"start": 1, "hours": []}) is None


def test_api(client):
    body = client.get("/api/stats/compare").get_json()
    assert set(body["day"]) == {"now", "then", "series", "has_then"} and len(body["day"]["series"]) == 24
    assert body["event"] is None
