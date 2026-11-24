"""The demo hall's live traffic continues its made-up day instead of jumping (#944)."""
from floorbit.blueprints.demo import demo_history
from floorbit.builtin_plugins.demo import plugin as demo


def _live_down(now, monkeypatch):
    monkeypatch.setattr(demo.time, "time", lambda: now)
    return sum(demo.Plugin._rates(i)[0] for _s, _b, _n, i in demo._seats() if demo._taken(i)) * 8


def test_the_live_hall_holds_its_level(monkeypatch):
    mean, _up, _taken = demo.live_level()
    reads = [_live_down(1_000_000 + k * 20, monkeypatch) for k in range(30)]   # ten minutes, two waves
    # The heavy downloaders used to swing in step: the total went from 0.3x to 1.7x the mean.
    assert all(0.65 * mean < r < 1.35 * mean for r in reads)


def test_the_made_up_day_ends_at_the_live_level():
    down, up, taken = demo.live_level()
    last = demo_history(now=2_000_000)[-1]
    assert 0.85 * down < last["down"] < 1.15 * down
    assert last["up"] < last["down"] and 0.85 * up < last["up"] < 1.15 * up
    assert taken - 10 <= last["online"] <= taken
