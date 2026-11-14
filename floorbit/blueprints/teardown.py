"""Teardown checklist (issue #37). Rules in floorbit/teardown.py.

- ``GET /teardown``: the page (React).
- ``GET /api/teardown``: what is done and what is left.
- ``PUT /api/teardown/switches/<id>`` ``{"done": bool}``: a switch's config is archived.
- ``POST /api/teardown/items``, ``PATCH|DELETE /api/teardown/items/<id>``: the team's own steps.
- ``GET /api/teardown/export.zip``: everything worth keeping in one zip; admins only, like a backup.
"""
from flask import Blueprint, Response, current_app, g, jsonify, request

from integrations import events

from .. import audit, incidents, report, report_pdf, spa, teardown
from ..store import load_data
from .backup import make_backup
from .replay import _checkins

bp = Blueprint('teardown', __name__)


def _who():
    from auth import current_user  # late: auth imports floorbit while it loads
    user = current_user() or {}
    return user.get('display_name') or user.get('username')


def _error(exc):
    return jsonify({'error': str(exc)}), getattr(exc, 'status', 400)


def _changed():
    events.publish('teardown.changed', {})
    return jsonify(teardown.status())


@bp.route('/teardown')
def teardown_page():
    return spa.render('Teardown')


@bp.route('/api/teardown', methods=['GET'])
def get_status():
    return jsonify(teardown.status())


@bp.route('/api/teardown/switches/<device_id>', methods=['PUT'])
def tick_switch(device_id):
    try:
        teardown.tick_switch(device_id, bool((request.get_json(silent=True) or {}).get('done')), _who())
    except teardown.TeardownError as exc:
        return _error(exc)
    return _changed()


@bp.route('/api/teardown/items', methods=['POST'])
def add_item():
    try:
        teardown.add_item((request.get_json(silent=True) or {}).get('text'), _who())
    except teardown.TeardownError as exc:
        return _error(exc)
    return _changed()


@bp.route('/api/teardown/items/<item_id>', methods=['PATCH'])
def tick_item(item_id):
    try:
        teardown.tick_item(item_id, bool((request.get_json(silent=True) or {}).get('done')), _who())
    except teardown.TeardownError as exc:
        return _error(exc)
    return _changed()


@bp.route('/api/teardown/items/<item_id>', methods=['DELETE'])
def remove_item(item_id):
    try:
        teardown.remove_item(item_id)
    except teardown.TeardownError as exc:
        return _error(exc)
    return _changed()


@bp.route('/api/teardown/export.zip', methods=['GET'])
def export():
    data = load_data()
    name = current_app.extensions['floorbit_settings'].get('theme.name') or ''
    built = report.build(current_app.extensions['floorbit_stats'].event(), _checkins(),
                         len(incidents.seat_numbers(data)), event_name=name)
    lang = 'de' if (request.args.get('lang') or '').lower().startswith('de') else 'en'
    try:
        tz = max(-840, min(840, int(request.args.get('tz') or 0)))
    except ValueError:
        tz = 0
    body = teardown.export_zip(make_backup(data), report_pdf.pdf(built, lang=lang, tz=tz), data)
    teardown.mark_exported(_who())
    audit.record('settings', 'Downloaded the event export', user=g.get('audit_user'))
    events.publish('teardown.changed', {})
    return Response(body, mimetype='application/zip', headers={
        'Content-Disposition': 'attachment; filename="floorbit-event-export.zip"', 'Cache-Control': 'no-store'})
