"""When a pool runs full (issue #1061): DHCP scopes first, anything a health check counts.

A health check may say how much of something is used: ``"capacity": {"used": 96, "total": 120}``
(the DHCP plugin does it per scope). The wall keeps those numbers for an hour and works out how fast
they grow, so at doors open the crew reads "full in ~25 min" while there are still addresses left,
not "0 left" once players are offline.

The rate is over the last ``WINDOW`` (enough to see a rush, short enough to stop warning once it
is over), and only after ``MIN_SPAN`` of samples, so one poll after a restart warns nobody.
"""
import threading
from collections import deque

WINDOW = 15 * 60        # seconds the rate is measured over
MIN_SPAN = 5 * 60       # seconds of samples needed before there is a rate
KEEP = 60 * 60          # seconds of samples kept per check
SOON = 60               # minutes: forecast full within this is worth a look
FULLISH = 0.85          # this share used is worth a look even when nothing grows


def clean(raw):
    """``{'used', 'total'}`` from what a plugin sent, or None."""
    if not isinstance(raw, dict):
        return None
    used, total = raw.get('used'), raw.get('total')
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in (used, total)):
        return None
    if total <= 0 or used < 0:
        return None
    return {'used': min(used, total), 'total': total}


def forecast(samples, used, total, now):
    """What ``samples`` [(time, used), ...] say about a pool with ``used`` of ``total`` now."""
    pct = used / total
    rate = full_in = None
    recent = [(t, u) for t, u in samples if now - WINDOW <= t < now]
    if recent and now - recent[0][0] >= MIN_SPAN:
        t0, u0 = recent[0]
        rate = (used - u0) / ((now - t0) / 60)
        if rate > 0 and used < total:
            full_in = (total - used) / rate
    level = 'down' if used >= total else 'warn' if pct >= FULLISH or (full_in is not None and full_in <= SOON) else None
    return {'used': used, 'total': total, 'pct': round(pct * 100),
            'rate_per_min': round(rate, 2) if rate is not None else None,
            'full_in_min': max(1, round(full_in)) if full_in is not None else None, 'level': level}


class Forecaster:
    """The samples per check id, in this process (each pod polls the wall itself)."""

    def __init__(self):
        self._lock = threading.Lock()
        self._samples = {}

    def observe(self, check_id, capacity, now):
        with self._lock:
            series = self._samples.setdefault(check_id, deque())
            while series and series[0][0] < now - KEEP:
                series.popleft()
            # A smaller pool than before (the scope was changed) makes the old samples meaningless.
            if series and series[-1][2] != capacity['total']:
                series.clear()
            out = forecast([(t, u) for t, u, _ in series], capacity['used'], capacity['total'], now)
            series.append((now, capacity['used'], capacity['total']))
            return out

    def keep_only(self, check_ids):
        with self._lock:
            for gone in set(self._samples) - set(check_ids):
                self._samples.pop(gone)

    def reset(self):
        with self._lock:
            self._samples.clear()
