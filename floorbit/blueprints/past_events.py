"""Past events and comparing them (issue #38). Rules in floorbit/event_archive.py.

- ``GET /events``: the page (React).
- ``GET /api/past-events``: the running event's figures and every archived event's, for the comparison.
- ``GET /api/past-events/<id>/report.pdf``: an archived event's report.
- ``GET /api/past-events/backup/<id>.json``: its floor plan as a backup file (Settings > Backup restores it).
- ``POST /api/past-events/close`` ``{"confirm": "<event name>", "next_name": "..."}``: archive the running
  event and start the next one from it. Admins only, and the event's name has to be typed.
- ``PATCH /api/past-events/<id>`` ``{"name": "..."}``, ``DELETE /api/past-events/<id>``: admins only.
"""
import time

from flask import Blueprint, Response, current_app, g, jsonify, request

from integrations import events

from .. import audit, event_archive, incidents, report, report_pdf, spa
from ..store import load_data
from .backup import make_backup
from .replay import _checkins

bp = Blueprint('past_events', __name__)


def _who():
    from auth import current_user  # late: auth imports floorbit while it loads
    user = current_user() or {}
    return user.get('display_name') or user.get('username')


def _error(exc):
    return jsonify({'error': str(exc)}), getattr(exc, 'status', 400)


def _name():
    return current_app.extensions['floorbit_settings'].get('theme.name') or ''


def _current(data):
    return report.build(current_app.extensions['floorbit_stats'].event(), _checkins(),
                        len(incidents.seat_numbers(data)), event_name=_name())


@bp.route('/events')
def events_page():
    return spa.render('Events')


@bp.route('/api/past-events', methods=['GET'])
def list_events():
    built = _current(load_data())
    return jsonify({
        'current': {'name': built['event_name'], 'start': built['start'], 'end': built['end'],
                    'figures': event_archive.figures(built)},
        'archived': event_archive.archived(),
    })


@bp.route('/api/past-events/<event_id>/report.pdf', methods=['GET'])
def event_report(event_id):
    try:
        record = event_archive.get(event_id)
    except event_archive.ArchiveError as exc:
        return _error(exc)
    lang = 'de' if (request.args.get('lang') or '').lower().startswith('de') else 'en'
    try:
        tz = max(-840, min(840, int(request.args.get('tz') or 0)))
    except ValueError:
        tz = 0
    return Response(report_pdf.pdf(record['report'], lang=lang, tz=tz), mimetype='application/pdf', headers={
        'Content-Disposition': f'attachment; filename="floorbit-report-{event_id}.pdf"', 'Cache-Control': 'no-store'})


@bp.route('/api/past-events/backup/<event_id>.json', methods=['GET'])
def event_backup(event_id):
    try:
        record = event_archive.get(event_id)
    except event_archive.ArchiveError as exc:
        return _error(exc)
    return Response(current_app.json.dumps(record.get('layout') or {}, indent=2), mimetype='application/json',
                    headers={'Content-Disposition': f'attachment; filename="floorbit-backup-{event_id}.json"',
                             'Cache-Control': 'no-store'})


@bp.route('/api/past-events/close', methods=['POST'])
def close_event():
    body = request.get_json(silent=True) or {}
    name = _name()
    expected = (name or 'close').strip().lower()
    if str(body.get('confirm') or '').strip().lower() != expected:
        return jsonify({'error': f'Type "{name or "close"}" to close the event.'}), 400
    next_name = str(body.get('next_name') or '').strip()[:event_archive.MAX_NAME]
    data = load_data()
    built = _current(data)
    # Archive first: if writing it fails, nothing has been cleared yet.
    saved = event_archive.archive(built, make_backup(data), _who())
    event_archive.reset_for_next(load_data())
    current_app.extensions['floorbit_stats'].new_event()
    if next_name:
        current_app.extensions['floorbit_settings'].update({'theme.name': next_name})
    audit.record('report', 'Closed the event and started the next', user=g.get('audit_user'), target=saved['name'])
    for kind in ('stats.changed', 'incident.changed', 'handover.changed', 'preflight.changed', 'gear.changed',
                 'teardown.changed', 'events.changed'):
        events.publish(kind, {})
    return jsonify({'archived': saved, 'started': time.time()})


@bp.route('/api/past-events/<event_id>', methods=['PATCH'])
def rename_event(event_id):
    try:
        saved = event_archive.rename(event_id, (request.get_json(silent=True) or {}).get('name'))
    except event_archive.ArchiveError as exc:
        return _error(exc)
    events.publish('events.changed', {})
    return jsonify(saved)


@bp.route('/api/past-events/<event_id>', methods=['DELETE'])
def delete_event(event_id):
    try:
        event_archive.delete(event_id)
    except event_archive.ArchiveError as exc:
        return _error(exc)
    events.publish('events.changed', {})
    return jsonify({'ok': True})
