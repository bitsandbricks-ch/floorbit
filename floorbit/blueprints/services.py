"""Servers and services (issue #471): ISP uplinks, DNS resolvers and the LAN cache. Rules in
floorbit/services.py, docs in docs/services.md.

- ``GET /services``: the page.
- ``GET /api/services``: every uplink and resolver with how it was when last checked, and the LAN cache.
- ``POST /api/services/check``: check everything now (``floorplan.edit``).
- ``POST /api/services/<kind>``, ``PUT/DELETE /api/services/<kind>/<id>`` (kind ``uplinks``,
  ``resolvers`` or ``sites``): ``floorplan.edit``.
- ``POST /api/services/sites/common``: add the usual internet sites that are missing (``floorplan.edit``).
"""
from flask import Blueprint, abort, g, jsonify, request

from .. import audit, i18n, services, spa

bp = Blueprint('services', __name__)
WHAT = {'uplinks': 'ISP uplink', 'resolvers': 'DNS resolver', 'sites': 'internet site'}


@bp.route('/services')
def services_page():
    return spa.render('Services')


@bp.route('/api/services', methods=['GET'])
def get_services():
    # The pollers keep their messages in English; a German page gets them in German.
    lang = i18n.language(request.headers.get('Accept-Language'))
    return jsonify(i18n.translate_fields(services.overview(), lang))


@bp.route('/api/services/check', methods=['POST'])
def check_services():
    services.poller.poll_once()
    # The pollers keep their messages in English; a German page gets them in German.
    lang = i18n.language(request.headers.get('Accept-Language'))
    return jsonify(i18n.translate_fields(services.overview(), lang))


@bp.route('/api/services/sites/common', methods=['POST'])
def add_common_sites():
    added = services.add_common_sites(g.get('audit_user'))
    if added:
        audit.record('floor plan', 'Added internet sites', g.get('audit_user'), ', '.join(s['name'] for s in added))
    return jsonify({'added': len(added), **services.overview()})


@bp.route('/api/services/<kind>', methods=['POST'])
@bp.route('/api/services/<kind>/<item_id>', methods=['PUT'])
def save_service(kind, item_id=None):
    if kind not in services.KINDS:
        abort(404)
    try:
        item = services.save(kind, request.get_json(silent=True) or {}, g.get('audit_user'), item_id)
    except services.ServiceError as exc:
        return jsonify({'error': str(exc)}), exc.status
    audit.record('floor plan', f"{'Changed' if item_id else 'Added'} {WHAT[kind]}", g.get('audit_user'), item['name'])
    return jsonify(item), 200 if item_id else 201


@bp.route('/api/services/<kind>/<item_id>', methods=['DELETE'])
def delete_service(kind, item_id):
    if kind not in services.KINDS:
        abort(404)
    gone = services.delete(kind, item_id)
    if gone is None:
        return jsonify({'error': 'Not found.'}), 404
    audit.record('floor plan', f'Removed {WHAT[kind]}', g.get('audit_user'), gone['name'])
    return jsonify({'ok': True})
