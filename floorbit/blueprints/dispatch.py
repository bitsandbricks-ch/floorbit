"""Tech dispatch (issue #30). Rules live in floorbit/dispatch.py; see docs/dispatch.md.

- ``GET /jobs``: the tech's phone page (React).
- ``GET /api/jobs``: my status, my jobs with the hall plan, where the job is and where I am.
- ``PUT /api/jobs/me``: go on or off duty, say where I am (``{"on_duty": true, "at": "B-7"}``).
- ``POST /api/jobs/<id>/take``, ``/done``, ``/give-back``: the tech's answers to a job.
- ``POST /api/incidents/<id>/dispatch``: send the incident to the nearest free tech (``incidents.assign``).
- ``GET /api/dispatch/crew``: who is on duty, where, with how many jobs (``incidents.assign``).

All of it needs ``incidents.work`` somewhere, like the incident board.
"""
from flask import Blueprint, jsonify, request

from auth import roles
from integrations import events

from .. import dispatch, halls, incidents, spa
from ..store import load_data
from .incidents import _board_user
from .screen import plan

bp = Blueprint('dispatch', __name__)


def _error(exc):
    return jsonify({'error': str(exc)}), getattr(exc, 'status', 400)


def _changed(incident):
    events.publish('incident.changed', {'id': incident['id'], 'status': incident['status']})


def _job(incident, data, seats, switches, me_at):
    target = dispatch.where_is(incident, seats, switches)
    out = {k: incident.get(k) for k in ('id', 'title', 'seat', 'switch_id', 'switch_name', 'circuit_id',
                                        'circuit_name', 'status', 'team', 'source', 'reports', 'created_at',
                                        'dispatched_at', 'taken_at', 'notes')}
    out['drawing'] = out['target'] = out['from'] = out['hall'] = None
    if target:
        hall_id = target[0]
        drawing, _found = plan(data, highlight=incident.get('seat'), hall_id=hall_id)
        out['drawing'] = drawing
        out['target'] = [round(target[1], 1), round(target[2], 1)]
        hall = halls.find(data, hall_id)
        out['hall'] = hall['name'] if hall and len(halls.halls(data)) > 1 else None
        if me_at and me_at[0] == hall_id:
            out['from'] = [round(me_at[1], 1), round(me_at[2], 1)]
    return out


@bp.route('/jobs')
def jobs_page():
    _board_user()
    return spa.render('My jobs')


@bp.route('/api/jobs', methods=['GET'])
def my_jobs():
    user = _board_user()
    data = load_data()
    seats, switches = dispatch.points(data)
    me = dispatch.status_of(user['username'], data)
    me_at = dispatch.position(me, seats, switches)
    mine = sorted(dispatch.open_jobs(user['username'], incidents.list_all()), key=lambda i: i['created_at'])
    can_dispatch = roles.can(user, 'incidents.assign')
    return jsonify({
        'me': me,
        'seats': sorted(seats),
        'jobs': [_job(i, data, seats, switches, me_at) for i in mine],
        'can_dispatch': can_dispatch,
    })


@bp.route('/api/jobs/me', methods=['PUT'])
def set_me():
    user = _board_user()
    body = request.get_json(silent=True) or {}
    try:
        at = body.get('at')
        status = dispatch.set_status(user, on_duty=body.get('on_duty'), at=at or None,
                                     clear_at='at' in body and not at)
    except dispatch.DispatchError as exc:
        return _error(exc)
    events.publish('dispatch.changed', {'username': user['username']})
    return jsonify(status)


def _answer(fn, incident_id, **kwargs):
    user = _board_user()
    try:
        incident = fn(user, incident_id, **kwargs)
    except (dispatch.DispatchError, incidents.IncidentError) as exc:
        return _error(exc)
    _changed(incident)
    return jsonify({'id': incident['id'], 'status': incident['status'], 'taken_at': incident.get('taken_at')})


@bp.route('/api/jobs/<incident_id>/take', methods=['POST'])
def take(incident_id):
    return _answer(dispatch.take, incident_id)


@bp.route('/api/jobs/<incident_id>/done', methods=['POST'])
def done(incident_id):
    note = str((request.get_json(silent=True) or {}).get('note') or '')
    return _answer(dispatch.done, incident_id, note=note)


@bp.route('/api/jobs/<incident_id>/give-back', methods=['POST'])
def give_back(incident_id):
    note = str((request.get_json(silent=True) or {}).get('note') or '')
    return _answer(dispatch.give_back, incident_id, note=note)


@bp.route('/api/incidents/<incident_id>/dispatch', methods=['POST'])
def send(incident_id):
    user = _board_user()
    try:
        incident, tech, _distance = dispatch.send(user, incident_id)
    except (dispatch.DispatchError, incidents.IncidentError) as exc:
        return _error(exc)
    _changed(incident)
    events.publish('incident.dispatched', {'id': incident['id'], 'assignee': tech['username']})
    return jsonify({'id': incident['id'], 'assignee': tech['username'],
                    'display_name': tech.get('display_name') or tech['username']})


@bp.route('/api/dispatch/crew', methods=['GET'])
def crew():
    user = _board_user()
    if not roles.can(user, 'incidents.assign'):
        return jsonify({'error': 'Needs the "assign incidents" permission.'}), 403
    return jsonify({'crew': dispatch.crew()})
