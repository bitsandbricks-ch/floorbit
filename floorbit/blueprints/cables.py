"""Cables and patching (issue #97). The rules live in floorbit/cables.py.

- ``GET /cables``: the page (React); ``/cables?cable=<id>`` opens one cable (what its labels' QR links to).
- ``GET /api/cables?q=&seat=``: the cables, and whether a plugin can import them.
- ``POST /api/cables``, ``PATCH /api/cables/<id>``, ``DELETE /api/cables/<id>``: the crew's own cables.
- ``POST /api/cables/import``: read the cables from NetBox again (replaces the last import).
- ``GET /api/cables/labels.pdf?ids=&q=``: two labels per cable to print. ``GET /api/cables.csv``.

Reading needs ``floorplan.view``, changing ``floorplan.edit`` (auth/roles.py).
"""
from flask import Blueprint, Response, current_app, g, jsonify, request

from integrations import events

from .. import audit, cables, spa

bp = Blueprint('cables', __name__)


def _registry():
    return current_app.extensions['floorbit_plugins']


def _who():
    from auth import current_user  # late: auth imports floorbit while it loads
    user = current_user() or {}
    return user.get('display_name') or user.get('username')


def _audit(action, cable, fields=None):
    audit.record('cables', action, g.get('audit_user'), f"{cable['label']}: {cables.route(cable)}", fields)


def _error(exc):
    return jsonify({'error': str(exc)}), getattr(exc, 'status', 400)


def _picked():
    rows = cables.all_cables()
    ids = set(filter(None, (request.args.get('ids') or '').split(','))) or None
    rows = cables.matching(rows, request.args.get('q'), ids)
    seat = (request.args.get('seat') or '').strip().upper()
    return [c for c in rows if c.get('seat') == seat] if seat else rows


@bp.route('/cables')
def cables_page():
    return spa.render('Cables')


@bp.route('/api/cables', methods=['GET'])
def list_cables():
    sources = [s.name for s in cables.sources(_registry())]
    return jsonify({'cables': _picked(), 'sources': sources})


@bp.route('/api/cables', methods=['POST'])
def add_cable():
    try:
        cable = cables.add(request.get_json(silent=True) or {}, _who())
    except cables.CableError as exc:
        return _error(exc)
    _audit('Added cable', cable)
    events.publish('cables.changed', {'id': cable['id']})
    return jsonify(cable), 201


@bp.route('/api/cables/<cable_id>', methods=['PATCH'])
def update_cable(cable_id):
    try:
        body = request.get_json(silent=True) or {}
        cable = cables.update(cable_id, body, _who())
    except cables.CableError as exc:
        return _error(exc)
    _audit('Changed cable', cable, [f for f in body if f in cables.FIELDS])
    events.publish('cables.changed', {'id': cable_id})
    return jsonify(cable)


@bp.route('/api/cables/<cable_id>', methods=['DELETE'])
def delete_cable(cable_id):
    cable = next((c for c in cables.all_cables() if c['id'] == cable_id), None)
    if not cable or not cables.delete(cable_id):
        return jsonify({'error': 'No such cable.'}), 404
    _audit('Removed cable', cable)
    events.publish('cables.changed', {'id': cable_id})
    return jsonify({'ok': True})


@bp.route('/api/cables/import', methods=['POST'])
def import_cables():
    if not cables.sources(_registry()):
        return jsonify({'error': 'No plugin that is on can tell Floorbit about cables. Turn on NetBox first.'}), 409
    try:
        count, errors = cables.import_from(_registry(), _who())
    except cables.CableError as exc:
        audit.record('cables', 'Imported cables', g.get('audit_user'), 'NetBox', ok=False)
        return _error(exc)
    audit.record('cables', f'Imported {count} cables', g.get('audit_user'), 'NetBox')
    events.publish('cables.changed', {})
    return jsonify({'imported': count, 'errors': errors})


@bp.route('/api/cables/labels.pdf', methods=['GET'])
def labels():
    # Behind a reverse proxy PUBLIC_URL is the address phones reach; else the one this request came in on.
    base = (current_app.extensions['auth'].public_url() or '').rstrip('/') or request.host_url.rstrip('/')
    headers = {'Content-Disposition': 'inline; filename="cable-labels.pdf"', 'Cache-Control': 'no-store'}
    return Response(cables.labels_pdf(_picked(), base), mimetype='application/pdf', headers=headers)


@bp.route('/api/cables.csv', methods=['GET'])
def csv_export():
    headers = {'Content-Disposition': 'attachment; filename="cables.csv"', 'Cache-Control': 'no-store'}
    return Response(cables.csv_text(_picked()), mimetype='text/csv', headers=headers)
