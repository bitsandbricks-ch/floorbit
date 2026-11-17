"""Event schedule and countdown (issue #106). The rules live in floorbit/schedule.py; see docs/schedule.md.

- ``GET /schedule``: the crew's page (React): the event's start and end, the items, the iCal import.
- ``GET /api/schedule``: everything, with who changed what.
- ``POST /api/schedule/items``, ``PATCH`` and ``DELETE /api/schedule/items/<id>``: one item.
- ``PUT /api/schedule/event``: ``{"start": <epoch>, "end": <epoch>}``, the countdown's target.
- ``POST /api/schedule/import``: ``{"ics": "<file text>", "tz": "Europe/Zurich"}``.
- ``GET /agenda``: the public page, for big screens (``?screen=1``) and phones, no account. Off unless
  Settings > Attendee pages turns it on.
- ``GET /agenda.json``: the same as JSON.
- ``GET /agenda.ics``: the programme as a calendar feed attendees subscribe to on their phones.

Reading the crew's page needs ``floorplan.view``, changing it ``floorplan.edit`` (auth/roles.py).
"""
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flask import Blueprint, Response, current_app, g, jsonify, request

from integrations import events

from .. import audit, schedule, spa

bp = Blueprint('schedule', __name__)


def page_on():
    return bool(current_app.extensions['floorbit_settings'].get('public.schedule'))


def _who():
    from auth import current_user  # late: auth imports floorbit while it loads
    user = current_user() or {}
    return user.get('display_name') or user.get('username')


def _changed():
    events.publish('schedule.changed', {})


def _error(exc):
    return jsonify({'error': str(exc)}), exc.status


@bp.route('/schedule')
def schedule_page():
    return spa.render('Schedule')


@bp.route('/api/schedule', methods=['GET'])
def get_schedule():
    body = schedule.get()
    body['kinds'] = list(schedule.KINDS)
    body['public'] = page_on()
    return jsonify(body)


@bp.route('/api/schedule/items', methods=['POST'])
def add_item():
    try:
        item = schedule.add(request.get_json(silent=True) or {}, _who())
    except schedule.ScheduleError as exc:
        return _error(exc)
    audit.record('schedule', 'Added a schedule item', g.get('audit_user'), item['title'])
    _changed()
    return jsonify(item), 201


@bp.route('/api/schedule/items/<item_id>', methods=['PATCH'])
def update_item(item_id):
    try:
        item = schedule.update(item_id, request.get_json(silent=True) or {}, _who())
    except schedule.ScheduleError as exc:
        return _error(exc)
    audit.record('schedule', 'Changed a schedule item', g.get('audit_user'), item['title'])
    _changed()
    return jsonify(item)


@bp.route('/api/schedule/items/<item_id>', methods=['DELETE'])
def delete_item(item_id):
    try:
        schedule.delete(item_id)
    except schedule.ScheduleError as exc:
        return _error(exc)
    audit.record('schedule', 'Removed a schedule item', g.get('audit_user'), item_id)
    _changed()
    return jsonify({'ok': True})


@bp.route('/api/schedule/event', methods=['PUT'])
def set_event():
    try:
        event = schedule.set_event(request.get_json(silent=True) or {})
    except schedule.ScheduleError as exc:
        return _error(exc)
    audit.record('schedule', 'Set the event times', g.get('audit_user'), None)
    _changed()
    return jsonify(event)


@bp.route('/api/schedule/import', methods=['POST'])
def import_ics():
    body = request.get_json(silent=True) or {}
    tz = None
    if body.get('tz'):
        try:
            tz = ZoneInfo(str(body['tz']))
        except (ZoneInfoNotFoundError, ValueError):
            return jsonify({'error': 'Unknown time zone.'}), 400
    try:
        result = schedule.import_ics(body.get('ics'), _who(), tz)
    except schedule.ScheduleError as exc:
        return _error(exc)
    audit.record('schedule', 'Imported the schedule from iCal', g.get('audit_user'),
                 f"{result['added']} added, {result['updated']} updated, {result['removed']} removed")
    _changed()
    return jsonify(result)


@bp.route('/agenda')
def agenda_page():
    """The page is React (frontend/src/pages/public/PublicAgenda.tsx), reading /agenda.json; 404
    while it is switched off."""
    html, status = spa.render('Schedule')
    return html, status if page_on() else 404


@bp.route('/agenda.json')
def agenda_json():
    if not page_on():
        return jsonify({'error': 'The schedule page is switched off.'}), 404
    return jsonify(schedule.public())


@bp.route('/agenda.ics')
def agenda_ics():
    if not page_on():
        return jsonify({'error': 'The schedule page is switched off.'}), 404
    name = current_app.extensions['floorbit_settings'].get('theme.name') or 'Schedule'
    body = schedule.to_ics(schedule.public()['items'], name, request.host.split(':')[0])
    # inline, not a download: calendar apps subscribe to the URL and fetch it again every hour
    return Response(body, mimetype='text/calendar', headers={'Content-Disposition': 'inline; filename="agenda.ics"',
                                                              'Cache-Control': 'public, max-age=300'})


for _view in (agenda_page, agenda_json, agenda_ics):
    _view._auth_public = True   # what auth.public_endpoint sets: attendees have no account
