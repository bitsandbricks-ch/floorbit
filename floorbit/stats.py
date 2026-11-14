"""Stats dashboard (issue #24): bandwidth now, peak, last hour and 24 hours. See docs/stats.md.

No requests of its own: the needs-attention watch (``attention.py``) already reads every port of
the placed, online switches each ``ATTENTION_INTERVAL``, and hands them here. From that read:

- **bandwidth:** download and upload summed over the access ports (to and from the players);
- **online seats:** seat ports (the description names a seat) that are up;
- **ports:** up, down and with errors;
- **uplinks:** per switch, its busiest up port whose description says ``uplink`` or ``trunk``
  (``STATS_UPLINK_PATTERN``) or names another switch;
- **top talkers:** the ports with the most traffic right now, by seat where the port has one.

One sample per read is kept for 24 hours, plus the event's peak, in Redis (``floorbit:stats``) so
a restart doesn't lose them; without Redis they live in memory only. Samples hold numbers, seats
and ports, never who sits there: nicks are added at request time for ``seats.view`` only.
"""
import json
import re
import threading
import time
from collections import deque

from integrations import config

from . import cache

DAY = 24 * 3600
HOUR = 3600
REDIS_KEY = 'floorbit:stats'
TOP = 10


def _num(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _uplink_re():
    pattern = config.get('STATS_UPLINK_PATTERN') or r'uplink|trunk'
    try:
        return re.compile(pattern, re.IGNORECASE)
    except re.error:
        return re.compile(r'uplink|trunk', re.IGNORECASE)


class Stats:
    def __init__(self):
        self._lock = threading.Lock()
        self.reset()

    def reset(self):
        self.samples = deque()   # {'t', 'down', 'up', 'online', 'ports_up', 'ports_down', 'ports_errors'}
        self.peak = None         # {'bps', 'at'}: the busiest read since the last reset
        self.uplinks = []
        self.top = []
        self.seat_bps = {}       # seat -> traffic right now, for the kiosk's heat view
        self.last = None
        self._loaded = False

    # ── storage ───────────────────────────────────────────────────────────────
    def _load(self):
        if self._loaded:
            return
        self._loaded = True
        client = cache.get_redis_client()
        if not client:
            return
        try:
            raw = client.get(REDIS_KEY)
            saved = json.loads(raw) if raw else None
        except Exception as exc:  # noqa: BLE001  # a broken cache never stops the stats
            print(f'[stats] could not read the saved stats: {exc}')
            return
        if isinstance(saved, dict):
            self.samples = deque(s for s in saved.get('samples') or [] if isinstance(s, dict) and 't' in s)
            self.peak = saved.get('peak')

    def _save(self):
        client = cache.get_redis_client()
        if not client:
            return
        try:
            client.set(REDIS_KEY, json.dumps({'samples': list(self.samples), 'peak': self.peak}))
        except Exception as exc:  # noqa: BLE001
            print(f'[stats] could not save the stats: {exc}')

    # ── recording ─────────────────────────────────────────────────────────────
    def record(self, reads, switch_names, now=None):
        """``reads`` is ``[(device, port, seat)]`` from one read of all switches."""
        now = time.time() if now is None else now
        uplink_re = _uplink_re()
        names = {n.lower() for n in switch_names}
        down = up = 0.0
        online = ports_up = ports_down = ports_errors = 0
        uplinks = {}
        talkers = []
        seat_bps = {}
        for dev, port, seat in reads:
            state = port.get('state')
            if state in ('up', 'errors'):
                ports_up += 1
            elif state == 'down':
                ports_down += 1
            if state == 'errors':
                ports_errors += 1
            desc = str(port.get('description') or '')
            other_switch = any(n in desc.lower() for n in names if n != str(dev['name']).lower())
            if not seat and state in ('up', 'errors') and (uplink_re.search(desc) or other_switch):
                bps = max(_num(port.get('download_bps')), _num(port.get('upload_bps')))
                best = uplinks.get(dev['id'])
                if best is None or bps > best['bps']:
                    uplinks[dev['id']] = {'switch_id': dev['id'], 'switch': dev['name'], 'port': port['name'],
                                          'bps': round(bps), 'speed_bps': port.get('speed_bps'),
                                          'utilization': port.get('utilization')}
                continue
            d, u = _num(port.get('download_bps')), _num(port.get('upload_bps'))
            down += d
            up += u
            if seat and state in ('up', 'errors'):
                online += 1
                seat_bps[seat] = round(d + u)
            if d + u > 0:
                talkers.append({'seat': seat, 'switch_id': dev['id'], 'switch': dev['name'], 'port': port['name'],
                                'download_bps': round(d), 'upload_bps': round(u), 'bps': round(d + u)})
        sample = {'t': now, 'down': round(down), 'up': round(up), 'online': online,
                  'ports_up': ports_up, 'ports_down': ports_down, 'ports_errors': ports_errors}
        with self._lock:
            self._load()
            self.samples.append(sample)
            while self.samples and now - self.samples[0]['t'] > DAY:
                self.samples.popleft()
            if not self.peak or sample['down'] + sample['up'] > self.peak['bps']:
                self.peak = {'bps': sample['down'] + sample['up'], 'at': now}
            self.uplinks = sorted(uplinks.values(), key=lambda u: -(u['utilization'] or 0))
            self.top = sorted(talkers, key=lambda t: -t['bps'])[:TOP]
            self.seat_bps = seat_bps
            self.last = now
            self._save()
        return sample

    def backfill(self, samples):
        """Older samples (the demo hall's made-up day), only while there are none yet."""
        with self._lock:
            self._load()
            if self.samples or not samples:
                return
            self.samples.extend(samples)
            busiest = max(samples, key=lambda s: s['down'] + s['up'])
            self.peak = {'bps': busiest['down'] + busiest['up'], 'at': busiest['t']}
            self._save()

    def seats(self):
        """Traffic per online seat from the latest read: seat numbers and numbers, nothing else."""
        with self._lock:
            return {'seats': dict(self.seat_bps), 'last_poll': self.last}

    def reset_peak(self):
        with self._lock:
            self._load()
            last = self.samples[-1] if self.samples else None
            self.peak = {'bps': last['down'] + last['up'], 'at': last['t']} if last else None
            self._save()

    # ── reading ───────────────────────────────────────────────────────────────
    def snapshot(self, now=None):
        now = time.time() if now is None else now
        with self._lock:
            self._load()
            samples = list(self.samples)
            out = {'last_poll': self.last or (samples[-1]['t'] if samples else None), 'peak': self.peak,
                   'uplinks': [dict(u) for u in self.uplinks], 'top': [dict(t) for t in self.top]}
        out['now'] = samples[-1] if samples else None
        out['hour'] = _window(samples, now - HOUR)
        out['day'] = _window(samples, now - DAY)
        out['series'] = [{k: s[k] for k in ('t', 'down', 'up', 'online')} for s in samples]
        return out


def _window(samples, since):
    rows = [s for s in samples if s['t'] >= since]
    if not rows:
        return None
    total = [s['down'] + s['up'] for s in rows]
    busiest = max(rows, key=lambda s: s['down'] + s['up'])
    return {'avg_bps': round(sum(total) / len(total)), 'peak_bps': busiest['down'] + busiest['up'],
            'peak_at': busiest['t'], 'online_max': max(s['online'] for s in rows), 'samples': len(rows)}


def init_stats(app):
    stats = Stats()
    app.extensions['floorbit_stats'] = stats
    return stats
