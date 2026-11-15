"""Crew notice (issue #246): one short message from a lead that every crew page shows as a banner,
such as "Hall B: power work at 14:00, leave row C alone".

Kept in data.json under ``crew_notice``: ``{"text", "level": "info"|"warn", "until", "by", "at"}``.
``until`` is a Unix time or None (until someone clears it). An expired notice reads as none.
"""
import threading
import time

from .store import load_data, save_data

KEY = 'crew_notice'
LEVELS = ('info', 'warn')
MAX_TEXT = 280
MAX_HOURS = 7 * 24
_lock = threading.Lock()


class NoticeError(ValueError):
    pass


def current(data=None, now=None):
    """The notice that is up now, or None."""
    data = data if data is not None else load_data()
    notice = data.get(KEY)
    if not isinstance(notice, dict) or not notice.get('text'):
        return None
    until = notice.get('until')
    if until is not None and until <= (now if now is not None else time.time()):
        return None
    return notice


def post(body, who, now=None):
    """Put up a notice in place of the one before. ``hours`` 0 or missing: until it is cleared."""
    now = now if now is not None else time.time()
    text = ' '.join(str(body.get('text') or '').split())
    if not text:
        raise NoticeError('Write what the crew should know.')
    if len(text) > MAX_TEXT:
        raise NoticeError(f'Keep it to {MAX_TEXT} characters.')
    level = body.get('level') or 'info'
    if level not in LEVELS:
        raise NoticeError('Level is info or warn.')
    hours = body.get('hours') or 0
    if isinstance(hours, bool) or not isinstance(hours, (int, float)) or not 0 <= hours <= MAX_HOURS:
        raise NoticeError(f'Hours is a number from 0 (until cleared) to {MAX_HOURS}.')
    notice = {'text': text, 'level': level, 'until': now + hours * 3600 if hours else None,
              'by': who, 'at': now}
    with _lock:
        data = load_data()
        data[KEY] = notice
        save_data(data)
    return notice


def clear():
    with _lock:
        data = load_data()
        if data.pop(KEY, None) is not None:
            save_data(data)
