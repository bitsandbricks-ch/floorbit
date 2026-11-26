"""Applications (issue #1481): the games, launchers and site groups Floorbit recognises. Rules in
floorbit/applications.py, docs in docs/applications.md.

- ``GET /applications``: the page.
- ``GET /api/applications?hours=24``: every application (hidden ones too) with what DNS, traffic, the
  LAN cache and the game servers saw of it in the last 1 to 168 hours, and the lists it came from.
- ``POST /api/applications``, ``PUT /api/applications/<id>``: add one, or change one (for a built-in
  one: what is added to it, and hidden). ``DELETE /api/applications/<id>``: remove an own one, or put
  a built-in one back as it shipped. Changing needs settings.manage (auth/roles.py's default).
"""
from flask import Blueprint, current_app, g, jsonify, request

from .. import application_sources, applications, audit, features, spa
from .flows import current as current_flows
from .games import servers_now

bp = Blueprint('applications', __name__)


@bp.route('/applications')
def applications_page():
    return spa.render('Applications')


@bp.route('/api/applications', methods=['GET'])
def list_applications():
    try:
        hours = int(request.args.get('hours', 24))
    except ValueError:
        hours = 0
    if not 1 <= hours <= 168:
        return jsonify({'error': 'hours is a whole number from 1 to 168.'}), 400
    ext = current_app.extensions
    dns_stats = ext.get('floorbit_dns') if features.on('dns') else None
    flows = current_flows() if features.on('traffic') else None
    lancache = ext.get('floorbit_lancache')
    cache = lancache.snapshot(hours) if lancache is not None else None
    apps = applications.listing()
    seen = applications.usage(
        apps, dns_stats.site_lookups(hours) if dns_stats is not None else {},
        {s['name']: s for s in (flows or {}).get('services') or []},
        {c['cache']: c for c in (cache or {}).get('caches') or []}, (cache or {}).get('downloads'),
        servers_now())
    rows = [{**a, 'seen': {**seen[a['id']], 'seats': applications.seats(seen[a['id']])}} for a in apps]
    # The rule sources by name only: their URLs are for settings.manage (blueprints/application_sources.py).
    synced = [{k: s[k] for k in ('id', 'name', 'on', 'ok', 'changed_at', 'count')}
              for s in application_sources.status()]
    return jsonify({'applications': rows, 'sources': applications.builtin()['sources'], 'synced': synced,
                    'frozen': application_sources.frozen(), 'hours': hours,
                    'kinds': list(applications.KINDS), 'categories': list(applications.CATEGORIES)})


def _saved(app_id=None):
    body = request.get_json(silent=True)
    try:
        app = applications.save(body, app_id)
    except applications.ApplicationError as exc:
        return jsonify({'error': exc.message}), exc.status
    fields = [k for k in ('name', 'kind', 'category', 'part_of', 'sites', 'ports', 'cidr', 'depots', 'hidden')
              if k in (body or {})]
    audit.record('applications', 'Changed an application' if app_id else 'Added an application',
                 g.get('audit_user'), app['name'], fields=fields)
    return jsonify(app), 200 if app_id else 201


@bp.route('/api/applications', methods=['POST'])
def add_application():
    return _saved()


@bp.route('/api/applications/<app_id>', methods=['PUT'])
def change_application(app_id):
    return _saved(app_id)


@bp.route('/api/applications/<app_id>', methods=['DELETE'])
def remove_application(app_id):
    gone = applications.remove(app_id)
    if gone is None:
        return jsonify({'error': 'No such application, or nothing changed on it.'}), 404
    shipped = applications.base()
    builtin = app_id in shipped
    audit.record('applications', 'Reset an application' if builtin else 'Removed an application',
                 g.get('audit_user'), gone.get('name') or shipped[app_id]['name'])
    return jsonify({'ok': True})
