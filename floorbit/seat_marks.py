"""Marks the crew put on single seats during the walk-through (issue #1356): the socket is broken,
come back later, or there is nothing to walk here. A mark carries an optional note, shows on the
walk's seat strip and row list, and a walk skips a marked seat unless someone checks it on purpose.

Per event (store.event_path), beside the walk; cleared with the event's seat ports.
"""
import threading
import time

from . import audit, store

FILE = 'seat_marks.json'
MARKS = ('broken', 'later', 'skip')
MAX_NOTE = 300
_lock = threading.Lock()


class MarkError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def _path():
    return store.event_path(FILE)


def all_marks():
    """``{seat: {"mark", "note", "by", "at"}}``."""
    rows = store.read_json(_path(), {}) or {}
    return {s: m for s, m in rows.items() if isinstance(m, dict) and m.get('mark') in MARKS}


def put(seat, mark, note, by, now=None):
    now = time.time() if now is None else now
    if mark not in MARKS:
        raise MarkError('A seat is marked broken, later or skip.')
    note = str(note or '').strip()[:MAX_NOTE] or None
    with _lock:
        rows = all_marks()
        rows[seat] = {'mark': mark, 'note': note, 'by': str(by or '')[:80], 'at': now}
        store.write_json(_path(), rows)
    audit.record('check-in', f'Walk-through: seat {seat} marked {mark}', by, note)
    return rows[seat]


def clear(seat, by):
    with _lock:
        rows = all_marks()
        gone = rows.pop(seat, None)
        if gone is None:
            return False
        store.write_json(_path(), rows)
    audit.record('check-in', f'Walk-through: mark on seat {seat} removed', by)
    return True


def clear_all():
    """Every mark of the current event, for the clearing a day after it ended."""
    with _lock:
        count = len(all_marks())
        store.write_json(_path(), {})
    return count
