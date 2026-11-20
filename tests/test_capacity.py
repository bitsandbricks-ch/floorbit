"""When a pool runs full (issue #1061): the forecast and how the health wall uses it."""
import types

from floorbit import capacity


def test_clean_keeps_only_numbers_that_make_sense():
    assert capacity.clean({"used": 10, "total": 120}) == {"used": 10, "total": 120}
    assert capacity.clean({"used": 130, "total": 120}) == {"used": 120, "total": 120}
    for bad in (None, "x", {"used": 1}, {"used": "1", "total": 2}, {"used": 1, "total": 0},
                {"used": -1, "total": 5}, {"used": True, "total": 5}):
        assert capacity.clean(bad) is None, bad


def test_no_rate_before_five_minutes_of_samples():
    out = capacity.forecast([(1000, 50)], 60, 120, 1000 + 120)
    assert out["rate_per_min"] is None and out["full_in_min"] is None and out["level"] is None


def test_a_rush_is_forecast_full_and_worth_a_look():
    # 1 lease a minute for 10 minutes, 40 left: full in 40 min.
    out = capacity.forecast([(0, 70)], 80, 120, 600)
    assert out["rate_per_min"] == 1 and out["full_in_min"] == 40 and out["level"] == "warn" and out["pct"] == 67
    # The same pool filling slowly: nothing to say yet.
    assert capacity.forecast([(0, 79)], 80, 120, 600)["level"] is None


def test_full_and_nearly_full_without_growth():
    assert capacity.forecast([], 120, 120, 0)["level"] == "down"
    assert capacity.forecast([], 103, 120, 0)["level"] == "warn"      # 86 %
    assert capacity.forecast([(0, 90)], 80, 120, 600)["full_in_min"] is None   # emptying


def test_only_the_last_window_counts():
    # The rush was an hour ago; the last quarter of an hour is flat.
    samples = [(0, 10), (2400, 80), (2700, 80)]
    assert capacity.forecast(samples, 80, 120, 3600)["rate_per_min"] == 0


def test_forecaster_keeps_its_samples_and_starts_over_on_a_new_pool():
    f = capacity.Forecaster()
    for minute in range(11):
        out = f.observe("dhcp", {"used": 70 + minute, "total": 120}, minute * 60)
    assert out["full_in_min"] == 40
    assert f.observe("dhcp", {"used": 81, "total": 200}, 700)["rate_per_min"] is None
    f.keep_only([])
    assert f.observe("dhcp", {"used": 81, "total": 200}, 760)["rate_per_min"] is None


def test_the_wall_raises_a_filling_scope_and_problems_say_when(client, app_module, monkeypatch):
    wall = app_module.app.extensions["floorbit_health"]
    wall.stop()
    wall.reset()
    registry = app_module.app.extensions["floorbit_plugins"]
    client.put("/api/settings/plugins/demo", json={"enabled": True})
    used = {"n": 70}
    real = registry.call

    def call(spec, method, *args):
        if method == "health_checks" and spec.id == "demo":
            return [{"id": "scope", "name": "DHCP players", "kind": "dhcp", "status": "up",
                     "summary": f"{120 - used['n']} of 120 leases left",
                     "capacity": {"used": used["n"], "total": 120}}]
        return real(spec, method, *args)

    monkeypatch.setattr(registry, "call", call)
    clock = {"t": 1_000_000.0}
    # Only the wall's clock: the session and everything else keep the real time.
    monkeypatch.setattr("floorbit.health.time", types.SimpleNamespace(time=lambda: clock["t"]))
    try:
        for _ in range(11):
            wall.poll_once()
            clock["t"] += 60
            used["n"] += 1
        check = next(c for c in wall.snapshot()["checks"] if c["id"] == "demo:scope")
        assert check["status"] == "warn" and check["forecast"]["raised"] and check["forecast"]["full_in_min"] == 40
        body = client.get("/api/problems").get_json()
        titles = [p["title"] for p in body["problems"] + body["attention"]]
        assert "DHCP players: full in about 40 min" in titles
        de = client.get("/api/problems", headers={"Accept-Language": "de-CH"}).get_json()
        assert "DHCP players: in etwa 40 Min. voll" in [p["title"] for p in de["problems"] + de["attention"]]
    finally:
        wall.reset()
