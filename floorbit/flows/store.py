"""Where flow data is kept, and for how long (``FLOWS_DIR``, by default ``state/flows``).

- ``raw/YYYY-MM-DD-HH.jsonl.gz``: the flow records as received, one file per hour, deleted after
  ``FLOWS_RETENTION_DAYS`` (7). For looking into an incident after the fact.
- ``hourly.jsonl``: one line per hour with the hall, area and service totals (services only when
  enough seats used them, see aggregate.py). No seats, no addresses: kept until deleted by hand.
- Redis ``floorbit:flows``: the collector's latest summary, which the app shows.
"""
import calendar
import gzip
import json
import os
import time

from integrations import config

from .. import cache

REDIS_KEY = 'floorbit:flows'
SNAPSHOT_TTL = 300   # a summary older than this means the collector stopped


def flows_dir():
    return config.get('FLOWS_DIR') or os.path.join(os.path.dirname(os.path.abspath(
        os.environ.get('FLOORBIT_DATA_FILE') or 'data.json')), 'flows')


class RawStore:
    def __init__(self, root=None):
        self.root = root or flows_dir()
        self.raw = os.path.join(self.root, 'raw')

    def write(self, flows, now=None):
        if not flows or not config.get_bool('FLOWS_KEEP_RAW', True):
            return
        now = time.time() if now is None else now
        os.makedirs(self.raw, exist_ok=True)
        name = time.strftime('%Y-%m-%d-%H', time.gmtime(now)) + '.jsonl.gz'
        # Appending makes a new gzip member each time; gzip readers read them as one stream.
        with gzip.open(os.path.join(self.raw, name), 'at', encoding='utf-8') as f:
            for flow in flows:
                f.write(json.dumps(flow, separators=(',', ':')) + '\n')

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
    client = cache.get_redis_client()
    if not client:
        return False
    client.setex(REDIS_KEY, SNAPSHOT_TTL, json.dumps(snapshot, separators=(',', ':')))
    return True


def latest():
    client = cache.get_redis_client()
    if not client:
        return None
    try:
        raw = client.get(REDIS_KEY)
        return json.loads(raw) if raw else None
    except Exception as exc:  # noqa: BLE001  # a broken summary reads as no collector
        print(f'[flows] could not read the collector summary: {exc}')
        return None
