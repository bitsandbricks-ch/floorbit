"""Bandwidth forecast (issue #89): when will the hall be busiest, and will it fit? See docs/forecast.md.

Simple and explainable on purpose, no black box. From the stats' hourly rows since the event
started (``Stats.event()``: the busiest read of each hour):

1. **Profile:** for each hour of the day, the average busiest read at that hour on earlier days.
   Hours of the day the event hasn't seen yet use the average of the last ``RECENT`` hours.
2. **Level:** how the last ``RECENT`` hours ran against the profile for those hours, as a factor
   (1.2 is 20 % busier than on earlier days), kept between 0.5 and 2.
3. **Forecast:** profile times level, for the next ``AHEAD`` hours, with a range from the quietest
   and the busiest day at that hour.

With a capacity (``FORECAST_CAPACITY_MBPS``, the internet line), a forecast at or over
``FORECAST_WARN_PERCENT`` (80) within ``FORECAST_LEAD_HOURS`` (3) is a warning: on the Problems
list, and once per expected peak to Discord and webhooks (event ``forecast.alert``).

Note the numbers are the hall's total (all access ports, LAN cache traffic included), so they are
an upper bound for what the internet line carries.
"""
import threading
import time

from integrations import config, events

from . import features

HOUR = 3600
RECENT = 3
AHEAD = 12
MIN_HOURS = 6        # less history than this: no forecast yet


def settings():
    mbps = config.get_int('FORECAST_CAPACITY_MBPS', 0, minimum=0)
    return {'capacity_bps': mbps * 1_000_000 or None,
            'warn_pct': config.get_int('FORECAST_WARN_PERCENT', 80, minimum=10),
            'lead_hours': config.get_int('FORECAST_LEAD_HOURS', 3, minimum=1)}


def _local_hour(t):
    return time.localtime(t).tm_hour


def forecast(rows, now=None, conf=None):
    """``rows`` are ``{"t", "peak_bps"}`` per hour. Returns the forecast and how it was made."""
    now = time.time() if now is None else now
    conf = conf or settings()
    current = int(now // HOUR * HOUR)
    done = sorted((r for r in rows if r['t'] < current and r.get('peak_bps') is not None), key=lambda r: r['t'])
    out = {'ready': False, 'history_hours': len(done), 'min_hours': MIN_HOURS, 'capacity_bps': conf['capacity_bps'],
           'warn_pct': conf['warn_pct'], 'lead_hours': conf['lead_hours'], 'points': [], 'alert': None,
           'level': None, 'days': 0, 'peak': None}
    if len(done) < MIN_HOURS:
        return out
    recent = done[-RECENT:]
    recent_avg = sum(r['peak_bps'] for r in recent) / len(recent)
    by_hour = {}
    for r in done:
        by_hour.setdefault(_local_hour(r['t']), []).append(r)

    def earlier(hour, before):
        return [r['peak_bps'] for r in by_hour.get(hour, []) if r['t'] < before]

    # The level: the last hours against the same hours on earlier days.
    pairs = []
    for r in recent:
        seen = earlier(_local_hour(r['t']), r['t'] - 12 * HOUR)
        if seen:
            pairs.append((r['peak_bps'], sum(seen) / len(seen)))
    level = 1.0
    if pairs and sum(p for _a, p in pairs) > 0:
        level = min(2.0, max(0.5, sum(a for a, _p in pairs) / sum(p for _a, p in pairs)))
    points = []
    for k in range(1, AHEAD + 1):
        t = current + k * HOUR
        seen = earlier(_local_hour(t), current + HOUR)
        if seen:
            base, low, high, basis = sum(seen) / len(seen), min(seen), max(seen), 'profile'
        else:
            base = low = high = recent_avg
            basis = 'recent'
        points.append({'t': t, 'bps': round(base * level), 'low': round(low * level), 'high': round(high * level),
                       'basis': basis})
    days = max((len(v) for v in by_hour.values()), default=0)
    out.update(ready=True, points=points, level=round(level, 2) if pairs else None, days=days,
               peak=max(points, key=lambda p: p['bps']))
    cap = conf['capacity_bps']
    if cap:
        for p in points[:conf['lead_hours']]:
            pct = round(p['bps'] / cap * 100)
            p['pct'] = pct
            if pct >= conf['warn_pct'] and out['alert'] is None:
                out['alert'] = {'t': p['t'], 'bps': p['bps'], 'pct': pct}
        for p in points[conf['lead_hours']:]:
            p['pct'] = round(p['bps'] / cap * 100)
    return out


class ForecastWatch:
    """Works the forecast out every few minutes and says once per expected peak when it won't fit."""

    def __init__(self, stats):
        self.stats = stats
        self._thread = None
        self._stop = threading.Event()
        self._warned = set()     # hours a warning was sent for
        self.last = None

    def current(self, now=None):
        rows = self.stats.event()['hours'] if self.stats is not None else []
        return forecast(rows, now)

    def check(self, now=None):
        result = self.current(now)
        self.last = result
        alert = result['alert']
        if alert and alert['t'] not in self._warned:
            self._warned.add(alert['t'])
            events.publish('forecast.alert', {**alert, 'capacity_bps': result['capacity_bps']})
        return result

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name='forecast-watch', daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _run(self):
        while True:
            if features.on('forecast'):
                try:
                    self.check()
                except Exception as exc:  # noqa: BLE001  # keep the thread alive no matter what
                    print(f'[forecast] check failed: {exc}')
            if self._stop.wait(300):
                return


def init_forecast(app, start_background=True):
    watch = ForecastWatch(app.extensions.get('floorbit_stats'))
    app.extensions['floorbit_forecast'] = watch
    started = threading.Event()

    @app.before_request
    def start_forecast_once():
        if start_background and not started.is_set():
            started.set()
            watch.start()

    return watch
