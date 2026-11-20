"""Who walks which rows (issue #1000): several crew members walk the hall at once, each with a laptop
on their own rows. A walker claims rows when they press Start, says which seat they are at while
they walk, and lets go when they stop; a walker nobody has heard from for ``IDLE`` seconds lets go
by itself (a closed tab, a flat battery). The page shows every row with its progress and who has it.

Kept beside the check-ins (store.event_path), per event. Usernames only: the crew's own.
"""
import secrets
import threading
import time

from . import store

FILE = 'seat_walkers.json'
IDLE = 10 * 60
MAX_WALKERS = 64
_lock = threading.Lock()


class ClaimError(ValueError):
    def __init__(self, message, status=400, held=None):
        super().__init__(message)
        self.status = status
        self.held = held or []


def _path():
    return store.event_path(FILE)


def _active(now):
    walkers = store.read_json(_path(), {}) or {}
    return {k: w for k, w in walkers.items() if isinstance(w, dict) and now - float(w.get('updated') or 0) < IDLE}


def active(now=None):
    """``{id: {"who", "rows", "seat", "started", "updated"}}`` of everyone walking now."""
    return _active(time.time() if now is None else now)


def claim(rows, who, take=False, now=None):
    """Start walking ``rows`` (row ids). Rows another walker holds stop it (409 naming them)
    unless ``take``: then that walker loses those rows (someone took over at their laptop)."""
    now = time.time() if now is None else now
    rows = [str(r) for r in rows][:50]
    if not rows:
        raise ClaimError('Pick a row.')
    with _lock:
        walkers = _active(now)
        held = [(wid, w) for wid, w in walkers.items() if set(w['rows']) & set(rows)]
        if held and not take:
            raise ClaimError('Someone else is walking one of these rows.', 409,
                             held=sorted({w['who'] for _, w in held}))
        for wid, w in held:
            w['rows'] = [r for r in w['rows'] if r not in rows]
            if not w['rows']:
                walkers.pop(wid)
        if len(walkers) >= MAX_WALKERS:
            raise ClaimError('Too many walks at once.', 429)
        wid = secrets.token_urlsafe(9)
        walkers[wid] = {'who': str(who or '')[:80], 'rows': rows, 'seat': None, 'started': now, 'updated': now}
        store.write_json(_path(), walkers)
        return {'id': wid, **walkers[wid]}


def at_seat(walker_id, seat, now=None):
    """The walker is at ``seat`` (None between seats); also says they are still there."""
    now = time.time() if now is None else now
    with _lock:
        walkers = _active(now)
        w = walkers.get(walker_id)
        if not w:
            raise ClaimError('This walk ended: start again.', 404)
        w['seat'] = str(seat).upper()[:16] if seat else None
        w['updated'] = now
        store.write_json(_path(), walkers)
        return {'id': walker_id, **w}


def release(walker_id, now=None):
    now = time.time() if now is None else now
    with _lock:
        walkers = _active(now)
        gone = walkers.pop(walker_id, None)
        store.write_json(_path(), walkers)
        return gone is not None


def hall(data, learned, now=None):
    """Every hall row with how far the walk got and who walks it:
    ``[{"id", "name", "block_label", "naming", "seats", "found", "walker": {"id", "who", "seat"} | None}]``.
    ``found``: the row's seats with a port from a walk or a check-in this event."""
    from .seat_names import hall_rows
    walking = {}
    for wid, w in active(now).items():
        for row in w['rows']:
            walking[row] = {'id': wid, 'who': w['who'], 'seat': w['seat']}
    out = []
    for r in hall_rows(data):
        out.append({'id': r['id'], 'name': r['name'], 'block_label': r['block_label'], 'naming': r['naming'],
                    'seats': len(r['seats']), 'found': sum(1 for s in r['seats'] if s in learned),
                    'walker': walking.get(r['id'])})
    return out
