"""Servers and services (issue #471): ISP uplinks, DNS resolvers and the LAN cache. Rules in
floorbit/services.py, docs in docs/services.md.

- ``GET /services``: the page.
- ``GET /api/services``: every uplink and resolver with how it was when last checked, and the LAN cache.
- ``GET /api/services/summary``: one count of every service the health wall knows, each internet site
  a row (floorbit/service_summary.py, issue #1037): the Services page and the health panes use it.
- ``POST /api/services/check``: check everything now, also what the health plugins watch
  (``floorplan.edit``).
- ``POST /api/services/<kind>``, ``PUT/DELETE /api/services/<kind>/<id>`` (kind ``uplinks``,
  ``resolvers``, ``sites`` or ``checks``, the crew's own checks of issue #1338): ``floorplan.edit``.
- ``POST /api/services/checks/test``: run an own check once from the agent, before saving it.
- ``POST /api/services/tags``: ``{"id": "<service id from the summary>", "tags": [...]}`` replaces a
  service's tags (issue #1337), for any service the page lists, plugin ones too.
- ``POST /api/services/sites/common``: add the usual internet sites that are missing (``floorplan.edit``).
"""
from flask import Blueprint, abort, current_app, g, jsonify, request

from .. import audit, game_servers, i18n, service_summary, services, spa

bp = Blueprint('services', __name__)
WHAT = {'uplinks': 'ISP uplink', 'resolvers': 'DNS resolver', 'sites': 'internet site', 'checks': 'own check'}


@bp.route('/services')
def services_page():
    return spa.render('Services')


@bp.route('/api/services', methods=['GET'])
def get_services():
    # The pollers keep their messages in English; a German page gets them in German.
    lang = i18n.language(request.headers.get('Accept-Language'))
    return jsonify(i18n.translate_fields(services.overview(), lang))


def _summary(translate=False):
    """The one list of services; ``translate``: in the reader's language (the page, the tiles)."""
    wall = current_app.extensions.get('floorbit_health')
    checks = wall.fresh()['checks'] if wall is not None else []
    # The wall polls once a minute; the page reads the pollers now. Their rows come straight from the
    # pollers, so the tile and the page never show one service in two states (#1411).
    live = {c['id']: c for c in services.health_checks() + game_servers.health_checks()}
    checks = [live.get(c.get('id'), c) for c in checks]
    sites = [{**site, **services.poller.state(site['id'])} for site in services.stored_sites()]
    tags = services.tags()
    # Every service's tags, also of one the wall hasn't polled yet (just added), for the page.
    out = {**service_summary.summary(checks, sites, tags), 'tags': tags}
    if translate:
        out = i18n.translate_fields(out, i18n.language(request.headers.get('Accept-Language')), ('error', 'summary'))
    return out


@bp.route('/api/services/summary', methods=['GET'])
def get_summary():
    return jsonify(_summary(translate=True))


@bp.route('/api/services/check', methods=['POST'])
def check_services():
    services.poller.poll_once()
    # One "Check now" for the whole page: the health plugins (DHCP, firewalls, ...) too.
    wall = current_app.extensions.get('floorbit_health')
    if wall is not None:
        wall.poll_once()
    # The pollers keep their messages in English; a German page gets them in German.
    lang = i18n.language(request.headers.get('Accept-Language'))
    return jsonify(i18n.translate_fields(services.overview(), lang))


@bp.route('/api/services/sites/common', methods=['POST'])
def add_common_sites():
    added = services.add_common_sites(g.get('audit_user'))
    if added:
        audit.record('floor plan', 'Added internet sites', g.get('audit_user'), ', '.join(s['name'] for s in added))
    return jsonify({'added': len(added), **services.overview()})


@bp.route('/api/services/checks/test', methods=['POST'])
def test_check():
    try:
        got = services.test_check(request.get_json(silent=True) or {})
    except services.ServiceError as exc:
        return jsonify({'error': exc.message}), exc.status
    lang = i18n.language(request.headers.get('Accept-Language'))
    return jsonify(i18n.translate_fields(got, lang))


@bp.route('/api/services/tags', methods=['POST'])
def save_tags():
    body = request.get_json(silent=True) or {}
    known = {**{r['id']: r['name'] for r in _summary()['rows']}, **services.own_ids()}
    row = {'id': body.get('id'), 'name': known.get(body.get('id'))} if body.get('id') in known else None
    if row is None:
        return jsonify({'error': 'There is no such service.'}), 404
    try:
        tags = services.set_tags(row['id'], body.get('tags'))
    except services.ServiceError as exc:
        return jsonify({'error': exc.message}), exc.status
    audit.record('floor plan', 'Changed service tags', g.get('audit_user'), f"{row['name']}: {', '.join(tags) or '-'}")
    return jsonify({'id': row['id'], 'tags': tags})


@bp.route('/api/services/<kind>', methods=['POST'])
@bp.route('/api/services/<kind>/<item_id>', methods=['PUT'])
def save_service(kind, item_id=None):
    if kind not in services.KINDS:
        abort(404)
    try:
        item = services.save(kind, request.get_json(silent=True) or {}, g.get('audit_user'), item_id)
    except services.ServiceError as exc:
        return jsonify({'error': exc.message}), exc.status
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
