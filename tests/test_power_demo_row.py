"""The demo's open Electrics incident is about C row 2, so C row 2 is the row near its limit, and no
other row looks close (issue #1427: the board showed B row 2 getting close instead)."""
from floorbit.builtin_plugins.demo import plugin as demo


def test_only_the_row_with_the_incident_runs_near_its_fuse(monkeypatch):
    for k in range(42):                                  # every half minute for 21 minutes: three peaks
        monkeypatch.setattr(demo.time, "time", lambda k=k: 1_000_000 + k * 30)
        amps = {r["meter"]: r["amps"] for r in demo.Plugin.power_readings(None)}
        assert amps["c2"] >= 0.8 * 16                    # warn from 80 % of its 16 A fuse
        assert all(a < 0.8 * 16 for m, a in amps.items() if m not in ("c2", "rack"))
