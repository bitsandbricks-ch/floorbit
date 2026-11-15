"""Event schedule and countdown (issue #106). The rules live in floorbit/schedule.py; see docs/schedule.md.

- ``GET /schedule``: the crew's page (React): the event's start and end, the items, the iCal import.
- ``GET /api/schedule``: everything, with who changed what.
- ``POST /api/schedule/items``, ``PATCH`` and ``DELETE /api/schedule/items/<id>``: one item.
- ``PUT /api/schedule/event``: ``{"start": <epoch>, "end": <epoch>}``, the countdown's target.
- ``POST /api/schedule/import``: ``{"ics": "<file text>", "tz": "Europe/Zurich"}``.
- ``GET /agenda``: the public page, for big screens (``?screen=1``) and phones, no account. Off unless
  Settings > Attendee pages turns it on.
- ``GET /agenda.json``: the same as JSON.

Reading the crew's page needs ``floorplan.view``, changing it ``floorplan.edit`` (auth/roles.py).
"""
import time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flask import Blueprint, current_app, g, jsonify, render_template, request

from integrations import events

from .. import audit, schedule, spa
from .status_page import _stamp

bp = Blueprint('schedule', __name__)

TEXTS = {
    'en': {'title': 'Schedule', 'off': 'This page is switched off.', 'starts_in': 'The event starts in',
           'days': 'd', 'now': 'On now', 'next': 'Up next', 'nothing_now': 'Nothing on the programme right now.',
           'quiet': 'Quiet hours until {time}. Please keep it down.', 'over': 'The event is over. Thanks for coming!',
           'programme': 'Programme', 'empty': 'The programme is not out yet.', 'until': 'until {time}',
           'kind': {'talk': 'Talk', 'tournament': 'Tournament', 'meal': 'Food', 'quiet': 'Quiet hours',
                    'other': 'Event'},
           'updated': 'Updated {time}. This page reloads every minute.'},
    'de': {'title': 'Programm', 'off': 'Diese Seite ist ausgeschaltet.', 'starts_in': 'Der Event beginnt in',
           'days': 'T', 'now': 'Jetzt', 'next': 'Als Nächstes', 'nothing_now': 'Gerade steht nichts auf dem Programm.',
           'quiet': 'Nachtruhe bis {time}. Bitte leise sein.', 'over': 'Der Event ist vorbei. Danke fürs Kommen!',
           'programme': 'Programm', 'empty': 'Das Programm ist noch nicht draussen.', 'until': 'bis {time}',
           'kind': {'talk': 'Vortrag', 'tournament': 'Turnier', 'meal': 'Essen', 'quiet': 'Nachtruhe',
                    'other': 'Programmpunkt'},
           'updated': 'Stand {time}. Die Seite lädt jede Minute neu.'},
}


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


def _countdown(secs):
    d, rest = divmod(int(secs), 86400)
    h, rest = divmod(rest, 3600)
    m, s = divmod(rest, 60)
    return {'d': d, 'h': h, 'm': m, 's': s}


@bp.route('/agenda')
def agenda_page():
    lang = request.accept_languages.best_match(['en', 'de'], default='en')
    text = TEXTS[lang]
    if not page_on():
        return render_template('agenda.html', lang=lang, t=text, off=True), 404
    now = time.time()
    s = schedule.public(now=now)
    return render_template('agenda.html', lang=lang, t=text, off=False, s=s, now=now, stamp=_stamp,
                           left=_countdown(s['countdown']) if s['countdown'] is not None else None,
                           screen=request.args.get('screen') == '1')


@bp.route('/agenda.json')
def agenda_json():
    if not page_on():
        return jsonify({'error': 'The schedule page is switched off.'}), 404
    return jsonify(schedule.public())


for _view in (agenda_page, agenda_json):
    _view._auth_public = True   # what auth.public_endpoint sets: attendees have no account
