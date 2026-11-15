"""Gear loans (issue #36). Rules in floorbit/gear.py.

- ``GET /gear``: the page (React); ``/gear?item=<id>`` opens one piece (what its QR label links to).
- ``GET /api/gear``: every piece of gear with its loan, and the latest check-outs and check-ins.
- ``POST /api/gear/<id>/out`` ``{"to", "kind": "person"|"area", "note"}``, ``POST /api/gear/<id>/in``.
- ``GET /api/gear/labels.pdf?role=&ids=``: QR labels to print.

All of it needs ``incidents.work``: it is the crew's, and names people.
"""
from flask import Blueprint, Response, current_app, jsonify, request

from integrations import events

from .. import gear, spa

bp = Blueprint('gear', __name__)


def _who():
    from auth import current_user  # late: auth imports floorbit while it loads
    user = current_user() or {}
    return user.get('display_name') or user.get('username')


def _error(exc):
    return jsonify({'error': str(exc)}), getattr(exc, 'status', 400)


@bp.route('/gear')
def gear_page():
    return spa.render('Gear')


@bp.route('/api/gear', methods=['GET'])
def list_gear():
    users = current_app.extensions['auth'].users.list()
    return jsonify({'items': gear.items(), 'log': gear.log(limit=50),
                    'people': [{'username': u['username'], 'display_name': u['display_name']} for u in users]})


@bp.route('/api/gear/<device_id>/out', methods=['POST'])
def check_out(device_id):
    try:
        loan = gear.check_out(device_id, request.get_json(silent=True) or {}, _who())
    except gear.GearError as exc:
        return _error(exc)
    events.publish('gear.changed', {'id': device_id})
    return jsonify(loan)


@bp.route('/api/gear/<device_id>/in', methods=['POST'])
def check_in(device_id):
    try:
        done = gear.check_in(device_id, request.get_json(silent=True) or {}, _who())
    except gear.GearError as exc:
        return _error(exc)
    events.publish('gear.changed', {'id': device_id})
    return jsonify(done)


@bp.route('/api/gear/labels.pdf', methods=['GET'])
def labels():
    rows = gear.items()
    role = request.args.get('role')
    ids = set(filter(None, (request.args.get('ids') or '').split(',')))
    rows = [r for r in rows if (not role or r['role'] == role) and (not ids or r['id'] in ids)]
    # Behind a reverse proxy PUBLIC_URL is the address phones reach; else the one this request came in on.
    base = (current_app.extensions['auth'].public_url() or '').rstrip('/') or request.host_url.rstrip('/')
    headers = {'Content-Disposition': 'inline; filename="gear-labels.pdf"', 'Cache-Control': 'no-store'}
    return Response(gear.labels_pdf(rows, base), mimetype='application/pdf', headers=headers)
