"""What alerts may say, and when (issue #10): muted switches and quiet hours.

- **Mutes**: a switch someone is working on (or knows is off) can be muted for a while. Its
  offline and back-online alerts go nowhere until the mute ends; the Problems page still lists it,
  marked muted. Stored in data.json under ``alert_mutes``: ``{switch id: {name, until, by, reason}}``.
  A service on the health wall can be muted the same way (issue #256), under ``health:<service id>``.
  When a mute runs out while its switch or service is still down, Discord hears about it once
  (issue #262), since no new change would ever page anyone.
- **Quiet hours** (``ALERT_QUIET_HOURS``, e.g. ``02:00-08:00`` in the server's time zone): Discord
  messages still go out, but silently and without the mention, so the night shift reads them and
  nobody's phone rings.
"""
import re
import threading
import time

from . import config

KEY = 'alert_mutes'
MAX_MINUTES = 7 * 24 * 60
HOURS_RE = re.compile(r'^\s*(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})\s*$')

_lock = threading.Lock()


class MuteError(ValueError):
    pass


def _store():
    from floorbit import store
    return store


def mutes(now=None):
    """The mutes still running: {switch id: {...}}."""
    now = now or time.time()
    raw = _store().load_data().get(KEY) or {}
    return {k: v for k, v in raw.items() if isinstance(v, dict) and float(v.get('until') or 0) > now}


def service_key(service_id):
    """The mute key of a service on the health wall, next to the switch ids."""
    return f'health:{service_id}'


def is_muted(switch_id, now=None):
    return switch_id in mutes(now)


def mute(switch_id, name, minutes, user, reason=''):
    try:
        minutes = int(minutes)
    except (TypeError, ValueError):
        raise MuteError('Say for how many minutes.') from None
    if not 1 <= minutes <= MAX_MINUTES:
        raise MuteError('A mute lasts between 1 minute and 7 days.')
    now = time.time()
    entry = {'name': str(name)[:80], 'until': now + minutes * 60, 'at': now, 'by': user,
             'reason': ' '.join(str(reason or '').split())[:200]}
    with _lock:
        store = _store()
        data = store.load_data()
        kept = {k: v for k, v in (data.get(KEY) or {}).items()
                if isinstance(v, dict) and float(v.get('until') or 0) > now}
        kept[switch_id] = entry
        data[KEY] = kept
        store.save_data(data)
    return entry


def extend(switch_id, minutes):
    """Push a running mute's end out by ``minutes``, keeping who set it and why (issue #264).
    Returns the entry, or None when it isn't muted (or already ran out)."""
    try:
        minutes = int(minutes)
    except (TypeError, ValueError):
        raise MuteError('Say for how many minutes.') from None
    if not 1 <= minutes <= MAX_MINUTES:
        raise MuteError('A mute lasts between 1 minute and 7 days.')
    now = time.time()
    with _lock:
        store = _store()
        data = store.load_data()
        entry = (data.get(KEY) or {}).get(switch_id)
        if not isinstance(entry, dict) or float(entry.get('until') or 0) <= now:
            return None
        until = float(entry['until']) + minutes * 60
        if until > now + MAX_MINUTES * 60:
            raise MuteError('A mute lasts at most 7 days.')
        entry['until'] = until
        store.save_data(data)
    return entry


def unmute(switch_id):
    with _lock:
        store = _store()
        data = store.load_data()
        found = (data.get(KEY) or {}).pop(switch_id, None)
        if found is not None:
            store.save_data(data)
    return found


def take_expired(now=None):
    """Remove the mutes that ran out and return them, so each ending is seen once (issue #262)."""
    now = now or time.time()
    with _lock:
        store = _store()
        data = store.load_data()
        raw = data.get(KEY) or {}
        ended = {k: v for k, v in raw.items() if isinstance(v, dict) and float(v.get('until') or 0) <= now}
        if not ended:
            return {}
        data[KEY] = {k: v for k, v in raw.items() if k not in ended}
        store.save_data(data)
    return ended


def quiet_hours():
    """(start minute, end minute) of the day, or None when not set or not readable."""
    m = HOURS_RE.match(str(config.get('ALERT_QUIET_HOURS', '') or ''))
    if not m:
        return None
    h1, m1, h2, m2 = map(int, m.groups())
    if h1 > 23 or h2 > 23 or m1 > 59 or m2 > 59:
        return None
    return h1 * 60 + m1, h2 * 60 + m2


def quiet_now(now=None):
    hours = quiet_hours()
    if not hours:
        return False
    t = time.localtime(now or time.time())
    minute = t.tm_hour * 60 + t.tm_min
    start, end = hours
    if start == end:
        return False
    return start <= minute < end if start < end else minute >= start or minute < end
