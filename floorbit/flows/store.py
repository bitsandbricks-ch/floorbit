"""Where flow data is kept, and for how long (``FLOWS_DIR``, by default ``state/flows``).

- ``raw/YYYY-MM-DD-HH.jsonl.gz``: the flow records, merged per minute (``compact``), one file per
  hour, deleted after ``FLOWS_RETENTION_DAYS`` (7), or the oldest first past ``FLOWS_RAW_MAX_MB``
  (10,240). For looking into an incident after the fact. Each line is
  ``[minute, src, dst, proto, src port, dst port, bytes, packets, records]``.
- ``hourly.jsonl``: one line per hour with the hall, area and service totals (services only when
  enough seats used them, see aggregate.py). No seats, no addresses: kept until deleted by hand.
- The event's ``flows-summary.json`` document in Floorbit's database: the latest summary the agent
  sent, which the Traffic page shows (every worker and pod reads the same one).
"""
import calendar
import contextlib
import gzip
import json
import os
import time

from integrations import config

SUMMARY_FILE = 'flows-summary.json'
SNAPSHOT_TTL = 300   # a summary older than this means the agent stopped sending


def flows_dir():
    from .. import store
    configured = config.get('FLOWS_DIR')
    return store.event_file(configured) if configured else store.event_path('flows')


RAW_FIELDS = ('t', 'src', 'dst', 'proto', 'sport', 'dport', 'bytes', 'packets', 'records')


def compact(flows, into, now):
    """Merge flow records per minute and conversation into ``into``: {(minute, src, dst, proto,
    sport, dport): [bytes, packets, records]}. An exporter reports a long flow again every active
    timeout (often 10 to 60 seconds); one line per minute answers "who talked to what, when" the
    same, at about half the disk (#1483)."""
    for f in flows:
        end = f.get('end')
        when = end if isinstance(end, (int, float)) and abs(end - now) < 3600 else now
        key = (int(when // 60) * 60, f['src'], f['dst'], f['proto'], f['sport'], f['dport'])
        row = into.get(key)
        if row is None:
            into[key] = [f['bytes'], f['packets'], 1]
        else:
            row[0] += f['bytes']
            row[1] += f['packets']
            row[2] += 1
    return into


def read_rows(lines):
    """Raw lines back as dicts (RAW_FIELDS); lines that are not one are skipped."""
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, list) and len(row) == len(RAW_FIELDS):
            yield dict(zip(RAW_FIELDS, row, strict=True))


class RawStore:
    def __init__(self, root=None):
        self.root = root or flows_dir()
        self.raw = os.path.join(self.root, 'raw')

    def write(self, rows, now=None):
        """Append merged rows ({key: [bytes, packets, records]} from ``compact``), each to the file
        of its own hour."""
        if not rows or not config.get_bool('FLOWS_KEEP_RAW', True):
            return
        os.makedirs(self.raw, exist_ok=True)
        by_file = {}
        for key, (size, packets, records) in rows.items():
            name = time.strftime('%Y-%m-%d-%H', time.gmtime(key[0])) + '.jsonl.gz'
            by_file.setdefault(name, []).append(json.dumps([*key, size, packets, records], separators=(',', ':')))
        for name, lines in sorted(by_file.items()):
            # Appending makes a new gzip member each time; gzip readers read them as one stream.
            # Level 1: at 20,000 flows a second the default (9) took most of the agent's CPU, for
            # files only about a fifth smaller.
            with gzip.open(os.path.join(self.raw, name), 'at', encoding='utf-8', compresslevel=1) as f:
                f.write('\n'.join(lines) + '\n')

    def prune(self, now=None):
        now = time.time() if now is None else now
        keep = config.get_int('FLOWS_RETENTION_DAYS', 7, minimum=1) * 86400
        removed = 0
        if not os.path.isdir(self.raw):
            return 0
        for name in os.listdir(self.raw):
            if not name.endswith('.jsonl.gz'):
                continue
            try:
                started = calendar.timegm(time.strptime(name[:13], '%Y-%m-%d-%H'))
            except ValueError:
                continue
            if started + 3600 < now - keep:
                os.remove(os.path.join(self.raw, name))
                removed += 1
        # And a size cap: at 20,000 flows a second a week is over 50 GB, on the agent's small disk
        # in the hall that also holds the syslog backlog. The hour being written always stays.
        cap = config.get_int('FLOWS_RAW_MAX_MB', 10_240, minimum=1) * 1024 * 1024
        names = sorted(n for n in os.listdir(self.raw) if n.endswith('.jsonl.gz'))
        sizes = {}
        for name in names:
            with contextlib.suppress(OSError):
                sizes[name] = os.path.getsize(os.path.join(self.raw, name))
        total = sum(sizes.values())
        for name in names[:-1]:
            if total <= cap:
                break
            with contextlib.suppress(OSError):
                os.remove(os.path.join(self.raw, name))
                removed += 1
            total -= sizes.get(name, 0)
        return removed

    def usage(self):
        if not os.path.isdir(self.raw):
            return {'files': 0, 'bytes': 0, 'oldest': None}
        names = sorted(n for n in os.listdir(self.raw) if n.endswith('.jsonl.gz'))
        size = sum(os.path.getsize(os.path.join(self.raw, n)) for n in names)
        return {'files': len(names), 'bytes': size, 'oldest': names[0][:13] if names else None}

    def append_hours(self, hours):
        if not hours:
            return
        os.makedirs(self.root, exist_ok=True)
        with open(os.path.join(self.root, 'hourly.jsonl'), 'a', encoding='utf-8') as f:
            for start, hour in hours:
                f.write(json.dumps({'hour': start, **hour}, separators=(',', ':')) + '\n')


def publish(snapshot):
    """Keep the agent's latest summary. False when the database could not take it."""
    from .. import database, store
    try:
        store.write_json(store.event_path(SUMMARY_FILE), {'at': time.time(), 'snapshot': snapshot})
        return True
    except (OSError, database.DatabaseError) as exc:   # the next summary comes in 10 seconds
        print(f'[flows] could not keep the traffic summary: {exc}')
        return False


def latest():
    """The latest summary, or None when there is none from the last 5 minutes."""
    from .. import database, store
    try:
        saved = store.read_json(store.event_path(SUMMARY_FILE), {})
    except (OSError, ValueError, database.DatabaseError) as exc:   # reads as no collector
        print(f'[flows] could not read the traffic summary: {exc}')
        return None
    at, snap = (saved.get('at'), saved.get('snapshot')) if isinstance(saved, dict) else (None, None)
    fresh = isinstance(at, (int, float)) and 0 <= time.time() - at < SNAPSHOT_TTL
    return snap if fresh and isinstance(snap, dict) else None
