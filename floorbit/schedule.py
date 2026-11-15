"""Event schedule and countdown (issue #106): talks, tournaments, meals and quiet hours. See docs/schedule.md.

Kept in data.json under ``schedule``: ``{"event": {"start", "end"}, "items": [...]}``. Leads edit it on
the Schedule page, or import an iCal file (``.ics``) from a calendar or the event website. An import
replaces the items it brought in before (matched by the file's UIDs) and leaves hand-made ones alone.

The public side (``/agenda``, floorbit/blueprints/schedule.py) shows a countdown to the event's start,
what is on now and next, and the day's programme. Nothing here names attendees.
"""
import datetime as dt
import re
import threading
import time
import uuid
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .store import load_data, save_data

KEY = 'schedule'
KINDS = ('talk', 'tournament', 'meal', 'quiet', 'other')
MAX_ITEMS = 500
MAX_TITLE = 120
MAX_TEXT = 500
MAX_ICS = 2_000_000
_lock = threading.Lock()


class ScheduleError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def _stored(data):
    s = data.get(KEY)
    s = s if isinstance(s, dict) else {}
    event = s.get('event') if isinstance(s.get('event'), dict) else {}
    items = [i for i in s.get('items') or [] if isinstance(i, dict)]
    return {'event': {'start': event.get('start'), 'end': event.get('end')}, 'items': items}


def get(data=None):
    s = _stored(load_data() if data is None else data)
    s['items'] = sorted(s['items'], key=lambda i: (i['start'], i.get('end') or i['start'], i['title']))
    return s


def _time(value, label, required=True):
    if value in (None, ''):
        if required:
            raise ScheduleError(f'{label} is missing.')
        return None
    try:
        t = float(value)
    except (TypeError, ValueError):
        raise ScheduleError(f'{label} must be a time in seconds since 1970.') from None
    if not 946_684_800 <= t <= 4_102_444_800:   # 2000 to 2100: anything else is a typo
        raise ScheduleError(f'{label} is not a believable date.')
    return round(t)


def _text(value, limit):
    return ' '.join(str(value or '').split())[:limit]


def _clean(body):
    title = _text(body.get('title'), MAX_TITLE)
    if not title:
        raise ScheduleError('Give the item a title.')
    kind = body.get('kind') or 'other'
    if kind not in KINDS:
        raise ScheduleError(f"The kinds are: {', '.join(KINDS)}.")
    start = _time(body.get('start'), 'The start')
    end = _time(body.get('end'), 'The end', required=False)
    if end is not None and end < start:
        raise ScheduleError('The end is before the start.')
    return {'title': title, 'kind': kind, 'start': start, 'end': end,
            'where': _text(body.get('where'), MAX_TITLE), 'note': _text(body.get('note'), MAX_TEXT)}


def _change(fn):
    with _lock:
        data = load_data()
        s = _stored(data)
        result = fn(s)
        data[KEY] = s
        save_data(data)
    return result


def add(body, by):
    clean = _clean(body)

    def run(s):
        if len(s['items']) >= MAX_ITEMS:
            raise ScheduleError(f'The schedule holds at most {MAX_ITEMS} items.')
        item = {'id': uuid.uuid4().hex[:10], **clean, 'source': 'floorbit', 'uid': None,
                'updated_at': time.time(), 'by': by}
        s['items'].append(item)
        return item
    return _change(run)


def update(item_id, body, by):
    def run(s):
        item = next((i for i in s['items'] if i['id'] == item_id), None)
        if item is None:
            raise ScheduleError('No such item.', 404)
        merged = {k: body.get(k, item.get(k)) for k in ('title', 'kind', 'start', 'end', 'where', 'note')}
        item.update(_clean(merged), updated_at=time.time(), by=by)
        return item
    return _change(run)


def delete(item_id):
    def run(s):
        before = len(s['items'])
        s['items'] = [i for i in s['items'] if i['id'] != item_id]
        if len(s['items']) == before:
            raise ScheduleError('No such item.', 404)
    return _change(run)


def set_event(body):
    start = _time(body.get('start'), 'The start', required=False)
    end = _time(body.get('end'), 'The end', required=False)
    if start is not None and end is not None and end < start:
        raise ScheduleError('The end is before the start.')

    def run(s):
        s['event'] = {'start': start, 'end': end}
        return s['event']
    return _change(run)


# ── iCal ───────────────────────────────────────────────────────────────────────────────────────

KIND_WORDS = (
    ('tournament', ('tournament', 'turnier', 'match', 'final', 'bracket', 'cup')),
    ('meal', ('breakfast', 'lunch', 'dinner', 'meal', 'food', 'pizza', 'zmorge', 'zmittag', 'znacht', 'essen',
              'frühstück', 'mittagessen', 'abendessen')),
    ('quiet', ('quiet', 'sleep', 'night rest', 'nachtruhe', 'ruhezeit', 'ruhe')),
    ('talk', ('talk', 'keynote', 'workshop', 'presentation', 'vortrag', 'panel')),
)


def guess_kind(*texts):
    words = ' '.join(t for t in texts if t).lower()
    for kind, hints in KIND_WORDS:
        if any(re.search(rf'\b{re.escape(h)}', words) for h in hints):
            return kind
    return 'other'


def _unfold(text):
    """iCal lines continue on the next line when it starts with a space or tab (RFC 5545 3.1)."""
    return re.sub(r'\r?\n[ \t]', '', text).splitlines()


def _unescape(value):
    return re.sub(r'\\([\\;,nN])', lambda m: '\n' if m.group(1) in 'nN' else m.group(1), value)


def _ical_time(value, params, default_tz):
    """A DTSTART/DTEND value as epoch seconds. Dates (all day) start at midnight."""
    tzid = params.get('TZID')
    tz = default_tz
    if tzid:
        try:
            tz = ZoneInfo(tzid.strip('"'))
        except (ZoneInfoNotFoundError, ValueError):
            tz = default_tz
    value = value.strip()
    if re.fullmatch(r'\d{8}', value):
        d = dt.datetime.strptime(value, '%Y%m%d')
        return d.replace(tzinfo=tz).timestamp(), True
    m = re.fullmatch(r'(\d{8}T\d{6})(Z?)', value)
    if not m:
        raise ValueError(value)
    d = dt.datetime.strptime(m.group(1), '%Y%m%dT%H%M%S')
    return d.replace(tzinfo=dt.UTC if m.group(2) else tz).timestamp(), False


def parse_ics(text, default_tz=None):
    """The VEVENTs of an iCal file as clean items (with ``uid``). Repeating events count once."""
    default_tz = default_tz or dt.datetime.now().astimezone().tzinfo
    events, current = [], None
    for line in _unfold(text):
        if line == 'BEGIN:VEVENT':
            current = {}
            continue
        if line == 'END:VEVENT':
            if current is not None:
                events.append(current)
            current = None
            continue
        if current is None or ':' not in line:
            continue
        head, value = line.split(':', 1)
        name, *rest = head.split(';')
        params = dict(p.split('=', 1) for p in rest if '=' in p)
        current[name.upper()] = (value, params)
    out = []
    for e in events:
        if 'DTSTART' not in e or 'SUMMARY' not in e:
            continue
        try:
            start, all_day = _ical_time(*e['DTSTART'], default_tz)
            end = _ical_time(*e['DTEND'], default_tz)[0] if 'DTEND' in e else None
        except ValueError:
            continue
        if end is None and all_day:
            end = start + 86400
        title = _unescape(e['SUMMARY'][0])
        where = _unescape(e.get('LOCATION', ('', {}))[0])
        note = _unescape(e.get('DESCRIPTION', ('', {}))[0])
        cats = _unescape(e.get('CATEGORIES', ('', {}))[0])
        try:
            clean = _clean({'title': title, 'kind': guess_kind(cats, title), 'start': start, 'end': end,
                            'where': where, 'note': note})
        except ScheduleError:
            continue
        uid = _text(e.get('UID', ('', {}))[0], 200) or f'{clean["start"]}-{clean["title"]}'
        out.append({**clean, 'uid': uid})
    return out


def import_ics(text, by, default_tz=None):
    """Replace the items an earlier import brought in. Returns {"added", "updated", "removed"}."""
    if not isinstance(text, str) or not text.strip():
        raise ScheduleError('Choose an iCal file (.ics).')
    if len(text) > MAX_ICS:
        raise ScheduleError('That file is too big for a schedule.')
    if 'BEGIN:VCALENDAR' not in text:
        raise ScheduleError("That isn't an iCal file: it has no BEGIN:VCALENDAR.")
    found = parse_ics(text, default_tz)
    if not found:
        raise ScheduleError('The file has no events Floorbit can read.')

    def run(s):
        old = {i['uid']: i for i in s['items'] if i.get('source') == 'ical'}
        kept = [i for i in s['items'] if i.get('source') != 'ical']
        if len(kept) + len(found) > MAX_ITEMS:
            raise ScheduleError(f'The schedule holds at most {MAX_ITEMS} items.')
        now = time.time()
        fresh, seen = [], set()
        for item in found:
            if item['uid'] in seen:   # a repeating event's later copies
                continue
            seen.add(item['uid'])
            prev = old.get(item['uid'])
            fresh.append({'id': prev['id'] if prev else uuid.uuid4().hex[:10], **item, 'source': 'ical',
                          'updated_at': now, 'by': by})
        s['items'] = kept + fresh
        return {'added': sum(1 for i in fresh if i['uid'] not in old),
                'updated': sum(1 for i in fresh if i['uid'] in old),
                'removed': sum(1 for u in old if u not in seen)}
    return _change(run)


# ── What the public side shows ─────────────────────────────────────────────────────────────────

def public(data=None, now=None):
    """The countdown, now and next, and every item, without who edited what."""
    now = time.time() if now is None else now
    s = get(data)
    items = [{k: i.get(k) for k in ('id', 'title', 'kind', 'start', 'end', 'where', 'note')} for i in s['items']]

    def running(i):
        return i['start'] <= now < (i['end'] or i['start'] + 1800)   # no end: half an hour
    start, end = s['event']['start'], s['event']['end']
    phase = 'unknown' if start is None else 'before' if now < start else 'after' if end and now >= end else 'during'
    return {
        'event': s['event'],
        'phase': phase,
        'countdown': max(0, round(start - now)) if phase == 'before' else None,
        'now': [i for i in items if running(i)],
        'next': [i for i in items if i['start'] == min((j['start'] for j in items if j['start'] > now), default=None)],
        'quiet': next((i for i in items if i['kind'] == 'quiet' and running(i)), None),
        'items': items,
        'server_time': now,
    }
