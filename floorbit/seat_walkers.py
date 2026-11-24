"""Who walks which rows (issue #1000) and where each walk got to (issue #1356).

Several crew members walk the hall at once, each with a laptop on their own rows. A walk claims rows
when its walker presses Start and says which seat it is at while they walk. A walk nobody has heard
from for ``IDLE`` seconds (a closed tab, a flat battery, a break) stops holding its rows, but it is
kept: its walker continues it later on any device, at the seat they stopped at, with what it found
and which seats failed. Someone else can **take over** a walk: it moves to them with all of that.
Ending a walk forgets it.

Kept beside the check-ins (store.event_path), per event. Usernames only: the crew's own.
"""
import secrets
import threading
import time

from . import store

FILE = 'seat_walkers.json'
IDLE = 10 * 60
KEEP = 7 * 24 * 3600       # a walk nobody touched for a week is gone
MAX_WALKERS = 64           # walking at once
MAX_KEPT = 200             # kept, walking or not
MAX_DONE = 500
_lock = threading.Lock()


class ClaimError(ValueError):
    def __init__(self, message, status=400, held=None):
        super().__init__(message)
        self.status = status
        self.held = held or []


def _path():
    return store.event_path(FILE)


def _is_active(w, now):
    return not w.get('paused') and now - float(w.get('updated') or 0) < IDLE


def _all(now):
    walkers = store.read_json(_path(), {}) or {}
    return {k: _normal(w) for k, w in walkers.items()
            if isinstance(w, dict) and now - float(w.get('updated') or 0) < KEEP}


def _normal(w):
    w.setdefault('rows', [])
    w.setdefault('seat', None)
    w.setdefault('order', 'rows')
    w.setdefault('user', None)
    w['done'] = [d for d in w.get('done') or [] if isinstance(d, dict) and d.get('seat')]
    w['failed'] = {s: f for s, f in (w.get('failed') or {}).items() if isinstance(f, dict)}
    return w


def _active(now):
    return {k: w for k, w in _all(now).items() if _is_active(w, now)}


def _save(walkers):
    if len(walkers) > MAX_KEPT:
        keep = sorted(walkers, key=lambda k: float(walkers[k].get('updated') or 0))[-MAX_KEPT:]
        walkers = {k: walkers[k] for k in keep}
    store.write_json(_path(), walkers)


def _public(wid, w, now):
    return {'id': wid, **w, 'active': _is_active(w, now)}


def active(now=None):
    """``{id: walk}`` of everyone walking now."""
    return _active(time.time() if now is None else now)


def walks(now=None):
    """Every kept walk, newest first: ``[{"id", "who", "user", "rows", "order", "seat", "started",
    "updated", "done", "failed", "active", "taken_from"?}]``."""
    now = time.time() if now is None else now
    return sorted((_public(k, w, now) for k, w in _all(now).items()), key=lambda w: -float(w.get('updated') or 0))


def claim(rows, who, take=False, now=None, user=None, order='rows'):
    """Start walking ``rows`` (row ids). Rows a walk in progress holds stop it (409 naming the
    walker) unless ``take``: then that walk loses those rows. A walk that is paused or idle doesn't
    hold its rows; a new walk on them takes them from it."""
    now = time.time() if now is None else now
    rows = [str(r) for r in rows][:50]
    if not rows:
        raise ClaimError('Pick a row.')
    with _lock:
        walkers = _all(now)
        held = [(wid, w) for wid, w in walkers.items() if set(w['rows']) & set(rows) and _is_active(w, now)]
        if held and not take:
            raise ClaimError('Someone else is walking one of these rows.', 409,
                             held=sorted({w['who'] for _, w in held}))
        for wid, w in list(walkers.items()):
            if set(w['rows']) & set(rows):
                w['rows'] = [r for r in w['rows'] if r not in rows]
                if not w['rows']:
                    walkers.pop(wid)
        if sum(1 for w in walkers.values() if _is_active(w, now)) >= MAX_WALKERS:
            raise ClaimError('Too many walks at once.', 429)
        wid = secrets.token_urlsafe(9)
        walkers[wid] = {'who': str(who or '')[:80], 'user': str(user or who or '')[:80] or None, 'rows': rows,
                        'order': order if order in ('rows', 'snake') else 'rows', 'seat': None,
                        'started': now, 'updated': now, 'done': [], 'failed': {}}
        _save(walkers)
        return _public(wid, walkers[wid], now)


def _mine(walkers, walker_id, user):
    w = walkers.get(walker_id)
    if not w:
        raise ClaimError('This walk ended: start again.', 404)
    if user and w.get('user') and w['user'] != user:
        # Someone took this walk over: the old tab must not keep writing to it.
        raise ClaimError('Someone else took over this walk.', 409, held=[w['who']])
    return w


def _revive(walkers, wid, w, now):
    """A walk that comes back after a pause holds its rows again, except those someone walks now."""
    if _is_active(w, now):
        return
    busy = {r for k, o in walkers.items() if k != wid and _is_active(o, now) for r in o['rows']}
    w['rows'] = [r for r in w['rows'] if r not in busy]
    if not w['rows']:
        raise ClaimError('Someone else is walking these rows now.', 409,
                         held=sorted({o['who'] for k, o in walkers.items() if k != wid and _is_active(o, now)}))


def at_seat(walker_id, seat, now=None, user=None):
    """The walker is at ``seat`` (None between seats); also says they are still there."""
    now = time.time() if now is None else now
    with _lock:
        walkers = _all(now)
        w = _mine(walkers, walker_id, user)
        _revive(walkers, walker_id, w, now)
        w['seat'] = str(seat).upper()[:16] if seat else None
        w['updated'] = now
        w.pop('paused', None)
        _save(walkers)
        return _public(walker_id, w, now)


def pause(walker_id, now=None, user=None):
    """The walker stops for now: the walk lets its rows go and waits to be continued."""
    now = time.time() if now is None else now
    with _lock:
        walkers = _all(now)
        w = _mine(walkers, walker_id, user)
        w['paused'] = True
        w['updated'] = now
        _save(walkers)
        return _public(walker_id, w, now)


def take_over(walker_id, who, user=None, now=None):
    """The walk moves to ``who``, with where it got to; its old walker's page stops writing to it."""
    now = time.time() if now is None else now
    with _lock:
        walkers = _all(now)
        w = walkers.get(walker_id)
        if not w:
            raise ClaimError('This walk ended: start again.', 404)
        if (w.get('user') or w['who']) != (user or who):
            w['taken_from'] = w['who']
        w['who'] = str(who or '')[:80]
        w['user'] = str(user or who or '')[:80] or None
        _revive(walkers, walker_id, w, now)
        w['updated'] = now
        w.pop('paused', None)
        _save(walkers)
        return _public(walker_id, w, now)


def found(walker_id, seat, port, ms=None, now=None):
    """The walk found ``seat``'s port: kept with the walk, and no longer failed."""
    now = time.time() if now is None else now
    with _lock:
        walkers = _all(now)
        w = walkers.get(walker_id)
        if not w:
            return None
        seat = str(seat).upper()[:16]
        row = {'seat': seat, 'switch': port['switch'], 'port': port['port'], 'ms': ms, 'at': now}
        w['done'] = [row, *[d for d in w['done'] if d['seat'] != seat][:MAX_DONE - 1]]
        w['failed'].pop(seat, None)
        w['updated'] = now
        _save(walkers)
        return _public(walker_id, w, now)


def failed(walker_id, seat, why=None, now=None, user=None):
    """The walk could not find ``seat``'s port: kept so the walker (or whoever takes over) comes back."""
    now = time.time() if now is None else now
    with _lock:
        walkers = _all(now)
        w = _mine(walkers, walker_id, user)
        seat = str(seat).upper()[:16]
        w['failed'][seat] = {'at': now, 'why': str(why or '')[:200] or None}
        w['done'] = [d for d in w['done'] if d['seat'] != seat]
        w['updated'] = now
        _save(walkers)
        return _public(walker_id, w, now)


def forget_seat(seat, now=None):
    """A seat's port was forgotten (Undo): no walk lists it as found any more."""
    now = time.time() if now is None else now
    seat = str(seat).upper()[:16]
    with _lock:
        walkers = _all(now)
        changed = False
        for w in walkers.values():
            before = len(w['done'])
            w['done'] = [d for d in w['done'] if d['seat'] != seat]
            changed = changed or len(w['done']) != before
        if changed:
            _save(walkers)


def release(walker_id, now=None):
    now = time.time() if now is None else now
    with _lock:
        walkers = _all(now)
        gone = walkers.pop(walker_id, None)
        _save(walkers)
        return gone is not None


def hall(data, learned, now=None, marks=None):
    """Every hall row with how far the walk got and who walks it:
    ``[{"id", "name", "block_label", "naming", "seats", "found", "marked", "failed",
    "walker": {"id", "who", "seat"} | None}]``. ``found``: the row's seats with a port from a walk or
    a check-in this event; ``marked``: seats the crew marked (seat_marks.py); ``failed``: seats a
    kept walk could not find."""
    from .seat_names import hall_rows
    now = time.time() if now is None else now
    marks = marks or {}
    walking, failing = {}, set()
    for wid, w in _all(now).items():
        failing |= set(w['failed'])
        if not _is_active(w, now):
            continue
        for row in w['rows']:
            walking[row] = {'id': wid, 'who': w['who'], 'seat': w['seat']}
    out = []
    for r in hall_rows(data):
        out.append({'id': r['id'], 'name': r['name'], 'block_label': r['block_label'], 'naming': r['naming'],
                    'seats': len(r['seats']), 'found': sum(1 for s in r['seats'] if s in learned),
                    'marked': sum(1 for s in r['seats'] if s in marks),
                    'failed': sum(1 for s in r['seats'] if s in failing and s not in learned),
                    'walker': walking.get(r['id'])})
    return out
