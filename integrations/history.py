"""Check-in history: who sat where, with which IP and MAC, over time.

``checkins.json`` only holds the current state, one row per seat. Every change
to it is also appended here, one JSON object per line, so the network team can
answer "who was on D-22 on Saturday night?" or "which seats has this MAC been
on?" after the event, and export the answer as CSV.

Events written by ``checkin.py``:

=============  ==============================================================
``checkin``    someone checked in (or checked in again) at a seat
``moved``      a seat was freed because the same machine checked in elsewhere
               (``to_seat`` says where it went)
``removed``    an admin deleted the check-in
``ip_changed`` the lease refresh saw the MAC on a new IP (``previous_ip``)
``mac_found``  the lease refresh found the MAC for a row that had none
=============  ==============================================================

Two views are built from the log:

* **events**: the raw log, newest first.
* **sessions**: one row per person per seat, from check-in until the seat was
  taken by someone else, freed, or removed (``end`` is empty while they are
  still there), with every IP seen in between.

The file is ``CHECKIN_HISTORY_FILE``, by default next to ``CHECKIN_FILE``.
Appending a line is cheap and a crash can only cut the last line, which the
reader skips. Writing history never blocks or fails a check-in.
"""
import csv
import io
import json
import os
import re
import threading
import time
from datetime import datetime

from . import config

EVENT_TYPES = ('checkin', 'moved', 'removed', 'ip_changed', 'mac_found')
EVENT_COLUMNS = ('time', 'event', 'seat', 'username', 'ip', 'mac', 'previous_ip', 'to_seat', 'timestamp')
SESSION_COLUMNS = ('seat', 'username', 'mac', 'ips', 'checked_in', 'left', 'minutes', 'end_reason',
                   'start_timestamp', 'end_timestamp')

_lock = threading.Lock()
_DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')


def enabled():
    return config.get_bool('CHECKIN_HISTORY_ENABLED', True)


def path():
    explicit = config.get('CHECKIN_HISTORY_FILE', '')
    if explicit:
        return explicit
    base = config.get('CHECKIN_FILE', 'checkins.json')
    return os.path.splitext(base)[0] + '-history.jsonl'


# ── write ────────────────────────────────────────────────────────────────────
def record(event, row, ts=None, **extra):
    """Append one event for ``row`` (a check-in row). Returns the entry, or None."""
    if not enabled():
        return None
    entry = {'ts': ts or time.time(), 'event': event, 'seat': row.get('seat'),
             'username': row.get('username'), 'ip': row.get('ip'), 'mac': row.get('mac')}
    entry.update({k: v for k, v in extra.items() if v is not None})
    line = json.dumps(entry, separators=(',', ':')) + '\n'
    target = path()
    try:
        with _lock:
            os.makedirs(os.path.dirname(os.path.abspath(target)), exist_ok=True)
            with open(target, 'a', encoding='utf-8') as f:
                f.write(line)
    except OSError as exc:
        print(f"[integrations] could not write check-in history: {exc}")
        return None
    return entry


# ── read ─────────────────────────────────────────────────────────────────────
def read_all():
    """Every event, oldest first. Broken lines are skipped."""
    try:
        with open(path(), 'r', encoding='utf-8') as f:
            lines = f.read().splitlines()
    except FileNotFoundError:
        return []
    out = []
    for line in lines:
        try:
            entry = json.loads(line) if line.strip() else None
        except ValueError:
            continue
        if isinstance(entry, dict) and entry.get('ts') is not None:
            out.append(entry)
    out.sort(key=lambda e: e['ts'])
    return out


def sessions(entries):
    """Fold the event log into who-sat-where sessions, oldest first."""
    open_by_seat = {}
    out = []

    def close(seat, ts, reason):
        cur = open_by_seat.pop(seat, None)
        if cur:
            cur['end'], cur['end_reason'] = ts, reason

    def add_ip(cur, ip):
        if ip and ip not in cur['ips']:
            cur['ips'].append(ip)

    for e in sorted(entries, key=lambda e: e['ts']):
        seat, kind = e.get('seat'), e.get('event')
        if not seat:
            continue
        cur = open_by_seat.get(seat)
        if kind == 'checkin':
            if cur and cur['username'] == e.get('username'):
                add_ip(cur, e.get('ip'))
                cur['mac'] = e.get('mac') or cur['mac']
                continue
            close(seat, e['ts'], 'replaced')
            cur = {'seat': seat, 'username': e.get('username'), 'mac': e.get('mac'),
                   'ips': [], 'start': e['ts'], 'end': None, 'end_reason': None}
            add_ip(cur, e.get('ip'))
            open_by_seat[seat] = cur
            out.append(cur)
        elif kind in ('moved', 'removed'):
            close(seat, e['ts'], kind)
        elif cur and kind in ('ip_changed', 'mac_found'):
            add_ip(cur, e.get('ip'))
            cur['mac'] = e.get('mac') or cur['mac']
    return out


# ── filters ──────────────────────────────────────────────────────────────────
def parse_time(value, end_of_day=False):
    """Epoch seconds, ``YYYY-MM-DD`` or ``YYYY-MM-DDTHH:MM[:SS]`` (server local time)."""
    if value in (None, ''):
        return None
    value = str(value).strip()
    try:
        return float(value)
    except ValueError:
        pass
    if _DATE_RE.match(value):
        day = time.mktime(time.strptime(value, '%Y-%m-%d'))
        return day + 86400 - 0.001 if end_of_day else day
    try:
        return datetime.fromisoformat(value.replace(' ', 'T')).timestamp()
    except ValueError:
        raise ValueError(f'Cannot read the time "{value}". Use YYYY-MM-DD or YYYY-MM-DDTHH:MM.') from None


def _mac_hex(value):
    return re.sub(r'[^0-9a-f]', '', str(value or '').lower())


def make_filter(args):
    """Build a predicate from query args: seat, user, ip, mac, event, since, until."""
    seat = (args.get('seat') or '').strip().upper()
    user = (args.get('user') or '').strip().lower()
    ip = (args.get('ip') or '').strip()
    mac = _mac_hex(args.get('mac'))
    event = (args.get('event') or '').strip().lower()
    since = parse_time(args.get('since'))
    until = parse_time(args.get('until'), end_of_day=True)

    def match(row):
        if seat and (row.get('seat') or '').upper() != seat:
            return False
        if user and user not in (row.get('username') or '').lower():
            return False
        ips = row.get('ips') if 'ips' in row else [row.get('ip')]
        if ip and not any(ip in (x or '') for x in ips):
            return False
        if mac and mac not in _mac_hex(row.get('mac')):
            return False
        if event and 'event' in row and row.get('event') != event:
            return False
        start = row.get('start', row.get('ts'))
        end = row.get('end', row.get('ts')) if 'start' in row else row.get('ts')
        if since is not None and end is not None and end < since:
            return False
        return until is None or start <= until

    return match


def query(args, view='events'):
    """Filtered rows for ``view`` ('events' or 'sessions'), newest first."""
    entries = read_all()
    rows = sessions(entries) if view == 'sessions' else entries
    match = make_filter(args)
    rows = [r for r in rows if match(r)]
    key = 'start' if view == 'sessions' else 'ts'
    rows.sort(key=lambda r: r[key], reverse=True)
    return rows


# ── CSV ──────────────────────────────────────────────────────────────────────
def _local(ts):
    return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ts)) if ts else ''


def _cell(value):
    """Plain text for spreadsheets. Usernames are typed by players, so a value
    that a spreadsheet would run as a formula gets a leading apostrophe."""
    if value is None:
        return ''
    text = str(value)
    if text and text[0] in '=+-@\t\r':
        return "'" + text
    return text


def _csv_rows(rows, view):
    if view == 'sessions':
        for s in rows:
            minutes = round(((s['end'] or time.time()) - s['start']) / 60)
            yield {'seat': s['seat'], 'username': s['username'], 'mac': s['mac'],
                   'ips': ' '.join(s['ips']), 'checked_in': _local(s['start']),
                   'left': _local(s['end']), 'minutes': minutes, 'end_reason': s['end_reason'] or '',
                   'start_timestamp': int(s['start']),
                   'end_timestamp': int(s['end']) if s['end'] else ''}
    else:
        for e in rows:
            yield {'time': _local(e['ts']), 'event': e.get('event'), 'seat': e.get('seat'),
                   'username': e.get('username'), 'ip': e.get('ip'), 'mac': e.get('mac'),
                   'previous_ip': e.get('previous_ip'), 'to_seat': e.get('to_seat'),
                   'timestamp': int(e['ts'])}


def to_csv(rows, view='events'):
    """CSV text with a UTF-8 BOM so Excel shows non-ASCII usernames correctly."""
    columns = SESSION_COLUMNS if view == 'sessions' else EVENT_COLUMNS
    buf = io.StringIO()
    buf.write('﻿')
    writer = csv.DictWriter(buf, fieldnames=columns, lineterminator='\r\n')
    writer.writeheader()
    for row in _csv_rows(rows, view):
        writer.writerow({k: _cell(row.get(k)) for k in columns})
    return buf.getvalue()


def to_json_rows(rows, view='events'):
    """Rows for the API, with readable local times next to the timestamps."""
    out = []
    for r in rows:
        r = dict(r)
        if view == 'sessions':
            r['start_local'], r['end_local'] = _local(r['start']), _local(r['end'])
        else:
            r['time_local'] = _local(r['ts'])
        out.append(r)
    return out
