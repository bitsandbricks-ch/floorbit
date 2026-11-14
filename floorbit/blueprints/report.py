"""Post-event report (issue #22). See docs/report.md.

- ``GET /report``: the page (React).
- ``GET /api/report``: the report as JSON, for the page.
- ``GET /api/report.pdf?lang=en|de&tz=<minutes>``: the same as a PDF to download.
- Both take ``people=1`` to add nicks and IPs, for admins (``settings.manage``) only; every such
  download goes to the audit log.
- ``POST /api/report/new-event``: start a new event, so the report and the peak begin again.
"""
from flask import Blueprint, Response, current_app, jsonify, request

from integrations import events, seat_sources

from .. import audit, incidents, recording, report, report_pdf, spa
from ..store import load_data
from .replay import _checkins

bp = Blueprint('report', __name__)


def _can(permission):
    from auth import current_user, roles  # late: auth imports floorbit while it loads
    if not current_app.extensions['auth'].enabled:
        return True
    user = current_user()
    return bool(user and roles.can(user, permission))


def _build():
    """The report, or a 403 answer when nicks and IPs were asked for without the right."""
    people = request.args.get('people') == '1'
    if people and not _can('settings.manage'):
        return None, (jsonify({'error': 'Only an admin can add nicks and IPs to the report.'}), 403)
    data = load_data()
    name = current_app.extensions['floorbit_settings'].get('theme.name') or ''
    built = report.build(current_app.extensions['floorbit_stats'].event(), _checkins(),
                         len(incidents.seat_numbers(data)), people=people,
                         seat_info=seat_sources.load() if people else None, event_name=name)
    if people:
        from flask import g
        audit.record('report', 'Downloaded the report with nicks and IPs', user=g.get('audit_user'),
                     target='pdf' if request.path.endswith('.pdf') else 'page')
    return built, None


@bp.route('/report')
def report_page():
    return spa.render('Report')


@bp.route('/api/report', methods=['GET'])
def report_data():
    built, refused = _build()
    if refused:
        return refused
    built['may_add_people'] = _can('settings.manage')
    return jsonify(built)


@bp.route('/api/report.pdf', methods=['GET'])
def report_file():
    built, refused = _build()
    if refused:
        return refused
    lang = 'de' if (request.args.get('lang') or '').lower().startswith('de') else 'en'
    try:
        tz = max(-14 * 60, min(14 * 60, int(request.args.get('tz') or 0)))
    except ValueError:
        tz = 0
    body = report_pdf.pdf(built, lang=lang, tz=tz)
    name = 'floorbit-report' + ('-with-people' if built['people'] else '') + '.pdf'
    return Response(body, mimetype='application/pdf', headers={
        'Content-Disposition': f'attachment; filename="{name}"',
        'Cache-Control': 'no-store',
    })


@bp.route('/api/report/new-event', methods=['POST'])
def new_event():
    current_app.extensions['floorbit_stats'].new_event()
    recording.clear()   # the whole-event replay starts over with the event (floorbit/recording.py)
    events.publish('stats.changed', {})
    return jsonify({'ok': True})
