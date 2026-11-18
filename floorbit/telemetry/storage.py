"""Where telemetry is kept over time (docs/telemetry.md).

- **VictoriaMetrics** (``FLOORBIT_VICTORIAMETRICS_URL``, the optional sidecar): every point that
  came in (``/write``, line protocol, for Grafana and deep dives), plus a normalised series per
  device and port every ``SAMPLE`` seconds: ``fb_port_in_bps``, ``fb_port_out_bps``,
  ``fb_port_errors``, ``fb_port_up``, ``fb_device_up``, ``fb_device_cpu``, ``fb_device_mem``,
  ``fb_device_states``, with ``device`` and ``port`` labels, the same whichever driver sent them.
- **Lite** (no VictoriaMetrics): the normalised series only, in Floorbit's own database
  (SQLite or Postgres, table ``floorbit_telemetry``): a point a minute for ``FINE_HOURS`` (6), a
  point every 15 minutes for ``FLOORBIT_TELEMETRY_DAYS`` (2).
- **VictoriaLogs** (``FLOORBIT_VICTORIALOGS_URL``, optional): log events, as JSON lines.

MAC tables, ARP and neighbours (state.PRIVATE) are never stored: they name the people at the seats.
Redis is not used for any of it.
"""
import json
import os
import time

import requests

from . import lineproto
from . import state as state_mod

SAMPLE = 30
FINE, COARSE = 60, 900
FINE_HOURS = 6
CHUNK = 200                      # rows per INSERT (4 values each, well under SQLite's limit)
SERIES_MAX = 300                 # floorbit_telemetry.series is VARCHAR(300)
TIMEOUT = 5
PORT_METRICS = ('in_bps', 'out_bps', 'errors', 'up')
DEVICE_METRICS = ('up', 'cpu', 'mem', 'states')


def vm_url():
    return (os.environ.get('FLOORBIT_VICTORIAMETRICS_URL') or '').rstrip('/') or None


def vl_url():
    return (os.environ.get('FLOORBIT_VICTORIALOGS_URL') or '').rstrip('/') or None


def keep_days():
    try:
        return max(1, min(30, int(os.environ.get('FLOORBIT_TELEMETRY_DAYS') or 2)))
    except ValueError:
        return 2


def series_key(device, port, metric):
    return f'{device}|{port or ""}|{metric}'


def snapshot(st=None, now=None):
    """{series key: value} from the latest picture: what gets stored every SAMPLE seconds."""
    st = st or state_mod.state
    now = time.time() if now is None else now
    out = {}
    with st._lock:
        for dev in st.devices.values():
            online = dev.online(now)
            out[series_key(dev.name, None, 'up')] = 1.0 if online else 0.0
            if not online:
                continue
            for metric, value in (('cpu', dev.cpu), ('mem', dev.mem), ('states', dev.states)):
                if value is not None:
                    out[series_key(dev.name, None, metric)] = float(value)
            for iface in dev.interfaces.values():
                if not iface.name or now - iface.seen > state_mod.STALE:
                    continue
                if iface.oper is not None:
                    out[series_key(dev.name, iface.name, 'up')] = 1.0 if iface.oper == 'up' else 0.0
                if iface.oper != 'up':
                    continue
                for metric, value in (('in_bps', iface.in_bps), ('out_bps', iface.out_bps)):
                    if value is not None:
                        out[series_key(dev.name, iface.name, metric)] = round(value, 1)
                rates = [r for r in (iface.in_err_rate, iface.out_err_rate) if r is not None]
                if rates:
                    out[series_key(dev.name, iface.name, 'errors')] = round(sum(rates), 3)
    return out


def _vm_line(key, value, at):
    device, port, metric = key.split('|', 2)
    tags = {'device': device}
    if port:
        tags['port'] = port
    name = f'fb_port_{metric}' if port else f'fb_device_{metric}'
    return lineproto.format_point(lineproto.Point(name, tags, {'value': float(value)}, at))


class Storage:
    def __init__(self, db):
        self.db = db                      # floorbit.database.Sql
        self.errors = {}                  # sink -> last error
        self.written = 0
        self._pruned = 0

    # ── writing ──
    def forward_raw(self, points):
        """Points that came in, to VictoriaMetrics, without the private tables."""
        url = vm_url()
        if not url:
            return 0
        lines = [lineproto.format_point(p) for p in points if p.measurement not in state_mod.PRIVATE]
        return self._vm_write(url, lines)

    def _vm_write(self, url, lines):
        if not lines:
            return 0
        try:
            resp = requests.post(f'{url}/write', data='\n'.join(lines).encode(), timeout=TIMEOUT)
        except requests.RequestException as exc:
            self.errors['victoriametrics'] = type(exc).__name__
            return 0
        if resp.status_code >= 300:
            self.errors['victoriametrics'] = f'HTTP {resp.status_code}'
            return 0
        self.errors.pop('victoriametrics', None)
        return len(lines)

    def sample(self, values, now=None):
        """Store one snapshot(): to VictoriaMetrics when it is there, else the lite rollups."""
        now = time.time() if now is None else now
        url = vm_url()
        if url:
            self.written += self._vm_write(url, [_vm_line(k, v, now) for k, v in values.items()])
            return
        rows = []
        for step in (FINE, COARSE):
            bucket = int(now // step * step)
            # A name the table can't hold (a NUL byte, longer than its column) would stop the
            # whole sample at that row: leave just that series out.
            rows += [(k, step, bucket, float(v)) for k, v in values.items()
                     if len(k) <= SERIES_MAX and '\x00' not in k]
        from ..database import DatabaseError
        try:
            # Many rows per statement: one round trip per row took 5 s for 10,000 numbers on
            # a local Postgres, longer than SAMPLE at a bigger event over a real network.
            for i in range(0, len(rows), CHUNK):
                part = rows[i:i + CHUNK]
                self.db.run('INSERT INTO floorbit_telemetry (series, step, bucket, value) VALUES '
                            + ', '.join(['(?, ?, ?, ?)'] * len(part))
                            + ' ON CONFLICT (series, step, bucket) DO UPDATE SET value = excluded.value',
                            [x for row in part for x in row])
        except DatabaseError as exc:      # the database is away: skip this sample, never stop
            self.errors['database'] = str(exc)[:200]
            return
        self.errors.pop('database', None)
        self.written += len(values)
        if now - self._pruned > 3600:
            self.prune(now)

    def prune(self, now=None):
        now = time.time() if now is None else now
        self._pruned = now
        from ..database import DatabaseError
        try:
            sql = 'DELETE FROM floorbit_telemetry WHERE step = ? AND bucket < ?'
            self.db.run(sql, (FINE, int(now - FINE_HOURS * 3600)))
            self.db.run(sql, (COARSE, int(now - keep_days() * 86400)))
        except DatabaseError as exc:
            self.errors['database'] = str(exc)[:200]

    def send_logs(self, events):
        """Log events ({time, device, msg, ...}) to VictoriaLogs. Returns how many went."""
        url = vl_url()
        if not url or not events:
            return 0
        body = '\n'.join(json.dumps(e, separators=(',', ':'), default=str) for e in events).encode()
        try:
            resp = requests.post(f'{url}/insert/jsonline', data=body, timeout=TIMEOUT,
                                 params={'_stream_fields': 'device,kind', '_msg_field': 'msg', '_time_field': 'time'})
        except requests.RequestException as exc:
            self.errors['victorialogs'] = type(exc).__name__
            return 0
        if resp.status_code >= 300:
            self.errors['victorialogs'] = f'HTTP {resp.status_code}'
            return 0
        self.errors.pop('victorialogs', None)
        return len(events)

    # ── reading ──
    def series(self, device, port, metric, hours=6, now=None):
        """[[unix time, value]] of one series, oldest first."""
        now = time.time() if now is None else now
        hours = max(0.25, min(float(hours), keep_days() * 24))
        since = now - hours * 3600
        url = vm_url()
        if url:
            return self._vm_series(url, device, port, metric, since, now)
        key = series_key(device, port, metric)
        step = FINE if hours <= FINE_HOURS else COARSE
        rows = self.db.run('SELECT bucket, value FROM floorbit_telemetry WHERE series = ? AND step = ? AND bucket >= ? '
                           'ORDER BY bucket', (key, step, int(since)), fetch=True) or []
        return [[int(b), float(v)] for b, v in rows]

    def _vm_series(self, url, device, port, metric, since, now):
        from ..builtin_plugins.prometheus.plugin import quote
        name = f'fb_port_{metric}_value' if port else f'fb_device_{metric}_value'
        selector = f'{name}{{device={quote(device)}' + (f',port={quote(port)}' if port else '') + '}'
        step = max(SAMPLE, int((now - since) / 400))
        try:
            resp = requests.get(f'{url}/api/v1/query_range', timeout=TIMEOUT,
                                params={'query': selector, 'start': int(since), 'end': int(now), 'step': step})
            body = resp.json()
        except (requests.RequestException, ValueError) as exc:
            self.errors['victoriametrics'] = f'{type(exc).__name__}'
            return []
        result = ((body.get('data') or {}).get('result') or [])
        return [[int(float(t)), float(v)] for t, v in (result[0].get('values') if result else [])]

    def status(self):
        return {'mode': 'victoriametrics' if vm_url() else 'lite',
                'logs': 'victorialogs' if vl_url() else None, 'keep_days': keep_days() if not vm_url() else None,
                'written': self.written, 'errors': dict(self.errors)}


_storage = None


def storage():
    """The process's storage, on Floorbit's database."""
    global _storage
    if _storage is None:
        from .. import database
        _storage = Storage(database.backend())
    return _storage


def reset():
    global _storage
    _storage = None
