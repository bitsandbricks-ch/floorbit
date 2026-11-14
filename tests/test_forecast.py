"""Bandwidth forecast (issue #89): profile per hour of the day, times how the last hours ran."""
import time

import pytest

from floorbit import forecast
from integrations import events

G = 1_000_000_000
CONF = {"capacity_bps": 10 * G, "warn_pct": 80, "lead_hours": 3}


def day_shape(hour):
    """A LAN day: 2 Gbps at night, 7 Gbps in the evening (19:00 to 23:00)."""
    return 7 * G if 19 <= hour <= 23 else 2 * G


@pytest.fixture
def start():
    # 2 days ago at local midnight, so hours of the day line up with the shape.
    t = time.time() - 2 * 86400
    lt = time.localtime(t)
    return int(time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1)))


def rows(start, hours, scale=1.0, last_scale=None):
    out = []
    for k in range(hours):
        t = start + k * 3600
        s = last_scale if last_scale and k >= hours - 3 else scale
        out.append({"t": t, "peak_bps": round(day_shape(time.localtime(t).tm_hour) * s)})
    return out


def test_needs_some_history_first(start):
    out = forecast.forecast(rows(start, 4), now=start + 4 * 3600 + 60, conf=CONF)
    assert out["ready"] is False and out["history_hours"] == 4 and out["points"] == []


def test_profile_from_earlier_days(start):
    now = start + (24 + 16) * 3600 + 60     # day two, 16:01
    out = forecast.forecast(rows(start, 24 + 16), now=now, conf=CONF)
    assert out["ready"] and out["level"] == 1.0 and out["days"] == 2
    by_hour = {time.localtime(p["t"]).tm_hour: p for p in out["points"]}
    assert by_hour[20]["bps"] == 7 * G and by_hour[20]["basis"] == "profile"
    assert by_hour[3]["bps"] == 2 * G
    assert out["peak"]["bps"] == 7 * G
    # At 16:01 the lead hours are 17, 18 and 19: 7 of 10 Gbps is 70 %, under the 80 % warning.
    assert out["alert"] is None and by_hour[19]["pct"] == 70


def test_a_busier_day_scales_the_forecast_and_warns(start):
    now = start + (24 + 17) * 3600 + 60     # day two, 17:01, the last 3 hours ran 30 % busier
    out = forecast.forecast(rows(start, 24 + 17, last_scale=1.3), now=now, conf=CONF)
    assert out["level"] == 1.3
    by_hour = {time.localtime(p["t"]).tm_hour: p for p in out["points"]}
    assert by_hour[19]["bps"] == round(7 * G * 1.3) and by_hour[19]["pct"] == 91
    assert out["alert"]["pct"] == 91 and time.localtime(out["alert"]["t"]).tm_hour == 19


def test_hours_not_seen_yet_use_the_recent_level(start):
    now = start + 10 * 3600 + 60            # day one, 10:01: nothing seen after 10:00 yet
    out = forecast.forecast(rows(start, 10), now=now, conf=CONF)
    assert all(p["basis"] == "recent" and p["bps"] == 2 * G for p in out["points"] if p["t"] < start + 24 * 3600)
    assert out["level"] is None


def test_the_watch_publishes_once_per_peak(app_module, start, monkeypatch):
    watch = app_module.app.extensions["floorbit_forecast"]
    watch.stop()
    monkeypatch.setenv("FORECAST_CAPACITY_MBPS", "10000")
    got = []
    monkeypatch.setattr(events, "publish", lambda kind, data: got.append((kind, data)))
    data = rows(start, 24 + 17, last_scale=1.3)
    monkeypatch.setattr(watch, "stats", type("S", (), {"event": lambda self: {"hours": data}})())
    now = start + (24 + 17) * 3600 + 60
    watch.check(now)
    watch.check(now + 60)
    assert [k for k, _d in got] == ["forecast.alert"]
    assert got[0][1]["pct"] == 91 and got[0][1]["capacity_bps"] == 10 * G


def test_api_and_problems(client, app_module, start, monkeypatch):
    watch = app_module.app.extensions["floorbit_forecast"]
    watch.stop()
    assert client.get("/api/forecast").get_json()["ready"] in (True, False)
    watch.last = {"alert": {"t": int(time.time() // 3600 * 3600) + 7200, "bps": 9 * G, "pct": 90}}
    problems = client.get("/api/problems").get_json()["problems"]
    item = next(p for p in problems if p["kind"] == "forecast")
    assert item["level"] == "warn" and "90 %" in item["title"]
    watch.last = None


def test_discord_and_webhooks_get_the_warning():
    from floorbit import webhooks
    from integrations.discord import DiscordNotifier
    alert = {"t": 1_794_650_400, "bps": 9 * G, "pct": 90, "capacity_bps": 10 * G}
    msg = DiscordNotifier().build_forecast_message(alert)
    assert "90 %" in msg["embeds"][0]["title"] and "9.0 Gbps of a 10.0 Gbps line" in msg["embeds"][0]["description"]
    assert webhooks.translate({"type": "forecast.alert", "data": alert}) == [("forecast.alert", alert)]
