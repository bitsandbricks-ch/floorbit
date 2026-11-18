"""Append-only logs in the database (issue #464).

The audit log, the event timeline, the check-in history and the event recording are logs: lines
added at the end, read whole, now and then cut to their newest part. They are rows in
``floorbit_log``, keyed by the path their ``.jsonl`` file had under the state folder, like documents
are, so several Floorbit processes share them and nothing is lost when a container is replaced.

A log the database doesn't have yet is imported from its file the first time it is used, once
(``journal-imported/<key>`` marks it); after that the file is left alone, as a backup of the moment
of the switch.
"""
import threading
import time

from . import database

_lock = threading.Lock()
# About how big each database log is, kept up as lines are added here: asking the database
# (SUM over every line) on each append held syslog back at a few hundred lines a second.
_sizes = {}          # key -> [bytes, monotonic time it was counted]
SIZE_RECOUNT = 30    # seconds: then the database is asked again (other pods add lines too)


def _key(path):
    db = database.backend()
    key = database.key_for(path, db.root)
    checked = db.__dict__.setdefault('journal_checked', set())   # keys whose import was looked at here
    if key in checked:
        return db, key
    with _lock:
        if key in checked:
            return db, key
        marker = f'journal-imported/{key}'
        if db.get(marker) is database._MISSING:
            try:
                with open(path, encoding='utf-8') as f:
                    old = [line.rstrip('\n') for line in f if line.strip()]
            except OSError:
                old = []
            if old and not db.log_size(key):
                db.log_replace(key, old)
            db.put(marker, '{"imported": true}')
        checked.add(key)
    return db, key


def append(path, line):
    """Add one line (no newline in it). Raises DatabaseError when it can't be saved."""
    db, key = _key(path)
    db.log_append(key, line)
    known = _sizes.get(key)
    if known is not None:
        known[0] += len(line)


def append_many(path, rows):
    """Add several lines at once, in one transaction."""
    rows = list(rows)
    if not rows:
        return
    db, key = _key(path)
    db.run_many('INSERT INTO floorbit_log (log_key, line) VALUES (?, ?)', [(key, line) for line in rows])
    known = _sizes.get(key)
    if known is not None:
        known[0] += sum(len(line) for line in rows)


def lines(path):
    """Every line, oldest first, without newlines. [] when there is no log yet."""
    db, key = _key(path)
    return db.log_lines(key)


def size(path):
    """About how many bytes the log holds."""
    db, key = _key(path)
    known = _sizes.get(key)
    if known is None or time.monotonic() - known[1] > SIZE_RECOUNT:
        known = _sizes[key] = [db.log_size(key), time.monotonic()]
    return known[0]


def replace(path, new_lines):
    """The log becomes ``new_lines`` (cutting it down, compacting it). All or nothing."""
    db, key = _key(path)
    db.log_replace(key, list(new_lines))
    _sizes.pop(key, None)


def keep_newest_half_over(path, max_bytes):
    """Cut the log to its newest half once it is bigger than ``max_bytes``."""
    if size(path) <= max_bytes:
        return
    rows = lines(path)
    replace(path, rows[len(rows) // 2:])


def remove(path):
    replace(path, [])
