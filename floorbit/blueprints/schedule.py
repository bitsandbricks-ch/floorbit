"""Event schedule (issue #106), for the crew. The rules live in floorbit/schedule.py; see docs/schedule.md.

- ``GET /schedule``: the crew's page (React): the event's start and end, the items, the iCal import.
- ``GET /api/schedule``: everything, with who changed what.
- ``POST /api/schedule/items``, ``PATCH`` and ``DELETE /api/schedule/items/<id>``: one item.
- ``PUT /api/schedule/event``: ``{"start": <epoch>, "end": <epoch>}``, the countdown's target.
- ``POST /api/schedule/import``: ``{"ics": "<file text>", "tz": "Europe/Zurich"}``.

Reading the crew's page needs ``floorplan.view``, changing it ``floorplan.edit`` (auth/roles.py).
"""
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flask import Blueprint, g, jsonify, request

from integrations import events

from .. import audit, schedule, spa

bp = Blueprint('schedule', __name__)


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

