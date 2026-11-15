"""Past events and comparing them (issue #38). See docs/events.md.

Closing an event keeps it as its own record: its report (without nicks or IPs), its floor plan as a
backup, and the key figures the events page compares side by side. Then the next event starts from
the last one: the floor plan, settings, planner and teardown steps stay, while the report's history,
incidents, handovers, pre-flight results and the gear log begin again.

Each archived event is a file in ``events/`` next to data.json, so data.json doesn't grow with every
year and one event can be copied or deleted on its own.
"""
import os
import re
import threading
import time
import uuid

from . import store

FOLDER = 'events'
ID_RE = re.compile(r'^[0-9]{8}-[0-9a-f]{8}$')
MAX_NAME = 120
# The parts of data.json that belong to one event and start empty for the next.
RESET_KEYS = ('incidents', 'handover', 'preflight')

_lock = threading.Lock()


class ArchiveError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def folder():
    return os.path.join(os.path.dirname(os.path.abspath(store.DATA_FILE)), FOLDER)


def _path(event_id):
    if not isinstance(event_id, str) or not ID_RE.match(event_id):
        raise ArchiveError('No such event.', 404)   # the id becomes a file name: nothing else gets through
    return os.path.join(folder(), event_id + '.json')


def figures(report):
    """The numbers the events page compares. Cache savings come once a cache source reports them (#88)."""
    inc = report.get('incidents') or {}
    peak = report.get('peak') or {}
    outages = report.get('outages') or []
    return {
        'seats': report.get('seats') or 0,
        'online_max': report.get('online_max') or 0,
        'checked_in_max': report.get('checked_in_max') or 0,
        'peak_bps': peak.get('bps'),
        'bytes_moved': report.get('bytes_moved') or 0,
        'hours': len(report.get('hours') or []),
        'incidents': inc.get('total') or 0,
        'incidents_fixed': inc.get('fixed') or 0,
        'from_seats': inc.get('from_seats') or 0,
        'median_fix_s': inc.get('median_fix_s'),
        'outages': sum(o['times'] for o in outages),
        'down_s': sum(o['down_s'] for o in outages),
        'problem_ports': len(report.get('problem_ports') or []),
        'cache_saved_bytes': report.get('cache_saved_bytes'),
    }


def _summary(record):
    return {k: record.get(k) for k in ('id', 'name', 'start', 'end', 'archived_at', 'archived_by', 'figures')}


def archived():
    """Every archived event, newest first, without its report and floor plan."""
    path = folder()
    if not os.path.isdir(path):
        return []
    out = []
    for name in os.listdir(path):
        if not name.endswith('.json') or not ID_RE.match(name[:-5]):
            continue
        try:
            record = store.read_json(os.path.join(path, name))
        except ValueError:
            continue   # a broken file shouldn't hide the others
        if isinstance(record, dict):
            out.append(_summary(record))
    return sorted(out, key=lambda r: -(r.get('start') or r.get('archived_at') or 0))


def get(event_id):
    record = store.read_json(_path(event_id))
    if not isinstance(record, dict):
        raise ArchiveError('No such event.', 404)
    return record


def archive(report, layout, user, now=None):
    """Write the event's record. Returns its summary."""
    now = time.time() if now is None else now
    name = str(report.get('event_name') or '').strip()[:MAX_NAME]
    start = report.get('start') or now
    record = {
        'id': time.strftime('%Y%m%d', time.gmtime(start)) + '-' + uuid.uuid4().hex[:8],
        'name': name or 'Event of ' + time.strftime('%Y-%m-%d', time.gmtime(start)),
        'start': start,
        'end': report.get('end') or now,
        'archived_at': now,
        'archived_by': user,
        'figures': figures(report),
        'report': report,
        'layout': layout,
    }
    os.makedirs(folder(), exist_ok=True)
    store.write_json(_path(record['id']), record)
    return _summary(record)


def rename(event_id, name):
    name = str(name or '').strip()[:MAX_NAME]
    if not name:
        raise ArchiveError('Give the event a name.')
    with _lock:
        record = get(event_id)
        record['name'] = name
        record['report']['event_name'] = name
        store.write_json(_path(event_id), record)
    return _summary(record)


def delete(event_id):
    path = _path(event_id)
    if not os.path.exists(path):
        raise ArchiveError('No such event.', 404)
    os.remove(path)


def reset_for_next(data):
    """Clear what belongs to the closed event, keep what the next one starts from. Saves data.json."""
    for key in RESET_KEYS:
        data.pop(key, None)
    loans = data.get('loans') if isinstance(data.get('loans'), dict) else {}
    # Gear that is still out stays out: it's physically somewhere. Only the log starts again.
    data['loans'] = {'out': dict(loans.get('out') or {}), 'log': []}
    teardown = data.get('teardown') if isinstance(data.get('teardown'), dict) else {}
    # The lead's own teardown steps are a checklist for every event: kept, unticked.
    data['teardown'] = {'items': [{**i, 'done_at': None, 'done_by': None}
                                  for i in teardown.get('items') or [] if isinstance(i, dict)],
                        'switches': {}, 'export': None}
    store.save_data(data)
