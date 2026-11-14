"""Tech dispatch (issue #30): send an incident to the nearest free tech. See docs/dispatch.md.

Techs say on their phone (``/jobs``) that they are on duty and where they are: a seat, or the seat or
switch of the job they finished last. "Nearest" is the straight line on the floor plan, in the same
hall first; the plan has no walls or aisles, so that is as good as it gets without a map of the hall.
A free tech is on duty, may work the incident's team and has no job they haven't finished.

Kept in data.json under ``dispatch``: per account, on duty or not, where, and since when. Nothing
leaves the app; a tech's position is a seat number, never GPS.
"""
import math
import threading
import time

from flask import current_app

from . import halls, incidents
from .store import load_data, save_data

KEY = 'dispatch'
OTHER_HALL = 100_000     # a tech in another hall is only sent when nobody is in this one
UNKNOWN = 1_000_000      # nor one who never said where they are

_lock = threading.Lock()


class DispatchError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


# ── Where things are on the plan ──────────────────────────────────────────────
def points(data):
    """{seat: (hall_id, x, y)} for every seat, and {switch_id: (hall_id, x, y)}, in plan units (screen.py)."""
    from .blueprints.screen import CELL, PLAN_H, PLAN_W
    from .power import block_rows
    ids = {h['id'] for h in halls.halls(data)}
    seats, switches = {}, {}
    for block in data.get('seat_blocks') or []:
        rows = block_rows(block)
        if not rows or block.get('x') is None:
            continue
        hall = halls.hall_of(block, data, ids)
        cx, cy = float(block['x']) / 100 * PLAN_W, float(block['y']) / 100 * PLAN_H
        w, h = len(rows[0]) * CELL, len(rows) * CELL
        turn = math.radians(int(block.get('rotation') or 0) % 360)
        cos, sin = math.cos(turn), math.sin(turn)
        for r, row in enumerate(rows):
            for c, seat in enumerate(row):
                lx, ly = c * CELL - w / 2 + CELL / 2, r * CELL - h / 2 + CELL / 2
                seats[seat] = (hall, cx + lx * cos - ly * sin, cy + lx * sin + ly * cos)
    for dev in data.get('inventory') or []:
        if dev.get('x') is not None and dev.get('y') is not None:
            switches[dev['id']] = (halls.hall_of(dev, data, ids), float(dev['x']) / 100 * PLAN_W,
                                   float(dev['y']) / 100 * PLAN_H)
    return seats, switches


def where_is(incident, seats, switches):
    if incident.get('seat'):
        return seats.get(incident['seat'])
    if incident.get('switch_id'):
        return switches.get(incident['switch_id'])
    return None


def distance(a, b):
    """Plan units between two points, with a penalty for another hall or an unknown place."""
    if a is None or b is None:
        return UNKNOWN
    d = math.hypot(a[1] - b[1], a[2] - b[2])
    return d if a[0] == b[0] else OTHER_HALL + d


# ── The crew ──────────────────────────────────────────────────────────────────
def _state(data):
    raw = data.get(KEY)
    return raw if isinstance(raw, dict) else {}


def status_of(username, data=None):
    data = data if data is not None else load_data()
    entry = _state(data).get(username) or {}
    return {'on_duty': bool(entry.get('on_duty')), 'at': entry.get('at'), 'since': entry.get('since')}


def set_status(user, on_duty=None, at=None, clear_at=False):
    """Go on or off duty, or say where you are (a seat or a switch id)."""
    with _lock:
        data = load_data()
        state = _state(data)
        entry = dict(state.get(user['username']) or {})
        if on_duty is not None:
            if bool(on_duty) != bool(entry.get('on_duty')):
                entry['since'] = time.time()
            entry['on_duty'] = bool(on_duty)
        if clear_at:
            entry['at'] = None
        elif at is not None:
            at = str(at).strip().upper()
            seats, switches = points(data)
            if at not in seats and at.lower() not in {k.lower() for k in switches}:
                raise DispatchError(f'There is no seat {at} on the floor plan.')
            entry['at'] = at
        entry['updated'] = time.time()
        state[user['username']] = entry
        data[KEY] = state
        save_data(data)
        return status_of(user['username'], data)


def position(entry, seats, switches):
    at = entry.get('at')
    if not at:
        return None
    if at in seats:
        return seats[at]
    return next((p for k, p in switches.items() if k.lower() == str(at).lower()), None)


def open_jobs(username, items):
    return [i for i in items if i.get('assignee') == username and i['status'] != 'fixed']


def crew(data=None):
    """Everyone on duty: where they are and how many jobs they have."""
    data = data if data is not None else load_data()
    users = {u['username']: u for u in current_app.extensions['auth'].users.list()}
    items = incidents.list_all()
    out = []
    for name, entry in sorted(_state(data).items()):
        if not entry.get('on_duty') or name not in users:
            continue
        out.append({'username': name, 'display_name': users[name].get('display_name') or name,
                    'at': entry.get('at'), 'since': entry.get('since'), 'jobs': len(open_jobs(name, items))})
    return out


def nearest(incident, data=None):
    """The free tech nearest to the incident, as (account, plan distance), or (None, None)."""
    data = data if data is not None else load_data()
    seats, switches = points(data)
    target = where_is(incident, seats, switches)
    items = incidents.list_all()
    auth_users = current_app.extensions['auth'].users
    best = None
    for name, entry in _state(data).items():
        if not entry.get('on_duty') or open_jobs(name, items):
            continue
        user = auth_users.get(name)
        if not user or user.get('disabled') or not incidents.can_work(user, incident):
            continue
        d = distance(position(entry, seats, switches), target)
        # Same distance: whoever went on duty or finished their last job first.
        key = (d, entry.get('updated') or 0)
        if best is None or key < best[0]:
            best = (key, user)
    return (best[1], best[0][0]) if best else (None, None)


# ── Jobs ──────────────────────────────────────────────────────────────────────
def send(by_user, incident_id):
    """Give the incident to the nearest free tech. Needs incidents.assign for its team."""
    incident = incidents.get(incident_id)
    if not incident:
        raise DispatchError('No such incident.', 404)
    if incident['status'] == 'fixed':
        raise DispatchError('This incident is fixed already.', 409)
    if not incidents.can_assign(by_user, incident.get('team')):
        raise DispatchError('Sending incidents to a tech needs the "assign incidents" permission.', 403)
    tech, d = nearest(incident)
    if not tech:
        raise DispatchError('No free tech on duty can take this incident.', 409)
    incidents.update(by_user, incident_id, {'assignee': tech['username']})
    changed = incidents.stamp(incident_id, dispatched_at=time.time(), dispatched_by=by_user['username'],
                              taken_at=None)
    return changed, tech, d


def _mine(user, incident_id):
    incident = incidents.get(incident_id)
    if not incident:
        raise DispatchError('No such incident.', 404)
    if incident.get('assignee') != user['username']:
        raise DispatchError('This job is not yours.', 403)
    return incident


def take(user, incident_id):
    """The tech saw the job and is on the way."""
    incident = _mine(user, incident_id)
    if incident['status'] == 'fixed':
        raise DispatchError('This incident is fixed already.', 409)
    return incidents.stamp(incident_id, taken_at=time.time())


def done(user, incident_id, note=''):
    """Fixed. The tech is now where the job was, which is where the next one is measured from."""
    incident = _mine(user, incident_id)
    body = {'status': 'fixed'}
    if note:
        body['note'] = note
    fixed = incidents.update(user, incident_id, body)
    at = incident.get('seat') or incident.get('switch_id')
    if at:
        set_status(user, at=at)
    return fixed


def give_back(user, incident_id, note=''):
    """Can't do it: the job goes back on the board, unassigned."""
    _mine(user, incident_id)
    body = {'status': 'open'}
    if note:
        body['note'] = note
    incidents.update(user, incident_id, body)
    return incidents.stamp(incident_id, taken_at=None, dispatched_at=None, dispatched_by=None)
