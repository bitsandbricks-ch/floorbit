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
MAX_SEAT_EVENTS = 100_000   # a flapping port must not grow the saved stats without end
# For the post-event report (issue #22), kept for the whole event, not just the last day.
EVENT_DAYS = 21
MAX_SWITCH_EVENTS = 5000
MAX_PROBLEM_PORTS = 1000


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
        # For the replay (issue #21): which seats went online or offline when, as [t, seat, 1|0] on
        # change only, and which seats were online at the start of what is kept.
        self.seat_events = deque()
        self.seat_base = {'t': None, 'online': []}
        self._online = None      # the seats online at the last read
        # For the report (issue #22), since the last "new event": one row per hour (most seats online,
        # busiest read, average), switches going down and up, and how often each port had a problem.
        self.hours = {}          # str(hour start) -> {'online_max', 'peak_bps', 'sum_bps', 'n'}
        self.switch_events = deque()   # [t, switch_id, name, 'offline'|'online']
        self.problem_ports = {}  # 'switch_id|port' -> {'switch', 'port', 'seat', 'count', 'kinds', 'last'}
        self.event_start = None
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
            self.seat_events = deque(e for e in saved.get('seat_events') or [] if isinstance(e, list) and len(e) == 3)
            base = saved.get('seat_base')
            if isinstance(base, dict):
                self.seat_base = {'t': base.get('t'), 'online': list(base.get('online') or [])}
            online = saved.get('online_now')
            self._online = set(online) if isinstance(online, list) else None
            hours = saved.get('hours')
            self.hours = {k: v for k, v in hours.items() if isinstance(v, dict)} if isinstance(hours, dict) else {}
            self.switch_events = deque(e for e in saved.get('switch_events') or []
                                       if isinstance(e, list) and len(e) == 4)
            problems = saved.get('problem_ports')
            self.problem_ports = {k: v for k, v in problems.items() if isinstance(v, dict)} \
                if isinstance(problems, dict) else {}
            self.event_start = saved.get('event_start')

    def _save(self):
        client = cache.get_redis_client()
        if not client:
            return
        try:
            client.set(REDIS_KEY, json.dumps({
                'samples': list(self.samples), 'peak': self.peak, 'seat_events': list(self.seat_events),
                'seat_base': self.seat_base, 'online_now': sorted(self._online) if self._online is not None else None,
                'hours': self.hours, 'switch_events': list(self.switch_events), 'problem_ports': self.problem_ports,
                'event_start': self.event_start,
            }))
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
            self._seat_changes(set(seat_bps), now)
            self._hour(sample)
            self.last = now
            self._save()
        return sample

    def _seat_changes(self, online, now):
        """Write down which seats went online or offline since the last read (lock held)."""
        before = self._online
        if before is None:
            # The first read since the start: what was online before it is unknown.
            if self.seat_base['t'] is None:
                self.seat_base = {'t': now, 'online': []}
            before = _replay(self.seat_base, self.seat_events)
        for seat in sorted(online - before):
            self.seat_events.append([now, seat, 1])
        for seat in sorted(before - online):
            self.seat_events.append([now, seat, 0])
        self._online = online
        # Keep the same day as the samples: older changes fold into the starting state.
        cutoff = now - DAY
        base = set(self.seat_base['online'])
        while self.seat_events and (self.seat_events[0][0] < cutoff or len(self.seat_events) > MAX_SEAT_EVENTS):
            t, seat, on = self.seat_events.popleft()
            (base.add if on else base.discard)(seat)
            self.seat_base = {'t': t, 'online': sorted(base)}

    def _hour(self, sample):
        """Fold one read into its hour (lock held)."""
        if self.event_start is None:
            self.event_start = sample['t']
        key = str(int(sample['t'] // HOUR * HOUR))
        total = sample['down'] + sample['up']
        row = self.hours.get(key) or {'online_max': 0, 'peak_bps': 0, 'sum_bps': 0, 'n': 0}
        row = {'online_max': max(row['online_max'], sample['online']), 'peak_bps': max(row['peak_bps'], total),
               'sum_bps': row['sum_bps'] + total, 'n': row['n'] + 1}
        self.hours[key] = row
        cutoff = sample['t'] - EVENT_DAYS * DAY
        for old in [k for k in self.hours if int(k) < cutoff]:
            del self.hours[old]

    def record_switch(self, change):
        """A switch went offline or came back (``switch.status`` from the status monitor)."""
        if change.get('status') not in ('online', 'offline'):
            return
        with self._lock:
            self._load()
            self.switch_events.append([change.get('since') or time.time(), change.get('id'),
                                       change.get('name') or '', change['status']])
            while len(self.switch_events) > MAX_SWITCH_EVENTS:
                self.switch_events.popleft()
            self._save()

    def count_problems(self, entries, now=None):
        """Needs-attention items that just started: counted per port for the report's problem ports."""
        if not entries:
            return
        now = time.time() if now is None else now
        with self._lock:
            self._load()
            for e in entries:
                key = f"{e.get('switch_id')}|{e.get('port')}"
                row = self.problem_ports.get(key) or {'switch': e.get('switch'), 'port': e.get('port'),
                                                      'seat': e.get('seat'), 'count': 0, 'kinds': {}}
                row['count'] += 1
                row['kinds'][e.get('kind') or 'other'] = row['kinds'].get(e.get('kind') or 'other', 0) + 1
                row['seat'] = e.get('seat') or row.get('seat')
                row['last'] = now
                self.problem_ports[key] = row
            if len(self.problem_ports) > MAX_PROBLEM_PORTS:
                keep = sorted(self.problem_ports.items(), key=lambda kv: (-kv[1]['count'], -kv[1]['last']))
                self.problem_ports = dict(keep[:MAX_PROBLEM_PORTS])
            self._save()

    def event(self):
        """What the post-event report needs, kept since the last new event."""
        with self._lock:
            self._load()
            hours = [{'t': int(k), 'online_max': v['online_max'], 'peak_bps': v['peak_bps'],
                      'avg_bps': round(v['sum_bps'] / v['n']) if v['n'] else 0} for k, v in self.hours.items()]
            return {'start': self.event_start, 'hours': sorted(hours, key=lambda h: h['t']), 'peak': self.peak,
                    'switch_events': [list(e) for e in self.switch_events],
                    'problem_ports': [dict(v, kinds=dict(v['kinds'])) for v in self.problem_ports.values()]}

    def new_event(self, now=None):
        """Start a new event: the report and the peak begin again. The last day's samples stay."""
        now = time.time() if now is None else now
        with self._lock:
            self._load()
            self.hours, self.problem_ports, self.event_start = {}, {}, now
            self.switch_events = deque()
            last = self.samples[-1] if self.samples else None
            self.peak = {'bps': last['down'] + last['up'], 'at': last['t']} if last else None
            self._save()

    def backfill_event(self, switch_events, problems):
        """The demo hall's made-up outages and problem ports, only while there are none yet."""
        with self._lock:
            self._load()
            if self.switch_events or self.problem_ports:
                return
            self.switch_events.extend(switch_events)
            self.problem_ports = dict(problems)
            self._save()

    def backfill_seats(self, events, base_t):
        """Older seat changes (the demo hall's made-up day), only while there are none yet."""
        with self._lock:
            self._load()
            if self.seat_events or not events:
                return
            self.seat_events.extend(events)
            self.seat_base = {'t': base_t, 'online': []}
            self._online = _replay(self.seat_base, self.seat_events)
            self._save()

    def timeline(self):
        """What the replay needs: the samples, the event's peak, and the seats' changes."""
        with self._lock:
            self._load()
            return {'samples': [{k: s[k] for k in ('t', 'down', 'up', 'online')} for s in self.samples],
                    'peak': self.peak, 'seat_base': dict(self.seat_base), 'seat_events': list(self.seat_events),
                    'last_poll': self.last}

    def backfill(self, samples):
        """Older samples (the demo hall's made-up day), only while there are none yet."""
        with self._lock:
            self._load()
            if self.samples or not samples:
                return
            self.samples.extend(samples)
            for sample in samples:
                self._hour(sample)
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


def _replay(base, events, until=None):
    online = set(base.get('online') or [])
    for t, seat, on in events:
        if until is not None and t > until:
            break
        (online.add if on else online.discard)(seat)
    return online


def _window(samples, since):
    rows = [s for s in samples if s['t'] >= since]
    if not rows:
        return None
    total = [s['down'] + s['up'] for s in rows]
    busiest = max(rows, key=lambda s: s['down'] + s['up'])
    return {'avg_bps': round(sum(total) / len(total)), 'peak_bps': busiest['down'] + busiest['up'],
            'peak_at': busiest['t'], 'online_max': max(s['online'] for s in rows), 'samples': len(rows)}


_current = None


def _on_switch_status(event):
    if _current is not None:
        _current.record_switch(event.get('data') or {})


def init_stats(app):
    global _current
    from integrations import events
    stats = Stats()
    app.extensions['floorbit_stats'] = stats
    # One subscription for the process: the newest app's stats take the switch changes.
    _current = stats
    events.subscribe_once('switch.status', _on_switch_status)
    return stats
